#!/usr/bin/env python3
"""本機生圖介面（只綁 127.0.0.1，外面連不到）。

用 mflux 的 python 跑，從專案根目錄：
    ~/.local/share/uv/tools/mflux/bin/python recipes/gui/app.py     （或 make gui）

設計重點：
- **模型常駐**：同一組（模型＋LoRA＋有無參考圖）只載入一次，之後每張省掉 30–60 秒的載入。
- 選項直接讀 `recipes/commercial/portrait_style_probe.py` 的寫法與膚色／胸型／長相設定，不另外維護一份。
- 參考圖從瀏覽器上傳（base64 JSON，不用解 multipart），自動裁臉後交給 FLUX.2 的參考圖編輯版。
- 只用標準函式庫的 http.server：mflux 的 venv 不必另外裝套件。
- 每張生成前檢查可用記憶體，低於門檻就拒絕，避免整台卡死（24GB 機器實測 klein-9B 會用到 swap）。
"""
import base64
import json
import mimetypes
import os
import random
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "recipes"))
sys.path.insert(0, str(ROOT / "recipes" / "commercial"))
sys.path.insert(0, str(ROOT / "recipes" / "personal"))
os.chdir(ROOT)

import local_models as lm  # noqa: E402
import portrait_style_probe as probe  # noqa: E402

HOST, PORT = "127.0.0.1", 8770
OUT_ROOT = Path("outputs/personal_style/gui")
MIN_FREE_PCT = 15  # 可用記憶體低於這個百分比就不開始生成
REF_SENTENCE = (" Her face matches the face in the reference image exactly, the same facial features and proportions. ")

# 介面上的模型選單（model 對應 local_models.MODELS；lora 為 None 代表不掛外掛）
MODELS = [
    dict(id="klein-9b", label="klein-9B（寫實、約 90 秒）", model="klein-9b", use="personal", lora=None),
    dict(id="klein-4b", label="klein-4B（快，約 65 秒）", model="klein-4b", use="personal", lora=None),
]

# 不進版控的本機模型設定（repo 是公開的）：同資料夾放 models_local.py，定義 EXTRA_MODELS = [dict(id=..., label=...,
# model=..., use=..., lora=...), ...]，會排在清單最前面。
_LOCAL_MODELS = Path(__file__).with_name("models_local.py")
if _LOCAL_MODELS.exists():
    import importlib.util
    _spec = importlib.util.spec_from_file_location("gui_models_local", _LOCAL_MODELS)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    MODELS = list(_mod.EXTRA_MODELS) + MODELS
SIZES = [("704x1216", "直式全身 704×1216"), ("768x1152", "直式半身 768×1152"), ("1024x1024", "方形 1024×1024")]

_state = dict(running=False, message="待命中", queue=0, done=0, total=0, results=[], error=None, started=None)
_lock = threading.Lock()
_loaded = dict(key=None, model=None)


def free_pct():
    try:
        out = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"free percentage:\s*(\d+)%", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def get_model(model_key, use, lora, edit):
    """同一組設定重用已載入的模型；換設定才重載（換之前先釋放）。"""
    key = (model_key, lora, edit)
    if _loaded["key"] == key:
        return _loaded["model"]
    if _loaded["model"] is not None:
        _loaded.update(key=None, model=None)
        lm.free()
    lora_path = probe.resolve_lora(lora) if lora else None
    model = lm.load(model_key, use, edit=edit, low_ram=True,
                    lora_paths=[lora_path] if lora_path else None, lora_scales=[1.0] if lora_path else None)
    _loaded.update(key=key, model=model)
    return model


def prepare_ref(data_url, out_dir):
    """瀏覽器上傳的圖（data URL）存檔並裁臉，回傳裁好的路徑。"""
    import travel_with_me as tw
    raw = base64.b64decode(data_url.split(",", 1)[-1])
    out_dir.mkdir(parents=True, exist_ok=True)
    src = out_dir / "upload.jpg"
    src.write_bytes(raw)
    return tw.prepare_refs([src], out_dir, size=640, face_crop=True)


