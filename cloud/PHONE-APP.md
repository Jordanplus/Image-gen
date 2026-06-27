# 📱 個人手機生圖 app（Mac Mini 後端 + apipass gpt-image-2）

在自己的 Android 手機用 PWA 輸入意圖＋參考圖 → Mac Mini 後端用**你現有的 Claude Code 訂閱**寫 prompt → apipass `gpt-image-2` 生圖回傳。**個人自用**、金鑰只在 Mac Mini、不另開付費 API。

```
[Android PWA]  ──Tailscale/LAN──>  [Mac Mini: FastAPI server.py]
                                      ├─ claude -p（訂閱）看參考圖 + 寫 gpt-image-2 prompt
                                      └─ apipass_gen.generate_apipass(...) → apipass → 回圖
```

## 已實證（2026-06-27）
- 無頭 `claude -p "..." --output-format json | jq -r .result` 在**訂閱登入**下可用（不設 `ANTHROPIC_API_KEY` 即走訂閱、預設 Haiku 4.5、不另計費）。
- `claude -p` 加 `--allowedTools Read` **能讀參考圖做視覺分析**並寫出 prompt（實測精準）。
- ⚠️ **ToS**：Anthropic 明文禁止「拿 claude.ai 登入/額度做產品給第三方」。**純個人自用＝低風險灰區**；一旦要分享給別人，必須改用付費 API key。另注意訂閱 5h/7d 用量上限。

## 前置（Mac Mini）
```bash
# 1) Claude Code 登入訂閱（一次；之後無頭呼叫免再登）
claude /login                      # 或無瀏覽器環境用： claude setup-token → 設 CLAUDE_CODE_OAUTH_TOKEN
unset ANTHROPIC_API_KEY            # 確保走訂閱（設了會被 API key 蓋掉、變計費）

# 2) apipass 金鑰（已集中於 /Users/mcgradymac/claude_prjs/apipass.env，server 自動載入）

# 3) 依賴
pip install fastapi "uvicorn[standard]" python-multipart   # + 既有 pillow / python-dotenv
```

## 本機先跑通
```bash
cd cloud
uvicorn server:app --host 0.0.0.0 --port 8765
# 同機測試： curl -F intent="黃昏台北101復古海報，標題TAIPEI" -F write_prompt=true http://127.0.0.1:8765/generate
```
瀏覽器開 `http://<mac-ip>:8765` → 應看到 PWA。

## 手機從「任何網路」連得到（不限同區網）

### 方案 A：Tailscale（推薦 · 個人免費 · 私有）
1. Mac Mini 與 Android 都裝 **Tailscale**、登入同一帳號（同一 tailnet）。
2. 手機**在 4G/5G、別人家 wifi 都一樣**：瀏覽器開 `http://<mac-mini-的-tailscale-IP>:8765`（`100.x.x.x`，或 MagicDNS 名 `mac-mini.<tailnet>.ts.net`）。跨網路、NAT 穿透、加密。
3. Chrome 選單 →「加到主畫面」→ 像原生 app。
- **唯一要求**：手機 Tailscale 保持連線（VPN 狀態）。私有、零公開曝險，**不需 `APP_TOKEN`**。

### 方案 B：公開 HTTPS 網址（手機免裝 VPN；包 APK 也用這個）
> 已用 Tailscale 的話最省事：`tailscale funnel --bg 8765` 直接給你固定公開網址 `https://<機器>.<tailnet>.ts.net`（免買網域，見 `apk/README.md`）。以下是 Cloudflare 版：
```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8765     # 快速：吐一個 https://xxx.trycloudflare.com
```
任何瀏覽器直接開那個網址，手機什麼都不用裝。**但後端變公開可達 → 必設 `APP_TOKEN`**：
```bash
export APP_TOKEN=$(python3 -c "import secrets;print(secrets.token_urlsafe(24))")  # 記下來
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8765
```
PWA 第一次被擋（401）會跳出輸入框要你貼 token，存進瀏覽器後續自動帶（`X-App-Token`）。
> ⚠️ 沒設 `APP_TOKEN` 就走 Cloudflare = 把你的 apipass/訂閱開放給全網路盜用，務必設。

## 常駐 24/7 + 重開機自動恢復
重開機後三件事要自己回來：**① 後端 uvicorn ② Tailscale Funnel ③ Claude 訂閱認證**。設好下列，重開機**全自動恢復、手機 app 無感**（公開網址 `.ts.net` 固定、`APP_TOKEN` 固定）。

