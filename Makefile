MFLUX_PY := $(HOME)/.local/share/uv/tools/mflux/bin/python

.PHONY: gui help

help:
	@echo "make gui   開本機生圖介面（瀏覽器 http://127.0.0.1:8770/，只綁本機）"

# 本機生圖介面：模型常駐、選寫法／膚色／胸型／長相／尺寸，可上傳參考圖；
# 產出可點圖看原尺寸，或按「放大」用 SeedVR2 放到約 2 倍
gui:
	@$(MFLUX_PY) recipes/gui/app.py
