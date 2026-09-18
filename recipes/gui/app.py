#!/usr/bin/env python3
"""本機生圖介面（只綁 127.0.0.1，外面連不到）。

用 mflux 的 python 跑，從專案根目錄：
    ~/.local/share/uv/tools/mflux/bin/python recipes/gui/app.py     （或 make gui）

設計重點：
- **模型常駐**：同一組（模型＋LoRA＋有無參考圖）只載入一次，之後每張省掉 30–60 秒的載入。
- 選項直接讀 `recipes/commercial/portrait_style_probe.py` 的寫法與膚色／胸型／長相設定，不另外維護一份。
- 參考圖從瀏覽器上傳（base64 JSON，不用解 multipart），自動裁臉後交給 FLUX.2 的參考圖編輯版；
  有參考圖時 prompt 會改成鎖臉寫法（不寫髮型／五官／膚色，交給參考圖），只開放內建寫法。
- 產出的圖可以點圖看原尺寸，或按「放大」用 SeedVR2 放到長邊 1536。
- 只用標準函式庫的 http.server：mflux 的 venv 不必另外裝套件。
- 每張生成前檢查可用記憶體，低於門檻就拒絕，避免整台卡死（24GB 機器實測 klein-9B 會用到 swap）。
"""
import base64
import json
import mimetypes
import os
import queue
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
# 可用記憶體門檻：32GB M5 下降為 5% 避免誤擋；24GB Mac mini 維持 15% 防線確保不崩潰
MIN_FREE_PCT = 15 if lm.total_ram_gb() < 30 else 5
# 放大上限：SeedVR2 的 resolution 參數指的是「短邊」，不是長邊。
UPSCALE_MAX_PIXELS = 1536 * 2304
UPSCALE_MAX_SCALE = 2.0

