#!/bin/bash
echo "啟動 ComfyUI 算圖伺服器 (Apple MPS 硬體加速模式)..."
source venv/bin/activate
cd ComfyUI
# --force-fp16 有助於節省 M 系列晶片的記憶體並提升產圖速度
python main.py --force-fp16
