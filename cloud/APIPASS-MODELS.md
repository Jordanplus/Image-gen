# apipass.dev 圖像模型參考（可選模型清單）

> 抓取日期：2026-10-28（The-Age-of-Exploration session，user：「把這邊的選擇列入之後的建議」）。
> 來源：模型市場 https://apipass.dev/zh/app/market ＋兩個模型頁（nano-banana-2、gpt-image-2）。
> ⚠️ **不是全集**：市場頁寫共 71 個模型，這份只收到快照裡的 **19 個圖像模型**；用前到市場頁篩「Image Generation」核對有沒有新的。
> ⚠️ **價格會變**：表列是市場頁的最低通道現價（Starter），同一模型依通道、解析度、文生圖／改圖差很多（例：gpt-image-2 文生 1K low $0.005、改圖 1K medium Regular $0.045）。實際扣點以後台為準。
> ⚠️ **商用授權頁面沒寫**：要做商品／遊戲素材前，逐一到模型頁或原廠條款查。

## 怎麼叫用

```bash
# 任意 apipass 模型：-b apipass --apipass-model <API 模型 ID>
python cloud/generate_image.py -b apipass --apipass-model google/nano-banana-2 -p "..." -o out.png -q 2K -a 16:9
```

**API 模型 ID ＝ 頁面網址標識把第一個 `_` 換成 `/`**。已在模型頁核對過的：
`google/nano-banana-2`、`openai/gpt-image-2`（別名 `gpt-image-2`）、`openai/gpt-image-2.5-sunburst`／`-flare`（本 repo 預設）。
其餘列在表裡的是**照這個規則推的，沒逐一核對**——第一次用某個模型先試一張。

### ⚠️ 參考圖欄位每個模型不一樣（`apipass_gen.py` 目前只處理兩種）

| 模型 | 參考圖欄位 | adapter 現況 |
|---|---|---|
| `openai/gpt-image-2.5-*` | `input.input_urls` | ✅ 自動 |
| `openai/gpt-image-2` | `input.images`（有參考圖時上游自動走 `/edit`） | ✅（預設就送 `images`） |
| `google/nano-banana-2` | `input.image_input`（URL 陣列，最多 14 張，jpeg/png，每張 ≤30MB） | ❌ **adapter 送的是 `images`，參考圖可能被忽略**——`-b gemini -r ...` 改圖結果若跟參考圖無關，先查這點 |
| 其他 | 未查 | 用前看模型頁 |

另外 adapter 只取前 5 張參考圖（`images[:5]`），超過的不會報錯。

## 圖像模型（19 個；價格＝每張美元，現價／原價）

