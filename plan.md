# plan.md — 專案目錄重排

## 目標
把散在頂層的人為檔案（生圖 `.py`、runner `.sh`、prompt `.txt`、workflow JSON、文件）分類歸位，並修正連帶的路徑引用，讓專案結構清晰、可維護。基礎設施（ComfyUI / venv ×3）不動。

## 決策紀錄（2026-06-26，由 HTML 報告 `docs/2026-06-26_structure-review.html` 提供方案、使用者拍板）
- **重排幅度：方案 B「一步到位」** — 連 `.py → scripts/`、`.sh → runners/`、JSON → `workflows/`、舊版 → `legacy/` 一次搬完，並同步修正所有路徑引用。
- **舊檔處理：照建議** — README 收斂為純圖片站（移除影片/音樂段落）；舊版 `my_imagen.py`、`my_ai_2026.py` 與孤兒 `workflow_api_dual.json` **歸檔到 legacy/（不刪）**。

## 步驟與驗證
1. 建目錄 + 搬檔 + 清雜物 → verify：新頂層只剩分類目錄與根層慣例檔 ✅
2. 修正路徑引用（§6 清單）→ verify：grep 無殘留裸檔名引用、現役/legacy 鏈路皆指向新路徑 ✅
3. Python 語法檢查 → verify：`py_compile` 三個 `.py` 全通過 ✅
4. 更新 README（移除影片/音樂、修正 `~/gemini→~/claude`、doc 連結與指令路徑）+ setup.sh 提示字串 → verify：README 無殘留 `my_video/my_music`、路徑指向新結構 ✅
5. 建立 plan.md / status.md 回寫決策 ✅

## 風險點（已處理）
- 腳本以**專案根為 CWD** 載入 workflow、寫 `./outputs`：搬 `.py`/JSON 後已將載入字串加 `workflows/`（含 `legacy/`）前綴；runner 改呼叫 `python scripts/my_imagen_v2.py`。執行慣例維持「從專案根執行」。
- `humming`（HF token，外部 subshell source 載入）**未搬動**，留根目錄避免斷掉 token 載入。
- `models/`（`guimei_test.sh` 絕對路徑指向 `models/flux_dev_8bit`）保留，僅刪空的 `flux2_klein/`。

## 後續補充（2026-06-27 完成）
- **prompts 筆記更新為現役寫法**：`prompts/jinlin*.txt` 的 `python my_imagen.py` → `python scripts/my_imagen_v2.py`；`--ref` 的舊 gemini 絕對路徑 → 相對 `refs/faces/...`（順手修好失效的 gemini 路徑）。
- **runner 路徑收斂**：runners 內 `--ref`/`--image-path`/`LOCAL_MODEL` 的絕對路徑 → 相對（`refs/faces/<name>.jpg`、`models/flux_dev_8bit`）。依據 `scripts/my_imagen_v2.py:84` 以 CWD（專案根）`shutil.copy` 開檔，相對路徑成立且不再因專案搬移而失效。
- **新增 `refs/faces/`** 作為鎖臉輸入統一放置處（含 README 說明慣例）。

## 待議（仍未動）
- face 輸入檔（`face01-04.jpg`、`gui01.jpg`、`wife03.jpg`）目前不在 repo，執行時放入 `refs/faces/` 即可。
