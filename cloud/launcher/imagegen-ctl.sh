#!/bin/zsh
# imagegen-ctl.sh — 個人生圖後端的「啟動／停止／狀態」控制腳本（給桌面 .app 呼叫，也可手動跑）。
# 用絕對路徑：從 GUI(.app / do shell script) 啟動時 PATH 很精簡，必須自己指定，
# 尤其要讓後端 uvicorn 的 PATH 含 /opt/homebrew/bin，server.py 的 subprocess 才找得到 claude。
set -u

REPO="/Users/mcgradymac/claude_prjs/Image-gen/cloud"
PORT=8765
VENV="$REPO/.venv"
TOKFILE="$REPO/.app_token"
LOG="/tmp/imagegen.app.log"
TS="/usr/local/bin/tailscale"
URL="https://mcgradysmac-mini.tail43cdaa.ts.net"
# 後端進程要用的 PATH（claude 在 /opt/homebrew/bin）
SRV_PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$VENV/bin"

pid_on_port() { /usr/sbin/lsof -nP -iTCP:$PORT -sTCP:LISTEN -t 2>/dev/null | head -1; }
healthz_ok()  { /usr/bin/curl -fsS -m 5 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; }
funnel_on()   { "$TS" funnel status 2>/dev/null | grep -q "Funnel on"; }

ensure_token() {
  [ -s "$TOKFILE" ] && return
  "$VENV/bin/python" -c 'import secrets;print(secrets.token_urlsafe(24))' > "$TOKFILE"
  chmod 600 "$TOKFILE"
}

start() {
  ensure_token
  if [ -z "$(pid_on_port)" ]; then
    cd "$REPO" || exit 1
    # nohup + 全 fd 導向檔案 → do shell script 不會卡著等；ANTHROPIC_API_KEY 清掉走訂閱
    APP_TOKEN="$(cat "$TOKFILE")" \
      /usr/bin/nohup /usr/bin/env -u ANTHROPIC_API_KEY PATH="$SRV_PATH" \
      "$VENV/bin/uvicorn" server:app --host 127.0.0.1 --port $PORT >> "$LOG" 2>&1 &
    disown 2>/dev/null
  fi
  # 確保 Funnel 開著（持久；已開就略過）
  funnel_on || "$TS" funnel --bg $PORT >/dev/null 2>&1
  # 等 healthz（最多 ~20s）
  for i in {1..20}; do healthz_ok && break; sleep 1; done
}

stop() {
  # 只停後端 uvicorn；Funnel 留著（指向死 port 只會回 502，不曝露任何東西，且重開機自動還原）
  local p; p="$(pid_on_port)"
  [ -n "$p" ] && /usr/sbin/lsof -nP -iTCP:$PORT -sTCP:LISTEN -t 2>/dev/null | xargs kill 2>/dev/null
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
  if funnel_on; then echo "Funnel: 🟢 公開中"; else echo "Funnel: 🔴 未開"; fi
  if /usr/bin/pgrep -f "klein_worker.py" >/dev/null 2>&1; then
    echo "本地4B: 🟢 已載入(閒置 10 分自動卸載)"
  else
    echo "本地4B: ⚪️ 未載入(手機選本地時才啟動)"
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
