# update-plan.md — 本地模型升級與驗證計畫（24GB vs 32GB 分工）

> **更新日期**：2026-10-03  
> **目標**：針對本專案的「商用角色立繪」與「個人照片修圖／旅遊合成」兩大核心本地需求，引進最新且更高效的模型版本，並依據硬體限制在 **Mac mini M4 (24GB)** 與 **MacBook Pro M5 (32GB)** 之間做精確分工。  
> **範圍備註**：雲端 API 備援路線（已接通 `gpt-image-2.5` 與 `gemini-3-pro-image`）表現穩定，本次計畫專注於**本地端（Local Models）**的架構升級。

---

## 🖥️ 硬體分工原則與執行機台劃分

| 任務領域 | 升級目標模型 | 預計執行機台 | 硬體原因與限制說明 |
|---|---|---|---|
| **領域一：商用立繪** | **Qwen-Image-2.1 (7.1B)** | **Mac mini M4 (24GB)**<br>（32GB 亦可） | 相比舊版 2512（27B）佔滿 24GB，新版 7.1B 量化後僅需 ~4–6GB VRAM，24GB 即可順暢運作，並具備完整 CFG 負面詞支援。 |
| **領域一：寫實鎖臉** | **Juggernaut XL Ragnarok** | **Mac mini M4 (24GB)**<br>（32GB 亦可） | 屬 SDXL 架構，記憶體需求與現役 v9 相同。24GB 順跑，直接相容現有 ComfyUI IP-Adapter 鎖臉與 FaceDetailer 管線。 |
| **領域二：個人修圖** | **FLUX.2-klein-9B-KV** | **MacBook Pro M5 (32GB)**<br>（專屬主力） | 針對多圖參考修圖優化的 KV 快取版。24GB 跑 9B 需限 768 且吃 swap；32GB 才能發揮 1024 解析度與快取加速的威力。 |
| **領域二：極致放大** | **SeedVR2-7B** | **MacBook Pro M5 (32GB)**<br>（⚠️ 獨佔，嚴禁在 24GB 跑） | 3B 版在 1024→1536 峰值已達 18GB；7B 模型在 24GB 必爆 OOM，必須在 32GB 設備上執行。 |

---

## 📋 升級項目詳細規劃

### 領域一：商用角色立繪（Game Art Pipeline）

#### 項目 1：Qwen-Image-2.1 (7.1B) 引入與評測
* **背景與痛點**：
  * 現役 `FLUX.2-klein-4B` 為蒸餾模型，無法吃負面提示詞。
  * 舊版 `Qwen-Image-2512`（27B）權重太大，24GB 載入後每步高達 83 秒且極易崩潰，本機快取已刪除。
* **新模型優勢**：
  * `mflux 0.20.0` 正式支援 Qwen-Image-2.1（7.1B，單流 Block-causal DiT + Qwen3-VL 編碼器）。
  * 支援 4-bit 量化（佔用約 4.5GB），原生支援 True CFG（負面提示詞生效），具備自然繪畫感與寫實混合能力。
* **執行機台**：Mac mini M4 (24GB)
* **實作步驟**：
  1. 升級環境：將 mflux 升級至 `>=0.20.0`（`uv tool upgrade mflux`）。
  2. 登錄模型：在 `recipes/local_models.py` 新增 `qwen-image-2.1`（4-bit 設定、預設步數與 guidance 建議）。
  3. 驗證腳本：建立測試腳本 `recipes/commercial/test_qwen21.py`，驗證立繪生成品質、年齡變動度、負面提示詞抑制雜訊/瑕疵之能力。
  4. 產出比對：與 `klein-4b` 進行 768×1152 速度與畫質橫向評比。

#### 項目 2：ComfyUI Juggernaut XL Ragnarok 替換升級
* **背景與痛點**：
  * 現役 `juggernautXL_v9Rdphoto2Lightning` 在複雜人體骨骼、手部與多角度特寫時仍偶有變形瑕疵。
* **新模型優勢**：
  * Civitai 釋出的 Ragnarok 為 Juggernaut SDXL 系列最終旗艦版，光影過渡更自然、手部與肢體解剖細節大幅改善。
  * 完全相容既有的 `workflow_api_face_fix.json`、IP-Adapter plus-face 與 FaceDetailer。
