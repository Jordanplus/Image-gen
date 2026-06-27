#!/usr/bin/env python3
"""angkor_wat 徹底攝影改寫 v2:保留場景事實,拔掉所有 painterly/mood 詞,換真攝影指令."""
import hashlib, time
from pathlib import Path

OUT = Path("/private/tmp/claude-501/-Users-mcgrady-claude-The-Age-of-Exploration-/f3118cfb-9774-4f57-93a0-ab52fe5e00ab/scratchpad/compare")
SID = "angkor_wat"
W, H, STEPS, G = 768, 512, 20, 3.5
seed = int(hashlib.sha1(SID.encode()).hexdigest()[:8], 16) % (2 ** 31)

# 只留「場景事實」,拔掉 god-rays / mood / oil 全部
SCENE = (
    "Angkor Wat, Cambodia in the year 1500: the quincunx of five lotus-bud sandstone towers — one tall "
    "central spire flanked by four lower corner towers — rising in warm grey-tan stone above tiered "
    "galleried walls, its long stepped silhouette mirrored in the still water of a wide rectangular moat "
    "in the foreground, a naga-balustraded stone causeway leading toward it. Half-reclaimed by tropical "
    "jungle: strangler-fig roots, moss and creeping vines on the weathered ramparts. A few egrets cross "
    "the sky; humid haze softens the distant towers. No people in modern dress, no modern structures."
)
PHOTO = (
    " Shot as a real, true-to-life wide-angle documentary landscape PHOTOGRAPH on a full-frame camera with "
    "a 24mm lens: sharp natural focus, ultra-fine realistic detail in the weathered sandstone and foliage, "
    "lifelike physically-accurate materials and textures, natural warm late-afternoon sunlight with realistic "
    "soft shadows and real atmospheric haze, high dynamic range, deep realistic depth, photojournalistic "
    "realism, the look of National Geographic travel photography. A genuine photograph of a real place — "
    "absolutely NOT a painting, NOT an illustration, NOT concept art, NOT a 3D render: no brushstrokes, "
    "no painterly texture, no canvas, no stylization."
)
photo_prompt = SCENE + PHOTO
neg = ("painting, oil painting, illustration, drawing, sketch, brushstrokes, painterly, impasto, canvas "
       "texture, concept art, matte painting, 3d render, CGI, digital art, stylized, cartoon, anime, "
       "modern elements, electric light, neon, people in modern dress, cars, power lines, lowres, blurry, "
       "oversaturated, watermark, text, signature")

t0 = time.time()
from mflux.models.qwen.variants.txt2img.qwen_image import QwenImage
print("loading ...", flush=True)
qwen = QwenImage(quantize=None, model_path="mlx-community/Qwen-Image-2512-4bit", lora_paths=None, lora_scales=None)
print(f"loaded {time.time()-t0:.0f}s", flush=True)
t1 = time.time()
img = qwen.generate_image(seed=seed, prompt=photo_prompt, negative_prompt=neg,
                          width=W, height=H, guidance=G, num_inference_steps=STEPS)
p = OUT / "angkor_wat_STYLE_photo_v2.png"
img.save(path=str(p))
print(f"[photo_v2] {time.time()-t1:.0f}s -> {p}", flush=True)
print("== done", flush=True)
