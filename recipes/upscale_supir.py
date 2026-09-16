#!/usr/bin/env python3
"""
SUPIR High-Fidelity AI Upscaler & Image Restorer for Apple Silicon MPS / ComfyUI.
Integrates ComfyUI Core native SUPIR (ModelPatchLoader + SUPIRApply) with SDXL Lightning.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMFY_DIR = REPO_ROOT / "ComfyUI"
COMFY_URL = "http://127.0.0.1:8188"
OUTPUT_DIR = REPO_ROOT / "outputs" / "supir"


def is_comfy_running() -> bool:
    try:
        req = urllib.request.Request(f"{COMFY_URL}/system_stats")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_comfy_server():
    print("[INFO] 正在啟動 ComfyUI 服務端...")
    venv_py = REPO_ROOT / "venv" / "bin" / "python"
    main_py = COMFY_DIR / "main.py"
    if not venv_py.exists():
        venv_py = Path(sys.executable)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

    proc = subprocess.Popen(
        [str(venv_py), str(main_py), "--force-fp16", "--listen", "127.0.0.1", "--port", "8188"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for i in range(30):
        time.sleep(1)
        if is_comfy_running():
            print("[INFO] ComfyUI 服務端已就緒 (http://127.0.0.1:8188)")
            return proc
    raise RuntimeError("ComfyUI 啟動逾時")


def upload_image(image_path: Path) -> str:
    """Upload input image to ComfyUI input folder."""
    target_name = f"supir_in_{int(time.time())}_{image_path.name}"
    dest = COMFY_DIR / "input" / target_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(image_path, dest)
    return target_name


def build_workflow(
    input_image_name: str,
    scale_by: float = 2.0,
    steps: int = 4,
    cfg: float = 1.5,
    prompt_text: str = "high quality, extremely detailed photo, 8k, sharp focus",
    neg_prompt: str = "bad quality, blurry, noisy, messy",
    restore_cfg: float = 4.0,
    seed: int = 42,
    output_prefix: str = "SUPIR_upscale",
) -> dict:
    return {
        "1": {
            "inputs": {
                "image": input_image_name
            },
            "class_type": "LoadImage"
        },
        "2": {
            "inputs": {
                "image": ["1", 0],
                "upscale_method": "lanczos",
                "scale_by": scale_by
            },
            "class_type": "ImageScaleBy"
        },
        "3": {
            "inputs": {
                "ckpt_name": "Juggernaut_RunDiffusionPhoto2_Lightning_4Steps.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "4": {
            "inputs": {
                "name": "SUPIR-v0Q_fp16.safetensors"
            },
            "class_type": "ModelPatchLoader"
        },
        "5": {
            "inputs": {
                "model": ["3", 0],
                "model_patch": ["4", 0],
                "vae": ["3", 2],
                "image": ["2", 0],
                "strength_start": 1.0,
                "strength_end": 1.0,
                "restore_cfg": restore_cfg,
                "restore_cfg_s_tmin": 0.05
            },
            "class_type": "SUPIRApply"
        },
        "6": {
            "inputs": {
                "text": prompt_text,
                "clip": ["3", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "7": {
            "inputs": {
                "text": neg_prompt,
                "clip": ["3", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "8": {
            "inputs": {
                "pixels": ["2", 0],
                "vae": ["3", 2]
            },
            "class_type": "VAEEncode"
        },
        "9": {
            "inputs": {
                "model": ["5", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["8", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "dpmpp_2m",
                "scheduler": "sgm_uniform",
                "denoise": 1.0
            },
            "class_type": "KSampler"
        },
        "10": {
            "inputs": {
                "samples": ["9", 0],
                "vae": ["3", 2]
            },
            "class_type": "VAEDecode"
        },
        "11": {
            "inputs": {
                "filename_prefix": output_prefix,
                "images": ["10", 0]
            },
            "class_type": "SaveImage"
        }
    }


def run_upscale(
    image_path: Path,
    scale: float = 2.0,
    prompt: str = "high quality, extremely detailed photo, 8k, sharp focus",
    negative: str = "bad quality, blurry, noisy, messy",
    steps: int = 4,
    cfg: float = 1.5,
    restore_cfg: float = 4.0,
    seed: int = 42,
    out_path: Path | None = None,
) -> Path:
    if not is_comfy_running():
        start_comfy_server()

    print(f"[INFO] 正在上傳與準備輸入圖: {image_path}")
    uploaded_name = upload_image(image_path)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"SUPIR_{timestamp}"

    workflow = build_workflow(
        input_image_name=uploaded_name,
        scale_by=scale,
        steps=steps,
        cfg=cfg,
        prompt_text=prompt,
        neg_prompt=negative,
        restore_cfg=restore_cfg,
        seed=seed,
        output_prefix=prefix,
    )

    data = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFY_URL}/prompt",
        data=data,
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode())
        prompt_id = res["prompt_id"]

    print(f"[INFO] 已排入 SUPIR 放大佇列，任務 ID: {prompt_id}（放大倍率: {scale}x, 步數: {steps}）")
    start_t = time.time()

    while True:
        time.sleep(3)
        elapsed = int(time.time() - start_t)
        hist_req = urllib.request.Request(f"{COMFY_URL}/history/{prompt_id}")
        with urllib.request.urlopen(hist_req) as resp:
            hist = json.loads(resp.read().decode())
            if prompt_id in hist:
                item = hist[prompt_id]
                status = item.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"SUPIR 執行失敗: {status.get('messages')}")

                outputs = item.get("outputs", {})
                img_info = outputs.get("11", {}).get("images", [{}])[0]
                saved_filename = img_info.get("filename")
                if not saved_filename:
                    raise RuntimeError("未在輸出節點找到生成圖片")

                generated_file = COMFY_DIR / "output" / saved_filename
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                final_dest = out_path or (OUTPUT_DIR / f"{prefix}_{image_path.stem}_{scale}x.png")
                shutil.copy2(generated_file, final_dest)
                print(f"[SUCCESS] 放大完成！耗時: {elapsed} 秒")
                print(f"[SUCCESS] 輸出儲存至: {final_dest}")
                return final_dest

            print(f"[{elapsed}s] 正在執行 SUPIR 重建採樣與特徵對齊...", end="\r", flush=True)


def main():
    parser = argparse.ArgumentParser(description="SUPIR AI 放大修復工具 (Apple Silicon M-series 優化)")
    parser.add_argument("input", type=str, help="欲放大的圖片路徑")
    parser.add_argument("--scale", type=float, default=2.0, help="放大倍率 (預設: 2.0)")
    parser.add_argument("--prompt", type=str, default="high quality, extremely detailed photo, 8k, sharp focus", help="正向提示詞引導細節重建")
    parser.add_argument("--negative", type=str, default="bad quality, blurry, noisy, messy", help="負向提示詞")
    parser.add_argument("--steps", type=int, default=4, help="Lightning 採樣步數 (預設: 4)")
    parser.add_argument("--cfg", type=float, default=1.5, help="提示詞引導強度 CFG (預設: 1.5)")
    parser.add_argument("--restore-cfg", type=float, default=4.0, help="對原圖忠實度 Restore CFG (預設: 4.0，越高越忠於原圖)")
    parser.add_argument("--seed", type=int, default=42, help="隨機種子")
    parser.add_argument("--output", type=str, default=None, help="自訂輸出檔案路徑")

    args = parser.parse_args()
    input_p = Path(args.input).resolve()
    if not input_p.exists():
        print(f"[ERROR] 找不到輸入檔案: {input_p}")
        sys.exit(1)

    out_p = Path(args.output).resolve() if args.output else None
    run_upscale(
        image_path=input_p,
        scale=args.scale,
        prompt=args.prompt,
        negative=args.negative,
        steps=args.steps,
        cfg=args.cfg,
        restore_cfg=args.restore_cfg,
        seed=args.seed,
        out_path=out_p,
    )


if __name__ == "__main__":
    main()
