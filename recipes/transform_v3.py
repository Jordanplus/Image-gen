#!/usr/bin/env python3
"""oil -> PHOTO 轉換 v3 (依 55 條稽核結果強化):
- 解包 5 條 malformed(prompt 是 JSON dump)取內層真 prompt
- 清場景段殘留 god-rays/volumetric/lapis/mood 詞
- 場景分類 -> 風景/野生動物/水下 攝影 block;夜景/陰天降 HDR
- 開頭加強攝影框 + 強化 negative
輸出到 scratch 供驗證,不直接改真檔."""
import json, re
from pathlib import Path

SRC = Path("/Users/mcgrady/claude/The-Age-of-Exploration-/assets/data/exploration/site_art_prompts.json")
DST = Path("/private/tmp/claude-501/-Users-mcgrady-claude-The-Age-of-Exploration-/f3118cfb-9774-4f57-93a0-ab52fe5e00ab/scratchpad/site_art_prompts.photo4.json")
SPLIT = "Rendered as a grounded, photorealistic oil painting"


def get_oil(e):
    p = e["prompt"]
    if p.lstrip().startswith("{"):
        try:
            return json.loads(p).get("prompt", p)
        except Exception:
            m = re.search(r'"prompt"\s*:\s*"(.+?)"\s*,\s*"', p, re.DOTALL)
            return m.group(1).encode().decode("unicode_escape") if m else p
    return p


def scene_of(oil):
    i = oil.find(SPLIT)
    return (oil[:i] if i != -1 else oil).strip()


REPL = [
    (r"in weighty volumetric god-rays", "in soft shafts of natural light"),
    (r"weighty volumetric god-rays", "soft shafts of natural light"),
    (r"weighty warm-gold volumetric shafts", "warm-gold shafts of light"),
    (r"weighty volumetric shafts", "soft shafts of light"),
    (r"in weighty god-rays", "in shafts of light"),
    (r"volumetric god-rays", "shafts of light"),
    (r"volumetric shafts", "shafts of light"),
    (r"weighty god-rays", "shafts of light"),
    (r"soft god-rays", "shafts of low sunlight"),
    (r"warm god-rays", "warm directional sunlight"),
    (r"god-rays", "shafts of light"),
    (r"god rays", "shafts of light"),
    (r"deep lapis-tinged blue", "deep ocean-blue"),
    (r"lapis-tinged", "ocean-blue"),
    (r"lapis ocean-blue", "deep ocean-blue"),
    (r"lapis sky-blue", "deep sky-blue"),
    (r"muted lapis sea", "muted deep-blue sea"),
    (r"real lapis ocean", "real deep-blue ocean"),
    (r"clear lapis-blue", "clear deep-blue"),
    (r"lapis-blue", "deep blue"),
    (r"lapis blue", "deep blue"),
    (r"lapis ", "deep-blue "),
    (r"\s*Mythic, melancholic, the silence of a lost city\.", ""),
    (r",?\s*the legend half-real in distance", ""),
    (r"half-shadowed and contemplative", "in shadow"),
    (r"half-shadowed", "shaded"),
    (r"weathered with the weight of time,?\s*", "weathered "),
    (r"faintly wary of the unknown", ""),
    (r",?\s*hushed and sacred", ""),
    (r"hushed and wary", "quiet"),
    (r"\bhushed,\s*", ""),
    (r",?\s*\bhushed\b", ""),
    (r"\bcontemplative\b", ""),
    (r"biblical stillness", "stillness"),
    (r"mythic stillness", "stillness"),
]


def clean(s):
    for pat, rep in REPL:
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    s = re.sub(r"\s{2,}", " ", s).replace(" ,", ",").replace(" .", ".").replace(",,", ",").strip()
    return s


PHOTO_LEAD = "A photorealistic, true-to-life documentary photograph. "
# v4 硬化(canary 學習):拿掉「Age of Sail」年代觸發詞,改「現代紀實旅遊照拍下這座真實地點」
# 框架 + 具體相機痕跡(DSLR/廣角/硬光/感光顆粒),壓建築/人文場景的油畫 prior。
LANDSCAPE = (" Shot as a real, true-to-life documentary travel PHOTOGRAPH of the real site as it stands, on a "
             "full-frame DSLR with a wide lens in bright natural daylight: edge-to-edge sharp focus, fine "
             "realistic sensor detail and true weathered material texture, true-to-life natural color, real "
             "hard sun shadows, faint atmospheric haze and fine airborne dust, deep realistic depth, slight "
             "natural sensor grain, photojournalistic National Geographic travel realism. A genuine PHOTOGRAPH "
             "— absolutely NOT a painting, illustration, orientalist art, watercolour, concept art, matte "
             "painting or 3D render: no brushstrokes, no painterly texture, no canvas, no soft romantic glow.")
