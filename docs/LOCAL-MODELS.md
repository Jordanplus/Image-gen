# 本機 Local Models — 清單與使用方法

> **Mac mini M4（Apple Silicon）本機所有 local AI model 與用法。**
> 動機：避免重蹈覆轍——曾因 ① mflux **CLI 載不動 FLUX.2** ② 生圖腳本散落各 session 的
> `/private/tmp/.../scratchpad`（會被清）而重複摸索半天才找回方法。
> **規範：每次用 local model 做事 → 腳本放 `image-gen/recipes/`、用法更新此檔。**
> Last updated: 2026-09-15（新增「商用／個人」兩組用途，mflux 升 0.19.1；立繪寫法探針、Z-Image-Turbo 4-bit、LoRA 外掛）

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

## 兩組用途：商用（自製遊戲）／個人（旅遊生圖、修照片）

> **規則：商用只准可商用授權的模型。** `recipes/local_models.py` 的 `require(key, "commercial")`
> 遇到非商用授權會直接中止，商用腳本一律經過它。授權出處：各模型 Hugging Face 模型卡（2026-09-15 查）。
> 一律用 mflux 的 python、從專案根目錄跑：`~/.local/share/uv/tools/mflux/bin/python recipes/...`；產出在 `outputs/`（不進版控）。

| 模型 key | mflux 設定／HF repo | 授權 | 商用 | 蒸餾 | 用途 | 實抓大小 |
|---|---|---|---|---|---|---|
| `klein-4b` | `flux2_klein_4b`／black-forest-labs/FLUX.2-klein-4B | Apache-2.0 | ✅ | 是 | 立繪主力、快速草稿、參考圖編輯 | 15GB |
| `klein-base-4b` | `flux2_klein_base_4b`／black-forest-labs/FLUX.2-klein-base-4B | Apache-2.0 | ✅ | 否 | 官方設定下偏繪畫風、服裝照 prompt，但年齡幾乎改不動、一張 16.6 分；可留給要繪畫感的少量主視覺、LoRA 訓練。**2026-09-16 本機權重已刪、也不再預抓**，要用會重新下載 | 15GB |
| `z-image` | `z_image`／Tongyi-MAI/Z-Image | Apache-2.0 | ✅ | 否 | 官方設定下雜訊消失，但服裝偏離 prompt、一張約 31 分；不建議用在立繪。**2026-09-16 本機權重已刪、也不再預抓**，要用會重新下載 | 19GB |
| `z-image-turbo` | `z_image_turbo`／Tongyi-MAI/Z-Image-Turbo | Apache-2.0 | ✅ | 是 | 官方權重是 F32：**24GB 機器生到第 2 步記憶體不足被砍**，這台請用下一列 | 31GB |
| `z-image-turbo-q4` | `z_image_turbo`／filipstrand/Z-Image-Turbo-mflux-4bit | 轉檔者標 Tongyi Qianwen License（與官方標籤不一致） | ❌（先歸個人） | 是 | 寫實照片感強；768×1152 每張約 173 秒、峰值 6.4GB；換 seed 臉和姿勢幾乎不變；近拍容易出現雀斑（要靠 `--skin beauty` 壓）。**2026-09-16 本機權重已刪** | 5.9GB |
| `qwen-image-2512` | `qwen_image`／mlx-community/Qwen-Image-2512-4bit | Apache-2.0 | ✅ | 否 | 6 月場景圖用；立繪測試時記憶體吃緊、每步 83 秒而中止。**2026-09-16 本機權重已刪**，`recipes/gen_photo_v2.py` 等 6 支場景圖腳本再跑會重新下載（約 37 分） | 24GB |
| `seedvr2-3b` | `seedvr2_3b`／numz/SeedVR2_comfyUI | Apache-2.0 | ✅ | — | 放大（兩組共用） | 6.8GB |
| `klein-9b` | `flux2_klein_9b`／black-forest-labs/FLUX.2-klein-9B | FLUX Non-Commercial License v2.1 | ❌ | 是 | 個人：修照片、把自己放進旅遊圖 | 約 32GB |

「蒸餾」＝把提示詞引導強度固定進模型換取少步數，代價是**不跑負面提示詞**。
原本推測遊戲立繪的「斑點壓不掉、改年齡數字沒反應」與此有關（The-Age-of-Exploration `tools/art-pipeline/FLUX2-KLEIN-PROMPT-LESSONS.md` §3、§4），
**2026-09-15 兩輪對照（含官方設定重測）都不支持這個推測**：同角色同 seed，klein-4B 從 19 → 35 歲明顯變老、皮膚乾淨；非蒸餾版年齡幾乎改不動（見下方實測）。斑點問題兩輪都沒有重現，仍未驗證。
**使用者的評比重點是畫質與風格，不是斑點／年齡**（2026-09-15 表明），之後的對照以畫質為準、直接看圖挑。

