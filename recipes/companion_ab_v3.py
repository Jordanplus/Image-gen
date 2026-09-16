#!/usr/bin/env python3
"""同伴立繪配方 A/B —— 在重生 80 張之前，先證明每一條改法真的有效。

為什麼要 A/B 而不是直接改：兩輪目視給出的三條主要改法，證據強度差很多。
  · 刪掉「Weather-worn and capable rather than glamorous.」—— 相關性很強
    （自創女 18/18 有、男 0/18 沒有；女平均 1.89、男 3.22），但**性別是混淆變數**，因果沒釘死。
  · 動 80/80 共用的 style block —— 完全沒證據，而且它一改就是整批 80 張都要重生。
    已知反證：三張 prompt 明文要求「乾淨、蒼白、未經風吹」的圖**照樣長斑**
    ⇒ 正面詞未必壓得住 `RAW` + `natural skin texture`。
  · 把年輕寫進臉的描述句 —— 只有 1 個正面樣本（ludovico_caboto，全批唯一年齡命中的一張）。

作法：**同一個 seed、只換 prompt**，逐條加碼，這樣每一格的差異可歸因到那一條改動。
"""
import argparse, gc, hashlib, json, os, sys, time
from pathlib import Path
from PIL import Image

SCR = Path("/private/tmp/claude-501/-Users-mcgradymac-claude-prjs-The-Age-of-Exploration"
           "/2170d8de-70fd-4fef-874e-750874bf800d/scratchpad/companion")
SRC = SCR / "portraits-v2"
OUT = SCR / "ab-v3"
GEN_W, GEN_H, W, H = 1024, 1536, 512, 768

OLD_STYLE = ("RAW DSLR photograph, vertical bust portrait, head turned slightly off-axis, "
             "both shoulders in frame, cropped below the chest, clear headroom above the top of "
             "the head and any hat, eyes at 62% of the frame height, soft key light from the "
             "upper left, weak fill light from the lower right, plain dark grey backdrop, "
             "soft vignette, natural skin texture, realistic proportions, muted period colour, "
             "face in sharp focus.")
# FLUX.2 沒有 negative prompt ⇒ 要排除的東西一律用正面詞蓋過去，不寫 no/without。
NEW_STYLE = ("Photorealistic portrait photograph, 85mm portrait lens, vertical bust portrait, "
             "head turned slightly off-axis, both shoulders in frame, cropped below the chest, "
             "a wide band of empty backdrop above the top of the head and any hat, "
             "eyes at 62% of the frame height, soft key light from the upper left, "
             "strong fill light from the lower right, softly graded warm dark backdrop, "
             "clear even complexion with healthy colour, smooth clean skin, bright clear eyes, "
             "handsome appealing features, realistic proportions, period colour, "
             "face in sharp focus.")
GLAM = "Weather-worn and capable rather than glamorous."
# 照抄 ludovico_caboto —— 全批唯一年齡命中的那一張，它的差別就是把年輕寫進了臉
YOUTH = (" The skin unlined and smooth at the eye corners and forehead, "
         "a soft young jawline, a fresh clear complexion.")
AGERS = ["skin burnt dark, the nose wind-reddened and the cheekbones peeling",
         "burnt dark, the nose wind-reddened and the cheekbones peeling",
         "the cheekbones peeling", "salt-crusted hair and lashes",
         "deeply sun- and salt-burned", "weather-worn"]


def load_prompts():
    out = {}
    for f in sorted(SRC.glob("*.json")):
        if f.name.startswith("_"):
            continue
        d = json.load(open(f, encoding="utf-8"))
        for r in (d if isinstance(d, list) else d.get("prompts") or []):
            out[r.get("slug")] = r
    return out


def strip(p, frag):
    """刪掉一個片語，並回報有沒有真的刪到 —— 沒刪到就不要假裝這一格測了東西。"""
    if frag not in p:
        return p, False
    q = p.replace(frag, "").replace("  ", " ").replace(" ,", ",").replace(" .", ".")
    return q.strip(), True


