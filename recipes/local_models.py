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


def total_ram_gb():
    """取得系統實體記憶體容量（GB）。32GB 機器可開 8-bit 與 1024 解析度，24GB 維持 4-bit 與記憶體防線。"""
    try:
        import subprocess
        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=3).stdout.strip()
        return int(out) / (1024 ** 3)
    except Exception:
        return 16.0


MODELS = {
    "klein-9b": dict(
        kind="flux2", config="flux2_klein_9b", repo="black-forest-labs/FLUX.2-klein-9B",
        license="FLUX Non-Commercial License v2.1", commercial=False, distilled=True,
        defaults=dict(steps=4, guidance=1.0),
        note="主力旗艦模型；32GB M5 建議 8-bit（quantize=8）畫質極高，24GB 機器用 4-bit"),
    "klein-9b-uncensored": dict(
        kind="flux2", config="flux2_klein_9b", repo="black-forest-labs/FLUX.2-klein-9B",
        license="FLUX Non-Commercial License v2.1", commercial=False, distilled=True,
        defaults=dict(steps=4, guidance=1.0), uncensored=True,
        text_encoder_repo="darknight9121/FLUX.2-klein-base-9B-bucket-uncensored",
        note="FLUX.2-klein-9B 掛載社群無審查 Text Encoder，解除提示詞審查限制"),
    "klein-4b": dict(
        kind="flux2", config="flux2_klein_4b", repo="black-forest-labs/FLUX.2-klein-4B",
        license="Apache-2.0", commercial=True, distilled=True,
        defaults=dict(steps=6, guidance=1.0),
        note="前代 4B 立繪模型；蒸餾版，guidance 固定 1.0、負面提示詞不生效"),
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
    # gated 模型（如 klein-9B）需要金鑰；依序檢查常用金鑰檔，不印出。
    candidates = [
        os.environ.get("HF_TOKEN_FILE"),
        Path.home() / "claude" / "api.env",
        Path.home() / "claude_prjs" / "Higgingface.env",
        Path.home() / ".cache" / "huggingface" / "token",
    ]
    for c in candidates:
        if c and Path(c).is_file():
            m = re.search(r"hf_[A-Za-z0-9]{20,}", Path(c).read_text(errors="ignore"))
            if m:
                os.environ["HF_TOKEN"] = m.group(0)
                break


def _load_text_encoder_weights(spec=None):
    """載入並映射無審查或自訂 Text Encoder 權重（Qwen3TextEncoder 結構）。
    spec 可為：
      - 本機 .safetensors 檔案或目錄
      - HF repo ID（例如 darknight9121/FLUX.2-klein-base-9B-bucket-uncensored）
    """
    _ensure_hf_env()
    import mlx.core as mx
    from mflux.models.flux2.weights.flux2_weight_mapping import Flux2WeightMapping
    from mflux.models.common.weights.mapping.weight_mapper import WeightMapper
    from mflux.models.common.weights.loading.weight_loader import WeightLoader
    from huggingface_hub import hf_hub_download

    spec = spec or "darknight9121/FLUX.2-klein-base-9B-bucket-uncensored"
    p = Path(spec).expanduser() if spec else None
    if p and p.exists():
        if p.is_dir():
            if (p / "model.safetensors.index.json").exists():
                raw = WeightLoader._load_safetensors(p, "multi_json")
            else:
                raw = WeightLoader._load_safetensors(p, "mlx_native")
        else:
            raw = dict(mx.load(str(p)).items())
    else:
        filename = "text_encoder/model.safetensors" if "bucket" in spec else "model.safetensors"
        token = os.environ.get("HF_TOKEN")
        dl_path = hf_hub_download(repo_id=spec, filename=filename, token=token)
        raw = dict(mx.load(str(dl_path)).items())

    mapped = WeightMapper.apply_mapping(
        hf_weights=raw,
        mapping=Flux2WeightMapping.get_text_encoder_mapping(),
    )
    return mapped


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
    """掛上 MemorySaver。

    注意：在 32GB 機器（M5 等）或需要常駐生成的場合，若 single_run=False 且非強制 low_ram，
    不掛載 MemorySaver，避免它在第 1 步把 text_encoder 刪掉（mflux 實作：self.model.text_encoder = None），
    導致常駐模型後續無法用不同 prompt 生圖。24GB 機器上或單張命令列時仍正常掛載。
    """
    if not hasattr(model, "callbacks"):
        return
    # 32GB 機器若不是強制 low_ram，不註冊 MemorySaver 以保留模型在記憶體中常駐重用
    if total_ram_gb() >= 30 and not low_ram and not single_run:
        return
    if not single_run and not low_ram:
        return
    from mflux.callbacks.instances.memory_saver import MemorySaver
    model.callbacks.register(MemorySaver(model=model, keep_transformer=True,
                                         cache_limit_bytes=1000**3 if low_ram else None,
                                         num_seeds=1 if single_run else 2))


def load(key, use, quantize=None, edit=False, low_ram=False, single_run=False,
         lora_paths=None, lora_scales=None, text_encoder_path=None):
    """依用途把關後載入模型。edit=True 載 FLUX.2 的參考圖編輯版；low_ram／single_run 見 _register_memory_saver。
    lora_paths：本機檔案或 mflux 認得的 HF 路徑 org/repo:檔名（FLUX.2 支援一般 LoRA 與 LyCORIS LoKr）；接 FLUX.2 與 Z-Image。
    text_encoder_path：自訂或無審查 Text Encoder（本機 safetensors 或 HF repo）。
    32GB 機器預設採 quantize=8（完全消除 4-bit 引起的色塊與眼周微變形），24GB 機器預設 4-bit。"""
    m = require(key, use)
    _ensure_hf_env()
    if quantize is None:
        quantize = 8 if total_ram_gb() >= 30 else 4
    from mflux.models.common.config import ModelConfig
    cfg = getattr(ModelConfig, m["config"])()
    if lora_paths and m["kind"] not in ("flux2", "z_image"):
        raise SystemExit(f"✗ {key} 這裡還沒接 LoRA（目前只接 FLUX.2、Z-Image）")
    if m["kind"] == "flux2":
        custom_te = text_encoder_path or (m.get("text_encoder_repo") if m.get("uncensored") else None)
        from mflux.models.flux2.variants import Flux2Klein, Flux2KleinEdit
        cls = Flux2KleinEdit if edit else Flux2Klein

        if custom_te:
            from mflux.models.flux2.flux2_initializer import Flux2Initializer
            orig_load_weights = Flux2Initializer._load_weights

            def hooked_load_weights(model_path):
                weights = orig_load_weights(model_path)
                try:
                    print(f"⚡ 正在掛載無審查／自訂 Text Encoder: {custom_te}...", flush=True)
                    te_weights = _load_text_encoder_weights(custom_te)
                    weights.components["text_encoder"] = te_weights
                    print("✓ 無審查 Text Encoder 掛載成功", flush=True)
                except Exception as e:
                    print(f"⚠️ 無審查 Text Encoder 掛載失敗 ({e})，自動使用預設 Text Encoder", flush=True)
                return weights

            Flux2Initializer._load_weights = hooked_load_weights
            try:
                model = _with_negative(cls)(
                    quantize=quantize, model_config=cfg, lora_paths=lora_paths, lora_scales=lora_scales)
            finally:
                Flux2Initializer._load_weights = orig_load_weights
        else:
            model = _with_negative(cls)(
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
             negative_prompt=None, image_paths=None, step_callback=None):
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

        cb = None
        if step_callback and hasattr(model, "callbacks"):
            class _StepProgressCallback:
                def call_before_loop(self, seed, prompt, latents, config, **kwargs):
                    step_callback(0, config.num_inference_steps, "開始降噪…")

                def call_in_loop(self, t, seed, prompt, latents, config, time_steps=None, **kwargs):
                    cur = getattr(time_steps, "n", None)
                    if cur is None:
                        cur = t + 1 if isinstance(t, int) else 1
                    step_callback(cur, config.num_inference_steps, f"降噪中（第 {cur}/{config.num_inference_steps} 步）")

                def call_after_loop(self, seed, prompt, latents, config, **kwargs):
                    step_callback(config.num_inference_steps, config.num_inference_steps, "解碼影像中…")

            cb = _StepProgressCallback()
            model.callbacks.register(cb)

        try:
            return model.generate_image(**kw)
        finally:
            if cb and hasattr(model, "callbacks"):
                if cb in getattr(model.callbacks, "in_loop", []):
                    model.callbacks.in_loop.remove(cb)
                if cb in getattr(model.callbacks, "before_loop", []):
                    model.callbacks.before_loop.remove(cb)
                if cb in getattr(model.callbacks, "after_loop", []):
                    model.callbacks.after_loop.remove(cb)
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