### 腳本
| 腳本 | 組別 | 用途 |
|---|---|---|
| `recipes/local_models.py` | 共用 | 模型清單、授權把關、載入、FLUX.2 自訂負面提示詞包裝、SeedVR2 相容修補 |
| `recipes/prefetch_models.py --set commercial\|personal\|all` | 共用 | 預抓並逐一生小圖驗證（新機器照這支建） |
| `recipes/commercial/ab_character_cfg.py` | 商用 | 蒸餾 vs 非蒸餾＋負面提示詞的角色立繪對照（斑點、年齡數字、速度），輸出 360px 對照表＋`results.json` |
| `recipes/commercial/portrait_style_probe.py` | 商用（`--use personal` 可個人） | 同一角色多種寫法 × 多種膚質 × 多顆 seed 對照；`--model`、`--lora 路徑或 org/repo:檔名`（LoRA／LoKr）、`--low-ram`、`--skin`（clean／fair／porcelain／beauty／natural，商用預設 clean、個人預設 fair）；預設寫實照片風（`--painted` 才用繪畫句）；不進版控的本機寫法放 `portrait_variants_local.py` |
| `recipes/personal/retouch_face.py` | 個人 | 真實照片臉部瑕疵：找臉 → 裁切 → klein 編輯 → 高解析時 SeedVR2 放大回去 → 羽化貼回；臉以外像素不動 |
| `recipes/personal/travel_with_me.py` | 個人 | 1–3 張臉部照片當參考，把自己放進旅遊場景 |

### 已實測（Mac mini M4 24GB，mflux 0.19.1）
- klein-4B：512² 4 步 21 秒；768×1152 6 步 62 秒。
- 修圖流程（klein-4B、AI 生成的 832×1216 測試人像）：編輯 163 秒；裁切框外像素與原圖完全相同（0／319,488 不同），貼回邊界看不出接縫。
- **真實照片修圖**（klein-9B；手機正面近距離自拍 1836×4080；`--edit-size 768`＋SeedVR2 放大回 1536 再拉到裁切框大小）：全程 277 秒，沒被砍。
  色斑、痣、細痕修掉、黑眼圈變淡，臉型五官保留，遮罩邊緣看不出接縫；**但皮膚被磨平、毛孔排列變得規則有人工感（推測是 SeedVR2 放大補出的紋理），睫毛被重畫得較濃**。
  舊版輸出 JPEG 讓臉以外也被重新壓縮（框外平均差 1.73、最大 12），已改預設輸出 PNG。
  已加 `--strength`（修圖強度）與 `--softness`（SeedVR2 柔化）。`--strength` 用上面這張的結果模擬 0.5／0.7／1.0（線性混合，效果等同實際加參數，
  `outputs/personal_test/me_front_strength_preview.jpg`）：0.5 斑點只淡化；**0.7 斑點大致消失、皮膚仍自然（設為預設）**；1.0 像磨皮。`--softness` 尚未實測。
- **旅遊合成**（klein-9B；參考＝正面＋四分之三側臉兩張真實照片，自動裁臉 640；輸出 768×1120；1 顆 seed）：生成 274 秒、全程 4.6 分鐘，
  程序最大常駐記憶體 8.8GB，swap 沒有再增加。**長相保留得很好**（臉型、五官、鬍渣、髮型），場景（布拉格石橋、河、老城）寫實；
  但**連參考照裡的灰 T 恤和左耳耳機都照搬**，構圖是自拍視角。要換衣服或拿掉耳機得在 `--scene` 寫明（例：`wearing a navy linen shirt, no earphones`，未實測）。
  24GB 上「768×1120 輸出＋兩張 640 參考」可跑；更大尺寸未測。
