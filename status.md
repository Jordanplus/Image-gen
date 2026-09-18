# status.md

## 2026-09-18：32GB M5 MacBook Pro 極致鎖臉（多圖特徵錨定）與無審查生圖架構落地
- **極致鎖臉架構升級（Multi-Reference Face Locking）**：
  - 以蘇菲·瑪索（Sophie Marceau）為基準測試資料，確立「正面高清主基準（`ref-03.jpeg`）＋ 側顏立體（`ref-01.jpg`）＋ 視角骨相（`ref-04.jpeg`）」最佳 3 圖互補黃金組合。
  - `recipes/commercial/portrait_style_probe.py` 升級支援動態多圖約束語法（`images 1, 2 and 3: keep identity, facial features, jawline identical to references`）。
  - 自動以 1024px 高清臉部裁切進行 Vision Encoder 交叉注意力錨定，徹底杜絕單圖在換姿勢時出現的臉盲與特徵漂移。
- **無審查能力實裝與落地（Uncensored Pipeline）**：
  - 成功於本機下載並掛載 `darknight9121/FLUX.2-klein-base-9B-bucket-uncensored` 無審查 Text Encoder（16.4GB 完整快取於 `~/.cache/huggingface/hub/`）。
  - 解除提示詞限制，完美直出大膽寫實寫真（如「性感蕾絲睡袍」、「微光半透真絲」、「濕身微透白襯衫」、「比基尼泳裝」等）。
  - 實測產出：`outputs/personal_style/gui/20260918_101844_klein-9b-uncensored/42.png`（768×1152，3 圖鎖臉，神韻五官精準還原，蕾絲透膚解剖結構自然，可用記憶體維持 37% 充裕）。
- **`make gui` 本機介面全面升級**：
  - 內建 `reference/` 圖庫快速勾選（預設選中「蘇菲·瑪索 3 圖經典鎖臉組」）與本機照片多選上傳（最多 3 張）。
  - 預覽卡片即時呈現縮圖與特徵鎖定狀態徽章（`🔒 已鎖定 3 張特徵 · 1024px 高清裁臉`）。
  - 預設推薦模型直接切換為 `klein-9b-uncensored`（8-bit 無審查·32GB 原生）。
- **膚色調性修復與多樣性擴充（8 款細分膚色）**：
  - 根治參考圖模式下膚色偏黃問題：五官輪廓與膚色解耦（鎖臉不再強鎖 90 年代老底片泛黃底色），白皙系自動置換環境暖光為清爽中性/冷調日光。
  - 擴充為 8 種細分膚色（極致冷白皮 ★預設、櫻花粉白、自然白皙、柔焦瓷白、暖白象牙、原生自然、乾淨膚質、陽光小麥）。
  - GUI 介面保持膚色下拉選單可用並支援自由覆蓋。
- **介面新增「🛑 關閉伺服器」功能**：
  - 介面右上角新增關閉按鈕，點擊二度確認後向後端 `/api/shutdown` 發送請求，安全終止背景 Python 服務並完整釋放 Apple Silicon 統一記憶體。
- **姿勢解剖結構優化與全新姿勢擴充**：
  - **修復坐木凳（`stool`）腿部畸變**：原 `legs crossed at the knee` 易造成 2D 擴散重疊與多肢錯誤，重構為「優雅斜並腿」經典寫真坐姿（雙腿併攏側斜自然下垂放地面），雙腿解剖清晰無畸變。
  - **新增「往前傾趴臥（`prone_forward`）」**：上身手肘支撐向前傾、弓背挺胸直視鏡頭。
  - **新增「趴在前方透明玻璃上（`glass_press`）」**：雙手手掌與胸口貼緊鏡頭前方透明玻璃，帶有清透倒影與微貼壓高光。
  - **新增「跪姿前傾（`kneel_lean`）」**：跪地雙手前撐、弓腰前俯視角。
  - 負面詞補強 `deformed limbs, deformed legs, extra legs, extra limbs, bad anatomy` 防護。
- **ComfyUI 獨立環境準備**：
  - 建立 Python 3.11 MPS 虛擬環境 (`venv`)，配置 `ComfyUI_PuLID_Flux_ll` 與 `ComfyUI-GGUF`。

## 2026-09-16：mflux 升級 0.19.1、解鎖 32GB M5 8-bit 與無審查設定、雙機型自動偵測適配
- **mflux 升級**：升級至 `v0.19.1`（搭配 `mlx 0.32.2`、`torch 2.14.0`、`huggingface-hub 1.31.0`）。
- **32GB M5 MacBook Pro 解鎖**：
  - 8-bit 量化（`quantize=8`）：消除 4-bit 量化造成的色塊與眼周微變形，實測 512×512 僅 8.44 秒，32GB 記憶體充裕且 0 swap。
  - 原生 1024×1024 / 1024×1536 尺寸與高畫質 1024px 臉部參考圖。
  - 模型常駐：解除過於激進的記憶體卸載（低壓防線由 15% 放寬至 5%），避免常駐模式下重複載入。
- **無審查設定與立繪寫法**：
  - `recipes/local_models.py` 支援 `klein-9b-uncensored`，支援自訂無審查 Text Encoder 與 LoRA 注入。
  - `recipes/commercial/portrait_style_probe.py` 預設改為 `klein-9b`，預設 `--use personal`，新增 6 款大膽寫實衣著風格與胸圍預設（`slender`、`maximum`）。
- **雙機型自動判斷適配（32GB vs 24GB）**：
  - **WebUI（`recipes/gui/app.py` & `index.html`）**：`/api/options` 動態回傳硬體規格與徽章；32GB 自動推薦 8-bit 原生模型與 1024×1536 尺寸，24GB 自動切換 4-bit 推薦與 704×1216 / 768×1152 尺寸並維持 15% 防線。
  - **手機端 PWA（`cloud/server.py`、`klein_worker.py`、`cloud/static/index.html`）**：新增 `/config` 接口，手機端連線時自動識別主機（32GB M5 原生 8-bit 40秒 vs 24GB 4-bit 90秒），下拉選單動態載入最適合的本地模型與解析度預設。

- 使用者評比重點是**畫質與風格**（不是斑點／年齡）→ 遊戲立繪用 klein-4B＋「露肩＋低胸＋柔光」寫法；測試一律寫實照片風。
- `recipes/commercial/portrait_style_probe.py`（新）：多種寫法 × 多顆 seed 對照；`--use personal`、`--lora`（LoRA／LoKr，自動改用 HF 快取路徑）、`--low-ram`、`--painted`、`--skin`（膚質／膚色：商用預設 clean、個人預設 fair 白皙）；本機私有寫法放不進版控的 `portrait_variants_local.py`。
- `recipes/local_models.py`：新增 `z-image-turbo`、`z-image-turbo-q4`、`qwen-image-2512`；`load()` 可帶 LoRA（FLUX.2、Z-Image）與預先量化模型。
- 實測（數字見 `docs/LOCAL-MODELS.md`）：Z-Image-Turbo 官方 F32 在 24GB 記憶體不足被砍 → 4-bit 版每張約 173 秒可跑；klein-9B＋LoRA 每張 90–108 秒但記憶體很緊；Qwen-Image-2512 記憶體吃緊時每步 83 秒而中止。依使用者要求精簡本機快取：刪掉 Z-Image 系列（19＋31＋5.5GB）、Qwen-Image-2512（24GB）、klein-base-4B（15GB）與測試用的 LoRA 外掛，預抓清單商用組只剩 klein-4b、seedvr2-3b；設定與實測數字都保留，要用會重新下載。
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
