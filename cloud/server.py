#!/usr/bin/env python3
"""image-gen 個人手機後端 (MVP)。

    [Android PWA] --Tailscale/LAN--> [Mac Mini: FastAPI /generate]
      ├─ claude -p (訂閱) 看參考圖 + 寫 gpt-image-2 prompt   ← 免費(吃訂閱)，不可設 ANTHROPIC_API_KEY
      └─ apipass_gen.generate_apipass(...) → apipass gpt-image-2 → 回圖

跑（從 cloud/ 目錄）：
    pip install fastapi "uvicorn[standard]" python-multipart   # + 既有 pillow / python-dotenv
    uvicorn server:app --host 0.0.0.0 --port 8765
手機（同 Tailscale/LAN）開 http://<mac-mini>:8765 → 「加到主畫面」。
APIPASS_API_KEY 由 apipass_gen 自動從 apipass.env 載入；金鑰只在這台機器、永不進手機。
部署成 24/7 服務 + Tailscale 見 cloud/PHONE-APP.md。
"""
import json
import os
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from apipass_gen import generate_apipass

HERE = Path(__file__).resolve().parent
OUT_DIR = Path(tempfile.gettempdir()) / "imagegen_out"
OUT_DIR.mkdir(exist_ok=True)

# ── 本地模型（FLUX.2 klein-4B，跑在這台 24GB Mac Mini）────────────────────────
# 由 klein_worker.py 承載：隨需啟動、閒置 10 分自動結束釋放 RAM（見該檔說明）。
# worker 用 mflux 的 venv 跑（與 server 的 .venv 隔離），server 只透過本機 HTTP 溝通。
MFLUX_PY = os.path.expanduser("~/.local/share/uv/tools/mflux/bin/python")
KLEIN_WORKER = str(HERE / "klein_worker.py")
KLEIN_PORT = int(os.environ.get("KLEIN_PORT", "8770"))
KLEIN_URL = f"http://127.0.0.1:{KLEIN_PORT}"
KLEIN_IDLE = os.environ.get("KLEIN_IDLE", "600")  # 閒置幾秒後 worker 自我結束
LOCAL_MODELS = {"local/flux2-klein-4b"}           # 手機下拉用這個 value 走本地

_worker_proc = None
_worker_lock = threading.Lock()


def _klein_health():
    """worker 活著就回它的狀態 dict，否則 None。"""
    try:
        with urllib.request.urlopen(f"{KLEIN_URL}/health", timeout=2) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def ensure_klein_worker():
    """確保本地 worker 在跑；沒在跑就用 mflux venv 把它拉起並等到 ready。"""
    global _worker_proc
    if _klein_health():
        return
    with _worker_lock:
        if _klein_health():
            return
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)
        env["KLEIN_PORT"] = str(KLEIN_PORT)
        env["KLEIN_OUT"] = str(OUT_DIR)
        env["KLEIN_IDLE"] = str(KLEIN_IDLE)
        env["HF_HUB_DISABLE_XET"] = "1"   # 抓模型時避開 Xet 空轉（已快取則無影響）
        logf = open("/tmp/klein_worker.log", "a")  # noqa: SIM115
        _worker_proc = subprocess.Popen([MFLUX_PY, KLEIN_WORKER],
                                        stdout=logf, stderr=subprocess.STDOUT, env=env)
        for _ in range(60):               # 等 worker 開始 listen（最多 ~30s）
            if _klein_health():
                return
            time.sleep(0.5)
        raise RuntimeError("本地 klein worker 啟動逾時（看 /tmp/klein_worker.log）")


def _wh_from_aspect(aspect: str, long_edge: int = 1024):
    """把比例字串(如 16:9)換成 width,height；長邊固定 long_edge，對齊 16 的倍數。"""
    try:
        a, b = (int(x) for x in aspect.split(":"))
    except Exception:  # noqa: BLE001
        a, b = 1, 1
    if a >= b:
        w, h = long_edge, round(long_edge * b / a / 16) * 16
    else:
        w, h = round(long_edge * a / b / 16) * 16, long_edge
    return max(256, w), max(256, h)

# 選用鑑權：設了 APP_TOKEN 才要求（公開曝露如 Cloudflare Tunnel 必設；Tailscale 純自用可不設）。
APP_TOKEN = os.environ.get("APP_TOKEN", "")