def variants(slug, base):
    """V0 對照組（原樣）→ V1 刪反美句 → V2 再加年輕描述並刪風霜詞 → V3 再換 style block。"""
    v = {}
    v["V0_原樣"] = (base, ["（對照組，一個字沒改）"])

    p1, hit = strip(base, GLAM)
    v["V1_刪反美句"] = (p1, [f"刪 '{GLAM}' → {'刪到了' if hit else '⚠️ 這則本來就沒有這句'}"])

    p2, notes = p1, []
    for a in AGERS:
        p2, h = strip(p2, a)
        if h:
            notes.append(f"刪風霜詞 '{a[:38]}…'")
    p2 = p2.rstrip() + YOUTH
    notes.append("加年輕描述句（照 ludovico_caboto 的寫法）")
    v["V2_加年輕減風霜"] = (p2, notes)

    p3 = p2.replace(OLD_STYLE, NEW_STYLE)
    v["V3_換style block"] = (p3, ["換掉 80/80 共用的 style block："
                                  "拿掉 RAW 與 natural skin texture、補正面的乾淨膚質與「好看」、"
                                  "補光加強、背景改暖色有層次"
                                  if p3 != p2 else "⚠️ style block 沒換到"])
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slugs", default="companion_self_create_europe_f,"
                                       "companion_self_create_ming_m,burak_reis")
    ap.add_argument("--which", default="", help="只跑某幾格，逗號分隔（預設全跑）")
    ap.add_argument("--steps", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    P = load_prompts()
    slugs = [s for s in a.slugs.split(",") if s]
    missing = [s for s in slugs if s not in P]
    if missing:
        sys.exit(f"✗ 找不到 prompt：{missing}")

    jobs = []
    for s in slugs:
        for k, (p, notes) in variants(s, P[s]["prompt_en"]).items():
            if a.which and k not in a.which.split(","):
                continue
            jobs.append((s, k, p, notes))
    if not jobs:
        sys.exit("✗ 空跑守衛：一格都沒有")

    OUT.mkdir(parents=True, exist_ok=True)
    json.dump([{"slug": s, "cell": k, "prompt": p, "changes": n} for s, k, p, n in jobs],
              open(OUT / "_cells.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"== {len(slugs)} 個主體 × {len(jobs)//len(slugs)} 格 = {len(jobs)} 張")
    for s, k, p, n in jobs:
        print(f"   {s:36s} {k:16s} {len(p):5d}字元  {' / '.join(n)[:90]}")
    if a.dry_run:
        return

    t0 = time.time()
    import mlx.core as mx
    from mflux.models.common.config import ModelConfig
    from mflux.models.flux2.variants import Flux2Klein
    print("== 載入 FLUX.2-klein-4B (q4) ...", flush=True)
    model = Flux2Klein(quantize=4, model_config=ModelConfig.flux2_klein_4b())
    print(f"== 模型載入完成 {time.time()-t0:.0f}s", flush=True)

    done, failed = 0, []
    for i, (s, k, p, _n) in enumerate(jobs, 1):
        # 同一主體的四格共用同一個 seed ⇒ 差異只能來自 prompt
        seed = int(hashlib.sha1(s.encode()).hexdigest()[:8], 16) % (2**31)
        dst = OUT / f"{s}__{k}.png"
        t1 = time.time()
        try:
            img = model.generate_image(seed=seed, prompt=p, num_inference_steps=a.steps,
                                       width=GEN_W, height=GEN_H, guidance=1.0)
            img.save(path=str(dst))
            Image.open(dst).convert("RGB").resize((W, H), Image.Resampling.LANCZOS).save(
                OUT / f"{s}__{k}.webp", "WEBP", quality=88, method=6)
            done += 1
            print(f"[{i}/{len(jobs)}] OK {s} {k} {time.time()-t1:.0f}s", flush=True)
        except Exception as ex:
            failed.append(f"{s}/{k}: {repr(ex)[:140]}")
            print(f"[{i}/{len(jobs)}] FAIL {s} {k}: {repr(ex)[:140]}", flush=True)
        try:
            mx.clear_cache()
        except Exception:
            pass
        gc.collect()

    print(f"\n== 完成 {done}/{len(jobs)}，{(time.time()-t0)/60:.0f} 分鐘")
    print(f"   出貨尺寸 WebP 與 1024×1536 母圖都在：{OUT}")
    print(f"   每一格改了什麼：{OUT/'_cells.json'}")
    if failed:
        print("   ✗ 失敗：" + "; ".join(failed))


main()
