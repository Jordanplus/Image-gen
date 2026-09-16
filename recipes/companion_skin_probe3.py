#!/usr/bin/env python3
"""第三輪 —— 回應 user 兩條：「人臉上不要有斑點」＋「盡量年輕一點」。

第二輪證實：斑點的來源是 prompt 裡的**瑕疵型識別錨**，刪掉即消失（burak S3X）。
但第二輪也留下兩個沒解決的：
  ① europe_f 就算沒有瑕疵錨，臉頰仍有細小深色斑點 —— 那是 `fine natural texture`
     這類質感詞召喚出來的，要用**正面句**把膚色壓成單一勻淨（FLUX 不吃否定句）。
  ② 我的替代錨用了「鬍子裡一道白」，被畫成**臉頰上一道白痕** ——
     替代錨不得使用任何會被讀成「臉上有東西」的字（streak / mark / line / patch / spot）。
  ③ 年齡：prompt 寫 20 歲，四格都像 30 出頭。青春句原本在**最後一句**（注意力最弱的位置），
     本輪把它移到**第二句**，並改寫成具體的解剖描述。

三格：
  S4  = 無斑點膚質詞 ＋ 青春句前移（錨仍為第二輪的替代錨，但 burak 換成骨相型）
  S4L = S4 再把年齡數字往下壓（20→19、44→38），驗年齡數字本身有沒有用
"""
import gc, hashlib, json, re, sys, time
from pathlib import Path
from PIL import Image

SCR = Path("/private/tmp/claude-501/-Users-mcgradymac-claude-prjs-The-Age-of-Exploration"
           "/2170d8de-70fd-4fef-874e-750874bf800d/scratchpad/companion")
OUT = SCR / "ab-skin"
GEN_W, GEN_H = 1024, 1536

S3_SKIN = ("flawless even-toned skin with fine natural texture, a healthy warm glow, "
           "clear unblemished complexion, a soft matte finish to the skin, "
           "bright clear eyes with crisp catchlights, handsome appealing features")
S4_SKIN = ("flawless skin in one single even clean tone across the whole face, "
           "smooth and fine-grained, a healthy warm glow, a soft matte finish, "
           "bright clear eyes with crisp catchlights, handsome appealing features")

OLD_YOUTH = (" The skin unlined and smooth at the eye corners and forehead, "
             "a soft young jawline, a fresh clear complexion.")
NEW_YOUTH = ("Youthful: skin drawn smooth and taut over the cheekbones, "
             "unlined at the eye corners and across the forehead, a soft rounded jawline, "
             "a fresh clear complexion. ")

# 第二輪用的替代錨（burak 那個造成白痕，本輪換成骨相型）
OLD_ANCHOR = {
    "burak_reis": ("A single narrow white scar-free streak of grey runs through the beard at the "
                   "left corner of the jaw. "),
    "companion_self_create_europe_f": ("Strong level brows with a high clean arch, set well apart. "),
}
NEW_ANCHOR = {
    "burak_reis": ("A wide square jaw and a heavy straight brow ridge, deep-set eyes under it. "),
    "companion_self_create_europe_f": ("Strong level brows with a high clean arch, set well apart. "),
}
AGE_DOWN = {"burak_reis": ("A 44-year-old", "A 38-year-old"),
            "companion_self_create_europe_f": ("A 20-year-old", "A 19-year-old")}


def main():
    cells = {(c["slug"], c["cell"]): c["prompt"]
             for c in json.load(open(OUT / "_cells.json", encoding="utf-8"))}
    jobs = []
    for s in OLD_ANCHOR:
        base = cells[(s, "S3X_柔霧＋換掉瑕疵錨")]
        for src, dst_, what in ((S3_SKIN, S4_SKIN, "膚質詞"),
                                (OLD_ANCHOR[s], NEW_ANCHOR[s], "識別錨"),
                                (OLD_YOUTH, "", "移除舊青春句")):
            if src not in base:
                sys.exit(f"✗ {s}: 找不到「{what}」的逐字來源 —— 要從 _cells.json 複製，不要憑記憶打")
            base = base.replace(src, dst_)
        # 青春句移到第二句（第一句是年齡＋身分）
        parts = base.split(". ", 1)
        if len(parts) != 2:
            sys.exit(f"✗ {s}: 切不出第一句")
        p4 = parts[0] + ". " + NEW_YOUTH + parts[1]
        if NEW_YOUTH not in p4 or OLD_YOUTH in p4:
            sys.exit(f"✗ {s}: 青春句前移失敗")
        jobs.append((s, "S4_無斑點＋更年輕", p4))

        a, b = AGE_DOWN[s]
        if a not in p4:
            sys.exit(f"✗ {s}: 找不到年齡字串 {a!r}")
        jobs.append((s, "S4L_再壓年齡數字", p4.replace(a, b)))

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
    print(f"== 模型載入 {time.time()-t0:.0f}s", flush=True)

    for i, (s, k, p) in enumerate(jobs, 1):
        seed = int(hashlib.sha1(s.encode()).hexdigest()[:8], 16) % (2**31)
        dst = OUT / f"{s}__{k}.png"
        t1 = time.time()
        try:
            img = model.generate_image(seed=seed, prompt=p, num_inference_steps=6,
                                       width=GEN_W, height=GEN_H, guidance=1.0)
            img.save(path=str(dst))
            im = Image.open(dst).convert("RGB"); W, H = im.size
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
    print(f"\n== 完成 {(time.time()-t0)/60:.0f} 分鐘")


main()
