#!/usr/bin/env python3
"""台灣副手 陳月娘 —— 四顆種子讓 user 挑臉。

年紀感由種子決定（今日實測：改年齡數字沒有作用），所以一次抽四顆。
配方沿用鎖定的 S4 style block ＋ ≤24 歲青春句 ＋ 兩層識別錨。
"""
import gc, hashlib, json, sys, time
from pathlib import Path
from PIL import Image

SCR = Path("/private/tmp/claude-501/-Users-mcgradymac-claude-prjs-The-Age-of-Exploration"
           "/2170d8de-70fd-4fef-874e-750874bf800d/scratchpad/companion")
SRC = SCR / "taiwan-aide" / "taiwan_v3.json"
OUT = SCR / "taiwan-aide"
GEN_W, GEN_H = 1024, 1536

rows = json.load(open(SRC, encoding="utf-8"))
if len(rows) != 1:
    sys.exit(f"✗ 預期 1 則，實得 {len(rows)}")
r = rows[0]
SEEDS = [(["v2s1"]+[f"pt{i}" for i in range(2,5)])[i-1] for i in range(1, 5)]

t0 = time.time()
import mlx.core as mx
from mflux.models.common.config import ModelConfig
from mflux.models.flux2.variants import Flux2Klein
model = Flux2Klein(quantize=4, model_config=ModelConfig.flux2_klein_4b())
print(f"== 模型載入 {time.time()-t0:.0f}s", flush=True)

done = []
for i, salt in enumerate(SEEDS, 1):
    # 第一格刻意用 v2 的 slug 產生 seed —— user 選中的那張臉就是這顆種子出來的，
    # 只換髮型描述時同種子能把臉保得最像。
    base_slug = "chen_yueh_niang_v2" if salt == "v2s1" else r["slug"]
    seed = int(hashlib.sha1((base_slug + salt).encode()).hexdigest()[:8], 16) % (2**31)
    dst = OUT / f"{r['slug']}__{salt}.png"
    t1 = time.time()
    try:
        img = model.generate_image(seed=seed, prompt=r["prompt_en"], num_inference_steps=6,
                                   width=GEN_W, height=GEN_H, guidance=1.0)
        img.save(path=str(dst))
        im = Image.open(dst).convert("RGB"); W, H = im.size
        im.resize((512, 768), Image.Resampling.LANCZOS).save(
            OUT / f"{r['slug']}__{salt}.webp", "WEBP", quality=88, method=6)
        im.crop((int(W*0.16), int(H*0.07), int(W*0.86), int(H*0.54))).save(
            OUT / f"{r['slug']}__{salt}__face.webp", "WEBP", quality=94, method=6)
        done.append(salt)
        print(f"[{i}/4] OK seed={seed} {time.time()-t1:.0f}s", flush=True)
    except Exception as ex:
        print(f"[{i}/4] FAIL {salt}: {repr(ex)[:160]}", flush=True)
    try:
        mx.clear_cache()
    except Exception:
        pass
    gc.collect()
print(f"\n== 完成 {len(done)}/4 · {(time.time()-t0)/60:.0f} 分鐘 · {OUT}")
