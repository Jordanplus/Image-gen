# Ideogram 4.0（NF4）on Colab T4 — 自託管試跑

用 `google-colab-cli` 租一張 **免費 T4 GPU**，自託管開源的 **Ideogram 4.0**（9.3B，NF4 量化）出一張圖再拉回本地。與專案 `cloud/`（apipass / 官方 API 路線）並列，這條是「自託管」路線。

> ⚠️ **免費 T4 跑不動這顆（2026-06-27 實測，見下方「實測結論」）。** 模型 ~16GB，而免費 T4 runtime 系統記憶體只有 ~13GB，載入即 host-OOM、runtime 失聯。**預設 GPU 已改 L4（24GB VRAM + ~53GB RAM）**；軟體 bug 都已修進腳本，待上 L4 驗證。

## 前置
1. **colab CLI**：`uv tool install google-colab-cli`，並完成 ADC 登入（`colab` 第一次會引導）。
2. **HF gated 授權**：到 <https://huggingface.co/ideogram-ai/ideogram-4-nf4-diffusers> 按下接受授權（non-commercial，個人/研究免費），再產一個 **read-only** token。
3. token 用環境變數帶入，**不要寫進 repo**：
   ```bash
   export HF_TOKEN=hf_xxxxxxxx
   ```

## 用法
```bash
HF_TOKEN=hf_xxx ./run_ideogram.sh -o out.png -g L4 \
  "a vintage travel poster of Taipei 101 at dusk, bold typographic title 'TAIPEI', clean vector style"
```
旗標：`-g/--gpu`（預設 L4；**勿用 T4**，見實測結論）、`-W/-H`（預設 1024）、`--steps`（28）、`--seed`（1405）、`--cfg`（guidance，預設不帶）。

流程：組自包含腳本（PROMPT + CFG + HF_TOKEN 三個 globals 接在 `ideogram_core.py` 前）→ `colab run --gpu T4`（開 VM → 跑 → 自動拆）→ stdout 的 base64 解回本地 `out.png`。

## 已知坑（已在 core 處理 / 待實測）
- **bf16 → fp16**：官方範例用 `bfloat16`，但 T4（Turing）無 bf16 tensor core → core 強制 `torch.float16`。
- **diffusers 版本**：`Ideogram4Pipeline` 只在 git 版 diffusers；Colab 預裝 transformers 5.x 會打架 → core pin `transformers<5` + git diffusers。**首次上機可能要試一兩輪版本**（會燒一點 Colab 額度）。
- **pipeline 呼叫簽章**未公開定版 → core 用 `inspect` 探測 `num_inference_steps`/`guidance_scale` 才帶，避免未知 kwarg 直接炸。
- **OOM**：撞了會印 `RESULT_FAIL OutOfMemory` 並提示降 `-W/-H`。

## 反覆調校的省錢做法
`run_ideogram.sh` 用一次性 `colab run`（每次重裝套件、較慢）。要連續試多張／調版本時，改用常駐 session 省去重裝：
```bash
colab new -s ideo --gpu T4
colab exec -s ideo -f /tmp/selfcontained.py   # 自行組裝後丟同一 session
colab stop -s ideo
```

## 實測結論（2026-06-27，免費 T4）
摸通了載入路徑，但**免費 T4 撞硬體牆**。`ideogram_core.py` 已內建 ① ② 兩個修補。

| 關卡 | 結果 | 處置 |
|---|---|---|
| 版本相容 | ✅ | git diffusers **0.39.0.dev0** + transformers **4.57.6** + torch **2.11.0+cu128**（`transformers<5` 即可，與影片 skill 的 CLIP 坑無關，因本模型用 Qwen3-VL） |
| ① Qwen3-VL `rope_scaling=None` 崩潰 | ✅ 已修 | monkeypatch `Qwen3VLTextRotaryEmbedding.__init__`，None → `{}`（fall back 預設 mrope `[24,20,20]`） |
| ② tokenizer `vocab_file=None` 崩潰 | ✅ 已修 | checkpoint 只附 `tokenizer.json`(fast)、卻宣告 slow `Qwen2Tokenizer` → 用 `AutoTokenizer(use_fast=True)` 載 fast 版、以 `tokenizer=` 注入 pipeline |
| **載入 ~16GB 模型** | ❌ **撞牆** | text_encoder=Qwen3-VL 5.5G + 雙 transformer 各 5.2G ≈ 16GB；`enable_model_cpu_offload` 全釘 host RAM，而免費 T4 runtime 只 ~13GB → OOM、runtime 失聯 |

**結論**：這顆 9.3B（含整顆 VLM 編碼器）對免費 T4 太大，是**硬體天花板非 bug**。下一步若要跑，用 **L4（24GB VRAM + ~53GB RAM）** 應可一次過；或改走 Ideogram 官方 API。

## 授權
Ideogram Non-Commercial Model Agreement — 個人/研究免費，商用需另購授權。
