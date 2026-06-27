#!/usr/bin/env python3
"""歷史建築類 canary:用『現代紀實旅遊照』框架硬攻 timbuktu + angkor_wat.
手法:拿掉 Age-of-Sail 年代框與 orientalist 人物/駱駝觸發詞,改框成「今日拍下這座
古蹟」的真實旅遊照 + 具體相機痕跡(DSLR/定焦/硬光/感光顆粒)+ guidance 調高 4.5。
生圖前刪舊 raw 防 mflux _N 不覆蓋.輸出到 canary/ 供判讀,不碰真檔."""
import hashlib, time, gc
from pathlib import Path
from PIL import Image

OUT = Path("/private/tmp/claude-501/-Users-mcgrady-claude-The-Age-of-Exploration-/f3118cfb-9774-4f57-93a0-ab52fe5e00ab/scratchpad/canary")
RAW = OUT / "raw"
OUT.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)
W, H, STEPS, G = 768, 512, 20, 4.5

PHOTO_TAIL = (
    " Shot on a full-frame DSLR with a 35mm lens in bright natural daylight: edge-to-edge sharp focus, "
    "fine realistic sensor detail and true material texture in the weathered stone/earth, true-to-life "
    "natural color, real hard sun shadows, faint atmospheric haze and fine airborne dust, deep realistic "
    "depth, slight natural sensor grain, photojournalistic National Geographic travel realism. A genuine "
    "PHOTOGRAPH of the real site as it stands — absolutely NOT a painting, illustration, orientalist art, "
    "watercolour, concept art, matte painting or 3D render: no brushstrokes, no painterly texture, no canvas, "
    "no soft romantic glow.")

NEG = ("painting, oil painting, orientalist painting, watercolour, romantic painting, illustration, drawing, "
       "sketch, brushstrokes, painterly, impasto, canvas texture, soft romantic haze, golden-hour painterly "
       "glow, concept art, matte painting, 3d render, CGI, digital art, stylized, cartoon, anime, modern "
       "elements, electric light, cars, power lines, tourists, modern clothing, lowres, blurry, oversaturated, "
       "HDR halos, watermark, text, signature, logo")

SITES = {
    "timbuktu": (
        "A real, true-to-life documentary travel PHOTOGRAPH of the ancient mud-brick architecture of Timbuktu "
        "on the southern edge of the Sahara: the great Djinguereber Mosque built of tan banco mud-plaster with "
        "rows of protruding wooden toron beams, smooth organic earthen walls and a stout pyramidal minaret, "
        "low flat-roofed mud-brick dwellings clustered around it on sun-bleached desert sand, a few sparse "
        "acacia trees, a pale hot hazy sky."),
    "angkor_wat": (
        "A real, true-to-life documentary travel PHOTOGRAPH of Angkor Wat, Cambodia: the quincunx of five "
        "lotus-bud sandstone towers — one tall central spire flanked by four lower corner towers — rising "
        "above tiered galleried walls in warm grey-tan stone, its long silhouette reflected in the still water "
        "of the wide rectangular moat, a naga-balustraded stone causeway leading toward it, the ramparts "
        "half-reclaimed by tropical jungle with strangler-fig roots, moss and creeping vines, humid haze "
        "softening the distant towers."),
}


def seed_for(sid):
    return int(hashlib.sha1(sid.encode()).hexdigest()[:8], 16) % (2 ** 31)


def crop_webp(src, dst):
    img = Image.open(src).convert("RGB")
    w, h = img.size
    th = int(round(w * 150 / 240))
    if th <= h:
        top = (h - th) // 2
        img = img.crop((0, top, w, top + th))
    else:
        tw = int(round(h * 240 / 150))
        left = (w - tw) // 2
        img = img.crop((left, 0, left + tw, h))
    img.resize((240, 150), Image.Resampling.LANCZOS).save(dst, "WEBP", quality=92, method=6)


t0 = time.time()
import mlx.core as mx
from mflux.models.qwen.variants.txt2img.qwen_image import QwenImage
print("loading ...", flush=True)
qwen = QwenImage(quantize=None, model_path="mlx-community/Qwen-Image-2512-4bit", lora_paths=None, lora_scales=None)
print(f"loaded {time.time()-t0:.0f}s", flush=True)

for sid, scene in SITES.items():
    for p in [RAW / f"{sid}.png", *RAW.glob(f"{sid}_*.png")]:
        p.unlink(missing_ok=True)
    t1 = time.time()
    img = qwen.generate_image(seed=seed_for(sid), prompt=scene + PHOTO_TAIL, negative_prompt=NEG,
                              width=W, height=H, guidance=G, num_inference_steps=STEPS)
    raw = RAW / f"{sid}.png"
    img.save(path=str(raw))
    crop_webp(raw, OUT / f"{sid}.webp")
    print(f"[canary] {sid} {time.time()-t1:.0f}s -> {raw.name}", flush=True)
    try:
        mx.clear_cache()
    except Exception:
        pass
    gc.collect()
print(f"== canary done {(time.time()-t0)/60:.0f}min", flush=True)
