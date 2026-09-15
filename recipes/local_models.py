#!/usr/bin/env python3
"""本地 mflux 模型清單 + 授權把關（商用 / 個人 兩組共用）。

用 mflux 的 python 跑：~/.local/share/uv/tools/mflux/bin/python
兩組用途：
  - commercial：自製遊戲要商用 → 只准可商用授權（Apache-2.0 等）；require() 遇到非商用模型直接中止。
  - personal  ：自己旅遊生圖、修照片 → 非商用授權也可以用。
授權出處：各模型 Hugging Face 模型卡與 license tag（2026-09-15 查）。mflux 以 0.19.1 驗證。
"""
import gc
import os
import re
from pathlib import Path

USES = ("commercial", "personal")

MODELS = {
    "klein-4b": dict(
        kind="flux2", config="flux2_klein_4b", repo="black-forest-labs/FLUX.2-klein-4B",
        license="Apache-2.0", commercial=True, distilled=True,
        defaults=dict(steps=6, guidance=1.0),
        note="現行立繪主力；蒸餾版，guidance 固定 1.0、負面提示詞不生效"),
    "klein-base-4b": dict(
        kind="flux2", config="flux2_klein_base_4b", repo="black-forest-labs/FLUX.2-klein-base-4B",
        license="Apache-2.0", commercial=True, distilled=False,
        defaults=dict(steps=50, guidance=1.5),
        note="非蒸餾；預設取 mflux 文件範例（50 步、guidance 1.5，建議 8-bit）；guidance>1 才做 CFG，自訂負面提示詞靠 _with_negative"),
    "z-image": dict(
        kind="z_image", config="z_image", repo="Tongyi-MAI/Z-Image",
        license="Apache-2.0", commercial=True, distilled=False,
        defaults=dict(steps=50, guidance=4.0),
        note="非蒸餾；預設取 mflux 文件範例（50 步、guidance 4，建議 8-bit），原生支援負面提示詞"),
    "z-image-turbo": dict(
        kind="z_image", config="z_image_turbo", repo="Tongyi-MAI/Z-Image-Turbo",
        license="Apache-2.0", commercial=True, distilled=True,
        defaults=dict(steps=9, guidance=0.0),
        note="蒸餾版，官方 9 步、guidance 固定 0、不吃負面提示詞。"
             "官方權重是 F32（31GB）：24GB 機器載入後生到第 2 步記憶體不足被砍（2026-09-15），24GB 請用 z-image-turbo-q4"),
    "z-image-turbo-q4": dict(
        kind="z_image", config="z_image_turbo", repo="filipstrand/Z-Image-Turbo-mflux-4bit",
        license="轉檔者標 Tongyi Qianwen License（基底 Z-Image-Turbo 的 HF 標籤是 Apache-2.0）", commercial=False,
        distilled=True, prequantized=True,
        defaults=dict(steps=9, guidance=0.0),
        note="mflux 作者預先量化的 4-bit 版（5.9GB，mflux 文件示範用這版）；授權標示和官方不一致，先歸個人用途"),
    "qwen-image-2512": dict(
        kind="qwen", config="qwen_image", repo="mlx-community/Qwen-Image-2512-4bit",
        license="Apache-2.0", commercial=True, distilled=False, prequantized=True,
        defaults=dict(steps=25, guidance=3.5),
        note="非蒸餾，20B＋7B 視覺語言編碼器；用 mlx-community 預先量化的 4-bit 版（原版約 58GB）；"
             "預設沿用 2026-06 場景圖設定（25 步、guidance 3.5，1152×768 約 270–340 秒）"),
    "klein-9b": dict(
        kind="flux2", config="flux2_klein_9b", repo="black-forest-labs/FLUX.2-klein-9B",
        license="FLUX Non-Commercial License v2.1", commercial=False, distilled=True,
        defaults=dict(steps=4, guidance=1.0),
        note="只限個人用途；多參考圖編輯品質高，24GB 機器會用到 swap"),
    "seedvr2-3b": dict(
        kind="seedvr2", config="seedvr2_3b", repo="numz/SeedVR2_comfyUI",
        license="Apache-2.0", commercial=True, distilled=None,
        defaults=dict(),
        note="放大；本質是影片修復模型，也吃單張圖"),
}


