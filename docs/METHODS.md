# image-gen — 本地 ComfyUI 生圖操作指南

> 本地堆疊的操作細節（指令 / 模型檔 / 工作流 / 已知問題）。
> **方法選用決策**見 The-Age-of-Exploration 專案的
> `tools/art-pipeline/art-creator/METHODS.md`。更新 **2026-06-19**。

## 環境
- ComfyUI v0.24.0 @ `image-gen/ComfyUI`；venv `image-gen/venv`（Python 3.14）；Apple MPS。
- 啟動（**務必先 robust kill 殭屍伺服器**）：
  ```bash
  pkill -9 -f "main.py --force-fp16"; lsof -ti :8188 | xargs -r kill -9
  cd ComfyUI && nohup ../venv/bin/python main.py --force-fp16 > /tmp/comfy.log 2>&1 &
  ```
  伺服器 `127.0.0.1:8188`。API：POST `/prompt`（回 prompt_id）→ poll `/history/{id}` 取 outputs → GET `/view?filename=...`。
- 每張約 **70–100s**（MPS；SDXL hires 兩段 / FLUX GGUF 皆然）。

## 模型檔
| 用途 | 檔案 |
|------|------|
| SDXL ckpt / vae | `models/checkpoints/juggernautXL_v9Rdphoto2Lightning.safetensors` · `models/vae/sdxl_vae.safetensors` |
| IP-Adapter | `models/ipadapter/ip-adapter-plus-face_sdxl_vit-h.safetensors` · CLIP-Vision `clip_vision_g.safetensors` |
| FLUX GGUF | `models/unet/flux1-schnell-Q4_K_S.gguf` (6.3G) · `models/clip/t5-v1_1-xxl-encoder-Q5_K_M.gguf` (3.15G) · `clip_l.safetensors` · `models/vae/flux-vae-bf16.safetensors` |
| PuLID | `models/pulid/pulid_flux_v0.9.1.safetensors` · InsightFace `models/insightface/models/antelopev2/`（5 onnx，首次自動下載） |
| custom_nodes | `ComfyUI-GGUF` · `ComfyUI_PuLID_Flux_ll` · `ComfyUI_IPAdapter_plus` |

## 方法 ② SDXL Juggernaut

### 純 prompt hires（無鎖臉，皮膚紋理最佳）
工作流：`Checkpoint → CLIPTextEncode → EmptyLatent(1024×1280) → KSampler(25, dpmpp_2m/karras, denoise 1) → LatentUpscale(1792×2240) → KSampler(12, denoise 0.45) → VAEDecode → Save`。
prompt 加 `RAW photo, ultra detailed skin pores, film grain, dslr`；negative 加 `plastic skin, airbrushed`。
範本：`/tmp/hires_photoreal.py`。

### IP-Adapter 鎖臉（CLI 最快路徑）
```bash
python my_imagen.py -p "<prompt>" -np "<neg>" -r <ref.png> -s <seed> -iw 0.6
```
`my_imagen.py` 用 `workflow_api_with_ipadapter.json`（**無磨皮節點**；磨皮來自 weight 高 + 無 refine）。降 `-iw 0.6` + 下方鎖臉食譜的 hires refine 緩解。

## ★ 純 prompt #1 → 鎖臉 #2…N（原創角色一致組）— 正式生產建議
第一張純 prompt 得**獨特且銳利**的臉，後續鎖它生一致變體：
1. **#1** 純 prompt hires → 存檔，複製到 `ComfyUI/input/`。
2. **#2…N**：`IPAdapterAdvanced(image=#1, weight 0.6, embeds_scaling="V only")` 接 `KSampler.model`，**並加 hires refine**（`LatentUpscale → KSampler denoise 0.4`）把毛孔補回。
範本：`/tmp/lock_demo.py`。
> **驗證（2026-06-19，`production/qa/evidence/lock_demo/`）**：#1 純 prompt → #2/#3 鎖臉（IPAdapter w0.6 + hires refine d0.4）實測 **成功**：#2/#3 與 #1 為同一人（骨架/鬍型/眼神一致），跨姿勢/帽子/外套鎖得住，且**皮膚紋理保留**（毛孔/鬍鬚在、非塑膠）。代價：後續張最細處略軟於 #1，但可接受。→ 原創角色一致立繪組的正式 pipeline。

## 方法 ③ FLUX GGUF (+PuLID)
API dict 工作流（範本 `/tmp/flux_gguf_test.py`、`/tmp/flux_pulid_only.py`）：
- `UnetLoaderGGUF(flux1-schnell-Q4_K_S.gguf)` + `DualCLIPLoaderGGUF(clip_l + t5 gguf, type=flux)` + `VAELoader(flux-vae-bf16)`
- `CLIPTextEncode → FluxGuidance(3.5) → BasicGuider`；`EmptySD3LatentImage`；`RandomNoise`；`KSamplerSelect(euler)`；`BasicScheduler(simple, 4, 1.0)`；`SamplerCustomAdvanced → VAEDecode → Save`
- **+PuLID**：`PulidFluxModelLoader` + `PulidFluxEvaClipLoader` + `PulidFluxInsightFaceLoader(provider=CPU)` + `LoadImage` + `ApplyPulidFlux(weight 0.9)`；把 `BasicScheduler` / `BasicGuider` 的 `model` 改接 `ApplyPulidFlux` 輸出。