- **商用組角色對照**（`outputs/commercial_ab/20260915_114402/`；768×1152、seed 1131265990、同一段 prompt，膚質句刻意保留 `fine natural texture`）：

  | 模型與設定 | 每張 | 19 → 35 歲 | 皮膚／畫面 |
  |---|---|---|---|
  | klein-4B（6 步、guidance 1.0） | 62–65 秒 | **明顯變老**（額紋、眼尾紋、法令紋），仍是同一張臉 | 寫實、無斑點 |
  | klein-base-4B（28 步、guidance 4、4-bit、負面提示詞） | 約 9.4 分 | 只有法令紋略深 | 蠟感、偏橘、像 3D 渲染 |
  | Z-Image base（28 步、guidance 4、4-bit、負面提示詞） | 約 18 分＊ | 有變化 | 偏黃、顆粒雜訊，表情與服裝偏離 prompt |
  | klein-base-4B **官方設定**（50 步、guidance 1.5、8-bit、負面提示詞） | 約 16.6 分 | 幾乎沒變 | 蠟感減輕、偏繪畫風，服裝照 prompt（高領、綁帶） |
  | Z-Image base **官方設定**（50 步、guidance 4、8-bit、負面提示詞） | 約 31 分 | 幾乎沒變 | 雜訊消失、柔和繪畫風；但領口改成低胸，偏離 prompt |

  ＊Z-Image 首輪期間與 klein-9B 下載測試撞在一起（swap 用到 11.8GB），秒數偏慢。官方設定重測（`outputs/commercial_ab/20260915_131202_official/`，設定取 mflux 文件範例）期間沒有其他模型在跑。
  所有版本皮膚都乾淨，斑點問題兩輪都沒重現；樣本只有 1 個角色 × 1 顆 seed。
  ⇒ **商用組批次立繪維持 klein-4B**：年齡反應最明顯、一張約 1 分鐘。非蒸餾版換官方設定後畫質變好，但年齡一樣改不動，且慢 16–30 倍
  （45 位 × 2 顆 seed 用 klein-base-4B 在這台約要 25 小時）。
  若美術方向要「繪畫感」，klein-base-4B 官方設定比 klein-4B 更貼近 prompt 的 painted 風格（klein-4B 會畫成照片），可留給少量主視覺。
  大幅改年齡（19 → 35）在 klein-4B 有效；小幅（20 → 19、44 → 38）無效（LESSONS §3）。
- **立繪寫法探針**（klein-4B；`outputs/commercial_style/20260915_191718/contact.jpg`；4 種寫法 × 2 顆 seed，每張約 65 秒）：只改 prompt 就保留 klein-4B 的寫實畫質並加上性感感。
  使用者選定「露肩＋低胸＋柔光」（襯衣滑落雙肩、低胸綁帶束腹、暖色窗光、帶笑直視）；缺點是束腹偏舞台戲服、時代感稍弱。
- **Z-Image-Turbo**：官方 F32 權重（31GB）在 24GB 上生到第 2 步記憶體不足被砍；4-bit 版（`z-image-turbo-q4`＋`--low-ram`）768×1152 每張 172–174 秒、峰值 6.4GB、可用記憶體最低 80%。照片感強，但兩顆 seed 的臉和姿勢幾乎一樣。
- **klein-9B＋LoRA**（個人用途）：mflux 0.19.1 可直接掛 BFL 命名的一般 LoRA 與 LyCORIS LoKr（實測鍵名全部對上）；768×1152 每張 90–108 秒、704×1216 每張 85–101 秒，但 24GB 上可用記憶體最低掉到 14–18%（再大的尺寸等 32GB 機器）。
- **膚色偏黃怎麼改**（klein-9B 這類蒸餾模型不吃負面提示詞，只能改正面描述）：風格句的 `warm soft window light`／`muted warm palette` 與膚質句的 `warm glow` 是主因。
  `--skin fair` 換成中性日光＋白皙膚色句，膚色明顯變白且保留自然光線（個人用途已設為預設）；`--skin porcelain` 更白但整個畫面連背景都轉冷、氣色偏弱。
- SeedVR2-3B（套相容修補）：1024² → 1536² 共 70 秒，MLX 峰值記憶體 18GB（24GB 機器上不能和其他模型同時跑）。
  和 LANCZOS 拉伸並排看（`outputs/mflux_check/seedvr2_vs_lanczos_detail.png`）：睫毛、虹膜紋路、眉毛、毛孔**明顯補出細節**；
  皮膚紋理略偏銳利，必要時調 `softness`（0–1）。它也會把原有的斑點放大得更清楚，所以修圖流程是「先修再放大」。

### 已知問題與規避
- **FLUX.2 沒開放負面提示詞**：`mflux-generate-flux2(-edit)` 會拒收 `--negative-prompt`；程式內部把負面詞寫死成空白，但 guidance>1（非蒸餾 base 版）仍會做 CFG。要自訂負面詞請用 `local_models.load()`（包裝依賴 mflux 內部 `_encode_prompt_pair`，0.18.0／0.19.1 驗證）。
- **SeedVR2 在 mflux 0.19.1 + MLX 0.32.2 會 TypeError**：`models/seedvr2/.../attention.py` 以陣列次數呼叫 `mx.repeat`（第 80、99、121、132 行），MLX 0.32 只收整數。`local_models.load("seedvr2-3b", …)` 會自動套相容修補（小陣列單元測試全過，實際放大 1024→1536 已驗證）。**命令列 `mflux-upscale-seedvr2` 仍會壞，放大請走 python。**
- klein-9b-kv（編輯加速）、klein-base-9B、FLUX.1-Fill-dev 需先在 HF 網頁同意授權（目前帳號只開通 klein-9B）。
- 下載一律 `HF_HUB_DISABLE_XET=1`；HF 金鑰從 `~/claude_prjs/Higgingface.env` 讀（可用 `HF_TOKEN_FILE` 改路徑），不要印出。
- **直接呼叫 mflux 的 python API 不會自動省記憶體**：命令列每次都會掛 `MemorySaver`（編碼完就把文字編碼器移出記憶體；mflux 原始碼註解說可省 8–12GB），python API 沒有這一步。
  `local_models.load(..., single_run=True, low_ram=True)` 已照命令列的做法補上（`single_run` 只能用在生一張的情況，FLUX.2 每次生成都會重新編碼）。
  2026-09-15 實測：klein-9B 在 24GB 以 1024 輸出＋1024 參考圖編輯、沒掛 MemorySaver → 第 2 步被系統因記憶體不足砍掉；掛上後改 768 可跑完（每步約 49 秒，swap 約 9GB）。