def require(key, use):
    """確認模型存在且授權允許這個用途；商用遇到非商用授權直接中止。"""
    if use not in USES:
        raise SystemExit(f"✗ 用途只能是 {USES}，收到 {use!r}")
    if key not in MODELS:
        raise SystemExit(f"✗ 未知模型 {key!r}；可用：{', '.join(MODELS)}")
    m = MODELS[key]
    if use == "commercial" and not m["commercial"]:
        ok = ", ".join(k for k, v in MODELS.items() if v["commercial"])
        raise SystemExit(f"✗ {key} 的授權是「{m['license']}」，不能用在商用（自製遊戲）。可商用的有：{ok}")
    return m


def license_record(key):
    """給生成紀錄用的授權欄位（對應遊戲專案 generation-log.csv 的 model_version / license_source）。"""
    m = MODELS[key]
    return dict(model=key, repo=m["repo"], license=m["license"], commercial_ok=m["commercial"])


def _ensure_hf_env():
    # 這台 Mac 的 Xet 傳輸會空轉、寫不進硬碟（2026-06-28 實測），一律退回 HTTPS。
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    if os.environ.get("HF_TOKEN"):
        return
    # gated 模型（如 klein-9B）需要金鑰；只從檔案讀進環境變數，不印出。
    f = Path(os.environ.get("HF_TOKEN_FILE", Path.home() / "claude_prjs" / "Higgingface.env"))
    if f.is_file():
        m = re.search(r"hf_[A-Za-z0-9]{20,}", f.read_text(errors="ignore"))
        if m:
            os.environ["HF_TOKEN"] = m.group(0)


def _with_negative(base_cls):
    """mflux 的 FLUX.2 把負面提示詞寫死成空白（guidance>1 時仍會做 CFG），這裡換成自訂字串。
    依賴 mflux 內部方法 _encode_prompt_pair（0.18.0 / 0.19.1 驗證過）；升級後不存在就直接中止。"""
    if not hasattr(base_cls, "_encode_prompt_pair"):
        raise SystemExit("✗ 這版 mflux 的 FLUX.2 沒有 _encode_prompt_pair，自訂負面提示詞的包裝失效，需要改寫")

    class WithNegative(base_cls):
        negative_prompt = " "

        def _encode_prompt_pair(self, *, prompt, negative_prompt, guidance):
            return super()._encode_prompt_pair(prompt=prompt, negative_prompt=self.negative_prompt,
                                               guidance=guidance)

    WithNegative.__name__ = base_cls.__name__ + "WithNegative"
    return WithNegative


def _patch_mlx_repeat():
    """SeedVR2 相容修補（mflux 0.19.1 + MLX 0.32.2 實測會壞）。

    mflux 的 SeedVR2 用 `mx.repeat(x, mx.array(counts), axis=0)`（每段重複不同次數），
    但 MLX 0.32 的 repeat 只收整數，直接 TypeError。這裡只在「陣列次數被拒」時包一層：
    整數次數照舊交給原本的 repeat，陣列次數改用等效的 mx.take（小陣列對照 numpy.repeat 完全相同）。
    MLX 或 mflux 修好後，開頭的檢查會通過，就不會套用。
    """
    import mlx.core as mx
    import numpy as np
    try:
        mx.repeat(mx.zeros((2,)), mx.array([1, 1]), axis=0)
        return
    except TypeError:
        pass
    original = mx.repeat

    def repeat(array, repeats, axis=None, **kw):
        if isinstance(repeats, int):
            return original(array, repeats, axis=axis, **kw)
        counts = np.array(repeats).astype(np.int64).reshape(-1)
        if counts.size == 1:
            return original(array, int(counts[0]), axis=axis, **kw)
        if axis is None:
            array, axis = array.reshape(-1), 0
        index = mx.array(np.repeat(np.arange(array.shape[axis]), counts))
        return mx.take(array, index, axis=axis)

    mx.repeat = repeat


def _register_memory_saver(model, *, low_ram, single_run):
    """照 mflux 命令列（callbacks/callback_manager.py）的做法掛上 MemorySaver。

    直接呼叫 python API 不會有這一步，文字編碼器整段生成期間都佔著記憶體（mflux 註解：浪費 8–12GB）。
    single_run=True：只生一張 → 編碼完就把文字編碼器移出記憶體；FLUX.2 每次生成都會重新編碼，所以要連續生多張時不能移。
    low_ram=True：再加 MLX 快取上限 1GB 與 VAE 分塊解碼（等同命令列 --low-ram）。
    """
    if not hasattr(model, "callbacks"):
        return
    from mflux.callbacks.instances.memory_saver import MemorySaver
    model.callbacks.register(MemorySaver(model=model, keep_transformer=True,
                                         cache_limit_bytes=1000**3 if low_ram else None,
                                         num_seeds=1 if single_run else 2))


