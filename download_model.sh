#!/bin/bash
set -e

echo "📦 準備下載 AI 算圖與影片模型 (SDXL 專業版)..."
mkdir -p ComfyUI/models/checkpoints/
mkdir -p ComfyUI/models/vae/
mkdir -p ComfyUI/models/ipadapter/
mkdir -p ComfyUI/models/clip_vision/
mkdir -p ComfyUI/models/ultralytics/bbox/
mkdir -p ComfyUI/models/animatediff_models/

# 1. Juggernaut XL 寫實模型
JUGGERNAUT_PATH="ComfyUI/models/checkpoints/juggernautXL_v9Rdphoto2Lightning.safetensors"
if [ ! -f "$JUGGERNAUT_PATH" ]; then
    echo "⏬ 下載 Juggernaut XL V9..."
    curl -L -o "$JUGGERNAUT_PATH" "https://civitai.com/api/download/models/357609"
fi

# 2. Mac 專用修復版 VAE
VAE_PATH="ComfyUI/models/vae/sdxl_vae.safetensors"
if [ ! -f "$VAE_PATH" ]; then
    echo "⏬ 下載 Mac 專用 SDXL VAE (解決色塊問題)..."
    curl -L -o "$VAE_PATH" "https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors"
fi

# 3. IP-Adapter 臉部特徵鎖定模型
IP_FACE_PATH="ComfyUI/models/ipadapter/ip-adapter-plus-face_sdxl_vit-h.safetensors"
if [ ! -f "$IP_FACE_PATH" ]; then
    echo "⏬ 下載 IP-Adapter Face SDXL..."
    curl -L -o "$IP_FACE_PATH" "https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors"
fi

CLIP_VISION_PATH="ComfyUI/models/clip_vision/clip_vision_g.safetensors"
if [ ! -f "$CLIP_VISION_PATH" ]; then
    echo "⏬ 下載 CLIP Vision (視覺編碼器)..."
    curl -L -o "$CLIP_VISION_PATH" "https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors"
fi

# 4. 臉部偵測 YOLO 模型
YOLO_PATH="ComfyUI/models/ultralytics/bbox/face_yolov8m.pt"
if [ ! -f "$YOLO_PATH" ]; then
    echo "⏬ 下載臉部偵測 YOLO 模型..."
    curl -L -o "$YOLO_PATH" "https://huggingface.co/Bingsu/adetailer/resolve/main/face_yolov8m.pt"
fi

# 5. AnimateDiff SDXL 運動模組
MOTION_PATH="ComfyUI/models/animatediff_models/mm_sdxl_v10_beta.ckpt"
if [ ! -f "$MOTION_PATH" ]; then
    echo "⏬ 下載 SDXL 影片動作模型 (mm_sdxl_v10_beta)..."
    echo "💡 提示: 若下載失敗，請手動下載並放入 $MOTION_PATH"
    curl -L -o "$MOTION_PATH" "https://huggingface.co/guoyww/AnimateDiff/resolve/main/mm_sdxl_v10_beta.ckpt?download=true"
fi

echo "✅ 所有模型準備就緒！"