* **執行機台**：Mac mini M4 (24GB) 或 MacBook Pro M5 (32GB)
* **實作步驟**：
  1. 更新下載腳本：在 `download_model.sh` 中加入 `juggernautXL_ragnarok.safetensors` 下載邏輯。
  2. 下載權重：下載並放置至 `ComfyUI/models/checkpoints/`。
  3. 鎖臉管線實測：以現役 `scripts/my_imagen_v2.py` 搭配同一張參考人臉（如 `refs/faces/face1.jpg`）進行生成。
  4. 驗收標準：確認 FaceID 相似度不變、手部與皮膚毛孔細節勝過 v9，且單張出圖速度維持在 70–100s。

---

### 領域二：個人照片修圖與旅遊合成（Retouch & Travel Pipeline）

#### 項目 3：FLUX.2-klein-9B-KV 多參考圖快取加速
* **背景與痛點**：
  * 現役 `recipes/personal/travel_with_me.py` 與 `retouch_face.py` 使用 `klein-9b`。在 24GB Mac mini 上因記憶體吃緊，輸出被迫降規至 768，且每次生成都要重新編碼參考圖，造成較長等待與發熱。
* **新模型優勢**：
  * BFL 推出的 `FLUX.2-klein-9B-kv` 針對多圖參考（Multi-reference）編輯進行 KV 快取優化。
  * 當固定人物臉部特徵、只更換背景提示詞或生成連續姿勢時，省去反覆運算參考圖特徵的時間。
* **執行機台**：**MacBook Pro M5 (32GB) 專屬**
* **實作步驟**：
  1. 授權確認：在 Hugging Face 帳號確認同意 `black-forest-labs/FLUX.2-klein-9B-kv` 授權。
  2. 模組串接：在 `recipes/local_models.py` 增設 `klein-9b-kv` 介面。
  3. 32GB 效能測試：在 MacBook Pro 上實測原生 1024×1024 解析度下，連續生成 3 張旅遊合成圖的首張耗時 vs 第 2、3 張快取加速幅度。
  4. 驗收標準：臉部特徵維持原樣，第 2 張起之生成時間明顯縮短，全程無 swap 卡頓。

#### 項目 4：SeedVR2-7B 極致細節放大
* **背景與痛點**：
  * 現役 `SeedVR2-3B` 在 24GB 上峰值達 18GB，已逼近極限；放大後偶有規則性毛孔偽影或銳化感。
* **新模型優勢**：
  * 7B 參數量提供更充沛的紋理解析力，睫毛根部、虹膜光澤、皮膚微血管與毛孔自然度均超越 3B 版，極適合大幅輸出與海報級修圖。
* **執行機台**：**MacBook Pro M5 (32GB) 專屬（嚴禁在 24GB 執行）**
* **實作步驟**：
  1. 介面包裝：在 `recipes/local_models.py` 加入 `seedvr2-7b` 定義，並延續 `mx.take` 的 repeat 相容修補。
  2. 放大壓力測試：在 32GB 設備上針對 1024² → 2048² 進行放大測試，監控記憶體峰值（預估 22–26GB）。
  3. 細節對照：對比 3B vs 7B 在眼部特寫與髮絲邊緣之偽影改善程度。

---

## 🚀 階段實施里程碑

### 階段一：24GB 輕量與現役管線升級（Mac mini M4）
- [ ] 升級 `mflux` 套件至 0.20+
- [ ] 在 `recipes/local_models.py` 接入 `qwen-image-2.1`（4-bit）並完成首輪立繪測試
- [ ] 下載 `Juggernaut XL Ragnarok`，使用 `scripts/my_imagen_v2.py` 驗證鎖臉管線
- [ ] 更新 `docs/LOCAL-MODELS.md` 實測數據

### 階段二：32GB 重裝火力部署（MacBook Pro M5）
- [ ] 在 32GB 設備上驗證 `FLUX.2-klein-9B-kv` 的多圖快取機制與 1024 解析度順暢度
- [ ] 在 32GB 設備上部署 `SeedVR2-7B`，完成 2K 放大極限與記憶體佔用測試
- [ ] 將 32GB 最佳執行參數回寫至 `docs/LOCAL-MODELS.md` 與 `status.md`

---

## 📌 風險控管與注意事項
1. **24GB 嚴禁誤載 7B/F32 模型**：`SeedVR2-7B` 與 `Z-Image-Turbo 官方 F32` 均會造成 24GB 設備立即 OOM 崩潰，程式面必須保留 `require()` 檢查與防呆防護。
2. **HF Token 管理**：Gated 模型（`klein-9b-kv`）依舊維持使用未進版控的本機 Token 檔讀取，禁止寫死在程式碼中。
3. **ComfyUI 批次防護維持**：升級 Ragnarok 後，批次跑圖依然必須保留每張 `POST /free {"free_memory":true,"unload_models":true}` 與高解析 `VAEDecodeTiled` 規則。