def run_job(job):
    spec = next(m for m in MODELS if m["id"] == job["model_id"])
    width, height = (int(v) for v in job["size"].split("x"))
    seeds = job["seeds"]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = OUT_ROOT / f"{stamp}_{spec['id']}"
    variant = probe.VARIANTS[job["variant"]]
    prompt = probe.build_prompt(variant, True, job["skin"], job["bust"], job["face"], job["pose"])
    refs = []
    try:
        if job.get("ref"):
            _set(message="處理參考圖（裁臉）…")
            refs = prepare_ref(job["ref"], out / "refs")
            prompt += REF_SENTENCE
        _set(message="載入模型…" if _loaded["key"] != (spec["model"], spec["lora"], bool(refs)) else "準備生成…")
        model = get_model(spec["model"], spec["use"], spec["lora"], bool(refs))
        neg = probe.negative_for(spec["model"], True)
        for i, seed in enumerate(seeds, 1):
            pct = free_pct()
            if pct is not None and pct < MIN_FREE_PCT:
                raise RuntimeError(f"可用記憶體只剩 {pct}%，為避免當機停止生成（已完成 {i - 1} 張）")
            _set(message=f"生成第 {i}/{len(seeds)} 張（seed {seed}）…", done=i - 1, total=len(seeds))
            t0 = time.time()
            img = lm.generate(model, spec["model"], prompt=prompt, seed=seed, width=width, height=height,
                              negative_prompt=neg, image_paths=refs or None)
            path = lm.save(img, out / f"{seed}.png")
            rec = dict(seed=seed, seconds=round(time.time() - t0, 1), url=f"/outputs/{path.relative_to('outputs')}",
                       path=str(path), variant=job["variant"], skin=job["skin"], bust=job["bust"], face=job["face"],
                       pose=job["pose"], model=spec["id"], size=job["size"], ref=bool(refs))
            with _lock:
                _state["results"].insert(0, rec)
            (out / "results.json").write_text(json.dumps(_state["results"][:len(seeds)], ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        _set(message=f"完成 {len(seeds)} 張", done=len(seeds), total=len(seeds))
    except Exception as ex:  # noqa: BLE001
        _set(message="失敗", error=f"{type(ex).__name__}: {ex}")
    finally:
        lm.free()
        with _lock:
            _state["running"] = False


def _set(**kw):
    with _lock:
        _state.update(kw)


def gallery(limit=60):
    """列出過去的產出（最新的在前）。"""
    items = []
    for p in sorted(OUT_ROOT.glob("*/*.png"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        items.append(dict(url=f"/outputs/{p.relative_to('outputs')}", name=p.parent.name + "/" + p.name,
                          seconds=None, seed=p.stem))
    return items


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            html = (Path(__file__).with_name("index.html")).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif path == "/api/options":
            self._json(200, dict(
                variants=list(probe.VARIANTS),
                skins=[dict(key=k, label=v["label"]) for k, v in probe.SKIN_PRESETS.items()],
                busts=[dict(key=k, label={"default": "原本", "full": "豐滿堅挺", "fuller": "更大更高", "huge": "再更大"}.get(k, k))
                       for k in probe.BUST_PRESETS],
                faces=[dict(key=k, label=v["label"]) for k, v in probe.FACE_PRESETS.items()],
                poses=[dict(key=k, label=v["label"]) for k, v in probe.POSE_PRESETS.items()],
                models=[dict(id=m["id"], label=m["label"]) for m in MODELS],
                sizes=[dict(key=k, label=v) for k, v in SIZES],
                default_skin=probe.DEFAULT_SKIN["personal"]))
        elif path == "/api/status":
            with _lock:
                self._json(200, dict(_state, free_pct=free_pct()))
        elif path == "/api/gallery":
            self._json(200, dict(items=gallery()))
        elif path.startswith("/outputs/"):
            f = Path("outputs") / path[len("/outputs/"):]
            if not f.is_file() or ".." in path:
                self._json(404, dict(error="找不到檔案"))
                return
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._json(404, dict(error="沒有這個路徑"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._json(400, dict(error="請求格式錯誤"))
            return
        if self.path == "/api/prompt":
            try:
                v = probe.VARIANTS[body["variant"]]
                prompt = probe.build_prompt(v, True, body.get("skin", "fair"), body.get("bust", "default"),
                                            body.get("face", "default"), body.get("pose", "default"))
                self._json(200, dict(prompt=prompt + (REF_SENTENCE if body.get("has_ref") else "")))
            except KeyError as ex:
                self._json(400, dict(error=f"未知的設定 {ex}"))
            return
        if self.path == "/api/generate":
            with _lock:
                if _state["running"]:
                    self._json(409, dict(error="已經有一張在生成，等它跑完"))
                    return
                _state.update(running=True, message="排隊中…", error=None, done=0, started=time.time())
            seeds_raw = (body.get("seeds") or "").strip()
            if seeds_raw:
                seeds = [int(s) for s in re.split(r"[,\s]+", seeds_raw) if s]
            else:
                seeds = [random.randint(1, 2**31 - 1) for _ in range(int(body.get("count", 1)))]
            job = dict(variant=body["variant"], skin=body.get("skin", "fair"), bust=body.get("bust", "default"),
                       face=body.get("face", "default"), pose=body.get("pose", "default"),
                       model_id=body.get("model_id", MODELS[0]["id"]),
                       size=body.get("size", "704x1216"), seeds=seeds, ref=body.get("ref"))
            _set(total=len(seeds))
            threading.Thread(target=run_job, args=(job,), daemon=True).start()
            self._json(200, dict(ok=True, seeds=seeds))
            return
        self._json(404, dict(error="沒有這個路徑"))


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    url = f"http://{HOST}:{PORT}/"
    print(f"本機生圖介面：{url}（只綁 127.0.0.1，外面連不到）")
    print(f"寫法 {len(probe.VARIANTS)} 種、膚色 {len(probe.SKIN_PRESETS)} 種；產出在 {OUT_ROOT}")
    if os.environ.get("GUI_NO_OPEN") != "1":
        subprocess.Popen(["open", url])
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