app = FastAPI(title="image-gen phone backend")

# prompt 模型策略（A/B 實測：Sonnet 品質≈Opus 但省額度；Haiku 抽象題/讀圖較弱）。
# 預設 Sonnet，手機可逐張切換；額度由小到大 haiku < sonnet < opus。
ALLOWED_PROMPT_MODELS = {"haiku", "sonnet", "opus"}
DEFAULT_PROMPT_MODEL = "sonnet"


def claude_write_prompt(intent: str, ref_paths: list, model: str = DEFAULT_PROMPT_MODEL) -> str:
    """用訂閱跑無頭 `claude -p` 把使用者意圖(+參考圖)寫成 gpt-image-2 prompt。

    強制 unset ANTHROPIC_API_KEY → 走 claude.ai 訂閱（設了 API key 會蓋掉訂閱、變成計費）。
    有參考圖時加 `--allowedTools Read`，讓 Claude 讀圖做視覺分析（已實測可行）。
    model: haiku/sonnet/opus（白名單外退回預設）；丟參考圖時 haiku 自動升 sonnet（讀圖視覺分析 Haiku 較弱）。
    """
    instr = (
        "You are an expert prompt writer for the gpt-image-2 text-to-image model. "
        "Turn the user's intent into ONE vivid, concrete English prompt under 80 words. "
        "Output ONLY the prompt text — no preamble, no quotes, no explanation.\n\n"
        f"User intent: {intent}"
    )
    if ref_paths:
        instr += " Read these reference image(s) and reflect their style/subject: " + ", ".join(ref_paths)
    m = model if model in ALLOWED_PROMPT_MODELS else DEFAULT_PROMPT_MODEL
    if ref_paths and m == "haiku":
        m = "sonnet"  # 讀參考圖至少用 Sonnet
    cmd = ["claude", "-p", instr, "--model", m, "--output-format", "json"]
    if ref_paths:
        cmd += ["--allowedTools", "Read"]
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)  # 強制走訂閱
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=150, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"claude -p 失敗 (rc={r.returncode}): {r.stderr[-300:]}")
    return json.loads(r.stdout)["result"].strip()


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/.well-known/assetlinks.json")
def assetlinks():
    """Digital Asset Links — TWA(APK) 全螢幕驗證用。填好 static/.well-known/assetlinks.json 後生效。"""
    p = HERE / "static" / ".well-known" / "assetlinks.json"
    if p.exists():
        return Response(p.read_text(), media_type="application/json")
    return JSONResponse({"error": "assetlinks not configured"}, status_code=404)


