#!/usr/bin/env python3
"""只重生兩位（quispe_sisa / malintzin），同種子，只有服飾用字改了 —— 這樣差異可歸因。"""
import gc, hashlib, json, sys, time
from pathlib import Path
from PIL import Image
W = Path("/private/tmp/claude-501/-Users-mcgradymac-claude-prjs-The-Age-of-Exploration"
         "/2170d8de-70fd-4fef-874e-750874bf800d/scratchpad/companion/women")
ONLY = {"quispe_sisa", "malintzin"}
rows = [r for r in json.load(open(W/"_assembled6.json", encoding="utf-8")) if r["slug"] in ONLY]
if len(rows) != 2:
    sys.exit(f"✗ 空跑守衛：預期 2 則，實得 {len(rows)}")
t0=time.time()
import mlx.core as mx
from mflux.models.common.config import ModelConfig
from mflux.models.flux2.variants import Flux2Klein
model = Flux2Klein(quantize=4, model_config=ModelConfig.flux2_klein_4b())
print(f"== 模型載入 {time.time()-t0:.0f}s", flush=True)
for i,(r,salt) in enumerate([(r,s) for r in rows for s in ("A","B")],1):
    out = W/f"gen2_{salt}"; out.mkdir(exist_ok=True)
    seed = int(hashlib.sha1((r["slug"]+"seed"+salt).encode()).hexdigest()[:8],16)%(2**31)
    dst = out/f"{r['slug']}.png"; t1=time.time()
    try:
        img = model.generate_image(seed=seed, prompt=r["prompt_en"], num_inference_steps=6,
                                   width=1024, height=1536, guidance=1.0)
        img.save(path=str(dst))
        im=Image.open(dst).convert("RGB"); Wd,Hd=im.size
        im.resize((512,768),Image.Resampling.LANCZOS).save(out/f"{r['slug']}.webp","WEBP",quality=82,method=6)
        im.crop((int(Wd*0.16),int(Hd*0.07),int(Wd*0.86),int(Hd*0.54))).resize((360,372),Image.Resampling.LANCZOS).save(
            out/f"{r['slug']}__face.webp","WEBP",quality=92,method=6)
        print(f"[{i}/4] OK {r['slug']} {salt} seed={seed} {time.time()-t1:.0f}s", flush=True)
    except Exception as ex:
        print(f"[{i}/4] FAIL {r['slug']} {salt}: {repr(ex)[:140]}", flush=True)
    try: mx.clear_cache()
    except Exception: pass
    gc.collect()
print(f"\n== 完成 {(time.time()-t0)/60:.0f} 分鐘")