def load(key, use, quantize=4, edit=False, low_ram=False, single_run=False, lora_paths=None, lora_scales=None):
    """依用途把關後載入模型。edit=True 載 FLUX.2 的參考圖編輯版；low_ram／single_run 見 _register_memory_saver。
    lora_paths：本機檔案或 mflux 認得的 HF 路徑 org/repo:檔名（FLUX.2 支援一般 LoRA 與 LyCORIS LoKr）；接 FLUX.2 與 Z-Image。"""
    m = require(key, use)
    _ensure_hf_env()
    from mflux.models.common.config import ModelConfig
    cfg = getattr(ModelConfig, m["config"])()
    if lora_paths and m["kind"] not in ("flux2", "z_image"):
        raise SystemExit(f"✗ {key} 這裡還沒接 LoRA（目前只接 FLUX.2、Z-Image）")
    if m["kind"] == "flux2":
        from mflux.models.flux2.variants import Flux2Klein, Flux2KleinEdit
        model = _with_negative(Flux2KleinEdit if edit else Flux2Klein)(
            quantize=quantize, model_config=cfg, lora_paths=lora_paths, lora_scales=lora_scales)
    elif edit:
        raise SystemExit(f"✗ {key} 不支援參考圖編輯")
    elif m["kind"] == "z_image":
        from mflux.models.z_image import ZImage
        model = ZImage(quantize=None if m.get("prequantized") else quantize,
                       model_path=m["repo"] if m.get("prequantized") else None,
                       model_config=cfg, lora_paths=lora_paths, lora_scales=lora_scales)
    elif m["kind"] == "qwen":
        from mflux.models.qwen.variants.txt2img.qwen_image import QwenImage
        model = QwenImage(quantize=None if m.get("prequantized") else quantize, model_path=m["repo"],
                          model_config=cfg)
    elif m["kind"] == "seedvr2":
        _patch_mlx_repeat()
        from mflux.models.seedvr2 import SeedVR2
        model = SeedVR2(quantize=quantize, model_config=cfg)
    else:
        raise SystemExit(f"✗ {key} 的 kind={m['kind']} 尚未支援")
    _register_memory_saver(model, low_ram=low_ram, single_run=single_run)
    return model


def generate(model, key, *, prompt, seed, width, height, steps=None, guidance=None,
             negative_prompt=None, image_paths=None):
    """統一的生成呼叫；步數與 guidance 沒指定時用 MODELS 裡的預設。"""
    m = MODELS[key]
    d = m["defaults"]
    steps = steps or d.get("steps")
    guidance = d.get("guidance") if guidance is None else guidance
    if m["kind"] == "flux2":
        if negative_prompt and (m["distilled"] or guidance <= 1.0):
            print(f"ℹ️ {key}：蒸餾版或 guidance≤1，負面提示詞不會生效", flush=True)
        model.negative_prompt = negative_prompt or " "
        kw = dict(seed=seed, prompt=prompt, num_inference_steps=steps, width=width, height=height,
                  guidance=guidance)
        if image_paths:
            kw["image_paths"] = [str(p) for p in image_paths]
        return model.generate_image(**kw)
    if m["kind"] in ("z_image", "qwen"):
        if image_paths:
            raise SystemExit(f"✗ {key} 不支援參考圖")
        return model.generate_image(seed=seed, prompt=prompt, num_inference_steps=steps, width=width,
                                    height=height, guidance=guidance, negative_prompt=negative_prompt)
    raise SystemExit(f"✗ {key} 不是生圖模型")


def to_pil(img):
    """FLUX.2 回傳 mflux 的 GeneratedImage（.image 是 PIL），Z-Image 直接回 PIL。"""
    return getattr(img, "image", img)


def save(img, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    to_pil(img).save(path)
    return path


def free():
    """換模型前釋放記憶體（呼叫端先把模型變數設成 None）。"""
    gc.collect()
    try:
        import mlx.core as mx
        mx.clear_cache()
    except Exception:
        pass