# 介面上的模型選單（model 對應 local_models.MODELS；lora 為 None 代表不掛外掛）
MODELS = [
    dict(id="klein-9b-uncensored", label="klein-9B（無審查 Text Encoder）", model="klein-9b-uncensored", use="personal", lora=None),
    dict(id="klein-9b", label="klein-9B（標準）", model="klein-9b", use="personal", lora=None),
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

# 尺寸選單：24GB 機器推薦 704×1216 / 768×1152；32GB 機器原生支援 1024×1024 / 1024×1536
SIZES = [
    ("704x1216", "直式 704×1216 (24GB 推薦)"),
    ("768x1152", "直式 768×1152"),
    ("1024x1024", "方形 1024×1024 (32GB 原生)"),
    ("1024x1536", "高解析直式 1024×1536 (32GB 原生)"),
    ("1536x1024", "高解析橫式 1536×1024 (32GB 原生)"),
]

_state = dict(running=False, message="待命中", queue=0, done=0, total=0, results=[], error=None, started=None, step=0, step_total=0, pct=0)
_lock = threading.Lock()
_loaded = dict(key=None, model=None)
_jobs = queue.Queue()


def _worker():
    """所有生成／放大都跑在同一條執行緒。

    MLX 的陣列綁在「建立它的那條執行緒」的 stream 上：常駐模型若在 A 執行緒載入、換 B 執行緒拿來用，
    第二次生成就會炸 `There is no Stream(cpu, 0) in current thread`（2026-09-16 實測：同一組設定連跑
    兩次必中；之前沒踩到是因為每次都換模型，等於重載一份在新執行緒）。單一 worker 就不會跨執行緒。
    """
    while True:
        kind, payload = _jobs.get()
        try:
            (run_job if kind == "generate" else run_upscale)(payload)
        except Exception as ex:  # noqa: BLE001  worker 不能死，否則之後都不會動
            _set(message="失敗", error=f"{type(ex).__name__}: {ex}")
            with _lock:
                _state["running"] = False
        finally:
            _jobs.task_done()


def _build():
    """頁面版本號＝index.html 的修改時間；頁面和後端不一致就代表瀏覽器拿的是舊版。"""
    return int(Path(__file__).with_name("index.html").stat().st_mtime)


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
    low_ram = (lm.total_ram_gb() < 30)
    quantize = 8 if lm.total_ram_gb() >= 30 else 4
    model = lm.load(model_key, use, quantize=quantize, edit=edit, low_ram=low_ram,
                    lora_paths=[lora_path] if lora_path else None, lora_scales=[1.0] if lora_path else None)
    _loaded.update(key=key, model=model)
    return model


def prompt_for(job, has_ref):
    """組 prompt；有參考圖時鎖臉五官神情，並尊重使用者所選膚色覆蓋老照片的偏黃底色。"""
    skin_key = job.get("skin") or probe.DEFAULT_SKIN["personal"]
    if skin_key not in probe.SKIN_PRESETS:
        skin_key = probe.DEFAULT_SKIN["personal"]
    preset = probe.SKIN_PRESETS[skin_key]

    custom = (job.get("custom_prompt") or "").strip()
    if custom:
        if has_ref:
            n = has_ref if (isinstance(has_ref, int) and has_ref > 1) else 1
            refs_str = "image 1" if n == 1 else ("images " + ", ".join(str(i) for i in range(1, n)) + f" and {n}")
            ref_lead = f"A photo of the exact same person as shown in {refs_str}, identical face and hair. "
            ref_tail = (f" Keep facial features, facial contours, eyes, eyebrows, nose, mouth, hair colour, hairstyle "
                        f"and facial likeness completely identical to {refs_str}. "
                        f"Her skin tone and complexion is: {preset['skin']} Natural candid pose, real camera photo, sharp focus.")
            return f"{ref_lead}{custom}.{ref_tail}"
        return custom

    name = job["variant"]
    return probe.build_prompt(probe.VARIANTS[name], True, skin_key, job["bust"], job["face"], job["pose"],
                              ref=has_ref, framing=job.get("framing", "default"))


def prepare_refs(refs_spec, out_dir):
    """處理單張或多張參考圖（可為 base64 data URL 或 reference/ 目錄路徑）。
    32GB M5 解鎖 1024 高清裁臉，24GB 機型維持 768。
    回傳裁切後的參考圖檔案路徑清單（最多 3 張）。
    """
    import travel_with_me as tw
    out_dir.mkdir(parents=True, exist_ok=True)
    if not refs_spec:
        return []
    if isinstance(refs_spec, str):
        refs_list = [refs_spec]
    else:
        refs_list = list(refs_spec)

    src_files = []
    for idx, item in enumerate(refs_list):
        if not item:
            continue
        if str(item).startswith("data:"):
            raw = base64.b64decode(item.split(",", 1)[-1])
            src = out_dir / f"upload_{idx}.jpg"
            src.write_bytes(raw)
            src_files.append(src)
        else:
            p = ROOT / item if not Path(item).is_absolute() else Path(item)
            if p.is_file():
                src_files.append(p)

    if not src_files:
        return []

    # 32GB 機器支援 1024 參考圖細節更精緻，24GB 機器維持 768；精選最多 3 張避免特徵模糊
    ref_size = 1024 if lm.total_ram_gb() >= 30 else 768
    return tw.prepare_refs(src_files[:3], out_dir, size=ref_size, face_crop=True)


def run_job(job):
    spec = next(m for m in MODELS if m["id"] == job["model_id"])
    width, height = (int(v) for v in job["size"].split("x"))
    seeds = job["seeds"]
    poses = job["poses"] or ["default"]
    total = len(poses) * len(seeds)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = OUT_ROOT / f"{stamp}_{spec['id']}"
    refs = []
    try:
        raw_refs = job.get("refs") or ([job["ref"]] if job.get("ref") else [])
        if raw_refs:
            _set(message=f"處理參考圖（{len(raw_refs)} 張·1024px 高清裁臉鎖定）…", pct=2)
            refs = prepare_refs(raw_refs, out / "refs")

        n_refs = len(refs)
        # 先把每種姿勢的 prompt 都組好（帶入實際參考圖張數，動態組裝 image 1, image 2... 鎖臉詞）
        prompts = {po: prompt_for(dict(job, pose=po), n_refs if n_refs > 0 else False) for po in poses}
        _set(message="載入模型…" if _loaded["key"] != (spec["model"], spec["lora"], bool(refs)) else "準備生成…", pct=4)
        model = get_model(spec["model"], spec["use"], spec["lora"], bool(refs))
        neg = probe.negative_for(spec["model"], True)
        i = 0
        for po in poses:
            for seed in seeds:
                i += 1
                cur_img = i
                pct_mem = free_pct()
                if pct_mem is not None and pct_mem < MIN_FREE_PCT:
                    raise RuntimeError(f"可用記憶體只剩 {pct_mem}%，為避免當機停止生成（已完成 {i - 1} 張）")
                label = probe.POSE_PRESETS[po]["label"]
                lock_text = f"【極致鎖臉 {n_refs} 圖】" if n_refs else ""
                base_pct = int(((cur_img - 1) / total) * 100)
                _set(message=f"生成第 {cur_img}/{total} 張{lock_text}（{label}・seed {seed}）…",
                     done=cur_img - 1, total=total, step=0, step_total=4, pct=base_pct)

                def _step_cb(cur_step, total_steps, status_text, img_idx=cur_img):
                    step_fraction = (cur_step / total_steps) if total_steps else 0
                    calc_pct = int(((img_idx - 1 + step_fraction) / total) * 100)
                    _set(message=f"生成第 {img_idx}/{total} 張{lock_text}（{label}・seed {seed}）… {status_text}",
                         done=img_idx - 1, total=total, step=cur_step, step_total=total_steps,
                         pct=min(99, max(0, calc_pct)))

                t0 = time.time()
                img = lm.generate(model, spec["model"], prompt=prompts[po], seed=seed, width=width, height=height,
                                  negative_prompt=neg, image_paths=refs or None, step_callback=_step_cb)
                path = lm.save(img, out / (f"{seed}.png" if po == "default" else f"{po}_{seed}.png"))
                rec = dict(seed=seed, seconds=round(time.time() - t0, 1),
                           url=f"/outputs/{path.relative_to('outputs')}", path=str(path), variant=job["variant"],
                           skin=job["skin"], bust=job["bust"], face=job["face"], pose=po, pose_label=label,
                           framing=job.get("framing", "default"), model=spec["id"], size=job["size"],
                           ref=bool(refs), ref_count=len(refs))
                with _lock:
                    _state["results"].insert(0, rec)
                (out / "results.json").write_text(json.dumps(_state["results"][:total], ensure_ascii=False, indent=1),
                                                  encoding="utf-8")
                _set(done=i, total=total, pct=int((i / total) * 100))
        _set(message=f"完成 {total} 張", done=total, total=total, step=0, step_total=0, pct=100)
    except Exception as ex:  # noqa: BLE001
        _set(message="失敗", error=f"{type(ex).__name__}: {ex}")
    finally:
        lm.free()
        with _lock:
            _state["running"] = False


def upscale_resolution(w, h):
    """依原圖尺寸算 SeedVR2 的 resolution（＝短邊），回傳 (短邊, 預估輸出尺寸)。"""
    scale = min(UPSCALE_MAX_SCALE, (UPSCALE_MAX_PIXELS / (w * h)) ** 0.5)
    short = max(min(w, h), int(min(w, h) * scale))
    k = short / min(w, h)
    return short, (int(w * k) // 2 * 2, int(h * k) // 2 * 2)


def run_upscale(src_rel):
    """把介面產出的某一張用 SUPIR 進行超解析度修復與放大 2x。"""
    try:
        root = OUT_ROOT.resolve()
        src = Path(src_rel).resolve()
        if root not in src.parents or not src.is_file():
            raise RuntimeError("只能放大這個介面產出的圖")
        pct = free_pct()
        if pct is not None and pct < MIN_FREE_PCT:
            raise RuntimeError(f"可用記憶體只剩 {pct}%，先關掉一些程式再放大")

        # 先把常駐的生圖模型釋放，釋放 RAM 給 SUPIR
        _set(message="釋放生圖模型，準備 SUPIR 放大…")
        _loaded.update(key=None, model=None)
        lm.free()

        from PIL import Image
        with Image.open(src) as im:
            orig_w, orig_h = im.size

        supir_py = ROOT / "venv" / "bin" / "python"
        supir_runner = ROOT / "recipes" / "upscale_supir.py"
        dst = src.with_name(f"{src.stem}_supir_2x.png")

        _set(message="啟動 SUPIR 放大引擎…", pct=10)
        t0 = time.time()
        cmd = [
            str(supir_py),
            str(supir_runner),
            str(src),
            "--scale", "2.0",
            "--output", str(dst),
        ]
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        while proc.poll() is None:
            time.sleep(2)
            elapsed = int(time.time() - t0)
            est_pct = min(95, 20 + int(elapsed * 2.5))
            _set(message=f"SUPIR 重建修復與放大中（已耗時 {elapsed} 秒）…", pct=est_pct)

        ret = proc.returncode
        stdout, _ = proc.communicate()
        if ret != 0 or not dst.exists():
            raise RuntimeError(f"SUPIR 放大失敗 (code {ret}): {(stdout or '')[-300:]}")

        with Image.open(dst) as up_im:
            up_w, up_h = up_im.size

        url = f"/outputs/{dst.relative_to(Path('outputs').resolve())}"
        with _lock:
            for r in _state["results"]:
                if Path(r["path"]).resolve() == src:
                    r.update(up_url=url, up_size=f"{up_w}×{up_h}")
        _set(message=f"SUPIR 放大完成 {up_w}×{up_h}（{time.time() - t0:.0f} 秒）", pct=100)
    except Exception as ex:  # noqa: BLE001
        _set(message="放大失敗", error=f"{type(ex).__name__}: {ex}")
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
            # 瀏覽器快取住舊頁面會很難察覺（2026-09-16：使用者用舊頁面選姿勢，新版後端收不到而靜靜跑成預設），
            # 所以一律不給快取，並把版本號（index.html 的修改時間）塞進頁面，跟 /api/status 比對。
            src = Path(__file__).with_name("index.html")
            html = src.read_text(encoding="utf-8").replace("__BUILD__", str(_build())).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif path == "/api/options":
            ram_gb = lm.total_ram_gb()
            is_32gb = ram_gb >= 30
            hardware = dict(
                ram_gb=round(ram_gb, 1),
                is_32gb=is_32gb,
                machine="32GB MacBook Pro" if is_32gb else "24GB Mac mini",
                mode="8-bit 常駐旗艦模式" if is_32gb else "4-bit 輕量安全模式",
                default_size="1024x1536" if is_32gb else "704x1216",
            )
            # 依硬體自動呈現最適模型標籤
            dyn_models = [
                dict(id="klein-9b-uncensored",
                     label="klein-9B（8-bit 無審查·32GB 原生）★推薦" if is_32gb else "klein-9B（4-bit 無審查·24GB）"),
                dict(id="klein-9b",
                     label="klein-9B（8-bit 標準·32GB 原生）" if is_32gb else "klein-9B（4-bit·24GB）"),
            ]
            # 依硬體推薦最佳尺寸
            dyn_sizes = [
                dict(key="1024x1536", label="高解析直式 1024×1536 ★32GB推薦" if is_32gb else "高解析直式 1024×1536 (24GB較吃記憶體)"),
                dict(key="1024x1024", label="方形 1024×1024 ★32GB推薦" if is_32gb else "方形 1024×1024 (24GB較吃記憶體)"),
                dict(key="1536x1024", label="高解析橫式 1536×1024 ★32GB推薦" if is_32gb else "高解析橫式 1536×1024 (24GB較吃記憶體)"),
                dict(key="768x1152", label="直式 768×1152" + ("" if is_32gb else " ★24GB推薦")),
                dict(key="704x1216", label="直式 704×1216" + ("" if is_32gb else " ★24GB推薦")),
            ]
            bust_labels = {
                "default": "原本",
                "slender": "苗條精巧",
                "full": "豐滿堅挺",
                "fuller": "更大更高",
                "huge": "超大",
                "maximum": "極致巨大",
            }
            # 列出 reference/ 目錄中可用的參考圖（蘇菲·瑪索等系列）
            preset_refs = []
            ref_dir = ROOT / "reference"
            if ref_dir.is_dir():
                for f in sorted(ref_dir.glob("*.*")):
                    if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                        is_main = ("ref-03" in f.name)
                        label = f"{f.name} (★主基準·正面)" if is_main else (
                            f"{f.name} (側顏立體)" if "ref-01" in f.name else (
                                f"{f.name} (3/4視角)" if "ref-04" in f.name else f.name
                            )
                        )
                        preset_refs.append(dict(
                            id=f.name,
                            label=label,
                            path=f"reference/{f.name}",
                            url=f"/reference/{f.name}",
                            is_main=is_main,
                            default_selected=f.name in ("ref-03.jpeg", "ref-01.jpg", "ref-04.jpeg")
                        ))
            self._json(200, dict(
                hardware=hardware,
                variants=list(probe.VARIANTS),
                skins=[dict(key=k, label=v["label"]) for k, v in probe.SKIN_PRESETS.items()],
                busts=[dict(key=k, label=bust_labels.get(k, k)) for k in probe.BUST_PRESETS],
                faces=[dict(key=k, label=v["label"]) for k, v in probe.FACE_PRESETS.items()],
                poses=[dict(key=k, label=v["label"]) for k, v in probe.POSE_PRESETS.items()],
                framings=[dict(key=k, label=v["label"]) for k, v in probe.FRAMING_PRESETS.items()],
                models=dyn_models,
                sizes=dyn_sizes,
                preset_refs=preset_refs,
                default_skin=probe.DEFAULT_SKIN["personal"]))
        elif path == "/api/status":
            with _lock:
                self._json(200, dict(_state, free_pct=free_pct(), build=_build()))
        elif path == "/api/gallery":
            self._json(200, dict(items=gallery()))
        elif path.startswith("/reference/"):
            rel = path[len("/reference/"):]
            f = ROOT / "reference" / rel
            if not f.is_file() or ".." in path:
                self._json(404, dict(error="找不到參考檔案"))
                return
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
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
                job = dict(variant=body["variant"], skin=body.get("skin", probe.DEFAULT_SKIN["personal"]), bust=body.get("bust", "default"),
                           face=body.get("face", "default"), pose=body.get("pose", "default"),
                           framing=body.get("framing", "default"), custom_prompt=body.get("custom_prompt"))
                ref_count = int(body.get("ref_count", 0)) if body.get("has_ref") else 0
                self._json(200, dict(prompt=prompt_for(job, ref_count if ref_count > 0 else bool(body.get("has_ref")))))
            except ValueError as ex:
                self._json(200, dict(error=str(ex)))
            except KeyError as ex:
                self._json(400, dict(error=f"未知的設定 {ex}"))
            return
        if self.path == "/api/upscale":
            with _lock:
                if _state["running"]:
                    self._json(409, dict(error="已經有工作在跑，等它跑完"))
                    return
                _state.update(running=True, message="排隊中…", error=None, done=0, total=0, started=time.time())
            _jobs.put(("upscale", body.get("path", "")))
            self._json(200, dict(ok=True))
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
            # 舊版頁面只送單一 pose，沒有 poses；沒接住的話選的姿勢會被靜靜吃掉（2026-09-16 踩過）
            raw_poses = body.get("poses") or [body.get("pose", "default")]
            poses = [p for p in raw_poses if p in probe.POSE_PRESETS] or ["default"]
            job = dict(variant=body["variant"], skin=body.get("skin", probe.DEFAULT_SKIN["personal"]), bust=body.get("bust", "default"),
                       face=body.get("face", "default"), pose=poses[0], poses=poses,
                       framing=body.get("framing", "default"), model_id=body.get("model_id", MODELS[0]["id"]),
                       size=body.get("size", "704x1216"), seeds=seeds,
                       refs=body.get("refs") or ([body["ref"]] if body.get("ref") else []),
                       custom_prompt=body.get("custom_prompt"))
            _set(total=len(seeds) * len(poses))
            _jobs.put(("generate", job))
            self._json(200, dict(ok=True, seeds=seeds))
            return
        if self.path == "/api/shutdown":
            self._json(200, dict(ok=True, message="伺服器正在安全關閉…"))
            def _stop():
                time.sleep(0.5)
                os._exit(0)
            threading.Thread(target=_stop, daemon=True).start()
            return
        self._json(404, dict(error="沒有這個路徑"))


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    url = f"http://{HOST}:{PORT}/"
    print(f"本機生圖介面：{url}（只綁 127.0.0.1，外面連不到）")
    print(f"寫法 {len(probe.VARIANTS)} 種、膚色 {len(probe.SKIN_PRESETS)} 種；產出在 {OUT_ROOT}")
    threading.Thread(target=_worker, daemon=True).start()
    if os.environ.get("GUI_NO_OPEN") != "1":
        subprocess.Popen(["open", url])
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