- **24GB 機器的實測上限**：SeedVR2 放大上限 1536（1024→1536 峰值 18GB，超過的部分用 LANCZOS）；klein-9B 編輯先用 `--edit-size 768`；兩個模型不要同時跑。
- **mflux 的 LoRA 路徑寫 `org/repo:檔名` 會另外下載一份**到 `~/Library/Caches/mflux/loras`（不讀 HF 快取）→ 探針的 `resolve_lora()` 先用 `hf_hub_download` 取 HF 快取的本機路徑再交給 mflux。
- **klein-9B、Qwen 等較照字面的模型會把 painted 真的畫成繪畫**（klein-4B 會畫成照片）→ 探針預設改寫實照片風，並拿掉會帶出遊戲 CG 感的 `for a historical strategy game`。
- **人臉偵測**：正面照用 OpenCV 內建 Haar；四分之三側臉、半邊臉 Haar（含側臉 Haar）都抓不到，改用 OpenCV 官方 YuNet（存在 `~/.cache/image-gen/`，首次自動下載並核對 SHA-256）。
  修圖遮罩比例依正面近距離自拍校正（寬 0.42、高 0.50、中心下移 0.04，原本 0.50×0.62 會蓋到耳朵、頭髮、脖子）；非正面照先 `--dry-run` 看遮罩。
- **旅遊合成的參考照片會自動裁臉**（`--ref-size` 預設 768，`--no-face-crop` 關閉）：手機原圖整張當參考大多是背景與衣服，mflux 會以約 1MP 編碼，負擔大。

### 在 MacBook Pro（M5 32GB）建同一套
1. `uv tool install mflux`（已裝則 `uv tool upgrade mflux`），確認版本 0.19.1。
2. HF 金鑰放 `~/claude_prjs/Higgingface.env`（或 `export HF_TOKEN_FILE=<路徑>`），並在 HF 網頁確認已同意 klein-9B 授權。
3. 專案根目錄跑 `~/.local/share/uv/tools/mflux/bin/python recipes/prefetch_models.py --set all`（約 90GB，每個模型都會生一張小圖驗證）。
4. 32GB 放 klein-9B 應不太需要 swap，速度應比 Mac mini 快（未實測）。

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
- 24GB 機器跑 Turbo 用預先量化的 `filipstrand/Z-Image-Turbo-mflux-4bit`（`local_models` 的 `z-image-turbo-q4`）；官方 F32 版會記憶體不足。

### Bonsai-4B-Realistic-Uncensored（mflux）
- HF：`mlx-community/Bonsai-4B-Realistic-Uncensored`。uncensored 寫實人像。

### SDXL — Juggernaut XL / Pony（ComfyUI）
- **用途**：goods icon 寫實重生（juggernautXL_v9 Lightning）。
- **坑**：連續批次 **MPS OOM** → 每張 `/free` unload_models:true + `VAEDecodeTiled`（全 6 參）+ 長批次前重啟進程；validation 失敗不留 history 別誤判 OOM；批次加 fail-fast。
- 模型下載：`image-gen/download_*.sh`（juggernaut/pony/ipadapter/clipvision）

mflux 0.19.1 內建模型（`ModelConfig`＋命令列）：FLUX.1 `dev, schnell, krea-dev`（含 kontext／fill／redux／depth／controlnet）、
FLUX.2 `flux2-klein-4b/9b/9b-kv/base-4b/base-9b`（含多參考圖編輯）、`qwen-image`、`qwen-image-edit`（預設 2509）、
`fibo, fibo-lite, fibo-edit, fibo-edit-rmbg`、`ernie-image(-turbo)`、`z-image(-turbo)`、`ideogram4-fp8`、`krea2`、`lens`、`boogu`、
放大 `seedvr2-3b/7b`；訓練 `mflux-train`（FLUX.2 支援 klein-base-4b/9b）。

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
