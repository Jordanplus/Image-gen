#!/usr/bin/env python3
"""angkor_wat 油畫 vs 照片 風格對照:同 seed/設定,只換 rendering 指令.
用 mflux venv python 跑."""
import json, hashlib, time
from pathlib import Path

PROJ = Path("/Users/mcgrady/claude/The-Age-of-Exploration-")
OUT = Path("/private/tmp/claude-501/-Users-mcgrady-claude-The-Age-of-Exploration-/f3118cfb-9774-4f57-93a0-ab52fe5e00ab/scratchpad/compare")
OUT.mkdir(parents=True, exist_ok=True)
SID = "angkor_wat"
W, H, STEPS, G = 768, 512, 20, 3.5

d = json.load(open(PROJ / "assets/data/exploration/site_art_prompts.json"))
e = d["sites"][SID]
oil_prompt = e["prompt"]
oil_neg = e["negative_prompt"]
seed = int(hashlib.sha1(SID.encode()).hexdigest()[:8], 16) % (2 ** 31)

# 動手術:把「Rendered as ... oil painting ... 」整段(到 Lighting is HARD-RULED 前)換成攝影
PHOTO_RENDER = (
    "Rendered as a grounded, true-to-life documentary photograph of a real place during the Age of Sail "
    "(1450-1650), believable enough that the viewer trusts this world truly existed; crisp photorealistic "
    "detail, realistic materials and weathered textures, natural atmospheric haze and depth, cinematic "
    "wide-landscape composition, true-to-life natural color and lighting captured on a real camera - this "
    "is a REAL PHOTOGRAPH, NOT a painting: no brushstrokes, no painterly texture, no canvas, no illustration. "
)
i1 = oil_prompt.find("Rendered as a grounded, photorealistic oil painting")
i2 = oil_prompt.find("Lighting is HARD-RULED")
if i1 == -1 or i2 == -1:
    raise SystemExit("prompt 結構非預期,找不到切點")
photo_prompt = oil_prompt[:i1] + PHOTO_RENDER + oil_prompt[i2:]
photo_neg = oil_neg + ", oil painting, painting, brushstrokes, painterly, canvas texture, impasto, illustration, drawing, sketch"

t0 = time.time()
from mflux.models.qwen.variants.txt2img.qwen_image import QwenImage
print("loading model ...", flush=True)
qwen = QwenImage(quantize=None, model_path="mlx-community/Qwen-Image-2512-4bit", lora_paths=None, lora_scales=None)
print(f"loaded in {time.time()-t0:.0f}s", flush=True)

for tag, prompt, neg in [("oil", oil_prompt, oil_neg), ("photo", photo_prompt, photo_neg)]:
    t1 = time.time()
    img = qwen.generate_image(seed=seed, prompt=prompt, negative_prompt=neg,
                              width=W, height=H, guidance=G, num_inference_steps=STEPS)
    p = OUT / f"angkor_wat_STYLE_{tag}.png"
    img.save(path=str(p))
    print(f"[{tag}] {time.time()-t1:.0f}s -> {p}", flush=True)
print("== done", flush=True)
