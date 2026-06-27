# toolchain.md — 工具鏈、模型與安裝指南（含踩過的雷）

本專案在 **Apple Silicon Mac（基礎款 MacBook Pro M5 / 32GB、macOS 26）** 上做本地端 AI 圖片生成。本文記錄用到哪些 tool / model、如何安裝下載，以及實作過程踩過、已驗證的地雷與規避方式。

> 路徑慣例：所有指令一律**從專案根目錄執行**（腳本以 CWD＝專案根載入 `workflows/`、寫入 `./outputs`）。

---

## 1. 工具總覽

| 工具 | 角色 | 安裝 |
| --- | --- | --- |
| **ComfyUI** | 主算圖後端（PyTorch-MPS），唯一能跑硬鎖臉（IP-Adapter / FaceID）的本地路徑 | `setup.sh` 內 `git clone` + `pip install -r ComfyUI/requirements.txt` |
| **mflux** | MLX 原生 CLI，無鎖臉草稿／批次生成（`mflux-generate`、`mflux-generate-qwen`、`mflux-generate-z-image-turbo`） | `uv pip install mflux` |
| **Draw Things**（選用） | Metal 原生 App，IP-Adapter FaceID / PuLID 鎖臉的快速路徑 | App Store；HTTP API 在 `127.0.0.1:7860` |
| **ComfyUI-Impact-Pack / -Subpack** | FaceDetailer / 臉部偵測 | `git clone` 進 `ComfyUI/custom_nodes/`，Subpack 跑 `python install.py` |
| **insightface + onnxruntime**（選用，FaceID） | ArcFace 身分鎖臉 | `uv pip install insightface onnxruntime`（進 ComfyUI venv） |
| **uv** | 建虛擬環境／裝 wheel（避開系統 Python 太新無 wheel） | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

### 主要程式進入點
- `scripts/my_imagen_v2.py` — 現役 CLI（ComfyUI + `workflows/workflow_api_face_fix.json` plus-face 管線，KSampler 30 步 / FaceDetailer 25 步）。
- `recipes/*.py` — 各式獨立生成腳本（mflux + FLUX.2 / Qwen-Image / Z-Image）。
- `start_backend.sh` — 啟動 ComfyUI 後端（port 8188）。

---

## 2. 模型總覽

| 模型 | 用途 | 來源 / 下載 | 需 HF token |
| --- | --- | --- | --- |
| **Juggernaut XL（v9 Lightning）** `juggernautXL_v9Rdphoto2Lightning.safetensors` | ComfyUI 寫實主模型 | `download_model.sh` → `ComfyUI/models/checkpoints/` | 否 |
| **FLUX.1-dev-8bit** `mlx-community/FLUX.1-dev-8bit` | mflux 8-bit 寫實 | mflux 首次執行自動拉 HF | 是（gated） |
| **FLUX.2-klein-9B** | mflux 底模 | HF（mlx-community） | 是（gated） |
| **Qwen-Image-2512(-4bit)** | mflux 編輯／生成 | HF（mlx-community） | 視版本 |
| **Z-Image-Turbo**（Tongyi-MAI） | mflux turbo 草稿（6B，6 步） | HF | 否 |
| **Mac 修正版 VAE** | 修 MPS VAE 解碼 | `download_model.sh` → `ComfyUI/models/vae/` | 否 |
| **YOLO 偵測器** | FaceDetailer 臉部偵測 | `download_model.sh` | 否 |
| FaceID 套件（選用）：`buffalo_l`、`CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`、IP-Adapter plus-face | 硬鎖臉 | `ComfyUI/models/insightface/models/buffalo_l/` 等 | 部分 |

---

## 3. 安裝 / 部署步驟

```bash
# 1) 基礎環境（ComfyUI + venv + torch-MPS）
cd ~/claude/image-gen
chmod +x *.sh
./setup.sh

# 2) 影像依賴
source venv/bin/activate
pip install ultralytics segment-anything opencv-python-headless pandas imageio-ffmpeg

# 3) 臉部偵測器
cd ComfyUI/custom_nodes
git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git
git clone https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git
cd ComfyUI-Impact-Subpack && python install.py
cd ../../..

# 4) 模型包
./download_model.sh

# 5)（選用）mflux MLX 路徑
uv pip install mflux
```

### HF gated 模型下載（FLUX.2 / Qwen-Image 等）
HF token 放在**未進版控的本機檔**，用 subshell 安全載入，讓 `huggingface_hub` 自動讀 `HF_TOKEN`：
```bash
set -a; source <你的token檔>; set +a
mflux-generate --model mlx-community/FLUX.1-dev-8bit ...   # 自動帶 token
```
> 🔒 **絕不**把 token 當 `--token <值>` 字面參數（會進 shell history / log），也**絕不** commit token 檔（已列入 `.gitignore`）。

