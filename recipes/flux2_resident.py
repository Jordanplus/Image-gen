#!/usr/bin/env python3
"""55 探險地 FLUX.2-klein-9B 常駐生成:模型載一次、迴圈生全部.
用 photo4.json 豐富 prompts、同 seed_for(sid).FLUX.2 蒸餾:6 步、guidance 1.0、無 negative.
非破壞:輸出到 scratchpad/flux2_full(webp)+ flux2_full_raw(png),驗證後再進專案.
必須用 mflux venv python 跑.
"""
import json, time, hashlib, argparse, gc
from pathlib import Path
from PIL import Image

SCR = Path("/private/tmp/claude-501/-Users-mcgrady-claude-The-Age-of-Exploration-/f3118cfb-9774-4f57-93a0-ab52fe5e00ab/scratchpad")
JSON = SCR / "site_art_prompts.photo4.json"
RAW = SCR / "flux2_full_raw"
FINAL_W, FINAL_H = 240, 150
LANCZOS = Image.Resampling.LANCZOS


def seed_for(sid):
    return int(hashlib.sha1(sid.encode()).hexdigest()[:8], 16) % (2 ** 31)


def crop_to_thumb(src, dst):
    img = Image.open(src).convert("RGB")
    w, h = img.size
    target_h = int(round(w * FINAL_H / FINAL_W))
    if target_h <= h:
        top = (h - target_h) // 2
        img = img.crop((0, top, w, top + target_h))
    else:
        target_w = int(round(h * FINAL_W / FINAL_H))
        left = (w - target_w) // 2
        img = img.crop((left, 0, left + target_w, h))
    img = img.resize((FINAL_W, FINAL_H), LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "WEBP", quality=92, method=6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="all")
    ap.add_argument("--gen-w", type=int, default=768)
    ap.add_argument("--gen-h", type=int, default=512)
    ap.add_argument("--steps", type=int, default=6)
    ap.add_argument("--outdir", default=str(SCR / "flux2_full"))
    ap.add_argument("--json", default=str(JSON))
    a = ap.parse_args()

    data = json.load(open(a.json))
    sites = data["sites"]
    ids = list(sites.keys()) if a.ids == "all" else a.ids.split(",")
    outdir = Path(a.outdir); outdir.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    todo = [s for s in ids if not (outdir / f"{s}.webp").exists()]
    print(f"== FLUX.2 resident: {len(todo)}/{len(ids)} to do {a.gen_w}x{a.gen_h} steps={a.steps}", flush=True)
    if not todo:
        print("== nothing to do", flush=True); return

    t0 = time.time()
    import mlx.core as mx
    from mflux.models.common.config import ModelConfig
    from mflux.models.flux2.variants import Flux2Klein
    print("== loading FLUX.2-klein-9B (q4) ...", flush=True)
    model = Flux2Klein(quantize=4, model_config=ModelConfig.flux2_klein_9b())
    print(f"== model loaded in {time.time() - t0:.0f}s", flush=True)

    def clear():
        try:
            mx.clear_cache()
        except Exception:
            pass
        gc.collect()

    times = []
    for i, sid in enumerate(todo, 1):
        e = sites[sid]
        raw_png = RAW / f"{sid}.png"
        out_webp = outdir / f"{sid}.webp"
        for stale in [raw_png, *RAW.glob(f"{sid}_*.png")]:
            stale.unlink(missing_ok=True)
        t1 = time.time()
        try:
            img = model.generate_image(
                seed=seed_for(sid), prompt=e["prompt"],
                num_inference_steps=a.steps, width=a.gen_w, height=a.gen_h, guidance=1.0)
            img.save(path=str(raw_png))
            crop_to_thumb(raw_png, out_webp)
        except Exception as ex:
            print(f"[{i}/{len(todo)}] FAIL {sid}: {repr(ex)[:200]}", flush=True)
            clear(); continue
        dt = time.time() - t1
        times.append(dt); avg = sum(times) / len(times)
        eta = (len(todo) - i) * avg / 60
        print(f"[{i}/{len(todo)}] OK {sid} {dt:.0f}s (avg {avg:.0f}s, ETA {eta:.0f}min) -> {out_webp.name}", flush=True)
        clear()
    print(f"== DONE {len(times)} imgs, total {(time.time() - t0) / 60:.0f}min", flush=True)


if __name__ == "__main__":
    main()
