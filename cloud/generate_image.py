import argparse
import os
from PIL import Image
import io
import base64

# 金鑰載入：先讀 cwd 的 .env，再讀集中式 apipass.env
# （Gemini/GPT 影像「線上路線」預設都走 apipass.dev 聚合閘道，金鑰 APIPASS_API_KEY 來自此檔）。
APIPASS_ENV = "/Users/mcgradymac/claude_prjs/apipass.env"
try:
    from dotenv import load_dotenv
    load_dotenv()
    if os.path.exists(APIPASS_ENV):
        load_dotenv(APIPASS_ENV)
except ImportError:
    pass

# apipass 非同步後端（generate_apipass 在同目錄 apipass_gen.py）
try:
    from apipass_gen import generate_apipass
except Exception:
    generate_apipass = None


def _apipass_model(backend: str, model_type: str) -> str:
    """後端名 → apipass.dev model id。"""
    if backend == "openai":
        return "openai/gpt-image-2"
    if backend == "gemini":
        return "google/nano-banana-pro" if model_type == "ultra" else "google/nano-banana-2"
    return "openai/gpt-image-2"


def generate_image(prompt: str, output_filename: str, model_type: str = "standard", upscale_factor: str = None, seed: int = None, reference_images: list = None, resolution: str = None, aspect_ratio: str = None, backend: str = "openai", apipass_model: str = None):
    """生圖統一入口，依 backend 分流。

    預設後端（gemini / openai / apipass）一律經 **apipass.dev**（金鑰 APIPASS_API_KEY，來自 apipass.env）：
      - openai  → apipass model openai/gpt-image-2
      - gemini  → apipass model google/nano-banana-pro(ultra) / google/nano-banana-2(其餘)
      - apipass → 由 apipass_model 指定（預設 openai/gpt-image-2，亦可填 flux/qwen/seedream…）
    直連 SDK 版（需各自 GEMINI_API_KEY / OPENAI_API_KEY）：gemini-direct / openai-direct。
    成功回傳 output_filename，失敗回傳 None（供 A/B 對照判斷）。
    """
    if backend == "gemini-direct":
        return _generate_gemini(prompt, output_filename, model_type, upscale_factor, seed, reference_images, resolution, aspect_ratio)
    if backend == "openai-direct":
        return _generate_openai(prompt, output_filename, model_type, upscale_factor, seed, reference_images, resolution, aspect_ratio)
    # 預設：經 apipass.dev
    model_id = apipass_model or _apipass_model(backend, model_type)
    return _generate_via_apipass(prompt, output_filename, model_id, model_type, upscale_factor, seed, reference_images, resolution, aspect_ratio)


def _generate_via_apipass(prompt, output_filename, model_id, model_type="ultra", upscale_factor=None, seed=None, reference_images=None, resolution=None, aspect_ratio=None):
    """經 apipass.dev 生圖（gpt-image-2 / nano-banana / flux …）；參考圖＝input.images（Identity Lock）。"""
    if generate_apipass is None:
        print("錯誤：無法載入 apipass_gen.generate_apipass（確認同目錄有 apipass_gen.py）。")
        return None
    if seed is not None:
        print("ℹ️ apipass 後端不支援固定 seed，已忽略 -s。")
    # quality 僅 gpt-image 系列吃；nano-banana 等省略以免被拒。
    quality = None
    if model_id.startswith("openai/"):
        quality = {"ultra": "high", "standard": "medium", "fast": "low"}.get(model_type, "high")
    out = generate_apipass(prompt, output_filename, aspect_ratio=(aspect_ratio or "1:1"),
                           resolution=resolution, quality=quality, images=reference_images, model=model_id)
    if out and upscale_factor:
        print(f"🔍 執行後處理放大 ({upscale_factor})...")
        img = Image.open(out)
        w, h = img.size
        factor = 2 if upscale_factor == "x2" else 4
        img.resize((w * factor, h * factor), Image.LANCZOS).save(out, quality=95)
        print("✨ 放大完成！")
    return out