---

## 4. 已踩過的雷（規避指南）

### 環境 / 路徑
1. **系統 Python 太新無 wheel** — macOS 系統 Python 3.14 對多數套件沒有預編 wheel。→ 用 **`uv` 建 3.12 env**，別硬裝系統 Python。
2. **搬專案目錄會整碗打翻** — 移動專案根會同時弄壞「硬編絕對路徑」與「venv」：`venv/bin/activate` 裡的 `VIRTUAL_ENV` 仍指舊路徑 → `python: command not found`。→ **一律用相對路徑**；真要搬，對整個 venv 文字檔（`bin/activate*`、`pyvenv.cfg`、~128 個 console-script shebang）做字串取代。`.pyc` 內舊路徑只影響 traceback，可不動。
3. **後端啟動最穩走絕對 venv python** — `source venv/bin/activate; python main.py` 在搬家後會壞。最穩：`venv/bin/python ComfyUI/main.py --force-fp16`（nohup 常駐 port 8188）。
4. **一律從專案根執行** — 腳本以 CWD 載入 `workflows/...`、寫 `./outputs`，face 參考圖也走相對路徑（script 自己 `shutil.copy` 進 `ComfyUI/input/`）。換目錄執行會找不到 workflow。

### 速度 / 引擎選擇
5. **基礎 M5 上 mflux 仍慢（compute-bound）** — bf16/q8/q4 量化對速度幾乎無感（bf16 最慢，每步讀 12GB 權重）；高解析每步時間飆升＝散熱節流。瓶頸是 10 核 M5 GPU 算力，不是記憶體。→ 別期待「換 MLX 就會快」；mflux 當無鎖臉草稿/批次，主力鎖臉走 ComfyUI 或 Draw Things。
6. **mflux 無內建鎖臉** — 無法取代 IP-Adapter 鎖臉管線；要身分一致只能 ComfyUI（FaceID/plus-face）或 Draw Things。

### 鎖臉（ComfyUI / FaceID）
7. **KSampler 維持 30 步** — 減步數會讓臉相似度與品質明顯崩；30 步為定案，別為了加速減步。
8. **`clip_vision_g.safetensors` 其實就是 ViT-H** — 只是檔名誤標（逐位元組相同），不是配錯。FaceID 用**檔名 regex** 挑 clip_vision，需備 `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`；insightface 放 `ComfyUI/models/insightface/models/buffalo_l/`。
9. **特寫 ref 偵測不到臉 + 多圖被縮成第一張尺寸** — SCRFD 對「臉佔滿」的 ref 會 `No face detected`；ComfyUI `ImageBatch` 把多張 ref 強縮成第一張尺寸→變形。→ ref 預處理：偵測不到加灰邊框、一律輸出正方 **640×640**。
10. **insightface 安裝** — `uv pip install insightface onnxruntime` 進現有 ComfyUI venv 即可（insightface 1.0.1 有 py3.14 wheel，免重建環境）。

### 高解析 / VRAM
11. **單次 VAE 解碼高解析會 OOM** — `MPS backend out of memory`。→ 改用 **`VAEDecodeTiled`**（6 個全 required：`tile_size 512 / overlap 64 / temporal_size 64 / temporal_overlap 8`）做 4K/8K，`overlap 64` 達單張內零接縫。
12. **連續批次 VRAM 累積** — 每張 POST `/free {"free_memory":true,"unload_models":true}`；長批次前重啟伺服器。

### Draw Things（選用）
13. **HTTP API 傳不進參考圖** — `/sdapi/v1/txt2img`（A1111 相容子集，port 7860）無法經 API 夾帶 IP-Adapter/ControlNet 參考圖（送 `init_images`/未知 key 會被拒或 422）。→ 鎖臉在 **GUI Moodboard / Control Input** 掛好，HTTP 腳本**只送 prompt/seed/steps/guidance_scale/sampler、不送 `controls`**（送了會覆寫 GUI）。注意 DT 用 `guidance_scale`（非 `cfg_scale`）、`strength`（=denoise）。

---

## 5. 排除在版控之外的東西（見 `.gitignore`）
`humming`（HF token）、`ComfyUI/`、`venv/`、`.venv-*/`（環境）、`outputs/`、`models/`、`characters/`、`refs/`（大型/個人素材）、個人 `prompts/`、`runners/`（本機工作腳本）。這些保留在本機、**不**進公開 repo。
