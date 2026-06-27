#!/usr/bin/env python3
"""55 探險地 Qwen-Image 本地生成 (mflux-generate-qwen).
每張 = 獨立 process 跑完即退 (避 MPS 32GB 連續累積 OOM).
生 3:2 -> 中央裁 16:10 -> 縮 240x150 -> WebP -> out_path.
"""
import json, subprocess, sys, time, hashlib, argparse, glob
from pathlib import Path
from PIL import Image

PROJ = Path("/Users/mcgrady/claude/The-Age-of-Exploration-")
JSON = PROJ / "assets/data/exploration/site_art_prompts.json"
SCRATCH = Path("/private/tmp/claude-501/-Users-mcgrady-claude-The-Age-of-Exploration-/f3118cfb-9774-4f57-93a0-ab52fe5e00ab/scratchpad")
TMP_RAW = SCRATCH / "site_gen_raw"
FINAL_W, FINAL_H = 240, 150
LANCZOS = Image.Resampling.LANCZOS


def seed_for(sid):
    return int(hashlib.sha1(sid.encode()).hexdigest()[:8], 16) % (2 ** 31)


def crop_to_thumb(src, dst):
    img = Image.open(src).convert("RGB")
    w, h = img.size
    target_h = int(round(w * FINAL_H / FINAL_W))  # 16:10 height for this width
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


def gen_one(sid, e, q, gw, gh, steps, guidance, out_webp, extra,
            model="", lora="", lora_scale=1.0, suffix=""):
    seed = seed_for(sid)
    TMP_RAW.mkdir(parents=True, exist_ok=True)
    raw = TMP_RAW / f"{sid}{suffix or ('_q' + str(q))}.png"
    if raw.exists():
        raw.unlink()
    if model:
        base = ["mflux-generate-qwen", "--model", model]
    else:
        base = ["mflux-generate-qwen", "-m", "qwen", "-q", str(q)]
    cmd = base + ["--prompt", e["prompt"], "--negative-prompt", e["negative_prompt"],
                  "--width", str(gw), "--height", str(gh),
                  "--steps", str(steps), "--guidance", str(guidance),
                  "--seed", str(seed), "--output", str(raw)]
    if lora:
        cmd += ["--lora-paths", lora, "--lora-scales", str(lora_scale)]
    cmd += (extra or [])
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.time() - t0
    found = raw if raw.exists() else None
    if not found:
        cands = [c for c in sorted(glob.glob(str(TMP_RAW / (raw.stem + "*"))))
                 if c.lower().endswith((".png", ".jpg", ".jpeg"))]
        found = Path(cands[-1]) if cands else None
    if r.returncode != 0 or not found:
        return False, dt, (r.stderr or r.stdout)[-1000:]
    crop_to_thumb(found, out_webp)
    return True, dt, str(out_webp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="all")
    ap.add_argument("--quant", type=int, default=8)
    ap.add_argument("--outdir", default=str(PROJ / "assets/art/sites"))
    ap.add_argument("--suffix", default="")
    ap.add_argument("--gen-w", type=int, default=1152)
    ap.add_argument("--gen-h", type=int, default=768)
    ap.add_argument("--steps", type=int, default=25)
    ap.add_argument("--guidance", type=float, default=3.0)
    ap.add_argument("--low-ram", action="store_true")
    ap.add_argument("--model", default="", help="HF repo for pre-quantized model; empty=stock -m qwen -q")
    ap.add_argument("--lora", default="")
    ap.add_argument("--lora-scale", type=float, default=1.0)
    a = ap.parse_args()

    data = json.load(open(JSON))
    sites = data["sites"]
    ids = list(sites.keys()) if a.ids == "all" else a.ids.split(",")
    outdir = Path(a.outdir)
    extra = ["--low-ram"] if a.low_ram else []

    tag = a.model or f"q{a.quant}"
    print(f"== site_art_gen model={tag} lora={a.lora or '-'} n={len(ids)} "
          f"gen={a.gen_w}x{a.gen_h} steps={a.steps} g={a.guidance} low_ram={a.low_ram}", flush=True)
    fail = 0
    for i, sid in enumerate(ids, 1):
        if sid not in sites:
            print(f"[{i}/{len(ids)}] SKIP unknown {sid}", flush=True)
            continue
        out_webp = outdir / f"{sid}{a.suffix}.webp"
        ok, dt, msg = gen_one(sid, sites[sid], a.quant, a.gen_w, a.gen_h,
                              a.steps, a.guidance, out_webp, extra,
                              model=a.model, lora=a.lora, lora_scale=a.lora_scale,
                              suffix=a.suffix)
        if ok:
            fail = 0
            print(f"[{i}/{len(ids)}] OK   {sid} {tag} {dt:.0f}s -> {out_webp}", flush=True)
        else:
            fail += 1
            print(f"[{i}/{len(ids)}] FAIL {sid} {tag} {dt:.0f}s :: {msg}", flush=True)
            if fail >= 5:
                print("ABORT: 5 consecutive failures", flush=True)
                break
    print("== done", flush=True)


if __name__ == "__main__":
    main()