### 0) macOS 設定（無人值守前提）
```bash
sudo pmset -a sleep 0 disksleep 0       # 不睡眠
```
- System Settings → Users → **開啟「自動登入」**（LaunchAgent 與 Keychain 要在開機後可用）。
- System Settings → Energy → **「停電後自動開機」**。

### 1) Claude 訂閱認證（免互動、跨重開機）
```bash
claude setup-token        # 產生長效 CLAUDE_CODE_OAUTH_TOKEN（複製，放進下面 plist）
```
比靠 Keychain 互動解鎖更穩；放進 plist 後，後端 `claude -p` 開機即可用、免再登入。

### 2) 後端 launchd（開機自啟、崩潰自動重拉）
`~/Library/LaunchAgents/com.imagegen.server.plist`（**此檔在本機、含 token、勿 commit**；改 `<你>` 與路徑）：
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.imagegen.server</string>
  <key>WorkingDirectory</key><string>/Users/<你>/claude_prjs/Image-gen/cloud</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/<你>/claude_prjs/Image-gen/cloud/.venv/bin/uvicorn</string>
    <string>server:app</string><string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8765</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/bin:/bin:/Users/<你>/claude_prjs/Image-gen/cloud/.venv/bin</string>
    <key>APP_TOKEN</key><string>＜你的固定 token，別每次隨機＞</string>
    <key>CLAUDE_CODE_OAUTH_TOKEN</key><string>＜步驟1 setup-token 的值＞</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/imagegen.log</string>
  <key>StandardErrorPath</key><string>/tmp/imagegen.err</string>
</dict></plist>
```
```bash
launchctl load ~/Library/LaunchAgents/com.imagegen.server.plist
```
> - `APP_TOKEN` **務必固定**（別用 `$(secrets...)` 每次隨機，否則手機存的 token 會失效）。
> - `PATH` 要含 `/opt/homebrew/bin`，否則後端 subprocess 找不到 `claude`。
> - `host 127.0.0.1`：對外一律經 Funnel/Tunnel，不直接綁 0.0.0.0。

### 3) Tailscale Funnel（`--bg` 即持久）
`tailscale funnel --bg 8765` 的設定會**存進 serve 設定、重開機由 tailscaled 自動還原**；tailscaled 本身開機自啟、登入狀態持久。重開機後 `tailscale funnel status` 確認網址還在即可。

### 驗證重開機恢復
重開機 → 等 1–2 分 → 手機開 app 應直接能用。或在任何機器：
```bash
curl https://<機器>.<tailnet>.ts.net/healthz      # 回 {"ok":true} 即三件事都回來了
```

## API
`POST /generate`（multipart form）：`intent`(必) · `model`(預設 openai/gpt-image-2) · `aspect`(1:1…) · `resolution`(""/1K/2K/4K) · `write_prompt`(true/false) · `refs`(檔案，最多 5)。
回 `{ok, prompt, image_url}`；圖經 `GET /img/<name>` 取回。`GET /healthz` 健康檢查。

## 包成 App（兩個層級）
PWA 已含 `manifest.webmanifest` + `static/sw.js`（service worker），**前提：HTTPS**（SW 只在安全來源註冊）。

1. **PWA 安裝（免商店、免 build，推薦）**：先讓站台走 HTTPS——
   - Tailscale：`tailscale serve --bg http://localhost:8765` → 用 `https://<mac-mini>.<tailnet>.ts.net` 開站。
   - 或 Cloudflare Tunnel（本來就 HTTPS）。
   Chrome 開站 → 選單「**安裝應用程式**」→ 獨立視窗、桌面圖示，像原生 app。
2. **真・APK（可側載/上 Play Store）**：用 **PWABuilder**（網頁，貼公開 HTTPS 網址 → 產 Android 套件）或 **Bubblewrap** CLI，把這個 PWA 包成 **TWA** 的 `.apk`/`.aab`（底層仍是此 PWA、零原生碼）。需公開 HTTPS（走 Cloudflare Tunnel）；上架另需 Digital Asset Links。

## 未來可加
- prompt 那層想完全避開 ToS 灰區 → 換 Mac Mini 本地 Ollama（免費、無疑慮）。
- 想分享給別人 → 改付費 API key + Cloudflare Tunnel + app 鑑權。
