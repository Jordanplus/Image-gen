-- ImageGen 個人生圖服務 · 桌面控制面板
-- 雙擊 → 自動啟動後端 + 確認 Funnel → 顯示狀態/網址/token，可停止、複製網址。
-- 編譯：osacompile -o ~/Desktop/ImageGen.app ImageGen.applescript

property ctlScript : "/Users/mcgradymac/claude_prjs/Image-gen/cloud/launcher/imagegen-ctl.sh"

on runCtl(cmd)
	try
		return do shell script "/bin/zsh " & quoted form of ctlScript & " " & cmd
	on error errMsg
		return "⚠️ 執行錯誤：" & errMsg
	end try
end runCtl

on run
	-- 點開即確保啟動（含等 healthz），再顯示控制面板
	set info to runCtl("start")
	repeat
		display dialog info with title "🎨 ImageGen 生圖服務" buttons {"停止服務", "複製網址", "完成"} default button "完成" with icon note
		set b to button returned of result
		if b is "完成" then
			exit repeat
		else if b is "停止服務" then
			set info to runCtl("stop")
		else if b is "複製網址" then
			set the clipboard to runCtl("url")
			set info to (runCtl("status") & return & return & "✅ 網址已複製，手機瀏覽器貼上即可開")
		end if
	end repeat
end run