@app.post("/generate")
def generate(
    intent: str = Form(...),
    model: str = Form("openai/gpt-image-2"),
    aspect: str = Form("1:1"),
    resolution: str = Form(""),
    write_prompt: str = Form("true"),
    prompt_model: str = Form(DEFAULT_PROMPT_MODEL),
    refs: list[UploadFile] = File(default=[]),
    x_app_token: str = Header(default=""),
):
    """收 意圖(+參考圖) → (選擇性)claude 寫 prompt → apipass 生圖。

    回**串流 NDJSON**（每行一個事件），讓手機有真進度、不會以為當機：
      {"stage":"prompt","prompt":...}   ← prompt 寫好（約 10–20s，先讓使用者看到字）
      {"stage":"generating"}            ← 開始打 apipass 生圖
      {"stage":"done","ok":true,"image_url":...}  或  {"stage":"error",...}
    """
    # 0) 選用鑑權（APP_TOKEN 有設才檢查）；401 在串流前以一般回應送出
    if APP_TOKEN and x_app_token != APP_TOKEN:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    # 1) 存參考圖到本機暫存（要在進入串流前讀完上傳檔）
    ref_paths = []
    for f in refs or []:
        if not getattr(f, "filename", None):
            continue
        ext = Path(f.filename).suffix or ".png"
        p = OUT_DIR / f"ref_{uuid.uuid4().hex}{ext}"
        p.write_bytes(f.file.read())
        ref_paths.append(str(p))

    def ev(d):
        return json.dumps(d, ensure_ascii=False) + "\n"

    def stream():
        # 2) 寫 prompt（訂閱 claude -p）或直接用使用者輸入
        try:
            prompt = claude_write_prompt(intent, ref_paths, prompt_model) if write_prompt.lower() == "true" else intent
        except Exception as e:
            yield ev({"stage": "error", "where": "prompt", "error": str(e)})
            return
        yield ev({"stage": "prompt", "prompt": prompt})

        # 2.5) 本地模型分支（FLUX.2 klein-4B）：隨需拉起 worker → 本機生圖 → 同樣心跳保活。
        #      免 apipass 額度；第一次會等 worker 啟動+載入模型（較久），之後常駐重用。
        if model in LOCAL_MODELS:
            yield ev({"stage": "generating"})
            try:
                ensure_klein_worker()
            except Exception as e:  # noqa: BLE001
                yield ev({"stage": "error", "where": "local_worker", "prompt": prompt, "error": str(e)})
                return
            w, h = _wh_from_aspect(aspect or "1:1", 1024)
            out_name = f"out_{uuid.uuid4().hex}.png"
            lbox = {}

            def _work_local():
                try:
                    payload = json.dumps({"prompt": prompt, "width": w, "height": h,
                                          "steps": 6, "guidance": 1.0, "out_name": out_name}).encode()
                    rq = urllib.request.Request(f"{KLEIN_URL}/generate", data=payload,
                                                headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(rq, timeout=900) as r:
                        lbox["result"] = json.loads(r.read())
                except Exception as e:  # noqa: BLE001
                    lbox["error"] = str(e)

            lt = threading.Thread(target=_work_local, daemon=True)
            lt.start()
            waited = 0
            while lt.is_alive():
                lt.join(timeout=4)
                if lt.is_alive():
                    waited += 4
                    yield ev({"stage": "progress", "waited": waited})
            if lbox.get("error"):
                yield ev({"stage": "error", "where": "generate", "prompt": prompt, "error": lbox["error"]})
                return
            res = lbox.get("result") or {}
            if not res.get("ok"):
                yield ev({"stage": "error", "where": "generate", "prompt": prompt,
                          "error": res.get("error", "本地生圖失敗")})
                return
            yield ev({"stage": "done", "ok": True, "prompt": prompt, "image_url": f"/img/{res['filename']}"})
            return

        # 3) apipass 生圖：在背景執行緒跑，等待期間每 4s 送「心跳」事件。
        #    apipass 排隊可能靜默數十秒～數分鐘；不送資料的話 Funnel/行動網路會把閒置連線斷掉
        #    → 手機看到 "Failed to fetch"。心跳讓連線持續有 bytes 流動。
        yield ev({"stage": "generating"})
        out_name = f"out_{uuid.uuid4().hex}.png"
        quality = "high" if model.startswith("openai/") else None
        box = {}

        def _work():
            try:
                box["result"] = generate_apipass(
                    prompt, str(OUT_DIR / out_name), aspect_ratio=(aspect or "1:1"),
                    resolution=(resolution or None), quality=quality,
                    images=(ref_paths or None), model=model,
                )
            except Exception as e:  # noqa: BLE001
                box["error"] = str(e)

        t = threading.Thread(target=_work, daemon=True)
        t.start()
        waited = 0
        while t.is_alive():
            t.join(timeout=4)
            if t.is_alive():
                waited += 4
                yield ev({"stage": "progress", "waited": waited})  # 心跳：保活
        if box.get("error"):
            yield ev({"stage": "error", "where": "generate", "prompt": prompt, "error": box["error"]})
            return
        if not box.get("result"):
            yield ev({"stage": "error", "where": "generate", "prompt": prompt,
                      "error": "apipass 生圖失敗（看後端 log）"})
            return
        yield ev({"stage": "done", "ok": True, "prompt": prompt, "image_url": f"/img/{out_name}"})

    # X-Accel-Buffering:no → 提示代理別緩衝；application/x-ndjson 逐行串流
    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


# 產出圖以 /img/<name> 取回；PWA 靜態檔掛在根目錄（html=True → 根路徑回 index.html）。
# 掛載順序在 /generate /healthz 之後，故不會攔截 API 路由。
app.mount("/img", StaticFiles(directory=str(OUT_DIR)), name="img")
app.mount("/", StaticFiles(directory=str(HERE / "static"), html=True), name="static")
