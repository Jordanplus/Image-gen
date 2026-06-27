#!/usr/bin/env python3
"""木質羅盤 — FLUX.2-klein-9B 生成（Flux2Klein python API，仿 scratchpad/flux2_resident.py）.

關鍵：mflux CLI 的 --base-model flux2-klein-9b 載不動本機 cache（vae root_path / 假找 text_encoder_2）；
正解＝python API Flux2Klein(quantize=4, ModelConfig.flux2_klein_9b())，且必須用 mflux venv python 跑：
  /Users/mcgrady/.local/share/uv/tools/mflux/bin/python tools/art-pipeline/_mapdecor/gen_compass_flux.py
配方：q4 / 6-step distilled / guidance 1.0 / no negative（同 55 探險地）。
"""
import argparse
from mflux.models.common.config import ModelConfig
from mflux.models.flux2.variants import Flux2Klein

ROOT = "/Users/mcgrady/claude/The-Age-of-Exploration"

ap = argparse.ArgumentParser()
ap.add_argument("--prompt-file", default=f"{ROOT}/tools/art-pipeline/_mapdecor/_compass_prompt.txt")
ap.add_argument("--out", default=f"{ROOT}/tools/art-pipeline/_mapdecor/compass_wood_flux.png")
ap.add_argument("--w", type=int, default=1024)
ap.add_argument("--h", type=int, default=1024)
ap.add_argument("--steps", type=int, default=6)
ap.add_argument("--seed", type=int, default=42)
a = ap.parse_args()

prompt = open(a.prompt_file).read().strip()
print("== loading FLUX.2-klein-9B (q4) ...", flush=True)
model = Flux2Klein(quantize=4, model_config=ModelConfig.flux2_klein_9b())
print(f"== generating {a.w}x{a.h} steps={a.steps} seed={a.seed} ...", flush=True)
img = model.generate_image(
    seed=a.seed, prompt=prompt,
    num_inference_steps=a.steps, width=a.w, height=a.h, guidance=1.0)
img.save(path=a.out)
print("== saved", a.out, flush=True)
