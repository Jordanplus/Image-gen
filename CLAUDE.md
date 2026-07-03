# Image-gen

Mac M 系列（32GB+ 統一記憶體）本地端 AI 圖片生成站，後端為 ComfyUI。
主打 Juggernaut XL 寫實模型 + FaceID / IP-Adapter 臉部修復，並以
VAEDecodeTiled 分塊解碼在本地產出 4K / 8K 影像。

## 佈局與主要腳本

- `scripts/my_imagen_v2.py`：現役生圖主程式（FaceID 臉部修復，讀
  `workflows/workflow_api_face_fix.json`）；`scripts/legacy/` 為舊版存查。
- `recipes/`：獨立生成腳本（mflux / FLUX.2 / Qwen-Image / Z-Image 等）。
- `cloud/`：線上備援路線（apipass.dev：GPT-image-2 / Nano Banana），
  含 `server.py`、`apipass_gen.py`、手機 App，見 `cloud/README.md`。
- `runners/`、`prompts/`、`refs/`、`outputs/`、`models/`、`ComfyUI/`、`venv/`：
  僅存本機、未進版控（見 `.gitignore`）。

## 執行慣例

- 所有 runner 與 `python scripts/...` 一律從專案根目錄執行
  （腳本以專案根為 CWD 載入 `workflows/`、產出寫入 `./outputs`）。
- 先 `./start_backend.sh` 啟動 ComfyUI 後端，再 `source venv/bin/activate`。

## 文件 SSOT

- 生圖方法選用：`docs/METHODS.md`；工具鏈／模型／安裝：`toolchain.md`；進度：`status.md`。