def _generate_gemini(prompt: str, output_filename: str, model_type: str = "standard", upscale_factor: str = None, seed: int = None, reference_images: list = None, resolution: str = None, aspect_ratio: str = None):
    """
    使用 Gemini 3.1 (Nano Banana 2 / Pro) 直連 SDK 生成影像（gemini-direct）。

    需 google-genai 套件與 GEMINI_API_KEY。一般線上生圖請改用預設的 apipass 路線（-b gemini）。
    resolution: 原生輸出解析度 "1K"/"2K"/"4K"（Nano Banana Pro 支援，4K≈16MP）。
    aspect_ratio: 長寬比 "1:1"/"16:9"/"9:16"/"4:3"/"3:4"。省略則用模型預設(1:1)。
    """
    # google-genai 惰性載入：apipass 路線不需此 SDK，故僅在 gemini-direct 時才 import。
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("錯誤：gemini-direct 需要 google-genai 套件（pip install google-genai）。")
        print("   一般線上生圖請改用預設 apipass 路線：-b gemini（無需此 SDK）。")
        return None

    # 檢查 API Key
    if not os.environ.get("GEMINI_API_KEY"):
        print("錯誤：找不到 GEMINI_API_KEY 環境變數。")
        return None

    # 初始化 Gemini 客戶端
    client = genai.Client()

    # 模型對照表 (2026 最新版)
    model_mapping = {
        "standard": "gemini-3.1-flash-image", # Nano Banana 2
        "ultra": "gemini-3-pro-image",        # Nano Banana Pro (支援 Identity Lock)
        "fast": "gemini-3.1-flash-image"
    }

    model_name = model_mapping.get(model_type, "gemini-3.1-flash-image")

    print(f"🚀 啟動 {model_name} (Nano Banana 系列)...")
    print(f"🎨 正在生成：{prompt}")
    if seed:
        print(f"🎲 使用固定種子 (Seed): {seed}")

    try:
        # 準備內容列表，如果有參考圖則加入
        contents = []
        if reference_images:
            missing = []
            for img_path in reference_images:
                abs_path = os.path.abspath(os.path.expanduser(img_path))
                if os.path.exists(abs_path):
                    contents.append(Image.open(abs_path))
                    print(f"   ✅ 參考圖: {abs_path}")
                else:
                    missing.append(abs_path)
                    print(f"   ⚠️ 找不到參考圖: {abs_path}")
            if missing:
                print(f"⚠️ {len(missing)}/{len(reference_images)} 張參考圖路徑不存在 (cwd={os.getcwd()})")
            # 全數載入失敗 → 中止，避免誤生「未鎖定」影像卻以為已啟動 Identity Lock
            if not contents:
                print("❌ 嚴重：要求 Identity Lock 參考圖，但 0 張載入成功 — 已中止生成。")
                print("   請改用絕對路徑，或確認工作目錄 (cwd)。")
                return None
            print(f"🖼️ 已載入 {len(contents)} 張參考圖 (Identity Lock 啟動)")

        contents.append(prompt)

        # 解析度 / 長寬比：僅在指定時才傳 image_config，
        # 省略則沿用模型預設 → 與舊版行為完全相同（零回歸）。
        image_config = None
        if resolution or aspect_ratio:
            image_config = types.ImageConfig(image_size=resolution, aspect_ratio=aspect_ratio)
            if resolution == "4K" and model_type != "ultra":
                print("⚠️ 4K 為 Nano Banana Pro 專屬，建議搭配 -m ultra（Flash 等級可能上限 2K）")
            print(f"🖥️ 解析度: {resolution or '模型預設(~1K)'} / 長寬比: {aspect_ratio or '模型預設(1:1)'}")

        # 使用 2026 最新 generate_content API
        # 設定 response_modalities=["IMAGE"] 以確保回傳影像
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                seed=seed if seed is not None else None,
                image_config=image_config
            )
        )

        # 從回應中提取影像數據
        image_data = None
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_data = part.inline_data.data
                    break

        if not image_data:
            print("❌ 生成失敗：模型未回傳影像內容。")
            if response.candidates and response.candidates[0].finish_reason:
                print(f"原因: {response.candidates[0].finish_reason}")
            return None

        # 儲存原始影像
        with open(output_filename, "wb") as f:
            f.write(image_data)

        print(f"✅ 影像已儲存至：{output_filename}")

        # 如果有 upscale 需求 (Nano Banana 2 原生支援高品質，但仍可搭配特定處理)
        if upscale_factor:
            print(f"🔍 執行後處理放大 ({upscale_factor})...")
            # 這裡可以加入 PIL 處理或調用特定的放大 API
            img = Image.open(io.BytesIO(image_data))
            width, height = img.size
            factor = 2 if upscale_factor == "x2" else 4
            new_img = img.resize((width * factor, height * factor), Image.LANCZOS)
            new_img.save(output_filename, quality=95)
            print(f"✨ 放大完成！")

        return output_filename

    except Exception as e:
        print(f"💥 發生嚴重錯誤：{e}")
        return None


