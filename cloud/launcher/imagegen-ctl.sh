#!/bin/zsh
# imagegen-ctl.sh — 個人生圖後端的「啟動／停止／狀態」控制腳本（給桌面 .app 呼叫，也可手動跑）。
# 用絕對路徑：從 GUI(.app / do shell script) 啟動時 PATH 很精簡，必須自己指定，
# 尤其要讓後端 uvicorn 的 PATH 含 /opt/homebrew/bin，server.py 的 subprocess 才找得到 claude。
set -u

REPO="/Users/mcgradymac/claude_prjs/Image-gen/cloud"
PORT=8765
VENV="$REPO/.venv"
TOKFILE="$REPO/.app_token"
# （選用）claude 訂閱 OAuth token。正常靠下面 LaunchAgent 讀 Mac 登入 Keychain 的訂閱即可；
# 這個檔只有在你想改用 setup-token 免 Keychain 時才需要，平常留空。
CCTOKFILE="$REPO/.claude_oauth_token"
LOG="/tmp/imagegen.app.log"
TS="/usr/local/bin/tailscale"
URL="https://mcgradysmac-mini.tail43cdaa.ts.net"
# 後端進程要用的 PATH（claude 在 /opt/homebrew/bin）
SRV_PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$VENV/bin"
# 關鍵：用 LaunchAgent（GUI domain）跑 uvicorn，行程才在你的登入 session 裡、claude -p 才
# 讀得到 Keychain 的訂閱憑證（舊的 nohup 背景版脫離 session → claude 讀不到會卡住逾時）。
PLIST="$HOME/Library/LaunchAgents/com.imagegen.server.plist"
LABEL="com.imagegen.server"
GUI="gui/$(id -u)"

pid_on_port() { /usr/sbin/lsof -nP -iTCP:$PORT -sTCP:LISTEN -t 2>/dev/null | head -1; }
healthz_ok()  { /usr/bin/curl -fsS -m 5 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; }
# 注意：funnel status 就算 Tailscale 停了也會印殘留設定的註解 "# Funnel on:"，
# 只有真正在服務時才有無註解的 "(Funnel on)" 那行 → 用它判斷才準。
funnel_on()   { "$TS" funnel status 2>/dev/null | grep -q "(Funnel on)"; }
# Tailscale 本身是否在跑（stopped 時 status 會印 "Tailscale is stopped."）。
ts_running()  { ! "$TS" status 2>&1 | grep -qi "stopped"; }
ensure_tailscale() {
  # 重開機／手動關過後，Tailscale 會是 stopped：funnel 設定還在但 tailnet 是死的，
  # 公開網址整個 DNS 都解不出來，手機必連不上。tailscale up 是冪等的：已在跑近乎 no-op。
  ts_running && return
  "$TS" up >/dev/null 2>&1
  for i in {1..10}; do ts_running && break; sleep 1; done
}

ensure_token() {
  [ -s "$TOKFILE" ] && return
  "$VENV/bin/python" -c 'import secrets;print(secrets.token_urlsafe(24))' > "$TOKFILE"
  chmod 600 "$TOKFILE"
}

write_plist() {
  # 產生／更新 LaunchAgent plist。ANTHROPIC_API_KEY 不放 → 走訂閱；PATH 含 /opt/homebrew/bin
  # 讓 server.py 的 subprocess 找得到 claude；PYTHONUNBUFFERED 讓 log 即時。
  local cctok_line=""
  [ -s "$CCTOKFILE" ] && cctok_line="    <key>CLAUDE_CODE_OAUTH_TOKEN</key><string>$(cat "$CCTOKFILE")</string>"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>ProgramArguments</key>
  <array>
    <string>$VENV/bin/uvicorn</string>
    <string>server:app</string><string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>$PORT</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$SRV_PATH</string>
    <key>PYTHONUNBUFFERED</key><string>1</string>
    <key>APP_TOKEN</key><string>$(cat "$TOKFILE")</string>
$cctok_line
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PLIST
  chmod 600 "$PLIST"
}

start() {
  ensure_token
  # 已在跑且健康就不重載（避免每次開 .app 都重啟後端）；否則(重)寫 plist 並載入 GUI domain。
  if ! healthz_ok; then
    write_plist
    launchctl bootout "$GUI/$LABEL" 2>/dev/null          # 冪等：先卸載殘留
    launchctl bootstrap "$GUI" "$PLIST" 2>/dev/null       # 載進 GUI session → 能讀 Keychain 訂閱
    launchctl enable "$GUI/$LABEL" 2>/dev/null
  fi
  # 先確保 Tailscale 本身活著（否則 funnel 設定再對也沒用，手機連不上）
  ensure_tailscale
  # 確保 Funnel 開著（持久；已在服務就略過）
  funnel_on || "$TS" funnel --bg $PORT >/dev/null 2>&1
  # 等 healthz（最多 ~20s；LaunchAgent 首次載入要幾秒）
  for i in {1..20}; do healthz_ok && break; sleep 1; done
}

stop() {
  # 卸載 LaunchAgent（連 KeepAlive 一起停）；Funnel 留著（指向死 port 只回 502，不曝露東西）。
  launchctl bootout "$GUI/$LABEL" 2>/dev/null
  # 保險：清掉任何殘留佔 port 的 uvicorn（含舊 nohup 版），確保真的停了。
  /usr/sbin/lsof -nP -iTCP:$PORT -sTCP:LISTEN -t 2>/dev/null | xargs kill 2>/dev/null
  # 也關掉本地 klein worker（若在跑）→ 釋放 ~7-8GB RAM
  /usr/bin/pkill -f "klein_worker.py" 2>/dev/null
}

status() {
  if [ -n "$(pid_on_port)" ] && healthz_ok; then
    echo "🟢 服務執行中"
  elif [ -n "$(pid_on_port)" ]; then
    echo "🟡 啟動中／無回應（看 $LOG）"
  else
    echo "🔴 服務未啟動"
  fi
  if ! ts_running; then
    echo "Tailscale: 🔴 已停止（手機會連不上，按啟動即自動叫起）"
  elif funnel_on; then
    echo "Funnel: 🟢 公開中"
  else
    echo "Funnel: 🔴 未開"
  fi
  if /usr/bin/pgrep -f "klein_worker.py" >/dev/null 2>&1; then
    echo "本地4B: 🟢 已載入(閒置 10 分自動卸載)"
  else
    echo "本地4B: ⚪️ 未載入(手機選本地時才啟動)"
  fi
  if [ -s "$CCTOKFILE" ]; then
    echo "寫prompt: 🟢 Claude（OAuth token）"
  else
    echo "寫prompt: 🟢 Claude（Mac 訂閱 · LaunchAgent 讀 Keychain；卡住會自動退回原文）"
  fi
  echo "網址　: $URL"
  echo "Token : $(cat "$TOKFILE" 2>/dev/null)"
}

case "${1:-status}" in
  start)  start; echo "----"; status ;;
  stop)   stop;  echo "已停止後端。"; echo "----"; status ;;
  status) status ;;
  url)    echo "$URL" ;;
  token)  cat "$TOKFILE" 2>/dev/null ;;
  *)      status ;;
esac
