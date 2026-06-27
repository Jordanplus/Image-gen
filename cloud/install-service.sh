#!/usr/bin/env bash
# 一鍵把手機生圖後端裝成「開機自啟 + 重開機自動恢復」的 Mac 服務，並用 Tailscale Funnel 公開。
# 在 Mac Mini 上跑一次：  cd cloud && ./install-service.sh
#
# 做的事：venv+依賴 → 固定 APP_TOKEN(持久) → (選)Claude 長效 token → launchd plist 並載入
#         → pmset 不睡眠 → tailscale funnel --bg → 印出 公開網址 / APP_TOKEN / 下一步。
# 前置（GUI/後台，腳本無法代勞，會提醒）：Tailscale 後台啟用 HTTPS+Funnel、macOS 開自動登入、
# 已 `claude /login`（訂閱）。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"          # .../cloud
PORT=8765
VENV="$HERE/.venv"
TOKFILE="$HERE/.app_token"
PLIST="$HOME/Library/LaunchAgents/com.imagegen.server.plist"
say(){ printf '\n\033[1;36m[install]\033[0m %s\n' "$*"; }

# 1) venv + 依賴
say "建立 venv + 安裝依賴 ..."
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q fastapi "uvicorn[standard]" python-multipart pillow python-dotenv

# 2) 固定 APP_TOKEN（持久；重跑沿用，避免換 token 害手機失效）
if [ -s "$TOKFILE" ]; then
  APP_TOKEN="$(cat "$TOKFILE")"; say "沿用既有 APP_TOKEN（$TOKFILE）"
else
  APP_TOKEN="$("$VENV/bin/python" -c 'import secrets;print(secrets.token_urlsafe(24))')"
  printf '%s' "$APP_TOKEN" > "$TOKFILE"; chmod 600 "$TOKFILE"; say "已產生固定 APP_TOKEN → $TOKFILE"
fi

# 3) Claude 訂閱長效 token（免互動、跨重開機）；留空則改靠 Keychain+自動登入
OAUTH="${CLAUDE_CODE_OAUTH_TOKEN:-}"
if [ -z "$OAUTH" ]; then
  echo "→ 取得 Claude 訂閱長效 token：另開終端跑  claude setup-token"
  read -rsp "  貼上 token（直接 Enter 跳過、改靠 Keychain+自動登入）: " OAUTH; echo
fi
OAUTH_LINE=""
[ -n "$OAUTH" ] && OAUTH_LINE="    <key>CLAUDE_CODE_OAUTH_TOKEN</key><string>${OAUTH}</string>"

# 4) 寫 launchd plist（含固定 token；本機檔、勿 commit）
say "寫入 $PLIST"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.imagegen.server</string>
  <key>WorkingDirectory</key><string>${HERE}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${VENV}/bin/uvicorn</string>
    <string>server:app</string><string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>${PORT}</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/bin:/bin:${VENV}/bin</string>
    <key>APP_TOKEN</key><string>${APP_TOKEN}</string>
${OAUTH_LINE}
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/imagegen.log</string>
  <key>StandardErrorPath</key><string>/tmp/imagegen.err</string>
</dict></plist>
PLIST
chmod 600 "$PLIST"

# 5) (重新)載入服務
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST" && say "launchd 服務已載入（開機自啟 + 崩潰自動重拉）"

# 6) 不睡眠（需 sudo）
say "設定不睡眠（需 sudo；可跳過自行設）..."
sudo pmset -a sleep 0 disksleep 0 2>/dev/null || echo "  (pmset 跳過/失敗，手動設定即可)"

# 7) Tailscale Funnel
TS="$(command -v tailscale || true)"; [ -z "$TS" ] && [ -x "/Applications/Tailscale.app/Contents/MacOS/Tailscale" ] && TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
URL=""
if [ -n "$TS" ]; then
  say "啟動 Tailscale Funnel :$PORT ..."
  "$TS" funnel --bg "$PORT" 2>/dev/null || echo "  (funnel 失敗：先到 Tailscale 後台啟用 HTTPS 憑證 + Funnel，再重跑)"
  URL="$("$TS" status --json 2>/dev/null | "$VENV/bin/python" -c 'import sys,json
try: print("https://"+json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))
except Exception: pass' 2>/dev/null || true)"
else
  echo "  找不到 tailscale CLI；手動跑： tailscale funnel --bg $PORT"
fi

# 8) 摘要
say "完成 ✅"
echo "  公開網址 : ${URL:-https://<機器>.<tailnet>.ts.net}"
echo "  APP_TOKEN: ${APP_TOKEN}   ← 手機第一次開 app 貼這個"
[ -n "$URL" ] && echo "  健康檢查 : curl ${URL}/healthz"
echo "  下一步   : 用上面公開網址在 pwabuilder.com 產 APK（見 apk/README.md）"
echo "  仍需後台 : Tailscale 啟用 HTTPS+Funnel｜macOS 自動登入｜Energy 停電後自動開機"
echo "  日誌     : tail -f /tmp/imagegen.log /tmp/imagegen.err"