# gpt-image-2 支援的固定 size 清單（官方文件 2026-04）。
_OPENAI_SIZES = {"1024x1024", "1536x1024", "1024x1536", "2048x2048", "2048x1152", "3840x2160", "2160x3840", "auto"}


def _openai_size(resolution: str, aspect_ratio: str):
    """把 (resolution, aspect) 對到 gpt-image-2 支援的最接近 size。

    gpt-image-2 只接受固定尺寸（非任意長寬比），故無法完全吻合的會取最接近者並回傳警告。
    回傳 (size, warn|None)。
    """
    ar = aspect_ratio or "1:1"
    res = (resolution or "1K").upper()
    # 各長寬比 → {1K,2K,4K} 的最接近支援尺寸
    table = {
        "1:1":  {"1K": "1024x1024", "2K": "2048x2048", "4K": "2048x2048"},
        "16:9": {"1K": "2048x1152", "2K": "2048x1152", "4K": "3840x2160"},
        "9:16": {"1K": "1024x1536", "2K": "1024x1536", "4K": "2160x3840"},
        "4:3":  {"1K": "1536x1024", "2K": "1536x1024", "4K": "1536x1024"},
        "3:4":  {"1K": "1024x1536", "2K": "1024x1536", "4K": "1024x1536"},
    }
    sizes = table.get(ar)
    if not sizes:
        return "auto", f"gpt-image-2 無對應長寬比 {ar} → 用 auto（模型自選）"
    size = sizes.get(res, sizes["1K"])
    warn = None
    if ar == "1:1" and res == "4K":
        warn = "gpt-image-2 無 4K 正方形 → 改用 2048x2048（最大方圖）"
    elif ar in ("9:16",) and res in ("1K", "2K"):
        warn = f"gpt-image-2 無 {res} 的 9:16 → 用 {size}(≈2:3)，真 9:16 僅 4K(2160x3840)"
    elif ar in ("4:3", "3:4") and res in ("2K", "4K"):
        warn = f"gpt-image-2 無 {ar} 高解析原生尺寸 → 用 {size}（之後可 -u 放大）"
    return size, warn


