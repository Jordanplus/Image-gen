#!/bin/bash
set -e

echo "🚀 [1/3] 開始建置 Mac 本地端 AI 算圖環境..."

# 1. Clone ComfyUI
if [ ! -d "ComfyUI" ]; then
    echo "📦 正在下載 ComfyUI 核心引擎..."
    git clone https://github.com/comfyanonymous/ComfyUI.git
else
    echo "✅ ComfyUI 目錄已存在"
fi

# 2. Setup venv
if [ ! -d "venv" ]; then
    echo "🐍 [2/3] 建立 Python 虛擬環境..."
    python3 -m venv venv
else
    echo "✅ 虛擬環境已存在"
fi

echo "📦 [3/3] 安裝依賴套件 (支援 Apple Silicon MPS，這可能需要幾分鐘)..."
source venv/bin/activate
pip install --upgrade pip --quiet
pip install torch torchvision torchaudio --quiet
cd ComfyUI
pip install -r requirements.txt --quiet
cd ..

chmod +x start_backend.sh

echo ""
echo "🎉 環境建置全部完成！"
echo ""
echo "========================================================="
echo "💡 【如何開始產圖】"
echo "1. 開啟一個新的終端機分頁，啟動算圖伺服器："
echo "   cd ~/claude/image-gen && ./start_backend.sh"
echo ""
echo "2. 開啟另一個終端機，使用指令開始產圖："
echo "   cd ~/claude/image-gen"
echo "   source venv/bin/activate"
echo "   python scripts/my_imagen_v2.py --prompt \"A cyberpunk girl...\""
echo "========================================================="
