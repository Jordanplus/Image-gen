#!/usr/bin/env python3
"""A/B 對照：同一個 prompt 同時用兩個後端生圖，並排輸出一張對照圖，
用「你自己的 prompt」做真實評測（勝過看 benchmark 跑分）。

預設 A=gemini（nano-banana）、B=openai（gpt-image-2），**兩邊都經 apipass.dev**
（單一把 APIPASS_API_KEY，來自 /Users/mcgradymac/claude_prjs/apipass.env，import generate_image 時自動載入）。

用法（在 cloud/ 下）：
  python ab_compare.py -p "<prompt>" [-m ultra] [-q 4K] [-a 16:9] [-o ab_out]
  python ab_compare.py -p "..." --backend-a gemini --backend-b openai
  # 想直連官方：--backend-a gemini-direct（需 GEMINI_API_KEY）等

缺對應金鑰的那一邊會被略過（只跑有 key 的那邊，不產生並排圖）。
輸出（預設 ./ab_out/）：A_<backend>.png  B_<backend>.png  AB_compare.png
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

import generate_image as gi  # import 時會自動載入 apipass.env

# macOS 內建字型；找不到則退回 PIL 預設點陣字
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

# 各後端需要的金鑰環境變數（任一存在即可）
_KEY_FOR = {
    "gemini": ("APIPASS_API_KEY", "APIPASS_KEY"),
    "openai": ("APIPASS_API_KEY", "APIPASS_KEY"),
    "apipass": ("APIPASS_API_KEY", "APIPASS_KEY"),
    "gemini-direct": ("GEMINI_API_KEY",),
    "openai-direct": ("OPENAI_API_KEY",),
}
_LABEL = {
    "gemini": "Gemini Nano Banana (apipass)",
    "openai": "GPT-image-2 (apipass)",
    "apipass": "apipass",
    "gemini-direct": "Gemini Nano Banana (direct)",
    "openai-direct": "GPT-image-2 (direct)",
}


def _have_key(backend):
    return any(os.environ.get(k) for k in _KEY_FOR.get(backend, ()))


def _load_font(size: int):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _labeled(img: Image.Image, text: str) -> Image.Image:
    """在圖上方加一條深色標題列。"""
    bar_h = max(28, img.width // 22)
    canvas = Image.new("RGB", (img.width, img.height + bar_h), (22, 22, 22))
    canvas.paste(img, (0, bar_h))
    draw = ImageDraw.Draw(canvas)
    font = _load_font(int(bar_h * 0.6))
    draw.text((10, int(bar_h * 0.18)), text, fill=(240, 240, 240), font=font)
    return canvas


def _run(side, backend, prompt, out_path, args, apipass_model):
    label = _LABEL.get(backend, backend)
    print(f"\n==================== 後端 {side}：{label} ====================")
    if not _have_key(backend):
        need = " 或 ".join(_KEY_FOR.get(backend, ("?",)))
        print(f"⏭️ 略過：未設定 {need}")
        return None
    return gi.generate_image(prompt, out_path, args.model, None, args.seed, args.ref,
                             args.resolution, args.aspect, backend=backend, apipass_model=apipass_model)


def main():
    backends = ["gemini", "openai", "apipass", "gemini-direct", "openai-direct"]
    ap = argparse.ArgumentParser(description="兩後端 A/B 對照（預設 gemini vs openai，皆經 apipass.dev）")
    ap.add_argument("-p", "--prompt", required=True, help="兩邊共用的提示詞")
    ap.add_argument("-o", "--outdir", default="ab_out", help="輸出資料夾（預設 ./ab_out）")
    ap.add_argument("--backend-a", choices=backends, default="gemini")
    ap.add_argument("--backend-b", choices=backends, default="openai")
    ap.add_argument("--apipass-model-a", default=None, help="backend=apipass 時 A 側的 model id")
    ap.add_argument("--apipass-model-b", default=None, help="backend=apipass 時 B 側的 model id")
    ap.add_argument("-m", "--model", choices=["standard", "ultra", "fast"], default="ultra")
    ap.add_argument("-q", "--resolution", choices=["1K", "2K", "4K"], default=None)
    ap.add_argument("-a", "--aspect", choices=["1:1", "16:9", "9:16", "4:3", "3:4"], default=None)
    ap.add_argument("-r", "--ref", nargs="+", default=None, help="參考圖（僅 *-direct 後端支援）")
    ap.add_argument("-s", "--seed", type=int, default=None, help="seed（僅 *-direct gemini 生效）")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    a_path = os.path.join(args.outdir, f"A_{args.backend_a.replace('-', '_')}.png")
    b_path = os.path.join(args.outdir, f"B_{args.backend_b.replace('-', '_')}.png")

    a_ok = _run("A", args.backend_a, args.prompt, a_path, args, args.apipass_model_a)
    b_ok = _run("B", args.backend_b, args.prompt, b_path, args, args.apipass_model_b)

    # 組並排對照圖
    panels = []
    if a_ok:
        panels.append(_labeled(Image.open(a_path).convert("RGB"), f"A · {_LABEL.get(args.backend_a)}"))
    if b_ok:
        panels.append(_labeled(Image.open(b_path).convert("RGB"), f"B · {_LABEL.get(args.backend_b)}"))

    print("\n========================================================================")
    if len(panels) == 2:
        h = min(p.height for p in panels)
        panels = [p.resize((max(1, int(p.width * h / p.height)), h)) for p in panels]
        gap = 16
        combo = Image.new("RGB", (sum(p.width for p in panels) + gap, h), (10, 10, 10))
        x = 0
        for p in panels:
            combo.paste(p, (x, 0))
            x += p.width + gap
        combo_path = os.path.join(args.outdir, "AB_compare.png")
        combo.save(combo_path)
        print(f"🆚 對照圖已輸出：{combo_path}")
        print(f"   單張：{a_path} / {b_path}")
    elif len(panels) == 1:
        print(f"ℹ️ 只有一個後端成功，未產生並排對照圖。單張：{a_path if a_ok else b_path}")
    else:
        print("❌ 兩個後端都沒有成功（檢查 APIPASS_API_KEY / 額度 / prompt）。")


if __name__ == "__main__":
    main()
