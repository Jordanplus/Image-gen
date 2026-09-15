#!/usr/bin/env python3
"""商用組 · 角色立繪 A/B：蒸餾版 klein-4B（現況） vs 非蒸餾 + 負面提示詞（klein-base-4B、Z-Image base）。

要驗的三件事（The-Age-of-Exploration/tools/art-pipeline/FLUX2-KLEIN-PROMPT-LESSONS.md §3、§4）：
  ① 臉上斑點：膚質句刻意保留會召喚斑點的 `fine natural texture`，看負面提示詞壓不壓得掉
  ② 年齡數字：同 seed 只改 19 → 35，看非蒸餾模型會不會真的變老（klein-4B 實測不會）
  ③ 速度：同解析度下每張秒數
prompt 依 LESSONS §1 的段落順序重組（原始 companion prompt 存在已清掉的 scratchpad，找不回原文）。
seed 取自 generation-log.csv 的 companion_self_create_europe_f（v3）。所有模型都過商用授權把關。

跑（專案根目錄）：
  ~/.local/share/uv/tools/mflux/bin/python recipes/commercial/ab_character_cfg.py \
      [--models klein-4b,klein-base-4b,z-image] [--size 768x1152] [--ages 19,35] [--dry-run]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_models as lm  # noqa: E402

SEED = 1131265990  # generation-log.csv：companion_self_create_europe_f，portraits-v3

STYLE = ("Semi-realistic painted character portrait for a historical strategy game, "
         "soft cinematic key light, muted warm palette, head-and-shoulders framing, plain dark backdrop. ")
CLOTHING = ("She wears a deep green wool bodice laced at the front over a white linen chemise "
            "with a high gathered collar. ")
HAIR = "Her chestnut hair is pinned up at the back of the head, a few loose strands at the temples. "
BODY = "Slender shoulders and an upright posture. "
IDENTITY = "A {age}-year-old woman, the daughter of a sixteenth-century Lisbon chart-maker. "
FACE = "Strong level brows with a high clean arch, set well apart. "
# 取自 recipes/companion_skin_probe3.py 的 S3_SKIN：其中 `fine natural texture` 在 klein-4B 會召喚細小深色斑點
SKIN = ("flawless even-toned skin with fine natural texture, a healthy warm glow, "
        "clear unblemished complexion, a soft matte finish to the skin, "
        "bright clear eyes with crisp catchlights, handsome appealing features.")
NEGATIVE = ("freckles, moles, blemishes, dark spots on the face, acne, skin marks, "
            "deformed face, extra eyes, text, watermark")


def build_prompt(age):
    return STYLE + CLOTHING + HAIR + BODY + IDENTITY.format(age=age) + FACE + SKIN


def contact_sheet(cells, models, ages, out, thumb_w=360):
    """列＝模型、欄＝年齡；360px 是遊戲專案審圖用的尺度（LESSONS §6）。"""
    from PIL import Image, ImageDraw
    if not cells:
        return None
    first = Image.open(next(iter(cells.values()))["path"])
    th = int(first.height * thumb_w / first.width)
    label_h = 22
    sheet = Image.new("RGB", (thumb_w * len(ages), (th + label_h) * len(models)), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)
    for r, key in enumerate(models):
        for c, age in enumerate(ages):
            cell = cells.get((key, age))
            x, y = c * thumb_w, r * (th + label_h)
            if not cell:
                draw.text((x + 6, y + 4), f"{key} age {age}: FAILED", fill=(255, 90, 90))
                continue
            im = Image.open(cell["path"]).convert("RGB").resize((thumb_w, th), Image.Resampling.LANCZOS)
            sheet.paste(im, (x, y + label_h))
            draw.text((x + 6, y + 4), f"{key} | age {age} | {cell['seconds']:.0f}s", fill=(235, 235, 235))
    sheet.save(out)
    return out


def main():
    ap = argparse.ArgumentParser(description="商用組角色立繪 A/B（蒸餾 vs 非蒸餾＋負面提示詞）")
    ap.add_argument("--models", default="klein-4b,klein-base-4b,z-image")
    ap.add_argument("--ages", default="19,35")
    ap.add_argument("--size", default="768x1152", help="寬x高，需為 16 的倍數")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--steps", type=int, default=None, help="只套用在非蒸餾模型；預設看 local_models")
    ap.add_argument("--guidance", type=float, default=None, help="只套用在非蒸餾模型")
    ap.add_argument("--quantize", type=int, default=4, choices=[3, 4, 5, 6, 8],
                    help="量化位元數；mflux 文件的量化範例多用 8（畫質損失較少、較慢）")
    ap.add_argument("--out", default=None, help="預設 outputs/commercial_ab/<時間>")
    ap.add_argument("--dry-run", action="store_true", help="只印計畫與 prompt，不載模型")
    a = ap.parse_args()

    models = [m.strip() for m in a.models.split(",") if m.strip()]
    ages = [int(x) for x in a.ages.split(",")]
    width, height = (int(v) for v in a.size.lower().split("x"))
    if width % 16 or height % 16:
        raise SystemExit(f"✗ 尺寸需為 16 的倍數：{a.size}")
    for key in models:
        lm.require(key, "commercial")  # 非商用授權在這裡就擋掉，不會浪費時間載入

    out = Path(a.out or f"outputs/commercial_ab/{time.strftime('%Y%m%d_%H%M%S')}")
    print(f"== {len(models)} 個模型 × {len(ages)} 個年齡 = {len(models) * len(ages)} 張，{width}x{height}，"
          f"seed={a.seed}，{a.quantize}-bit，steps={a.steps or '預設'}，guidance={a.guidance or '預設'}")
    for key in models:
        m = lm.MODELS[key]
        print(f"   {key:<14} {m['license']:<11} 蒸餾={m['distilled']}  {m['note']}")
    print(f"== prompt（age={ages[0]}）：\n{build_prompt(ages[0])}\n== negative：{NEGATIVE}")
    if a.dry_run:
        return

    results, cells = [], {}
    t_all = time.time()
    for key in models:
        m = lm.MODELS[key]
        t0 = time.time()
        model = lm.load(key, "commercial", quantize=a.quantize)
        load_s = time.time() - t0
        print(f"== {key} 載入 {load_s:.0f}s", flush=True)
        for age in ages:
            t1 = time.time()
            rec = dict(**lm.license_record(key), age=age, seed=a.seed, width=width, height=height, quantize=a.quantize,
                       steps=(m["defaults"].get("steps") if m["distilled"] or a.steps is None else a.steps),
                       guidance=(m["defaults"].get("guidance") if m["distilled"] or a.guidance is None else a.guidance),
                       prompt=build_prompt(age), negative_prompt=None if m["distilled"] else NEGATIVE)
            try:
                img = lm.generate(model, key, prompt=rec["prompt"], seed=a.seed, width=width, height=height,
                                  steps=None if m["distilled"] else a.steps,
                                  guidance=None if m["distilled"] else a.guidance,
                                  negative_prompt=rec["negative_prompt"])
                path = lm.save(img, out / f"{key}__age{age}.png")
                rec.update(ok=True, path=str(path), seconds=round(time.time() - t1, 1), load_seconds=round(load_s, 1))
                cells[(key, age)] = rec
                print(f"   ✓ {key} age {age}：{rec['seconds']:.0f}s → {path}", flush=True)
            except Exception as ex:  # noqa: BLE001
                rec.update(ok=False, error=repr(ex)[:300], seconds=round(time.time() - t1, 1))
                print(f"   ✗ {key} age {age}：{rec['error']}", flush=True)
            results.append(rec)
            lm.free()
        model = None
        lm.free()

    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    sheet = contact_sheet(cells, models, ages, out / "contact_360px.png")
    print(f"\n== 完成 {(time.time() - t_all) / 60:.0f} 分鐘 · 對照表 {sheet} · 紀錄 {out / 'results.json'}")


if __name__ == "__main__":
    main()