## 附錄 A：Mac / MPS 已知問題
- **FLUX fp8（Float8_e4m3fn）MPS 不支援** → 一律用 GGUF 量化版（city96）。
- **殭屍伺服器**：起新伺服器前務必 `pkill -9 -f "main.py --force-fp16"; lsof -ti :8188 | xargs -r kill -9`。
- 輸出在 `outputs/result_*.png`；批次抓檔請從 stdout「儲存至」行取**確切檔名**（`ls -t` 有 race，曾抓錯檔）。

## 附錄 B：PuLID 節點 `timestep_zero_index` shim
ComfyUI 核心 flux forward 新增 kwarg `timestep_zero_index`，`ComfyUI_PuLID_Flux_ll/PulidFluxHook.py` 的 `pulid_forward_orig()` 未接 → `TypeError`。
**修**：於該函式簽章補 `timestep_zero_index=None, **kwargs`（接受並忽略；單人立繪不需該 timestep-masking）。改後**重啟伺服器**重載節點。

## 附錄 C：批次連續生成的 MPS 記憶體管理（2026-06-20 踩坑，72 張 SDXL hires）

**核心教訓：單張成功 ≠ 連續成功。** MPS 上 ComfyUI 連續生成，model + 中間 tensor **不會自動釋放**，VRAM 累積撞 ~32GB 統一記憶體上限 → VAEDecode（大圖解碼峰值最高）先 OOM（`MPS backend out of memory`）。實測 1536×2240 連續跑，前幾張 OK、第 N 張起大量 FAIL。

**根因辨正**：是**連續累積 +「啟動時伺服器已不乾淨」**，**不是單張峰值不足**——單張普通 VAEDecode 本來就過（gen_verbose 單張測試全綠）。OOM 報在 VAEDecode node 只因它峰值最高、累積撐滿後它先爆；別被誤導去「降 VAEDecode 峰值」。

**真正必要（兩項，關鍵）**：
1. **長批次前重啟 ComfyUI 進程**：累積過的伺服器即使 `/free` 也清不乾淨（MPS allocator 殘留）；只有重啟進程才真正釋放（idle RSS 才 ~1GB，故 OOM 訊息的 27GB「殘留」其實是生成峰值、非常駐）。給乾淨起點。
2. **每張之間 POST `/free` 且 `unload_models:true`**：body `{"free_memory":true,"unload_models":true}`。
   - ⚠️ **只給 `free_memory:true`（不卸 model）無效**——累積照樣 OOM。必須 `unload_models:true` 徹底卸載。代價：下張 reload model ~15–20s。
   - **實證**：v1（無 unload）abel/afonso/cabeza 前 3 張即 FAIL；v4（重啟+unload）同 3 張連續 OK。

**optional 保險（非必要，別反射性加）**：
3. **VAEDecode → VAEDecodeTiled** 再降解碼峰值。①②已解累積後**嚴格說不需要**；只在更高解析/邊際 case 才考慮。若用，**6 參數全 `required`**：`samples, vae, tile_size, overlap, temporal_size, temporal_overlap`（缺則 validation `REJECTED: required_input_missing`；default `512/64/64/8`，512tile+64overlap 單張內無接縫）。**踩坑：只給 tile_size 連錯兩輪**——這就是「反射性加非必要複雜度」的代價。

**診斷陷阱（害我連錯數輪）**：
- **validation 失敗的 prompt 不留 execution-error history**（提交階段就被拒、沒進執行）。別只看 `/history` 的 error → 要看 POST `/prompt` 回傳的 `node_errors`（HTTP 400 body）。曾把「VAEDecodeTiled 缺參數」誤判成「OOM」連錯兩輪。
- OOM 訊息的 `other allocations: NN GiB` 是**生成當下峰值**，不是常駐殘留。

**批次腳本必備**：
- **fail-fast**：連續 ≥5 FAIL 自動 abort，免 OOM/bug 白跑數小時。
- **勿誤判卡死**：SDXL hires（1536×2240 + 每張 unload reload）≈ **4–5min/張**（比 §環境 標的 70–100s 慢，因含 model reload + 更高解析）；`/history` 出現前的等待是正常排隊，別太早 kill。
- 範本：`/tmp/roster_gen2.py`（free_mem unload + VAEDecodeTiled 全參 + fail-fast）。

---
- 方法選用決策：`<The-Age-of-Exploration>/tools/art-pipeline/art-creator/METHODS.md`
- 實證報告：`<The-Age-of-Exploration>/docs/local-imagegen-final-review-2026-06-19.html`
