#!/usr/bin/env python3
"""把 55 條 site prompt 由『歷史油畫』轉成『紀實攝影』(photo v2 手法,程式化).
保留每條的場景事實(Rendered as... 之前那段),丟掉油畫/god-ray/mood,接通用攝影 block.
輸出新 JSON 到 scratch 供驗證;不直接改真檔."""
import json, sys
from pathlib import Path

SRC = Path("/Users/mcgrady/claude/The-Age-of-Exploration-/assets/data/exploration/site_art_prompts.json")
DST = Path("/private/tmp/claude-501/-Users-mcgrady-claude-The-Age-of-Exploration-/f3118cfb-9774-4f57-93a0-ab52fe5e00ab/scratchpad/site_art_prompts.photo.json")

SPLIT = "Rendered as a grounded, photorealistic oil painting"

PHOTO_BLOCK = (
    " Captured as a real, true-to-life wide-angle documentary landscape PHOTOGRAPH of a real place during the "
    "Age of Sail (1450-1650), with no modern elements or anachronisms — shot on a full-frame camera with a wide "
    "lens: sharp natural focus, ultra-fine realistic detail and physically-accurate weathered materials and "
    "textures, realistic natural light appropriate to the scene with true-to-life soft shadows and real "
    "atmospheric haze, high dynamic range, deep realistic depth of field, photojournalistic realism, the look "
    "of National Geographic travel photography. A genuine photograph of a real place — absolutely NOT a "
    "painting, NOT an illustration, NOT concept art, NOT a 3D render: no brushstrokes, no painterly texture, "
    "no canvas, no stylization."
)
PHOTO_NEG = (
    "painting, oil painting, illustration, drawing, sketch, brushstrokes, painterly, impasto, canvas texture, "
    "concept art, matte painting, 3d render, CGI, digital art, stylized, cartoon, anime, modern elements, "
    "electric light, neon, LED, people in modern dress, modern clothing, contemporary buildings, cars, power "
    "lines, plastic, glass skyscrapers, lowres, blurry, jpeg artifacts, oversaturated, HDR halos, watermark, "
    "text, letters, signature, logo, two competing focal points, busy cluttered composition"
)

d = json.load(open(SRC))
sites = d["sites"]
fails, short = [], []
for sid, e in sites.items():
    p = e["prompt"]
    i = p.find(SPLIT)
    if i == -1:
        fails.append(sid)
        continue
    scene = p[:i].strip()
    if len(scene) < 180:
        short.append((sid, len(scene)))
    e["prompt"] = scene + PHOTO_BLOCK
    e["negative_prompt"] = PHOTO_NEG

# 更新頂層 metadata
d["model"] = "Qwen-Image-2512 (8-bit/4-bit quant) — PHOTO realism rewrite 2026-06-25"
d["canonical_style_suffix_v2"] = ("PHOTO REALISM:" + PHOTO_BLOCK).strip()
d["shared_negative_prompt"] = PHOTO_NEG
d["_comment"] = ("Style switched OIL->PHOTO 2026-06-25 (user decision). Each site 'prompt' keeps its "
                 "scene facts + a documentary-photography render block; painterly/god-ray/mood language removed.")

json.dump(d, open(DST, "w"), ensure_ascii=False, indent=2)
print(f"轉換完成: {len(sites)} 條 -> {DST}")
print(f"切點失敗(找不到 SPLIT): {len(fails)} -> {fails}")
print(f"場景偏短(<180字,需人工看): {len(short)} -> {short}")
print()
for sid in ["angkor_wat", "antarctica", "timbuktu"]:
    if sid in sites:
        print(f"=== {sid} 轉換後 prompt ===")
        print(sites[sid]["prompt"][:520])
        print("...")
        print()
