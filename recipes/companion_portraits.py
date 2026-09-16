#!/usr/bin/env python3
"""45 位開局同伴的立繪批次生成（FLUX.2-klein，常駐：模型載一次、迴圈跑完）。

輸入 ＝ scratchpad/companion/portraits/*.json（八桶，每筆含 filename / prompt_en / slug）
輸出 ＝ RAW PNG（母圖，512x768 原生）＋ WebP（512x768，q82，flat RGB）

非破壞：只寫到 scratchpad，**不碰 repo**。驗過之後由主 session 搬進
assets/art/characters/companions/ 並補 tools/art-pipeline/generation-log.csv。

必須用 mflux venv 的 python 跑：
    ~/.local/share/uv/tools/mflux/bin/python recipes/companion_portraits.py

已知的坑（都付過帳，寫在這裡免得再踩）：
  · **同 seed ＝ 同一張圖。** 要重生某一張就換 seed，不是重跑。
  · **不要用參照圖（-r／image-to-image）指向另一個角色** —— 會做出近乎複製的臉，
    而且檔案雜湊不同，自動檢查看不出來，只能靠人並列比對。本批一律純文字生成。
  · **Godot 匯入 PNG 偶爾 ERR_FILE_CORRUPT** —— 所以出貨走 WebP，母圖 PNG 只留存查。
  · FLUX.2 是蒸餾模型：6 步、guidance 1.0、**沒有 negative prompt**。
    要排除的東西必須用正面詞蓋過去（prompt 那一側已經處理）。
"""
import argparse
import gc
import glob
import hashlib
import json
import os
import time
from pathlib import Path

from PIL import Image

SCR = Path("/private/tmp/claude-501/-Users-mcgradymac-claude-prjs-The-Age-of-Exploration"
           "/2170d8de-70fd-4fef-874e-750874bf800d/scratchpad")
PROMPT_DIR = SCR / "companion" / "portraits"
RAW = SCR / "companion" / "portraits_raw"
OUT = SCR / "companion" / "portraits_webp"
W, H = 512, 768          # 出貨尺寸（與 assets/art/characters/ 既有 413 張一致）
GEN_W, GEN_H = 1024, 1536  # 母圖尺寸：生大再 LANCZOS 縮，保細節（錨定規格 §7.3）


def seed_for(slug: str, salt: str = "") -> int:
    return int(hashlib.sha1((slug + salt).encode()).hexdigest()[:8], 16) % (2 ** 31)


def load_prompts(only=None, prompt_dir=None) -> list[dict]:
    rows = []
    for f in sorted(glob.glob(str(Path(prompt_dir or PROMPT_DIR) / "*.json"))):
        if os.path.basename(f).startswith("_"):
            continue
        doc = json.load(open(f))
        # 八個桶不是同一個 agent 寫的，所以頂層有兩種形狀：裸陣列，或 {"prompts": [...]}。
        entries = doc if isinstance(doc, list) else (doc.get("prompts") or [])
        for p in entries:
            if not p.get("prompt_en"):
                continue
            slug = p.get("slug") or p.get("companion_id")
            rows.append({
                "slug": slug,
                "filename": p.get("filename") or f"char_{slug}_portrait_{W}x{H}.webp",
                "prompt": p["prompt_en"],
                "bucket": os.path.basename(f)[:-5],
            })
    if only:
        keep = set(only.split(","))
        rows = [r for r in rows if r["slug"] in keep]
    return rows


