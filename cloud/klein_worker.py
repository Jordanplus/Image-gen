#!/usr/bin/env python3
"""本地 FLUX.2 klein-9B 生圖 worker（隨需載入 + 閒置自動卸載）。

設計：
  - 用 **mflux 的 venv** 跑（不是 server 的 .venv）：
        ~/.local/share/uv/tools/mflux/bin/python klein_worker.py
  - server.py 在收到「本地模型」請求時才把它拉起（隨需啟動），平時不佔 RAM。
  - 模型在「第一次 /generate」才真正載入（lazy）；之後常駐重用。
  - 閒置 KLEIN_IDLE 秒（預設 600=10 分）沒有請求 → **整個 process 結束**，
    這是最徹底的「卸載」：作業系統回收全部 RAM，下次 server 會再把它拉起。
  - 單一 GPU，所有生成以 lock 序列化。

只用標準函式庫的 http.server（mflux venv 不必另裝 fastapi/uvicorn）。
環境變數：KLEIN_PORT(8772)、KLEIN_OUT(輸出資料夾)、KLEIN_IDLE(閒置秒數)。
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PORT = int(os.environ.get("KLEIN_PORT", "8772"))
OUT_DIR = os.environ.get("KLEIN_OUT", "/tmp/imagegen_out")
IDLE_SECONDS = int(os.environ.get("KLEIN_IDLE", "600"))

_model = None
_model_edit = None
_lock = threading.Lock()       # 單 GPU → 生成序列化
_last = time.time()            # 最後一次活動時間（給閒置卸載用）


def _prepare_refs(raw_refs, out_dir):
    """如果有參考照片，使用 travel_with_me.prepare_refs 自動裁切人臉（768x768），精準鎖定五官特徵並節省記憶體。"""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "recipes"))
    sys.path.insert(0, str(REPO_ROOT / "recipes" / "personal"))
    try:
        import travel_with_me as tw
        prep_dir = Path(out_dir) / "refs"
        return [str(p) for p in tw.prepare_refs([Path(p) for p in raw_refs], prep_dir, size=768, face_crop=True)]
    except Exception as e:
        print(f"[klein_worker] 自動裁臉失敗，退回原圖: {e}", flush=True)
        return raw_refs


def _load(edit: bool = False):
    """第一次呼叫才載入 klein-9B；有參考圖時載入 Flux2KleinEdit，純文字生圖載入 Flux2Klein。"""
    global _model, _model_edit
    if _model is not None and _model_edit != edit:
        print(f"[klein_worker] 切換模型模式 (edit={edit})，釋放先前模型...", flush=True)
        _model = None
        import gc
        gc.collect()

    if _model is None:
        from mflux.models.common.config import ModelConfig
        from mflux.models.flux2.variants import Flux2Klein, Flux2KleinEdit
        from mflux.callbacks.instances.memory_saver import MemorySaver
        cls = Flux2KleinEdit if edit else Flux2Klein
        print(f"[klein_worker] 正在載入 {cls.__name__} (FLUX.2 klein-9B)...", flush=True)
        _model = cls(quantize=4, model_config=ModelConfig.flux2_klein_9b())
        if hasattr(_model, "callbacks"):
            _model.callbacks.register(
                MemorySaver(model=_model, keep_transformer=True, cache_limit_bytes=1000**3, num_seeds=2)
            )
        _model_edit = edit
        print(f"[klein_worker] 模型已就緒 (edit={edit})", flush=True)
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
            self._json(200, {"ok": True, "loaded": _model is not None, "edit": _model_edit})
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
            raw_images = req.get("images") or []
        except Exception as e:  # noqa: BLE001
            self._json(400, {"ok": False, "error": f"bad request: {e}"})
            return

        with _lock:                       # 一次只生一張
            _last = time.time()
            try:
                is_edit = bool(raw_images)
                model = _load(edit=is_edit)
                seed = int(req.get("seed") or int(time.time()))

                prep_refs = []
                if is_edit:
                    prep_refs = _prepare_refs(raw_images, OUT_DIR)
                    # 確保 prompt 具有鎖臉約束（比照 travel_with_me）
                    p_lower = prompt.lower()
                    if "image 1" not in p_lower and "reference" not in p_lower:
                        n_refs = len(prep_refs)
                        ref_txt = "image 1" if n_refs == 1 else "images " + ", ".join(str(i) for i in range(1, n_refs)) + f" and {n_refs}"
                        prompt = (
                            f"{prompt.rstrip('.')}. Keep the person's face, identity, facial features, "
                            f"skin tone, age and hairstyle strictly identical to {ref_txt}. "
                            "Photorealistic camera photo, natural lighting, sharp focus on the face."
                        )

                gen_kw = dict(
                    seed=seed,
                    prompt=prompt,
                    num_inference_steps=int(req.get("steps", 4)),
                    width=int(req.get("width", 1024)),
                    height=int(req.get("height", 1024)),
                    guidance=float(req.get("guidance", 1.0)),
                )
                if prep_refs:
                    gen_kw["image_paths"] = prep_refs

                img = model.generate_image(**gen_kw)
                os.makedirs(OUT_DIR, exist_ok=True)
                fn = req.get("out_name") or f"local_{int(time.time())}.png"
                img.save(path=os.path.join(OUT_DIR, fn))
                _last = time.time()
                self._json(200, {"ok": True, "filename": fn, "seed": seed, "edit": is_edit})
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
