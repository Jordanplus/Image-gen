# 本機 Local Models — 清單與使用方法

> **Mac mini M4（Apple Silicon）本機所有 local AI model 與用法。**
> 動機：避免重蹈覆轍——曾因 ① mflux **CLI 載不動 FLUX.2** ② 生圖腳本散落各 session 的
> `/private/tmp/.../scratchpad`（會被清）而重複摸索半天才找回方法。
> **規範：每次用 local model 做事 → 腳本放 `image-gen/recipes/`、用法更新此檔。**
> Last updated: 2026-06-26

---

## 環境

| 後端 | 位置 | 跑法 |
|---|---|---|
| **mflux**（MLX；FLUX/Qwen/z-image/Bonsai…） | venv `~/.local/share/uv/tools/mflux/` | python = `~/.local/share/uv/tools/mflux/bin/python`（→ cpython-3.12）；CLI = `~/.local/bin/mflux-generate` |
| **ComfyUI**（SDXL/Juggernaut/Pony） | `~/claude/image-gen/ComfyUI/` | server + workflow JSON |
| **MLX / face venv** | `~/claude/image-gen/.venv-mlx`、`.venv-face` | |
| **HF model cache** | `~/.cache/huggingface/hub/` | |

通用環境變數：`export HF_HUB_ENABLE_HF_TRANSFER=0`（hf_transfer 會 hang）。
**勿設** `HF_HUB_OFFLINE=1`（會擋 diffusers component 解析，FLUX.2 直接報 vae 缺）。

---

## 生圖 Models

### ⭐ FLUX.2-klein-9B —— 寫實攝影主力
- **用途**：紀實攝影風（55 探險地、自然/建築/場景、裝飾物）。蒸餾 6 步、電影感真實照片。
- **HF**：`black-forest-labs/FLUX.2-klein-9B`（diffusers 結構；**只有一個 text_encoder，無 text_encoder_2**）
- **⚠️ CLI 載不動本機 cache（別浪費時間試）**：
  - `mflux-generate --base-model flux2-klein-9b` → `No root_path / download_url for component: vae`
  - `-m <snapshot dir>` → 假找不存在的 `text_encoder_2`（FLUX.2 沒這 component）
  - 單檔 `flux-2-klein-9b.safetensors` = 0B（LFS pointer 未拉）
  - 不是網路問題（繞 sandbox 連網也一樣）—— 純粹是 CLI 對此模型的載入 bug
- **✅ 正解 = python API（必須用 mflux venv python）**：
  ```python
  from mflux.models.common.config import ModelConfig
  from mflux.models.flux2.variants import Flux2Klein
  model = Flux2Klein(quantize=4, model_config=ModelConfig.flux2_klein_9b())
  img = model.generate_image(seed=42, prompt=PROMPT,
            num_inference_steps=6, width=1024, height=1024, guidance=1.0)
  img.save(path=OUT)
  ```
- **配方**：q4 / 6-step / guidance 1.0 / 無 negative。約 8s/step（1024²，M4）。
- **跑法**：`~/.local/share/uv/tools/mflux/bin/python recipes/gen_compass_flux.py`
- **範本**：`recipes/gen_compass_flux.py`（單張，argparse，最乾淨）、`recipes/flux2_resident.py`（批次常駐：模型載一次迴圈生 N 張，省重載）
- **構圖坑**：要「完整不裁切」→ prompt 強調 `entirely visible, centered, generous margin on all four sides, nothing cropped, nothing touching the edges`。小字母（如羅盤 EWSN）FLUX 生得淡，必要時後製疊字。

### Qwen-Image-2512（mflux base-model `qwen`）
- **用途**：自然類寫實。**photo 天花板**：自然/風景/動物成功；人文歷史/建築/沙漠/神話地 → 死命輸出油畫（攝影術前場景訓練資料只有畫）。故探險地人文站改用 FLUX.2。
- **坑**：`img.save` 不覆蓋（會加 `_N`）→ 生前先刪 raw；270–340s/張。
- 範本：`recipes/site_art_resident.py`、`recipes/gen_photo_v2.py`

### z-image / z-image-turbo（mflux base-model `z-image` / `z-image-turbo`）
- 範本：`recipes/z_image_resident.py`

### Bonsai-4B-Realistic-Uncensored（mflux）
- HF：`mlx-community/Bonsai-4B-Realistic-Uncensored`。uncensored 寫實人像。

### SDXL — Juggernaut XL / Pony（ComfyUI）
- **用途**：goods icon 寫實重生（juggernautXL_v9 Lightning）。
- **坑**：連續批次 **MPS OOM** → 每張 `/free` unload_models:true + `VAEDecodeTiled`（全 6 參）+ 長批次前重啟進程；validation 失敗不留 history 別誤判 OOM；批次加 fail-fast。
- 模型下載：`image-gen/download_*.sh`（juggernaut/pony/ipadapter/clipvision）

mflux 全部支援的 base-model：`dev, schnell, krea-dev, dev-krea, qwen, fibo(-lite/-edit), z-image(-turbo), flux2-klein-4b/9b/base`。

---

## 雲端對照（非 local，但同屬生圖）
- **Nano Banana Pro**（`gemini-3-pro-image`）：`The-Age-of-Exploration/tools/art-pipeline/art-creator/generate_image.py -m ultra`，需 `GEMINI_API_KEY`（`~/claude/api.env`，~1hr 短效）。強項：構圖/指令遵循；可生帶背景的完整裝飾；但易把物件頂到邊裁切（prompt 要強調留白）。

## 其他（非生圖）
- `whisper-large-v3-mlx`：語音轉文字。
- `docling-*`：文件版面解析。

---

## recipes/ 腳本索引
| 腳本 | 用途 |
|---|---|
| `gen_compass_flux.py` | FLUX.2 單張生圖範本（argparse，最簡乾淨，**從這支起步**） |
| `flux2_resident.py` | FLUX.2 批次常駐（載一次迴圈生，含 seed_for/crop_to_thumb） |
| `site_art_resident.py` / `site_art_gen.py` | 探險地 driver（讀 prompts JSON → 批次生） |
| `z_image_resident.py` | z-image 批次 |
| `gen_photo_v2.py` / `transform_to_photo.py` / `transform_v3.py` | 攝影風生成 / 後製轉換 |
| `gen_style_compare.py` / `contact_sheet.py` | 風格對照 / 接觸表 |
| `robust_download.py` | HF 模型穩健下載 |
| `canary_arch.py` | 架構探針 |

> ⚠️ 複製自 session scratchpad 的腳本含 hardcoded scratchpad 路徑，當**範本**參考；
> 實跑改路徑或直接仿 `gen_compass_flux.py`（路徑已對齊專案）。
