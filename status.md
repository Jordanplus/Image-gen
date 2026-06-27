# status.md

## 最新狀態（2026-06-26）
**專案目錄重排（方案 B）完成。** 頂層由約 35 個散檔收斂為分類目錄；所有路徑引用已修正並通過驗證。

### 新目錄結構
```
image-gen/
├─ scripts/        my_imagen_v2.py（現役） + legacy/（my_imagen.py、my_ai_2026.py）
├─ runners/        guimei_*.sh、jinlin_pro*.sh、wife_pro.sh、guimei_test.sh
├─ prompts/        jinlin*.txt（指令筆記）
├─ workflows/      workflow_api_face_fix*.json（現役） + legacy/（舊版 + 孤兒 dual）
├─ refs/           ref_oruc.png、_batch_refs/
├─ docs/           METHODS.md、LOCAL-MODELS.md、test.md、video.md、*.html（含結構報告）
├─ characters/  outputs/  recipes/   （未動）
├─ models/         （保留；已刪空目錄 flux2_klein）
├─ README.md  plan.md  status.md  setup.sh  start_backend.sh  download_model.sh
├─ humming         （HF token，未動）
└─ ComfyUI/  venv/  .venv-face/  .venv-mlx/   （基礎設施，未動）
```

### 已套用的路徑修正
| 檔案 | 修正 |
| --- | --- |
| `scripts/my_imagen_v2.py` | workflow 載入 → `workflows/workflow_api_face_fix.json` |
| `scripts/legacy/my_imagen.py` | 3 個 workflow → `workflows/legacy/...` |
| `runners/*.sh`（6 個 pro/角色） | `python my_imagen_v2.py` → `python scripts/my_imagen_v2.py` |
| `README.md` | 移除影片/音樂段落；`~/gemini`→`~/claude`；doc 連結與指令改新路徑；加「專案結構」「執行慣例」 |
| `setup.sh` | 提示字串 `~/gemini`→`~/claude`、`my_imagen.py`→`scripts/my_imagen_v2.py` |

### 驗證結果
- 路徑引用 grep：無殘留裸檔名引用 ✅
- `py_compile` scripts/ 三檔：通過 ✅
- README：無殘留 `my_video.py` / `my_music.py` ✅

### 現役鏈路（重排後）
`runners/*.sh → python scripts/my_imagen_v2.py → workflows/workflow_api_face_fix.json → ./outputs`
（**從專案根目錄執行**；需先 `./start_backend.sh` 並 `source venv/bin/activate`）

### 2026-06-27 追加：路徑收斂
- **prompts/jinlin*.txt** 全部更新為現役寫法：`python scripts/my_imagen_v2.py` + `--ref refs/faces/...`（並修好原本失效的 gemini 絕對路徑）。
- **runners/*.sh** 的 `--ref`/`--image-path`/`LOCAL_MODEL` 絕對路徑 → 相對（`refs/faces/<name>.jpg`、`models/flux_dev_8bit`）。
- **新增 `refs/faces/`**（鎖臉輸入統一放置處，含 README 慣例說明）。
- 收斂後**現役鏈路全程相對路徑**，不再因專案搬移失效。face 輸入檔執行時放入 `refs/faces/`。

### 注意事項
- 所有 runner 與 `python scripts/...` 一律**從專案根執行**（CWD=根）。
- `humming`（HF token）未搬動，請維持原位與外部 source 載入方式。
