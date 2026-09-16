#!/usr/bin/env python3
"""膚質再往上一級 —— 在整批 80 張重生之前，先把 style block 的膚質那幾個字試對。

V3 已確認方向對（拿掉 RAW 與 natural skin texture、補正面的乾淨膚質詞、補光加強、背景改暖）。
user 要求「肌膚可以再好一點」。這裡試兩種再推一級的寫法，並保留 V3 當對照。

⚠️ 已知的反方向風險：拿掉 texture 類的字會滑向塑膠感／AI 感，而本專案的既定方向是**照片寫實**
（memory: characters-photoreal-not-oil）。所以 S1 刻意**保留** fine natural texture，
只把「勻、乾淨、健康」推上去；S2 才加柔光。兩種都要看過再選，不要直接跳 S2。
"""
import gc, hashlib, json, sys, time
from pathlib import Path
from PIL import Image

SCR = Path("/private/tmp/claude-501/-Users-mcgradymac-claude-prjs-The-Age-of-Exploration"
           "/2170d8de-70fd-4fef-874e-750874bf800d/scratchpad/companion")
AB = SCR / "ab-v3"
OUT = SCR / "ab-skin"
GEN_W, GEN_H, W, H = 1024, 1536, 512, 768

# V3 用的那一段（對照組）
V3_SKIN = ("clear even complexion with healthy colour, smooth clean skin, bright clear eyes, "
           "handsome appealing features")
V3_LIGHT = ("soft key light from the upper left, strong fill light from the lower right, "
            "softly graded warm dark backdrop")

# S1：膚質再推一級，但**保留**真實質感的字，避免滑向塑膠臉
S1_SKIN = ("flawless even-toned skin with fine natural texture, a healthy warm glow, "
           "clear unblemished complexion, a soft natural sheen on the cheekbones, "
           "bright clear eyes with crisp catchlights, handsome appealing features")
# S2：S1 再加柔光（美膚光），光位改成包覆式
S2_LIGHT = ("soft diffused beauty lighting from the upper left, generous wrap-around fill "
            "from the lower right, softly graded warm dark backdrop")

VARIANTS = {
    "S0_V3對照": (V3_SKIN, V3_LIGHT),
    "S1_膚質推一級": (S1_SKIN, V3_LIGHT),
    "S2_再加柔光": (S1_SKIN, S2_LIGHT),
}
SUBJ = ["companion_self_create_europe_f", "burak_reis"]


def main():
    cells = {(c["slug"], c["cell"]): c for c in json.load(open(AB / "_cells.json", encoding="utf-8"))}
    jobs = []
    for s in SUBJ:
        base = cells[(s, "V3_換style block")]["prompt"]
        for k, (skin, light) in VARIANTS.items():
            p = base.replace(V3_SKIN, skin).replace(V3_LIGHT, light)
            if k != "S0_V3對照" and p == base:
                sys.exit(f"✗ {s}/{k}：字串沒有替換到，這一格會是空跑")
            jobs.append((s, k, p))
    if not jobs:
        sys.exit("✗ 空跑守衛：一格都沒有")

    OUT.mkdir(parents=True, exist_ok=True)
    json.dump([{"slug": s, "cell": k, "prompt": p} for s, k, p in jobs],
              open(OUT / "_cells.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"== {len(jobs)} 張（{len(SUBJ)} 主體 × {len(VARIANTS)} 格），同 seed 只換膚質與光的字")

    t0 = time.time()
    import mlx.core as mx
    from mflux.models.common.config import ModelConfig
    from mflux.models.flux2.variants import Flux2Klein
    model = Flux2Klein(quantize=4, model_config=ModelConfig.flux2_klein_4b())
    print(f"== 模型載入完成 {time.time()-t0:.0f}s", flush=True)

    done = 0
    for i, (s, k, p) in enumerate(jobs, 1):
        seed = int(hashlib.sha1(s.encode()).hexdigest()[:8], 16) % (2**31)
        dst = OUT / f"{s}__{k}.png"
        t1 = time.time()
        try:
            img = model.generate_image(seed=seed, prompt=p, num_inference_steps=6,
                                       width=GEN_W, height=GEN_H, guidance=1.0)
            img.save(path=str(dst))
            Image.open(dst).convert("RGB").resize((W, H), Image.Resampling.LANCZOS).save(
                OUT / f"{s}__{k}.webp", "WEBP", quality=88, method=6)
            done += 1
            print(f"[{i}/{len(jobs)}] OK {s} {k} {time.time()-t1:.0f}s", flush=True)
        except Exception as ex:
            print(f"[{i}/{len(jobs)}] FAIL {s} {k}: {repr(ex)[:140]}", flush=True)
        try:
            mx.clear_cache()
        except Exception:
            pass
        gc.collect()
    print(f"\n== 完成 {done}/{len(jobs)}，{(time.time()-t0)/60:.0f} 分鐘 · 產出在 {OUT}")


main()
