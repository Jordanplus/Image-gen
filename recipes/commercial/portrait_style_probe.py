#!/usr/bin/env python3
"""立繪風格探針：同一組角色 prompt × 多種寫法 × 多顆 seed，比較模型的畫質與寫法效果。

背景（2026-09-15）：使用者看了三模型對照（outputs/commercial_ab/20260915_131202_official/quality_compare_*.jpg），
偏好 klein-4B 的寫實畫質（A），但喜歡 Z-Image base 那張低胸領口的性感感（C）。
做法：預設模型 klein-4B（Apache-2.0，可商用），只改 prompt。寫法依
The-Age-of-Exploration/tools/art-pipeline/FLUX2-KLEIN-PROMPT-LESSONS.md：
§1 服裝／身形放前面、§2 描述衣服底下的身體並避開會帶偏的名詞、§4 不寫否定句。
角色年齡設 24 歲（成年）。每種寫法 × 多顆 seed，輸出中文標籤對照表與 results.json。
個人用途（不商用）：--use personal 可用非商用授權模型（如 klein-9B）＋ --lora 外掛；
不進版控的本機寫法放同資料夾的 portrait_variants_local.py（定義 extra_variants(style, expression)），存在就自動載入。

跑（專案根目錄）：
  ~/.local/share/uv/tools/mflux/bin/python recipes/commercial/portrait_style_probe.py \
      [--use commercial|personal] [--model klein-4b|klein-9b|z-image-turbo|...] [--lora 路徑或 org/repo:檔名] \
      [--lora-scale 1.0] [--painted] [--variants 名稱,...] [--seeds 1131265990,424242] [--size 768x1152] [--dry-run]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_models as lm  # noqa: E402

MODEL = "klein-4b"
STYLE = ("Semi-realistic painted character portrait for a historical strategy game, "
         "soft cinematic key light, muted warm palette, head-and-shoulders framing, plain dark backdrop. ")
HAIR = "Her chestnut hair is pinned up at the back of the head, a few loose strands at the temples. "
IDENTITY = "A 24-year-old woman, the daughter of a sixteenth-century Lisbon chart-maker. "
FACE = "Strong level brows with a high clean arch, set well apart. "
SKIN = ("Flawless skin in one single even clean tone, a healthy warm glow, a soft matte finish, "
        "bright clear eyes with crisp catchlights, beautiful appealing features.")
EXPRESSION = ("A soft knowing half-smile, lips slightly parted, a warm confident gaze straight at the viewer, "
              "head tilted slightly. ")
LOW_NECK = ("She wears a deep green wool bodice laced at the front, cut low and square across the chest, "
            "over a white linen chemise whose gathered neckline sits low below the collarbones, "
            "showing her décolletage and the upper curve of her bust. ")
LOW_BODY = ("Under the bodice her figure is slender with a narrow cinched waist and a full bust; "
            "bare collarbones, upright posture. ")

VARIANTS = {
    "原版高領（對照）": dict(
        style=STYLE, extra="", body="Slender shoulders and an upright posture. ",
        clothing="She wears a deep green wool bodice laced at the front over a white linen chemise with a high gathered collar. "),
    "低胸方領": dict(style=STYLE, clothing=LOW_NECK, body=LOW_BODY, extra=""),
    "低胸方領＋神情": dict(style=STYLE, clothing=LOW_NECK, body=LOW_BODY, extra=EXPRESSION),
    "露肩＋低胸＋柔光": dict(
        style=STYLE.replace("soft cinematic key light", "warm soft window light grazing her bare shoulders"),
        clothing=("She wears a white linen chemise slipping off both shoulders, with a deep green wool bodice laced "
                  "at the front cut low across the chest, showing her décolletage and the upper curve of her bust. "),
        body="Bare smooth shoulders and collarbones, a narrow cinched waist and a full bust. ",
        extra=EXPRESSION),
}

# 不進版控的本機寫法（repo 是公開的）：接在上面四種之後，輸出檔名的編號照順序往後排。
_LOCAL_VARIANTS = Path(__file__).with_name("portrait_variants_local.py")
if _LOCAL_VARIANTS.exists():
    import importlib.util
    _spec = importlib.util.spec_from_file_location("portrait_variants_local", _LOCAL_VARIANTS)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    VARIANTS.update(_mod.extra_variants(style=STYLE, expression=EXPRESSION))


# 寫實照片風（預設）：klein-4B 會把 painted 直接畫成照片，但 klein-9B、Qwen 等較照字面的模型會真的畫成繪畫。
# 使用者 2026-09-15：「不要繪畫風格，都測寫實的」→ 預設一律照片風（也拿掉會帶出遊戲 CG 感的 for a game），--painted 才用原句。
PHOTO_STYLE = ("Semi-realistic painted character portrait for a historical strategy game",
               "Photorealistic portrait photograph, natural skin texture")
QUALITY_NEGATIVE = "blurry, low quality, deformed face, deformed hands, extra fingers, watermark, text"
PAINT_NEGATIVE = "painting, oil painting, illustration, drawing, cartoon, anime, 3d render, cgi, plastic skin"


def build_prompt(v, photo=False):
    # LESSONS §1 的段落順序：風格 → 服裝 → 髮型 → 身形 → 身分 → 臉 → 神情 → 膚質
    style = v["style"].replace(*PHOTO_STYLE) if photo else v["style"]
    return style + v["clothing"] + HAIR + v["body"] + IDENTITY + FACE + v["extra"] + SKIN


def negative_for(key, photo):
    """只有非蒸餾模型吃負面提示詞；照片風再加推離繪畫感的詞（同 2026-06 Qwen 場景圖 recipes 的做法）。"""
    if lm.MODELS[key]["distilled"]:
        return None
    return f"{PAINT_NEGATIVE}, {QUALITY_NEGATIVE}" if photo else QUALITY_NEGATIVE


def load_font(size):
    from PIL import ImageFont
    for path in ("/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/PingFang.ttc"):
        try:
            return ImageFont.truetype(path, size, index=0)
        except Exception:
            continue
    return ImageFont.load_default()


def contact_sheet(cells, names, seeds, out, thumb_w=384):
    """列＝寫法、欄＝seed；中文標籤用系統內建的冠群黑體。"""
    from PIL import Image, ImageDraw
    if not cells:
        return None
    first = Image.open(next(iter(cells.values()))["path"])
    th = int(first.height * thumb_w / first.width)
    bar = 34
    font = load_font(20)
    sheet = Image.new("RGB", (thumb_w * len(seeds), (th + bar) * len(names)), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    for r, name in enumerate(names):
        for c, seed in enumerate(seeds):
            x, y = c * thumb_w, r * (th + bar)
            cell = cells.get((name, seed))
            label = f"{name} · seed {seed}"
            if not cell:
                draw.text((x + 8, y + 6), label + " · 失敗", font=font, fill=(255, 120, 120))
                continue
            im = Image.open(cell["path"]).convert("RGB").resize((thumb_w, th), Image.Resampling.LANCZOS)
            sheet.paste(im, (x, y + bar))
            size = 20  # 標籤太長會疊到隔壁格：縮字直到放得下
            while size > 12 and draw.textlength(label, font=load_font(size)) > thumb_w - 16:
                size -= 1
            draw.text((x + 8, y + 6), label, font=load_font(size), fill=(240, 240, 240))
    sheet.save(out, quality=92)
    return out


def resolve_lora(spec):
    """org/repo:檔名 → HF 快取裡的本機路徑。直接把 org/repo:檔名 交給 mflux，它會另外下載一份到自己的快取（2026-09-15 實測）。"""
    if not spec or ":" not in spec or Path(spec).expanduser().exists():
        return spec
    repo, filename = spec.split(":", 1)
    lm._ensure_hf_env()
    from huggingface_hub import hf_hub_download
    return hf_hub_download(repo_id=repo, filename=filename)


def main():
    ap = argparse.ArgumentParser(description="立繪風格探針（畫質＋寫法對照）")
    ap.add_argument("--seeds", default="1131265990,424242")
    ap.add_argument("--size", default="768x1152", help="寬x高，需為 16 的倍數")
    ap.add_argument("--variants", default=None, help="只跑部分寫法，逗號分隔（預設全部）")
    ap.add_argument("--use", default="commercial", choices=lm.USES,
                    help="commercial＝只准可商用授權；personal＝自用，非商用授權也可以")
    ap.add_argument("--model", default=MODEL,
                    choices=[k for k, m in lm.MODELS.items() if m["kind"] in ("flux2", "z_image", "qwen")])
    ap.add_argument("--lora", default=None, help="LoRA／LoKr：本機檔案，或 HF 的 org/repo:檔名.safetensors")
    ap.add_argument("--lora-scale", type=float, default=1.0)
    ap.add_argument("--painted", action="store_true",
                    help="改用原本的繪畫風格句（預設是寫實照片風，非蒸餾模型另加推離繪畫感的負面提示詞）")
    ap.add_argument("--photo-style", action="store_true", help=argparse.SUPPRESS)  # 舊參數：現在預設就是照片風
    ap.add_argument("--low-ram", action="store_true",
                    help="MLX 快取上限 1GB＋VAE 分塊解碼（24GB 機器跑大模型用）")
    ap.add_argument("--dry-run", action="store_true", help="只印計畫與 prompt，不載模型")
    a = ap.parse_args()

    key = a.model
    photo = not a.painted
    lm.require(key, a.use)
    seeds = [int(s) for s in a.seeds.split(",")]
    width, height = (int(v) for v in a.size.lower().split("x"))
    if width % 16 or height % 16:
        raise SystemExit(f"✗ 尺寸需為 16 的倍數：{a.size}")
    names = [n.strip() for n in a.variants.split(",")] if a.variants else list(VARIANTS)
    unknown = [n for n in names if n not in VARIANTS]
    if unknown:
        raise SystemExit(f"✗ 未知寫法 {unknown}；可用：{list(VARIANTS)}")

    lora_tag = f"_{re.sub(r'[^A-Za-z0-9._-]+', '-', Path(a.lora.split(':')[-1]).stem)}" if a.lora else ""
    out = Path(f"outputs/{a.use}_style/{time.strftime('%Y%m%d_%H%M%S')}_{key}{lora_tag}")
    neg = negative_for(key, photo)
    d = lm.MODELS[key]["defaults"]
    print(f"== {key}（{lm.MODELS[key]['license']}）· 用途 {a.use} · {len(names)} 種寫法 × {len(seeds)} 顆 seed = "
          f"{len(names) * len(seeds)} 張 · {width}x{height} · steps {d.get('steps')} · guidance {d.get('guidance')} · "
          f"{'照片風' if photo else '原風格句'}")
    print(f"== LoRA：{f'{a.lora}（強度 {a.lora_scale}）' if a.lora else '無'}")
    print(f"== 負面提示詞：{neg or '（蒸餾模型不吃）'}")
    for n in names:
        print(f"-- {n}：{build_prompt(VARIANTS[n], photo)}")
    if a.dry_run:
        return

    t0 = time.time()
    lora_path = resolve_lora(a.lora)
    if lora_path:
        print(f"== LoRA 本機路徑：{lora_path}", flush=True)
    model = lm.load(key, a.use, low_ram=a.low_ram, lora_paths=[lora_path] if lora_path else None,
                    lora_scales=[a.lora_scale] if lora_path else None)
    results, cells = [], {}
    for n in names:
        prompt = build_prompt(VARIANTS[n], photo)
        for seed in seeds:
            t1 = time.time()
            rec = dict(**lm.license_record(key), use=a.use, lora=a.lora, lora_scale=a.lora_scale if a.lora else None,
                       photo_style=photo, variant=n, seed=seed, width=width, height=height, prompt=prompt,
                       negative_prompt=neg, steps=d.get("steps"), guidance=d.get("guidance"))
            try:
                img = lm.generate(model, key, prompt=prompt, seed=seed, width=width, height=height,
                                  negative_prompt=neg)
                path = lm.save(img, out / f"{list(VARIANTS).index(n)}_{seed}.png")
                rec.update(ok=True, path=str(path), seconds=round(time.time() - t1, 1))
                cells[(n, seed)] = rec
                print(f"   ✓ {n} seed {seed}：{rec['seconds']:.0f}s → {path}", flush=True)
            except Exception as ex:  # noqa: BLE001
                rec.update(ok=False, error=repr(ex)[:300], seconds=round(time.time() - t1, 1))
                print(f"   ✗ {n} seed {seed}：{rec['error']}", flush=True)
            results.append(rec)
            lm.free()
    model = None
    lm.free()
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    sheet = contact_sheet(cells, names, seeds, out / "contact.jpg")
    print(f"\n== 完成 {(time.time() - t0) / 60:.0f} 分鐘 · 對照表 {sheet} · 紀錄 {out / 'results.json'}")


if __name__ == "__main__":
    main()
