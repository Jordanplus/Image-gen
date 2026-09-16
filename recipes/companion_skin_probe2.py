#!/usr/bin/env python3
"""膚質探針第二輪 —— 因為第一輪的結論是「膚質那幾個字不是主要槓桿」。

第一輪（S0/S1/S2）親眼看過後的三個觀察：
  1. burak_reis 的黑點在三格**全都在** —— 它是 prompt 指定的識別錨（powder-burn speckles），
     正面的膚質詞蓋不掉它。⇒ 天花板是錨，不是膚質詞。
  2. S1/S2 的 `a soft natural sheen on the cheekbones` 在女性主體上被讀成**油光／汗**，
     那是**退步**，不是進步。
  3. 三格都仍讀起來像 30 歲，而 prompt 寫的是 20 歲。

本輪四格，每一格都在回答上面一個問題：
  S3  = S1 但把「顴骨光澤」換成「柔霧感」——驗油光是不是那一句造成的
  S3X = S3 且**刪掉該主體的瑕疵型識別錨** ——驗天花板是不是錨（這是決定性的一格）
"""
import gc, hashlib, json, sys, time
from pathlib import Path
from PIL import Image

SCR = Path("/private/tmp/claude-501/-Users-mcgradymac-claude-prjs-The-Age-of-Exploration"
           "/2170d8de-70fd-4fef-874e-750874bf800d/scratchpad/companion")
OUT = SCR / "ab-skin"
GEN_W, GEN_H = 1024, 1536

S1_SKIN = ("flawless even-toned skin with fine natural texture, a healthy warm glow, "
           "clear unblemished complexion, a soft natural sheen on the cheekbones, "
           "bright clear eyes with crisp catchlights, handsome appealing features")
S3_SKIN = ("flawless even-toned skin with fine natural texture, a healthy warm glow, "
           "clear unblemished complexion, a soft matte finish to the skin, "
           "bright clear eyes with crisp catchlights, handsome appealing features")

# 每個主體的「瑕疵型識別錨」原句（逐字，取自 _cells.json）
ANCHOR = {
    "burak_reis": ("Dark powder-burn speckles are driven permanently into the skin of his chin "
                   "and down the sides of his neck, ignited grains lodged under the surface like "
                   "tattooing, spread evenly on both sides of the jaw. "),
    "companion_self_create_europe_f": ("One natural unbroken brow meets fully across the bridge "
                                       "of the nose, low on the centre of the forehead. "),
}
# 刪掉錨之後補一個**不減損好看**的替代錨（骨相／髮質／配件類）
REPLACEMENT = {
    "burak_reis": ("A single narrow white scar-free streak of grey runs through the beard at the "
                   "left corner of the jaw. "),
    "companion_self_create_europe_f": ("Strong level brows with a high clean arch, set well apart. "),
}


def main():
    cells = {(c["slug"], c["cell"]): c for c in json.load(open(OUT / "_cells.json", encoding="utf-8"))}
    jobs = []
    for s in ANCHOR:
        base = cells[(s, "S1_膚質推一級")]["prompt"]
        p3 = base.replace(S1_SKIN, S3_SKIN)
        if p3 == base:
            sys.exit(f"✗ {s}/S3：膚質字串沒替換到")
        jobs.append((s, "S3_柔霧不油光", p3))

        if ANCHOR[s] not in p3:
            sys.exit(f"✗ {s}/S3X：找不到錨句逐字 —— 錨句要從 _cells.json 複製，不要憑記憶打")
        p3x = p3.replace(ANCHOR[s], REPLACEMENT[s])
        if p3x == p3 or ANCHOR[s] in p3x:
            sys.exit(f"✗ {s}/S3X：錨句沒被換掉")
        jobs.append((s, "S3X_柔霧＋換掉瑕疵錨", p3x))

    if len(jobs) != 4:
        sys.exit(f"✗ 空跑守衛：預期 4 格，實得 {len(jobs)}")

    old = json.load(open(OUT / "_cells.json", encoding="utf-8"))
    json.dump(old + [{"slug": s, "cell": k, "prompt": p} for s, k, p in jobs],
              open(OUT / "_cells.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"== {len(jobs)} 張，同 seed")

    t0 = time.time()
    import mlx.core as mx
    from mflux.models.common.config import ModelConfig
    from mflux.models.flux2.variants import Flux2Klein
    model = Flux2Klein(quantize=4, model_config=ModelConfig.flux2_klein_4b())
    print(f"== 模型載入完成 {time.time()-t0:.0f}s", flush=True)

    for i, (s, k, p) in enumerate(jobs, 1):
        seed = int(hashlib.sha1(s.encode()).hexdigest()[:8], 16) % (2**31)
        dst = OUT / f"{s}__{k}.png"
        t1 = time.time()
        try:
            img = model.generate_image(seed=seed, prompt=p, num_inference_steps=6,
                                       width=GEN_W, height=GEN_H, guidance=1.0)
            img.save(path=str(dst))
            im = Image.open(dst).convert("RGB")
            W, H = im.size
            im.resize((720, 1080), Image.Resampling.LANCZOS).save(
                OUT / f"{s}__{k}__full.webp", "WEBP", quality=92, method=6)
            im.crop((int(W*0.16), int(H*0.09), int(W*0.86), int(H*0.56))).save(
                OUT / f"{s}__{k}__face.webp", "WEBP", quality=94, method=6)
            print(f"[{i}/4] OK {s} {k} {time.time()-t1:.0f}s", flush=True)
        except Exception as ex:
            print(f"[{i}/4] FAIL {s} {k}: {repr(ex)[:140]}", flush=True)
        try:
            mx.clear_cache()
        except Exception:
            pass
        gc.collect()
    print(f"\n== 完成，{(time.time()-t0)/60:.0f} 分鐘")


main()
