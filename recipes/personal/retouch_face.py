#!/usr/bin/env python3
"""個人組 · 真實照片臉部瑕疵精修（不商用）：只修臉部皮膚，照片其他部分保持原解析度、完全不動。

流程：OpenCV 找臉 → 以臉為中心裁正方形 → klein 參考圖編輯「只去掉痘痘／斑點，其他不變」
      → 裁切框比編輯尺寸大很多時用 SeedVR2 放大回去（高解析照片的臉才不會比周圍糊）
      → 對齊整體色調 → 用羽化橢圓遮罩貼回原圖（頭髮、背景、衣服不受影響）。
預設 klein-9B（FLUX Non-Commercial License，只限個人用途）；--model klein-4b 較快（Apache-2.0）。

跑（專案根目錄）：
  ~/.local/share/uv/tools/mflux/bin/python recipes/personal/retouch_face.py photo.jpg \
      [-o out.jpg] [--model klein-9b|klein-4b] [--box x,y,w,h] [--seed 0] [--dry-run]
輸出預設在 outputs/personal_retouch/：<檔名>_retouched.<副檔名> 與 <檔名>_compare.jpg（修前／修後臉部並排）。
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_models as lm  # noqa: E402

PROMPT = ("Retouch this portrait photo. Remove only the acne, pimples, blemishes and dark spots from the "
          "facial skin while keeping natural skin texture. Keep everything else exactly the same: the same "
          "person and identity, facial features, expression, eyes, eyebrows, hair, makeup, lighting, colors "
          "and framing.")
EDIT_SIZE = 1024

# OpenCV 官方 YuNet 人臉偵測模型（約 0.23MB）；雜湊於 2026-09-15 下載時記錄，不符就刪檔中止。
YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
YUNET_PATH = Path.home() / ".cache" / "image-gen" / "face_detection_yunet_2023mar.onnx"


def _yunet_model():
    import hashlib
    import urllib.request
    if not YUNET_PATH.is_file():
        YUNET_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(YUNET_URL, YUNET_PATH)
    digest = hashlib.sha256(YUNET_PATH.read_bytes()).hexdigest()
    if digest != YUNET_SHA256:
        YUNET_PATH.unlink()
        raise SystemExit(f"✗ YuNet 模型檔雜湊不符（{digest[:16]}…），已刪除；請確認下載來源")
    return str(YUNET_PATH)


def detect_face(img):
    """回傳最大的一張臉 (x, y, w, h)；找不到回 None。

    先用 OpenCV 內建的正面 Haar（修圖遮罩比例依它校正）；找不到時改用 YuNet。
    2026-09-15 真實照片實測：四分之三側臉、半邊臉 Haar（含側臉 Haar）都漏掉，YuNet 三張都抓到（信心 0.87–0.89）。
    YuNet 的框比 Haar 高瘦，非正面照修圖前建議先 --dry-run 看遮罩。
    """
    import cv2
    import numpy as np
    rgb = img.convert("RGB")
    gray = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2GRAY)
    min_side = max(48, min(img.size) // 12)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(min_side, min_side))
    if len(faces):
        return tuple(int(v) for v in max(faces, key=lambda f: f[2] * f[3]))

    W, H = img.size
    s = min(1.0, 1024 / max(W, H))  # 大圖先縮到長邊 1024 再偵測，框再換回原圖座標
    small = cv2.cvtColor(np.array(rgb.resize((round(W * s), round(H * s)))), cv2.COLOR_RGB2BGR)
    detector = cv2.FaceDetectorYN.create(_yunet_model(), "", (small.shape[1], small.shape[0]), 0.6, 0.3, 5000)
    _, found = detector.detect(small)
    if found is None or len(found) == 0:
        return None
    x, y, w, h = max(found, key=lambda r: r[2] * r[3])[:4]
    return tuple(int(v / s) for v in (max(0.0, x), max(0.0, y), w, h))


def square_crop_box(face, size, margin=1.8):
    """以臉為中心、邊長為臉的 margin 倍的正方形，超出邊界時往內推。"""
    x, y, w, h = face
    W, H = size
    side = min(int(max(w, h) * margin), W, H)
    cx, cy = x + w // 2, y + h // 2
    left = min(max(cx - side // 2, 0), W - side)
    top = min(max(cy - side // 2, 0), H - side)
    return left, top, left + side, top + side


def match_color(edited, reference):
    """把編輯結果的整體平均色與對比拉回原圖，避免貼回去出現色差接縫。"""
    import numpy as np
    from PIL import Image
    e = np.asarray(edited.convert("RGB"), dtype=np.float32)
    r = np.asarray(reference.convert("RGB"), dtype=np.float32)
    out = (e - e.mean((0, 1))) / (e.std((0, 1)) + 1e-6) * r.std((0, 1)) + r.mean((0, 1))
    return Image.fromarray(out.clip(0, 255).astype("uint8"))


def upscale_seedvr2(img, target_side, tmp_path, softness=0.0):
    """用 SeedVR2 把修好的臉放大回裁切框大小；超過 1536px 的部分交給 LANCZOS。
    1536 是 24GB 機器實測可跑的上限（1024→1536 峰值 18GB）；更大會被系統因記憶體不足砍掉。"""
    img.save(tmp_path)
    side = min(target_side, 1536)
    t0 = time.time()
    model = lm.load("seedvr2-3b", "personal", quantize=None, low_ram=True, single_run=True)
    out = lm.to_pil(model.generate_image(seed=0, image_path=str(tmp_path), resolution=side,
                                         softness=softness)).convert("RGB")
    model = None
    lm.free()
    print(f"== SeedVR2 放大回 {out.size[0]}x{out.size[1]}：{time.time() - t0:.0f}s", flush=True)
    return out


def face_mask(crop_box, face, feather_ratio=0.08):
    """裁切框內、蓋住臉部皮膚的羽化橢圓（白＝用修過的、黑＝保留原圖）。

    比例依真實近距離自拍校正（2026-09-15）：Haar 臉框會涵蓋兩耳，舊的 0.50×0.62 會蓋到耳朵、頭髮、脖子；
    改成寬 0.42、高 0.50、中心下移 0.04，範圍約從額頭到下巴、兩頰之間。
    """
    from PIL import Image, ImageDraw, ImageFilter
    left, top, right, bottom = crop_box
    x, y, w, h = face
    cx, cy = x + w / 2 - left, y + h / 2 - top + h * 0.04
    rx, ry = w * 0.42, h * 0.50
    mask = Image.new("L", (right - left, bottom - top), 0)
    ImageDraw.Draw(mask).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(max(6, w * feather_ratio)))


def main():
    ap = argparse.ArgumentParser(description="真實照片臉部瑕疵精修（個人用途）")
    ap.add_argument("photo")
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--model", default="klein-9b", choices=["klein-9b", "klein-4b"])
    ap.add_argument("--box", default=None, help="偵測不到臉時手動給臉的位置 x,y,w,h（原圖像素）")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--edit-size", type=int, default=EDIT_SIZE,
                    help="編輯時的臉部尺寸（16 的倍數）；24GB 機器跑 klein-9B 記憶體不夠時改 768")
    # 預設 0.7：2026-09-15 真實照片模擬 0.5／0.7／1.0，0.7 斑點大致消失、皮膚仍自然；1.0 皮膚被磨平。
    ap.add_argument("--strength", type=float, default=0.7,
                    help="修圖強度 0–1（預設 0.7）：1＝完全用修過的臉，會比較像磨皮；0.5 斑點只淡化")
    ap.add_argument("--softness", type=float, default=0.0,
                    help="SeedVR2 柔化 0–1；放大後皮膚紋理太規則、像刻出來時調到 0.3–0.5")
    ap.add_argument("--hires", default="auto", choices=["auto", "off"],
                    help="auto：裁切框大於編輯尺寸 1.15 倍時用 SeedVR2 放大回去；off：直接 LANCZOS 拉伸")
    ap.add_argument("--dry-run", action="store_true", help="只偵測臉、輸出裁切與遮罩，不載模型")
    a = ap.parse_args()

    from PIL import Image, ImageOps
    lm.require(a.model, "personal")
    if a.edit_size % 16:
        raise SystemExit(f"✗ --edit-size 需為 16 的倍數：{a.edit_size}")
    if not (0.0 <= a.strength <= 1.0 and 0.0 <= a.softness <= 1.0):
        raise SystemExit("✗ --strength 與 --softness 都要在 0–1 之間")
    src = Path(a.photo)
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    face = tuple(int(v) for v in a.box.split(",")) if a.box else detect_face(img)
    if not face:
        raise SystemExit("✗ 找不到臉；請用 --box x,y,w,h 手動指定臉的位置")
    box = square_crop_box(face, img.size)
    out_dir = Path("outputs/personal_retouch")
    out_dir.mkdir(parents=True, exist_ok=True)
    crop = img.crop(box)
    crop_path = out_dir / f"{src.stem}_crop.png"
    crop.resize((a.edit_size, a.edit_size), Image.Resampling.LANCZOS).save(crop_path)
    mask = face_mask(box, face)
    print(f"== 原圖 {img.size[0]}x{img.size[1]}；臉 {face}；裁切 {box}；模型 {a.model}（{lm.MODELS[a.model]['license']}）")
    if a.dry_run:
        mask.save(out_dir / f"{src.stem}_mask.png")
        print(f"   乾跑：裁切 {crop_path}、遮罩 {out_dir / (src.stem + '_mask.png')}")
        return

    t0 = time.time()
    model = lm.load(a.model, "personal", edit=True, low_ram=True, single_run=True)
    print(f"== 載入 {time.time() - t0:.0f}s；編輯尺寸 {a.edit_size}", flush=True)
    t1 = time.time()
    result = lm.generate(model, a.model, prompt=PROMPT, seed=a.seed, width=a.edit_size, height=a.edit_size,
                         image_paths=[crop_path])
    model = None
    lm.free()
    edited = lm.to_pil(result).convert("RGB")
    if a.hires == "auto" and crop.width > a.edit_size * 1.15:
        edited = upscale_seedvr2(edited, crop.width, out_dir / f"{src.stem}_edit_{a.edit_size}.png",
                                 softness=a.softness)
    edited = match_color(edited.resize(crop.size, Image.Resampling.LANCZOS), crop)
    edited.save(out_dir / f"{src.stem}_edited_crop.png")  # 保留修好的臉部裁切：之後調 --strength 可直接重貼，不必重跑模型
    if a.strength < 1.0:
        mask = mask.point(lambda v: int(v * a.strength))
    blended = Image.composite(edited, crop, mask)
    final = img.copy()
    final.paste(blended, box[:2])

    # 預設存 PNG：原圖多為 JPEG，再存一次 JPEG 會讓臉以外的像素也被重新壓縮（2026-09-15 實測框外平均差 1.73、最大 12）。
    out = Path(a.output) if a.output else out_dir / f"{src.stem}_retouched.png"
    if out.suffix.lower() in (".jpg", ".jpeg"):
        print("ℹ️ 輸出指定為 JPEG：臉以外的區域會被重新壓縮，要完全保留原像素請改用 .png", flush=True)
        final.save(out, quality=95)
    else:
        final.save(out)
    compare = Image.new("RGB", (crop.width * 2, crop.height))
    compare.paste(crop, (0, 0))
    compare.paste(blended, (crop.width, 0))
    compare.thumbnail((1600, 800))
    compare.save(out_dir / f"{src.stem}_compare.jpg", quality=92)
    print(f"✓ 生成 {time.time() - t1:.0f}s → {out}（並排對照 {out_dir / (src.stem + '_compare.jpg')}）")


if __name__ == "__main__":
    main()