| 模型 | 頁面標識 | 推定 API ID | 能力 | 解析度 | 價格 |
|---|---|---|---|---|---|
| Nano Banana 2 | `google_nano-banana-2` | `google/nano-banana-2` ✔ | 文生圖、改圖（最多 14 張參考） | 1K/2K/4K | $0.014 / $0.070 |
| Nano Banana 2 Lite | `google_nano-banana-2-lite` | `google/nano-banana-2-lite` | 文生圖、改圖 | 1K | $0.009 / $0.034 |
| Nano Banana 2.1 | `google_nano-banana-2-1` | `google/nano-banana-2-1` | 文生圖、改圖（最多 10 張參考） | 4K | $0.009 / $0.034 |
| Nano Banana Pro | `google_nano-banana-pro` | `google/nano-banana-pro`（本 repo `-b gemini -m ultra`） | 文生圖 | — | $0.005 / $0.134 |
| GPT Image 2.5 | `openai_gpt-image-2.5` | `openai/gpt-image-2.5-sunburst`／`-flare` ✔ | 文生圖、改圖 | 1K/2K/4K | $0.001 / $0.050 |
| GPT Image 2 | `openai_gpt-image-2` | `openai/gpt-image-2` ✔ | 文生圖、改圖；`quality` low/medium/high | 1K/2K/4K | $0.005 / $0.015 |
| Flux 3 Klein（edit） | `flux-3-klein-edit` | 未知（標識沒有 `_`） | 文生圖、多參考改圖（最多 10 張） | 1K/2K/4K | $0.009 |
| flux-pro-image-2 | `flux_flux-pro-image-2` | `flux/flux-pro-image-2` | 文生圖、改圖、圖內文字 | — | $0.003 / $0.030 |
| Seedream 4 | `bytedance_seedream-v4` | `bytedance/seedream-v4` | 文生圖、改圖 | — | $0.003 / $0.030 |
| Seedream 4.5 | `bytedance_seedream-4.5` | `bytedance/seedream-4.5` | 文生圖、改圖 | — | $0.004 / $0.040 |
| Seedream 5 Lite | `seedream_seedream-5-lite-image` | `seedream/seedream-5-lite-image` | 文生圖 | — | $0.003 / $0.035 |
| Seedream 5 Pro | `seedream_seedream-5-pro-image` | `seedream/seedream-5-pro-image` | 文生圖、改圖 | — | $4.541（頁面原樣，量級可疑） |
| Wan 2.7 image | `wan_wan-2-7-image` | `wan/wan-2-7-image` | 文生圖 | — | $0.003 / $0.030 |
| Qwen Image 2 | `qwen_qwen-image-2` | `qwen/qwen-image-2` | 文生圖、圖內文字 | 2K | $0.003 / $0.035 |
| Qwen Image 2.1 | `qwen_qwen-image-2-1` | `qwen/qwen-image-2-1` | 文生圖、改圖 | — | $4.541（頁面原樣，量級可疑） |
| Z-Image Turbo | `z-image_turbo` | `z-image/turbo` | 文生圖、圖內文字 | 2K | $0.001 / $0.015 |
| Luma Photon | `luma_photon` | `luma/photon` | 文生圖、改圖 | — | $0.002 |
| Grok Imagine | `grok-imagine_extend` | `grok-imagine/extend` | 圖到圖（頁面以影片為主） | — | $0.001 / $0.050 |
| 去浮水印／文字 | `apipass_image-watermaker-remove` | `apipass/image-watermaker-remove` | 去浮水印、logo、圖內文字 | — | $0.002 |

✔ ＝ 已在模型頁核對；其餘是推定。

其他類別（不在本表）：影片 Vidu Q4、Seedance 2.0、Veo 3.1、Kling、海螺、Runway；音樂／語音 Suno V5、MiniMax Music、ElevenLabs；文字 Claude、GPT、Gemini、DeepSeek、Qwen。

## 依用途挑（建議，未逐一實測）

| 要做的事 | 先試 | 理由 |
|---|---|---|
| **保留構圖只改局部**（換天氣、換季節、修掉雜物） | GPT Image 2（改圖）、Nano Banana 2／2.1、Flux 3 Klein edit | 都支援參考圖改圖；Nano Banana 要先補 adapter 的 `image_input` |
| **跟既有一批圖同畫風** | 用當初那批的同一個模型 | 例：The-Age-of-Exploration 155 張港口全景（油畫風）是 `gpt-image-2` 畫的 |
| **圖內文字、地圖標註、文件感 UI** | flux-pro-image-2、Qwen Image 2、Z-Image Turbo、GPT Image | 頁面標了「圖內文字」 |
| **大量草稿、便宜試構圖** | GPT Image 2.5、Z-Image Turbo、Grok Imagine（$0.001 級） | 單價最低 |
| **4K 成品** | Nano Banana 2／2.1、Flux 3 Klein、GPT Image 2.5 | 標了 4K |
| **生圖後清掉 AI 假簽名／假字** | apipass 去浮水印 | 專做這件事 |

本機（免費、不外傳）的可商用選項仍見 `docs/LOCAL-MODELS.md`（klein-4B、Qwen-Image-2512；klein-9B 是非商用授權）。

## 金鑰

`generate_image.py` 讀 `APIPASS_API_KEY`（先讀 cwd 的 `.env`，再讀寫死的 `/Users/mcgradymac/claude_prjs/apipass.env`——那是 Mac mini 的路徑）。
**MacBook Pro M5**：金鑰在 `~/claude/api.env`，變數名是小寫 `apipass`；用前在同一條指令內轉成 `APIPASS_API_KEY`：

```bash
export APIPASS_API_KEY="$(grep '^apipass=' ~/claude/api.env | cut -d= -f2-)"
```

值**絕不** `cat`／`echo`／印出；確認存在只用 `grep -c '^apipass=' ~/claude/api.env`。
