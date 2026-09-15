#!/usr/bin/env python3
"""依用途預抓並驗證本地模型（兩台 Mac 通用）：每個模型載入後生一張小圖（SeedVR2 則放大一張），確認真的能用。

用途組（清單與授權見 local_models.py）：
  commercial：klein-4b、klein-base-4b、z-image、seedvr2-3b（全部可商用）
  personal  ：klein-9b、klein-4b、seedvr2-3b（klein-9b 為非商用授權，需 HF 金鑰且已在網頁同意授權）

跑（專案根目錄）：
  ~/.local/share/uv/tools/mflux/bin/python recipes/prefetch_models.py --set commercial|personal|all [--dry-run]
下載走 HTTPS（HF_HUB_DISABLE_XET=1）；金鑰讀 HF_TOKEN 或 HF_TOKEN_FILE（預設 ~/claude_prjs/Higgingface.env）。
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_models as lm  # noqa: E402

SETS = {
    # 2026-09-16 依使用者要求精簡：z-image 系列與 klein-base-4b 都太慢、立繪不採用，本機權重已刪，也不再預抓。
    "commercial": ["klein-4b", "seedvr2-3b"],
    "personal": ["klein-9b", "klein-4b", "seedvr2-3b"],
}
OUT = Path("outputs/prefetch_check")


def smoke(key, use):
    m = lm.MODELS[key]
    t0 = time.time()
    model = lm.load(key, use, quantize=None if m["kind"] == "seedvr2" else 4, single_run=True)
    load_s = time.time() - t0
    if m["kind"] == "seedvr2":
        from PIL import Image
        src = OUT / "seedvr2_input.png"
        OUT.mkdir(parents=True, exist_ok=True)
        Image.radial_gradient("L").convert("RGB").resize((256, 256)).save(src)
        img = model.generate_image(seed=1, image_path=str(src), resolution=512)
    else:
        img = lm.generate(model, key, prompt="a lighthouse on a rocky coast at sunset, photorealistic",
                          seed=1, width=512, height=512, steps=2)
    path = lm.save(img, OUT / f"{key}.png")
    model = None
    lm.free()
    return load_s, time.time() - t0 - load_s, path


def main():
    ap = argparse.ArgumentParser(description="依用途預抓並驗證本地模型")
    ap.add_argument("--set", required=True, choices=["commercial", "personal", "all"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    uses = ["commercial", "personal"] if a.set == "all" else [a.set]
    plan = []
    for use in uses:
        for key in SETS[use]:
            if key not in [k for k, _ in plan]:
                lm.require(key, use)
                plan.append((key, use))
    for key, use in plan:
        m = lm.MODELS[key]
        print(f"   [{use}] {key:<14} {m['license']:<34} {m['repo']}")
    if a.dry_run:
        return
    failed = []
    for key, use in plan:
        print(f"== {key}", flush=True)
        try:
            load_s, gen_s, path = smoke(key, use)
            print(f"   ✓ 載入 {load_s:.0f}s（首次含下載）/ 測試 {gen_s:.0f}s → {path}", flush=True)
        except BaseException as ex:  # noqa: BLE001 — SystemExit 也要記下來繼續下一個
            failed.append(key)
            print(f"   ✗ {key}：{repr(ex)[:300]}", flush=True)
    print(f"== 完成：{len(plan) - len(failed)}/{len(plan)} 可用" + (f"；失敗 {failed}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