def to_webp(src: Path, dst: Path, quality: int = 82) -> None:
    img = Image.open(src).convert("RGB")
    if img.size != (W, H):
        img = img.resize((W, H), Image.Resampling.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "WEBP", quality=quality, method=6)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="逗號分隔的 slug；預設全跑")
    ap.add_argument("--bucket", default="", help="逗號分隔的桶名；預設全跑")
    ap.add_argument("--skip-bucket", default="", help="逗號分隔的桶名，跳過它們")
    ap.add_argument("--steps", type=int, default=6)
    ap.add_argument("--salt", default="", help="換一個 salt ＝ 換一組 seed ＝ 重生（同 seed 會得到同一張）")
    ap.add_argument("--force", action="store_true", help="已存在也重生")
    ap.add_argument("--dry-run", action="store_true", help="只列出要做什麼，不載模型")
    ap.add_argument("--gen-w", type=int, default=GEN_W)
    ap.add_argument("--gen-h", type=int, default=GEN_H)
    ap.add_argument("--prompt-dir", default=str(PROMPT_DIR), help="改讀第二輪的 prompt 目錄")
    ap.add_argument("--tag", default="", help="輸出目錄後綴。同一批要抽多顆種子時，"
                                             "每顆種子一個 tag，否則兩輪會互相覆蓋（raw png 用 slug 命名）")
    a = ap.parse_args()

    global RAW, OUT
    if a.tag:
        RAW = RAW.with_name(RAW.name + "_" + a.tag)
        OUT = OUT.with_name(OUT.name + "_" + a.tag)
        # ⚠️ tag 只換目錄是不夠的 —— seed 沒換的話兩輪會產出**一模一樣的圖**，
        #    而兩個資料夾都會印「完成」。第一版就是這樣，實測 seedA / seedB 的 seed 完全相同。
        #    所以 tag 預設同時當 salt；要拆開時才明寫 --salt。
        if not a.salt:
            a.salt = a.tag
        print(f"== tag={a.tag} → raw {RAW.name} / out {OUT.name} · salt={a.salt!r}")

    rows = load_prompts(a.only or None, a.prompt_dir)
    if a.bucket:
        keep = set(a.bucket.split(","))
        rows = [r for r in rows if r["bucket"] in keep]
    if a.skip_bucket:
        drop = set(a.skip_bucket.split(","))
        rows = [r for r in rows if r["bucket"] not in drop]
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    todo = [r for r in rows if a.force or not (OUT / r["filename"]).exists()]

    # 反空跑：prompt 一則都沒讀到就直接停，不要印一行「完成」然後什麼都沒做。
    if not rows:
        raise SystemExit(f"✗ 空跑守衛：{PROMPT_DIR} 底下一則 prompt 都沒讀到")
    print(f"== 讀到 {len(rows)} 則 prompt，待生成 {len(todo)} 張"
          f"（母圖 {a.gen_w}x{a.gen_h} → 出貨 {W}x{H}, steps={a.steps}）", flush=True)
    if a.dry_run:
        for r in todo:
            print(f"   {r['bucket']:16s} {r['slug']:28s} seed={seed_for(r['slug'], a.salt)}")
        return
    if not todo:
        print("== 全部已存在，沒有要做的（要重生請加 --force 或換 --salt）")
        return

    t0 = time.time()
    import mlx.core as mx
    from mflux.models.common.config import ModelConfig
    from mflux.models.flux2.variants import Flux2Klein

    print("== 載入 FLUX.2-klein-4B (q4) ...", flush=True)
    model = Flux2Klein(quantize=4, model_config=ModelConfig.flux2_klein_4b())
    print(f"== 模型載入完成 {time.time() - t0:.0f}s", flush=True)

    def clear():
        try:
            mx.clear_cache()
        except Exception:
            pass
        gc.collect()

    times, failed = [], []
    for i, r in enumerate(todo, 1):
        raw_png = RAW / f"{r['slug']}.png"
        out_webp = OUT / r["filename"]
        t1 = time.time()
        try:
            img = model.generate_image(
                seed=seed_for(r["slug"], a.salt), prompt=r["prompt"],
                num_inference_steps=a.steps, width=a.gen_w, height=a.gen_h, guidance=1.0)
            img.save(path=str(raw_png))
            to_webp(raw_png, out_webp)
        except Exception as ex:
            print(f"[{i}/{len(todo)}] FAIL {r['slug']}: {repr(ex)[:200]}", flush=True)
            failed.append(r["slug"])
            clear()
            continue
        dt = time.time() - t1
        times.append(dt)
        avg = sum(times) / len(times)
        eta = (len(todo) - i) * avg / 60
        print(f"[{i}/{len(todo)}] OK {r['slug']} {dt:.0f}s (avg {avg:.0f}s, ETA {eta:.0f}min)", flush=True)
        clear()

    # 成功訊息要描述使用者接下來真正需要的整組東西，不是手上剛好握著的那一個變數。
    print(f"== 完成 {len(times)}/{len(todo)}，總計 {(time.time() - t0) / 60:.0f} 分鐘")
    print(f"   WebP（出貨用）：{OUT}")
    print(f"   PNG 母圖（存查）：{RAW}")
    if failed:
        print(f"   ✗ 失敗 {len(failed)} 張：{', '.join(failed)}")


if __name__ == "__main__":
    main()
