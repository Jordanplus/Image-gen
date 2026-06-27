# Mac M-Series 本地端 AI 圖片創作站 CLI 終極專業版

這是一套專為 Mac M 系列晶片 (32GB+ 統一記憶體) 深度優化的本地端 AI 圖片創作站。集成了 **Juggernaut XL 寫實模型**、**核彈級臉部修復 (FaceID / IP-Adapter)**，**並以 VAEDecodeTiled 分塊解碼突破單次 VAE 解碼的 VRAM 上限，本地即可產出 4K / 8K 超高解析度影像（單張內零接縫）。**

> 📋 **生圖方法選用（純 prompt / IP-Adapter 鎖臉 / FLUX+PuLID）與本地操作指南見 [`docs/METHODS.md`](docs/METHODS.md)。**
>
> 🧰 **工具鏈、模型、安裝下載與踩雷規避見 [`toolchain.md`](toolchain.md)。**

> 📁 **本專案目錄結構見下方「專案結構」一節；2026-06-26 完成一次目錄重排，腳本/workflow/prompt/文件已分類歸位（細節見 [`status.md`](status.md)）。**

---

## 🗂️ 專案結構

```
image-gen/
├─ scripts/         生圖主程式
│  ├─ my_imagen_v2.py        ★現役（FaceID 臉部修復 → workflows/workflow_api_face_fix.json）
│  └─ legacy/                舊版存查（my_imagen.py）
├─ workflows/       ComfyUI workflow JSON（現役 face_fix；legacy/ 放舊版與孤兒）
├─ recipes/         獨立生成腳本（flux2_resident、gen_photo_v2、transform_v3…）
├─ docs/            文件（METHODS / LOCAL-MODELS）
├─ README.md  toolchain.md  plan.md  status.md
├─ setup.sh  start_backend.sh  download_model.sh
│
│  ── 以下保留在本機、未進版控（見 .gitignore）──
├─ runners/  prompts/        個人跑圖腳本／指令筆記
├─ refs/  characters/  outputs/  models/   參考素材／角色臉／產出
└─ ComfyUI/  venv/  .venv-*/  humming       基礎設施／HF token
```

> ⚠️ **執行慣例：所有 runner 與 `python scripts/...` 指令一律從專案根目錄執行**（腳本以專案根為 CWD 載入 `workflows/` 與寫入 `./outputs`）。

---

## 🛠️ 核心環境建置 (全自動安裝)

若要在新環境部署，或修復功能報錯，請依序執行：

### 1. 基礎環境設定
```bash
cd ~/claude/image-gen
chmod +x *.sh
./setup.sh
```

### 2. 安裝影像依賴套件
```bash
source venv/bin/activate
# 影像處理核心
pip install ultralytics segment-anything opencv-python-headless pandas imageio-ffmpeg matrix-client decorator gitpython

# 臉部偵測器核心
cd ComfyUI/custom_nodes
git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git
git clone https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git
cd ComfyUI-Impact-Subpack && python install.py
cd ../../..
```

### 3. 下載終極模型包
```bash
./download_model.sh
```
*(含：寫實模型、Mac 修正版 VAE、臉部鎖定模型、YOLO 偵測器)*

---

## 🚀 每日創作流程

### 步驟一：啟動算圖伺服器
```bash
cd ~/claude/image-gen && ./start_backend.sh
```

### 步驟二：呼叫 CLI 開始創作
```bash
cd ~/claude/image-gen && source venv/bin/activate
```

---

## 🎨 圖片生成：scripts/my_imagen_v2.py (臉部還原 100%)

### 📌 指令範例
```bash
python scripts/my_imagen_v2.py \
  --prompt "Raw photograph of a person standing on the beach, soft natural light, 35mm lens, f/5.6, 8k, cinematic" \
  --ref "./refs/faces/face1.jpg"
```

> 個人化的批次跑圖腳本放在本機 `runners/`（未進版控）；從專案根執行，須先啟動後端並 `source venv/bin/activate`。

---

## 🖼️ 超高解析度生圖：本地 4K / 8K（VAEDecodeTiled 分塊解碼）

> **2026-06-20 正式採用。** 在 32GB 統一記憶體上，把高解析度 latent **一次** VAE 解碼會 `MPS backend out of memory`。改用 **`VAEDecodeTiled`** 把整張 latent 切成 tile 逐塊解碼再拼回，**單張 VRAM 峰值大降** → 本地得以產出 **4K / 8K** 超高解析度影像。

- **工作流末端**：`… → LatentUpscale（階梯放大至目標解析度）→ KSampler refine → VAEDecodeTiled → Save`。
- **節點參數**：`tile_size 512 / overlap 64 / temporal_size 64 / temporal_overlap 8`（**6 個全 required**，缺任一則 validation 拒）。
- **單張內零接縫**：`overlap 64` 使相鄰 tile 重疊 64px 混合、邊界徹底融合。**實證** 1536×2240 金線刺繡／織紋高頻區 100% 像素零接縫（檢視頁 `<The-Age-of-Exploration>/docs/tile-check.html`）；更高解析度循同一技術。
- **連續批次**：每張 POST `/free {"free_memory":true,"unload_models":true}` 清 VRAM 累積 + 長批次前重啟伺服器（細節見 [`docs/METHODS.md`](docs/METHODS.md) 附錄 C）。

> 一般 1–2K 單張**不需要**（單張峰值本就夠）；唯解析度推高、單次 VAE 解碼撞 VRAM 上限時才換 Tiled。

---

## 📂 專案重要目錄說明

- `scripts/`：生圖主程式（現役 `my_imagen_v2.py`；`legacy/` 為舊版存查）。
- `workflows/`：ComfyUI workflow JSON（現役 `workflow_api_face_fix.json`；`legacy/` 為舊版與未引用的孤兒）。
- `recipes/`：獨立的 mflux / FLUX.2 / Qwen-Image / Z-Image 生成腳本。
- `docs/`：操作指南（`METHODS.md` / `LOCAL-MODELS.md`）。
- `runners/`、`prompts/`、`refs/`、`characters/`、`outputs/`：個人腳本與素材／產出，**保留在本機、未進版控**（見 `.gitignore`）。

---

## 💡 疑難排解
- **Q: 報錯 'Face Detector not found'？** 請確認已安裝 `Impact-Subpack` 並重啟伺服器。
- **Q: 報錯找不到 workflow JSON？** 請確認從**專案根目錄**執行（腳本以根為 CWD 載入 `workflows/...`）。
- **Q: 連線不到 ComfyUI 後台？** 請先在另一個終端機執行 `./start_backend.sh`。

---

> 🗒️ **歷史備註：** 影片 (AnimateDiff/SDXL) 與音樂 (MusicGen / Magenta RT2) 功能已於 2026-06-06 移除，專案聚焦回圖片生成。
