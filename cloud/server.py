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
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from apipass_gen import generate_apipass

HERE = Path(__file__).resolve().parent
OUT_DIR = Path(tempfile.gettempdir()) / "imagegen_out"
OUT_DIR.mkdir(exist_ok=True)

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

        # 3) apipass 生圖（沿用既有 adapter；quality 僅 gpt-image 系列吃）
        yield ev({"stage": "generating"})
        out_name = f"out_{uuid.uuid4().hex}.png"
        quality = "high" if model.startswith("openai/") else None
        try:
            result = generate_apipass(
                prompt, str(OUT_DIR / out_name), aspect_ratio=(aspect or "1:1"),
                resolution=(resolution or None), quality=quality,
                images=(ref_paths or None), model=model,
            )
        except Exception as e:
            yield ev({"stage": "error", "where": "generate", "prompt": prompt, "error": str(e)})
            return
        if not result:
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
