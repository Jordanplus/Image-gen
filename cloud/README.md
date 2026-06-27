# ☁️ 線上生圖路線（apipass.dev：GPT-image-2 / Nano Banana）

本資料夾是 Image-gen 的**線上備援路線**，補在本機 ComfyUI 堆疊（SDXL / FLUX，見專案根 `docs/METHODS.md`）旁邊。
當你要的是**圖內文字 / 地圖 / 文件感 UI** 或臨時想用雲端模型對照時，走這條最快——
所有後端都經 **apipass.dev** 聚合閘道，**單一金鑰** `APIPASS_API_KEY`。

| 路線 | 在哪 | 何時用 |
| :--- | :--- | :--- |
| 本機 ComfyUI（SDXL/FLUX，鎖臉、4K Tiled） | 專案根 `scripts/`、`recipes/` | 寫實人像、量產、零成本、隱私 |
| **線上 apipass（本資料夾）** | `cloud/` | 圖內文字 / 文件 UI / 雲端模型快速對照、無本機 GPU 時 |

---

## 🔑 金鑰

集中於 `/Users/mcgradymac/claude_prjs/apipass.env` 的 `APIPASS_API_KEY=apk_...`，
`generate_image.py` import 時**自動載入**（先讀 cwd `.env`，再讀此檔）。
也可臨時 `export APIPASS_API_KEY=apk_...`。

> ⚠️ 金鑰只注入 env，**絕不** cat / Read / echo 其值。apipass key 只送往 `api.apipass.dev`。
> auto 模式會擋「送 key 給外部服務」——首次執行請用 `! python cloud/...` 或加 Bash 允許規則。

---

## 🚀 快速開始（從專案根或 `cloud/` 執行）

```bash
# 預設後端 = openai（gpt-image-2，線上首選）
python cloud/generate_image.py -p "a 16th-century world map cartouche with ornate latin labels" \
       -o out.png -q 2K -a 16:9

# 用 Gemini Nano Banana
python cloud/generate_image.py -b gemini -p "..." -o out.png -q 4K -m ultra

# Identity Lock：拿一張參考圖鎖角色，轉風格 / 換場景（image-to-image）
python cloud/generate_image.py -b openai -p "the same person, photorealistic portrait" \
       -o out.png -r ref.png

# 任意 apipass 模型（flux / qwen / seedream …）
python cloud/generate_image.py -b apipass --apipass-model flux/flux-pro-image-2 -p "..." -o out.png
```

A/B 對照（同 prompt 兩後端並排）：

```bash
python cloud/ab_compare.py -p "<你的 prompt>" -q 2K -a 16:9 -o cloud/ab_out
# 預設 A=gemini B=openai，皆經 apipass；缺 key 的那邊自動略過
```

底層 adapter 也可單獨用：

```bash
python cloud/apipass_gen.py --prompt-file p.txt -o out.png --aspect 16:9 -q 2K -r ref.png
```

---

## 🎛️ `generate_image.py` 旗標

| 旗標 | 說明 |
| :--- | :--- |
| `-b {openai,gemini,apipass,gemini-direct,openai-direct}` | 後端（前三者經 apipass.dev）：`openai`=gpt-image-2（**預設/首選**）/ `gemini`=nano-banana / `apipass`=自訂 model；`*-direct`=直連官方 SDK |
| `--apipass-model <id>` | `-b apipass` 時指定，如 `openai/gpt-image-2`、`google/nano-banana-pro`、`flux/flux-pro-image-2`、`qwen/qwen-image-2`、`seedream/seedream-5-lite-image` |
| `-m {standard,ultra,fast}` | 等級；gemini→`ultra`=nano-banana-pro / 其餘=nano-banana-2；openai→quality high/medium/low |
| `-q {1K,2K,4K}` | 解析度（apipass `input.resolution`）；省略＝模型預設 |
| `-a {1:1,16:9,9:16,4:3,3:4}` | 長寬比；省略＝模型預設 1:1 |
| `-r <img...>` | Identity Lock 參考圖（apipass 走 `input.images`，最多 5；direct 後端另計） |
| `-u {x2,x4}` | LANCZOS 後處理放大（純拉伸不增細節；真高解析用 `-q`） |
| `-s <int>` | Seed（僅 `gemini-direct` 生效；apipass / openai 忽略） |

---

## 📦 依賴

apipass 路線只需 **標準庫 + Pillow + python-dotenv**（系統 python3 已具備，無需 venv）。
`gemini-direct` 另需 `google-genai`、`openai-direct` 另需 `openai`（見 `requirements.txt`）。

---

## ⚙️ 運作原理（apipass adapter）

非同步任務制：`POST /api/v1/jobs/createTask` → 輪詢 `/api/v1/jobs/recordInfo` → 下載 CDN 圖（常為 JPEG，
`_save_image` 依副檔名正規化）。參考圖本地檔自動轉 `data:image/...;base64`（Identity Lock / image-to-image）。

> 🪤 **陷阱（已處理）**：`recordInfo` 會在 `param` 等欄位**原樣回吐輸入**（含參考圖 base64）。
> 結果抽取時 `_walk(skip=_ECHO_KEYS)` 會跳過這些子樹，否則會把**輸入參考圖誤當輸出**（「回傳同一張圖」）。
