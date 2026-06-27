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
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from apipass_gen import generate_apipass

HERE = Path(__file__).resolve().parent
OUT_DIR = Path(tempfile.gettempdir()) / "imagegen_out"
OUT_DIR.mkdir(exist_ok=True)

# 選用鑑權：設了 APP_TOKEN 才要求（公開曝露如 Cloudflare Tunnel 必設；Tailscale 純自用可不設）。
APP_TOKEN = os.environ.get("APP_TOKEN", "")

app = FastAPI(title="image-gen phone backend")


def claude_write_prompt(intent: str, ref_paths: list) -> str:
    """用訂閱跑無頭 `claude -p` 把使用者意圖(+參考圖)寫成 gpt-image-2 prompt。

    強制 unset ANTHROPIC_API_KEY → 走 claude.ai 訂閱（設了 API key 會蓋掉訂閱、變成計費）。
    有參考圖時加 `--allowedTools Read`，讓 Claude 讀圖做視覺分析（已實測可行）。
    """
    instr = (
        "You are an expert prompt writer for the gpt-image-2 text-to-image model. "
        "Turn the user's intent into ONE vivid, concrete English prompt under 80 words. "
        "Output ONLY the prompt text — no preamble, no quotes, no explanation.\n\n"
        f"User intent: {intent}"
    )
    if ref_paths:
        instr += " Read these reference image(s) and reflect their style/subject: " + ", ".join(ref_paths)
    cmd = ["claude", "-p", instr, "--output-format", "json"]
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


@app.post("/generate")
def generate(
    intent: str = Form(...),
    model: str = Form("openai/gpt-image-2"),
    aspect: str = Form("1:1"),
    resolution: str = Form(""),
    write_prompt: str = Form("true"),
    refs: list[UploadFile] = File(default=[]),
    x_app_token: str = Header(default=""),
):
    """收 意圖(+參考圖) → (選擇性)claude 寫 prompt → apipass 生圖 → 回 {prompt, image_url}。"""
    # 0) 選用鑑權（APP_TOKEN 有設才檢查）
    if APP_TOKEN and x_app_token != APP_TOKEN:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    # 1) 存參考圖到本機暫存（claude Read 與 apipass input.images 共用）
    ref_paths = []
    for f in refs or []:
        if not getattr(f, "filename", None):
            continue
        ext = Path(f.filename).suffix or ".png"
        p = OUT_DIR / f"ref_{uuid.uuid4().hex}{ext}"
        p.write_bytes(f.file.read())
        ref_paths.append(str(p))

    # 2) 寫 prompt（訂閱 claude -p）或直接用使用者輸入
    try:
        prompt = claude_write_prompt(intent, ref_paths) if write_prompt.lower() == "true" else intent
    except Exception as e:
        return JSONResponse({"ok": False, "stage": "prompt", "error": str(e)}, status_code=500)

    # 3) apipass 生圖（沿用既有 adapter；quality 僅 gpt-image 系列吃）
    out_name = f"out_{uuid.uuid4().hex}.png"
    quality = "high" if model.startswith("openai/") else None
    result = generate_apipass(
        prompt, str(OUT_DIR / out_name), aspect_ratio=(aspect or "1:1"),
        resolution=(resolution or None), quality=quality,
        images=(ref_paths or None), model=model,
    )
    if not result:
        return JSONResponse(
            {"ok": False, "stage": "generate", "prompt": prompt,
             "error": "apipass 生圖失敗（看後端 log）"}, status_code=502)
    return JSONResponse({"ok": True, "prompt": prompt, "image_url": f"/img/{out_name}"})


# 產出圖以 /img/<name> 取回；PWA 靜態檔掛在根目錄（html=True → 根路徑回 index.html）。
# 掛載順序在 /generate /healthz 之後，故不會攔截 API 路由。
app.mount("/img", StaticFiles(directory=str(OUT_DIR)), name="img")
app.mount("/", StaticFiles(directory=str(HERE / "static"), html=True), name="static")
