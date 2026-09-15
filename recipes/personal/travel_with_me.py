#!/usr/bin/env python3
"""個人組 · 把自己放進旅遊場景（不商用）：用你的 1–3 張臉部照片當參考，klein 多參考圖編輯生成。

預設 klein-9B（FLUX Non-Commercial License，只限個人用途）；--model klein-4b 較快（Apache-2.0）。
一次抽多顆 seed 再挑臉最像的一張（同 LESSONS §3：長相與年紀感受 seed 影響很大）。

跑（專案根目錄）：
  ~/.local/share/uv/tools/mflux/bin/python recipes/personal/travel_with_me.py \
      --refs me1.jpg me2.jpg --scene "standing on the Charles Bridge in Prague at sunrise, river behind" \
      [--size 832x1216] [--seeds 2] [--model klein-9b|klein-4b] [--dry-run]
輸出在 outputs/personal_travel/<時間>/。
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_models as lm  # noqa: E402


def prepare_refs(refs, out_dir, size=768, face_crop=True):
    """參考照片先裁出臉部並縮到 size×size。

    手機原圖（如 1836×4080）大多是背景和衣服，整張當參考 mflux 會以約 1MP 編碼，每一步多算上千個 token，
    klein-9B 在 24GB 機器容易被系統砍掉；裁臉後長相資訊保留、負擔約減到六成。找不到臉就整張等比縮圖。
    """
    import retouch_face as rf
    from PIL import Image, ImageOps
    out_dir.mkdir(parents=True, exist_ok=True)
    prepared = []
    for i, p in enumerate(refs, 1):
        img = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
        face = rf.detect_face(img) if face_crop else None
        if face:
            img = img.crop(rf.square_crop_box(face, img.size, margin=1.5)).resize((size, size), Image.Resampling.LANCZOS)
            note = f"裁臉 {face}"
        else:
            img.thumbnail((size, size))
            note = "找不到臉，整張縮圖" if face_crop else "整張縮圖"
        dst = out_dir / f"ref{i}_{Path(p).stem}.jpg"
        img.save(dst, quality=95)
        print(f"   參考 {i}：{p} → {dst}（{note}）")
        prepared.append(dst)
    return prepared


def build_prompt(scene, n_refs):
    refs = "image 1" if n_refs == 1 else "images " + ", ".join(str(i) for i in range(1, n_refs)) + f" and {n_refs}"
    return (f"A photorealistic travel photo of the person shown in {refs}. Scene: {scene}. "
            "Keep the person's face, identity, facial features, skin tone, age and hairstyle identical to the "
            "reference photos. Natural candid pose, real camera photo, natural light, sharp focus on the face.")


def main():
    ap = argparse.ArgumentParser(description="把自己放進旅遊場景（個人用途）")
    ap.add_argument("--refs", nargs="+", required=True, help="你的臉部照片 1–3 張（正面、清楚）")
    ap.add_argument("--scene", required=True, help="英文場景描述")
    ap.add_argument("--size", default="832x1216", help="寬x高，需為 16 的倍數")
    ap.add_argument("--seeds", type=int, default=2, help="抽幾顆 seed")
    ap.add_argument("--seed-start", type=int, default=1)
    ap.add_argument("--model", default="klein-9b", choices=["klein-9b", "klein-4b"])
    ap.add_argument("--ref-size", type=int, default=768, help="參考照片裁臉後的邊長")
    ap.add_argument("--no-face-crop", action="store_true", help="不裁臉，整張等比縮到 --ref-size")
    ap.add_argument("--dry-run", action="store_true", help="只準備參考圖、印 prompt，不載模型")
    a = ap.parse_args()

    lm.require(a.model, "personal")
    refs = [Path(p) for p in a.refs]
    missing = [str(p) for p in refs if not p.is_file()]
    if missing:
        raise SystemExit(f"✗ 找不到參考照片：{missing}")
    if not 1 <= len(refs) <= 3:
        raise SystemExit("✗ 參考照片請給 1–3 張")
    width, height = (int(v) for v in a.size.lower().split("x"))
    if width % 16 or height % 16:
        raise SystemExit(f"✗ 尺寸需為 16 的倍數：{a.size}")
    prompt = build_prompt(a.scene, len(refs))
    out = Path(f"outputs/personal_travel/{time.strftime('%Y%m%d_%H%M%S')}")
    print(f"== {a.model}（{lm.MODELS[a.model]['license']}）· {len(refs)} 張參考 · {a.seeds} 顆 seed · {width}x{height}")
    refs = prepare_refs(refs, out, size=a.ref_size, face_crop=not a.no_face_crop)
    print(f"== prompt：{prompt}")
    if a.dry_run:
        return

    t0 = time.time()
    model = lm.load(a.model, "personal", edit=True, low_ram=True, single_run=(a.seeds == 1))
    print(f"== 載入 {time.time() - t0:.0f}s", flush=True)
    for seed in range(a.seed_start, a.seed_start + a.seeds):
        t1 = time.time()
        img = lm.generate(model, a.model, prompt=prompt, seed=seed, width=width, height=height, image_paths=refs)
        path = lm.save(img, out / f"travel_seed{seed}.png")
        print(f"   ✓ seed {seed}：{time.time() - t1:.0f}s → {path}", flush=True)
        lm.free()
    model = None
    lm.free()
    print(f"== 完成 {(time.time() - t0) / 60:.1f} 分鐘 · {out}")


if __name__ == "__main__":
    main()
