# status.md

## 2026-09-15（晚）：立繪寫法探針、Z-Image-Turbo 4-bit、LoRA 外掛
- 使用者評比重點是**畫質與風格**（不是斑點／年齡）→ 遊戲立繪用 klein-4B＋「露肩＋低胸＋柔光」寫法；測試一律寫實照片風。
- `recipes/commercial/portrait_style_probe.py`（新）：多種寫法 × 多顆 seed 對照；`--use personal`、`--lora`（LoRA／LoKr，自動改用 HF 快取路徑）、`--low-ram`、`--painted`、`--skin`（膚質／膚色：商用預設 clean、個人預設 fair 白皙）；本機私有寫法放不進版控的 `portrait_variants_local.py`。
- `recipes/local_models.py`：新增 `z-image-turbo`、`z-image-turbo-q4`、`qwen-image-2512`；`load()` 可帶 LoRA（FLUX.2、Z-Image）與預先量化模型。
- 實測（數字見 `docs/LOCAL-MODELS.md`）：Z-Image-Turbo 官方 F32 在 24GB 記憶體不足被砍 → 4-bit 版每張約 173 秒可跑；klein-9B＋LoRA 每張 90–108 秒但記憶體很緊；Qwen-Image-2512 記憶體吃緊時每步 83 秒而中止。已刪 Z-Image-Turbo 官方快取（31GB）。
- 未完成：MacBook Pro（M5 32GB）上重測 klein-9B＋LoRA 與 Z-Image-Turbo 官方版。

## 2026-09-15：本地模型分兩組建置（商用／個人），mflux 升 0.19.1
模型、授權、腳本、實測數字、已知問題、MacBook Pro 建置步驟都在 `docs/LOCAL-MODELS.md`「兩組用途」。

| 組別 | 模型（授權） | 腳本 |
| --- | --- | --- |
| 商用（自製遊戲） | klein-4B（Apache-2.0，立繪主力）、klein-base-4B／Z-Image base（Apache-2.0，候選）、SeedVR2-3B（Apache-2.0，放大） | `recipes/commercial/ab_character_cfg.py`；`recipes/local_models.py` 會擋非商用授權 |
| 個人（不商用） | klein-9B（FLUX 非商用授權）、klein-4B、SeedVR2-3B | `recipes/personal/retouch_face.py`、`recipes/personal/travel_with_me.py` |
| 共用 | — | `recipes/local_models.py`（清單＋授權把關＋載入）、`recipes/prefetch_models.py`（新機器預抓驗證） |

### 實測結論（Mac mini M4 24GB）
- 商用：同角色同 seed，**klein-4B 最好**（62 秒／張、19→35 歲明顯變老、無斑點）。非蒸餾版改用官方設定（8-bit、50 步）重測後畫質變好，但年齡幾乎改不動，且一張 16.6 分（klein-base-4B）／31 分（Z-Image，服裝還偏離 prompt）→ 批次立繪維持 klein-4B；klein-base-4B 可留給要繪畫感的少量主視覺。
- 個人：真實照片修圖 277 秒，去斑有效、長相保留；強度 1.0 像磨皮 → 預設改 0.7。旅遊合成 4.6 分鐘，長相保留很好，但會照搬參考照的衣服與耳機。
- 修掉的坑：SeedVR2 在 mflux 0.19.1＋MLX 0.32.2 會 TypeError（載入時自動相容修補）；python API 沒掛 MemorySaver 讓 klein-9B 被系統砍掉（已補）；Haar 抓不到側臉（加 YuNet 後備）；修圖遮罩太大（依真實自拍重新校正）；輸出 JPEG 二次壓縮（改預設 PNG）。

### 未完成
- `--softness` 實測；旅遊合成換衣服、較大尺寸；MacBook Pro（M5 32GB）實際建置。
- 模型快取在 `~/.cache/huggingface/hub`；個人照片與產出都在 `outputs/`（不進版控）。

## 2026-09-14：線上路線改用 gpt-image-2.5（預設 Sunburst）
OpenAI 2026-09-08 推出 gpt-image-2.5（Flare 快／Sunburst 品質高）。apipass 已登記
`openai/gpt-image-2.5`、`-flare`、`-sunburst`（送故意不合法的請求探測：回「參數錯誤」而非「找不到 model」，未扣點）。

| 檔案 | 改動 |
| --- | --- |
| `cloud/apipass_gen.py` | 預設 `openai/gpt-image-2.5-sunburst`；2.5 參考圖送 `input_urls`（2 仍送 `images`）、不送 `quality` |
| `cloud/server.py`、`static/index.html`、`static/sw.js` | 手機預設 Sunburst，選單加 Flare、保留 gpt-image-2 備援；2.5 寫 prompt 指令照官方 prompting guide（場景→主體→細節→限制、參考圖編號＋保留項），上限 120 字；快取 v4 |
| `cloud/generate_image.py` | `-b openai` → Sunburst（`-m fast` → Flare）；openai-direct 改 2.5：精確自訂尺寸、新增 `--openai-quality`（含 xhigh/max） |
| 文件 | `cloud/README.md`、`PHONE-APP.md`、根 `README.md`、`CLAUDE.md`、`docs/METHODS.md` 附錄 D、`requirements.txt`、`manifest.webmanifest` |

### 驗證（全離線、未花點數）
- 假 apipass 伺服器：2.5 送出欄位＝`prompt/aspect_ratio/resolution/input_urls`；gpt-image-2、nano-banana 維持 `images`（gpt-image-2 另帶 quality）✅
- openai-direct 尺寸換算：3 種解析度 × 5 種比例全部符合官方限制（16 的倍數、每邊 ≤3840、長寬比 ≤3:1、總像素上下限）✅
- 假 OpenAI SDK：generate / edit 的 model、size、quality 正確 ✅
- 手機後端：寫 prompt 指令（2.5 → 120 字＋參考圖編號）、`/generate` 預設 model 與參考圖轉交 ✅

### 未實測（使用者決定先不花點數）
- ~~apipass 2.5 實際出圖~~ → **2026-09-15 手機實測通過**：Sunburst / 16:9 / 4K 兩張，各約 10–12MB PNG（後端 log `refs=0`）。
- `input_urls` 是否接受 base64 data URI（apipass 文件只「建議」用 https 網址）→ 仍未測（上面兩張都沒帶參考圖）；若鎖臉／參考圖沒作用先查這點。
- openai-direct：本機無 `OPENAI_API_KEY`，只驗證了參數組裝。
- 手機後端（LaunchAgent `com.imagegen.server`）需重啟才載入新程式。

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
