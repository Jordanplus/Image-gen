MFLUX_PY := $(HOME)/.local/share/uv/tools/mflux/bin/python

.PHONY: gui help

help:
	@echo "make gui     開本機生圖介面（瀏覽器 http://127.0.0.1:8770/）"
	@echo "make supir   使用 SUPIR AI 高畫質修復放大圖片 (例: make supir IMG=path.png SCALE=1.5)"

# 本機生圖介面：模型常駐、選寫法／膚色／胸型／長相／尺寸，可上傳參考圖；
# 產出可點圖看原尺寸，或按「放大」用 SeedVR2 放到約 2 倍
gui:
	@$(MFLUX_PY) recipes/gui/app.py

# SUPIR 超解析度影像修復放大 (ComfyUI 原生 Core 核心 + SDXL Lightning)
# 用法: make supir IMG=outputs/.../image.png [SCALE=2.0] [PROMPT="..."]
supir:
	@test -n "$(IMG)" || (echo "請提供 IMG 參數，例如: make supir IMG=outputs/test.png" && exit 1)
	@venv/bin/python recipes/upscale_supir.py "$(IMG)" \
		$$(test -n "$(SCALE)" && echo "--scale $(SCALE)") \
		$$(test -n "$(PROMPT)" && echo "--prompt \"$(PROMPT)\"")

