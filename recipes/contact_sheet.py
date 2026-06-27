#!/usr/bin/env python3
"""55 raw PNG 排成 contact sheet,每格標站名+類別,供逐站判讀."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SCR = Path("/private/tmp/claude-501/-Users-mcgrady-claude-The-Age-of-Exploration-/f3118cfb-9774-4f57-93a0-ab52fe5e00ab/scratchpad")
RAW = SCR / "site_gen_raw"
JSON = Path("/Users/mcgrady/claude/The-Age-of-Exploration-/assets/data/exploration/site_art_prompts.json")
OUT = SCR / "contact_sheet.png"

d = json.load(open(JSON))
sites = d["sites"]
ids = list(sites.keys())

COLS = 7
CELL_W, CELL_H = 300, 200
LABEL_H = 26
PAD = 6
rows = (len(ids) + COLS - 1) // COLS
W = COLS * (CELL_W + PAD) + PAD
H = rows * (CELL_H + LABEL_H + PAD) + PAD

sheet = Image.new("RGB", (W, H), (24, 24, 28))
draw = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
except Exception:
    font = ImageFont.load_default()

for i, sid in enumerate(ids):
    r, c = divmod(i, COLS)
    x = PAD + c * (CELL_W + PAD)
    y = PAD + r * (CELL_H + LABEL_H + PAD)
    png = RAW / f"{sid}.png"
    if png.exists():
        im = Image.open(png).convert("RGB")
        im.thumbnail((CELL_W, CELL_H), Image.Resampling.LANCZOS)
        ox = x + (CELL_W - im.width) // 2
        oy = y + (CELL_H - im.height) // 2
        sheet.paste(im, (ox, oy))
    else:
        draw.rectangle([x, y, x + CELL_W, y + CELL_H], outline=(120, 60, 60))
        draw.text((x + 8, y + 8), "MISSING", fill=(220, 120, 120), font=font)
    cat = sites[sid].get("category", "")
    label = f"{i+1:02d} {sid}"
    draw.text((x + 2, y + CELL_H + 4), label, fill=(235, 235, 235), font=font)
    draw.text((x + 2, y + CELL_H + 4 + 0), label, fill=(235, 235, 235), font=font)

sheet.save(OUT)
print(f"contact sheet -> {OUT}  ({W}x{H}, {len(ids)} cells, {rows} rows)")
# 同時印出 id+category 對照供判讀
for i, sid in enumerate(ids):
    print(f"{i+1:02d} {sid} [{sites[sid].get('category','?')}]")