WILDLIFE = (" Captured as a real close-up wildlife PHOTOGRAPH on a telephoto lens: the animal in sharp crisp "
            "focus with fine fur/skin/scale detail against a softly blurred natural background, true-to-life "
            "natural light, photojournalistic wildlife realism like National Geographic. A genuine PHOTOGRAPH "
            "— absolutely NOT a painting, illustration, concept art or render: no brushstrokes, no painterly "
            "texture, no canvas.")
UNDERWATER = (" Captured as a real underwater PHOTOGRAPH: natural sunlight filtering down through clear water "
              "in soft caustic dapples, crisp realistic detail, true-to-life color, photojournalistic "
              "underwater realism. A genuine PHOTOGRAPH — absolutely NOT a painting, illustration, concept art "
              "or render: no brushstrokes, no painterly texture, no canvas.")
LOWLIGHT = (" Natural low light true to the scene's described time of day, muted dynamic range, deep natural "
            "shadows retained, no artificial brightening.")

SET_WILDLIFE = {"dodo", "madagascar_interior", "galapagos_wildlife", "galapagos_islands", "sperm_whale", "arctic_wonders"}
SET_UNDERWATER = {"great_barrier_reef", "atlantis"}
SET_LOWLIGHT = {"hudson_bay", "arctic_wonders", "norumbega", "papua_interior", "el_dorado", "north_pole", "south_pole"}


def block_for(sid):
    b = UNDERWATER if sid in SET_UNDERWATER else WILDLIFE if sid in SET_WILDLIFE else LANDSCAPE
    return b + (LOWLIGHT if sid in SET_LOWLIGHT else "")


PHOTO_NEG = ("painting, oil painting, orientalist painting, watercolour, romantic painting, illustration, "
             "drawing, sketch, brushstrokes, painterly, impasto, canvas texture, soft romantic haze, "
             "golden-hour painterly glow, concept art, matte painting, 3d render, CGI, digital art, stylized, "
             "cartoon, anime, god rays, volumetric light beams, modern elements, electric light, neon, LED, "
             "people in modern dress, modern clothing, contemporary buildings, cars, power lines, plastic, "
             "glass skyscrapers, tourists, lowres, blurry, jpeg artifacts, oversaturated, HDR halos, watermark, "
             "text, letters, signature, logo")

d = json.load(open(SRC))
unwrapped = []
for sid, e in d["sites"].items():
    oil = get_oil(e)
    if e["prompt"].lstrip().startswith("{"):
        unwrapped.append(sid)
    scene = clean(scene_of(oil))
    e["prompt"] = PHOTO_LEAD + scene + block_for(sid)
    e["negative_prompt"] = PHOTO_NEG

d["model"] = "Qwen-Image-2512 4bit — PHOTO realism v4 (canary-hardened) 2026-06-25"
d["canonical_style_suffix_v2"] = LANDSCAPE.strip()
d["shared_negative_prompt"] = PHOTO_NEG
d["_comment"] = ("Style OIL->PHOTO v4 2026-06-25 (user decision C + 55-prompt audit + arch-canary hardening): "
                 "unwrapped 5 malformed, stripped god-rays/lapis/mood, scene-type photo blocks "
                 "(landscape/wildlife/underwater); landscape/architecture block dropped 'Age of Sail' era trigger "
                 "for 'real travel photograph as it stands' + camera artifacts + orientalist/watercolour negatives "
                 "(Qwen ceiling: famous sites convert, obscure/desert/mythic stay painterly), low-light soften.")
json.dump(d, open(DST, "w"), ensure_ascii=False, indent=2)

# 報告 + 殘留檢查
print(f"v3 完成 -> {DST}")
print(f"解包 malformed: {len(unwrapped)} -> {unwrapped}")
resid_gr = [s for s, e in d["sites"].items() if re.search(r"god.?ray|volumetric", e["prompt"], re.I)]
resid_lapis = [s for s, e in d["sites"].items() if "lapis" in e["prompt"].lower()]
resid_mood = [s for s, e in d["sites"].items() if re.search(r"\bhushed\b|half-shadowed|contemplative", e["prompt"], re.I)]
still_brace = [s for s, e in d["sites"].items() if e["prompt"].lstrip().startswith("{")]
print(f"殘留 god-ray/volumetric: {len(resid_gr)} -> {resid_gr}")
print(f"殘留 lapis: {len(resid_lapis)} -> {resid_lapis}")
print(f"殘留 mood: {len(resid_mood)} -> {resid_mood}")
print(f"仍是 brace 開頭(解包失敗): {len(still_brace)} -> {still_brace}")
print(f"\n=== timbuktu v3 ===\n{d['sites']['timbuktu']['prompt'][:600]}")
print(f"\n=== galapagos_islands v3 (was malformed) ===\n{d['sites']['galapagos_islands']['prompt'][:600]}")