def _generate_openai(prompt: str, output_filename: str, model_type: str = "standard", upscale_factor: str = None, seed: int = None, reference_images: list = None, resolution: str = None, aspect_ratio: str = None):
    """使用 OpenAI gpt-image-2 直連 SDK 生成影像（openai-direct，需 OPENAI_API_KEY）。

    一般線上生圖請改用預設 apipass 路線（-b openai）；此 direct 版供無 apipass 時備援 / A/B 對照。
    - model_type 對應 gpt-image-2 的 quality：fast→low / standard→medium / ultra→high。
    - 有參考圖 → 走 images.edit（等同 Identity Lock）；否則 images.generate。
    - gpt-image-2 不支援固定 seed（會忽略 -s）；解析度走固定 size 對照（見 _openai_size）。
    """
    if not os.environ.get("OPENAI_API_KEY"):
        print("錯誤：找不到 OPENAI_API_KEY 環境變數。")
        return None
    try:
        from openai import OpenAI
    except ImportError:
        print("錯誤：未安裝 openai 套件。請執行：pip install openai")
        return None

    client = OpenAI()
    model_name = "gpt-image-2"
    quality = {"fast": "low", "standard": "medium", "ultra": "high"}.get(model_type, "medium")
    size, warn = _openai_size(resolution, aspect_ratio)

    print(f"🚀 啟動 {model_name} (OpenAI)... quality={quality} / size={size}")
    print(f"🎨 正在生成：{prompt}")
    if warn:
        print(f"⚠️ {warn}")
    if seed is not None:
        print("ℹ️ gpt-image-2 不支援固定 seed，已忽略 -s（A/B 跨模型本就無法共用 seed）。")

    opened = []
    try:
        if reference_images:
            missing = []
            for img_path in reference_images:
                abs_path = os.path.abspath(os.path.expanduser(img_path))
                if not os.path.exists(abs_path):
                    missing.append(abs_path)
                    print(f"   ⚠️ 找不到參考圖: {abs_path}")
                    continue
                # gpt-image-2 的 images.edit 只吃 PNG；專案參考圖多為 .webp → 一律在記憶體內轉 PNG。
                try:
                    ref_img = Image.open(abs_path)
                    if ref_img.mode not in ("RGB", "RGBA"):
                        ref_img = ref_img.convert("RGBA")
                    buf = io.BytesIO()
                    ref_img.save(buf, format="PNG")
                    buf.seek(0)
                    buf.name = f"ref_{len(opened)}.png"  # SDK 以 .name 判斷檔型
                    opened.append(buf)
                    print(f"   ✅ 參考圖: {abs_path}")
                except Exception as conv_e:
                    missing.append(abs_path)
                    print(f"   ⚠️ 參考圖讀取/轉檔失敗: {abs_path} ({conv_e})")
            if missing:
                print(f"⚠️ {len(missing)}/{len(reference_images)} 張參考圖路徑不存在 (cwd={os.getcwd()})")
            # 與 Gemini 後端一致：要求參考圖卻 0 張載入成功 → 中止，避免誤生未鎖定影像
            if not opened:
                print("❌ 嚴重：要求 Identity Lock 參考圖，但 0 張載入成功 — 已中止生成。")
                print("   請改用絕對路徑，或確認工作目錄 (cwd)。")
                return None
            print(f"🖼️ 已載入 {len(opened)} 張參考圖 (images.edit 模式)")
            response = client.images.edit(
                model=model_name,
                image=opened,
                prompt=prompt,
                size=size,
                quality=quality,
            )
        else:
            response = client.images.generate(
                model=model_name,
                prompt=prompt,
                size=size,
                quality=quality,
                n=1,
            )

        b64 = response.data[0].b64_json if response.data else None
        if not b64:
            print("❌ 生成失敗：模型未回傳影像內容。")
            return None
        image_data = base64.b64decode(b64)

        with open(output_filename, "wb") as f:
            f.write(image_data)
        print(f"✅ 影像已儲存至：{output_filename}")

        if upscale_factor:
            print(f"🔍 執行後處理放大 ({upscale_factor})...")
            img = Image.open(io.BytesIO(image_data))
            width, height = img.size
            factor = 2 if upscale_factor == "x2" else 4
            new_img = img.resize((width * factor, height * factor), Image.LANCZOS)
            new_img.save(output_filename, quality=95)
            print(f"✨ 放大完成！")

        return output_filename

    except Exception as e:
        print(f"💥 發生嚴重錯誤：{e}")
        return None
    finally:
        for f in opened:
            try:
                f.close()
            except Exception:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nano Banana / GPT-image-2 線上影像生成（apipass.dev）")
    parser.add_argument("-p", "--prompt", required=True, help="影像生成提示詞")
    parser.add_argument("-o", "--output", required=True, help="輸出檔案路徑")
    parser.add_argument("-b", "--backend",
                        choices=["gemini", "openai", "apipass", "gemini-direct", "openai-direct"],
                        default="openai",
                        help="後端（預設皆經 apipass.dev）：openai=gpt-image-2（首選）/ gemini=nano-banana / "
                             "apipass=自訂 model(見 --apipass-model)；直連 SDK：gemini-direct / openai-direct")
    parser.add_argument("--apipass-model", default=None,
                        help="backend=apipass 時的 model id，如 openai/gpt-image-2、google/nano-banana-pro、"
                             "flux/flux-pro-image-2、qwen/qwen-image-2、seedream/seedream-5-lite-image")
    parser.add_argument("-m", "--model", choices=["standard", "ultra", "fast"], default="ultra",
                        help="模型等級：gemini→ultra=nano-banana-pro/其餘=nano-banana-2；openai→quality high/medium/low")
    parser.add_argument("-u", "--upscale", choices=["x2", "x4"], default=None,
                        help="LANCZOS 後處理放大（純拉伸不增細節）；真高解析請改用 -q")
    parser.add_argument("-s", "--seed", type=int, default=None, help="隨機種子值 (僅 gemini-direct；apipass/openai 會忽略)")
    parser.add_argument("-r", "--ref", nargs="+", help="參考影像路徑 (Identity Lock)", default=None)
    parser.add_argument("-q", "--resolution", choices=["1K", "2K", "4K"], default=None,
                        help="原生輸出解析度（gemini 任意比；openai-direct 對到最接近固定 size）。省略＝模型預設。")
    parser.add_argument("-a", "--aspect", choices=["1:1", "16:9", "9:16", "4:3", "3:4"], default=None,
                        help="長寬比（省略＝模型預設 1:1）。如港口/地圖 16:9、立繪 3:4")

    args = parser.parse_args()
    generate_image(args.prompt, args.output, args.model, args.upscale, args.seed, args.ref,
                   args.resolution, args.aspect, args.backend, args.apipass_model)
