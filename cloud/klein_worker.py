#!/usr/bin/env python3
"""本地 FLUX.2 klein-4B 生圖 worker（隨需載入 + 閒置自動卸載）。

設計：
  - 用 **mflux 的 venv** 跑（不是 server 的 .venv）：
        ~/.local/share/uv/tools/mflux/bin/python klein_worker.py
  - server.py 在收到「本地模型」請求時才把它拉起（隨需啟動），平時不佔 RAM。
  - 模型在「第一次 /generate」才真正載入（lazy）；之後常駐重用。
  - 閒置 KLEIN_IDLE 秒（預設 600=10 分）沒有請求 → **整個 process 結束**，
    這是最徹底的「卸載」：作業系統回收全部 ~7-8GB，下次 server 會再把它拉起。
  - 單一 GPU，所有生成以 lock 序列化。

只用標準函式庫的 http.server（mflux venv 不必另裝 fastapi/uvicorn）。
環境變數：KLEIN_PORT(8770)、KLEIN_OUT(輸出資料夾)、KLEIN_IDLE(閒置秒數)。
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("KLEIN_PORT", "8770"))
OUT_DIR = os.environ.get("KLEIN_OUT", "/tmp/imagegen_out")
IDLE_SECONDS = int(os.environ.get("KLEIN_IDLE", "600"))

_model = None
_lock = threading.Lock()       # 單 GPU → 生成序列化
_last = time.time()            # 最後一次活動時間（給閒置卸載用）


def _load():
    """第一次呼叫才載入 klein-4B（lazy）；之後重用同一個 model。"""
    global _model
    if _model is None:
        from mflux.models.common.config import ModelConfig
        from mflux.models.flux2.variants import Flux2Klein
        _model = Flux2Klein(quantize=4, model_config=ModelConfig.flux2_klein_4b())
    return _model


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 靜音預設 access log（自己用 print）
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True, "loaded": _model is not None})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        global _last
        if self.path != "/generate":
            self._json(404, {"ok": False, "error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            prompt = req["prompt"]
        except Exception as e:  # noqa: BLE001
            self._json(400, {"ok": False, "error": f"bad request: {e}"})
            return

        with _lock:                       # 一次只生一張
            _last = time.time()
            try:
                model = _load()
                seed = int(req.get("seed") or int(time.time()))
                img = model.generate_image(
                    seed=seed,
                    prompt=prompt,
                    num_inference_steps=int(req.get("steps", 6)),
                    width=int(req.get("width", 1024)),
                    height=int(req.get("height", 1024)),
                    guidance=float(req.get("guidance", 1.0)),
                )
                os.makedirs(OUT_DIR, exist_ok=True)
                fn = req.get("out_name") or f"local_{int(time.time())}.png"
                img.save(path=os.path.join(OUT_DIR, fn))
                _last = time.time()
                self._json(200, {"ok": True, "filename": fn, "seed": seed})
            except Exception as e:  # noqa: BLE001
                self._json(500, {"ok": False, "error": str(e)})


def _idle_watch():
    """閒置超過 IDLE_SECONDS 就結束整個 process（徹底釋放 RAM）。"""
    while True:
        time.sleep(20)
        if time.time() - _last > IDLE_SECONDS:
            print(f"[klein_worker] idle > {IDLE_SECONDS}s → 結束以釋放 RAM", flush=True)
            os._exit(0)


if __name__ == "__main__":
    threading.Thread(target=_idle_watch, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[klein_worker] listening 127.0.0.1:{PORT} out={OUT_DIR} idle={IDLE_SECONDS}s", flush=True)
    srv.serve_forever()
