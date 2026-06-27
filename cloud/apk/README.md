# 📦 把 PWA 包成真・APK（TWA · 可側載/上架）

底層仍是 `cloud/static/` 那個 PWA，用 **TWA（Trusted Web Activity）** 包成 Android `.apk`/`.aab`，**零原生程式碼**。

## 🔑 唯一硬前提：一個「穩定」公開 HTTPS 網址
TWA 會把網址烤進 APK，且要靠 Digital Asset Links 驗證 → **不能用每次變動的臨時 tunnel**。

### 方式 A：Tailscale Funnel（推薦 · 免買網域）
你既有的 Tailscale 就能給一個**固定的公開 HTTPS 網址** `https://<mac-mini>.<tailnet>.ts.net`：
1. Tailscale 管理後台啟用 **HTTPS 憑證**（MagicDNS + HTTPS Certificates）與 **Funnel**（Access Controls 給該機 `funnel` nodeAttr）。
2. 後端跑著（:8765），然後：
   ```bash
   tailscale funnel --bg 8765        # 公開 443 → localhost:8765；--bg = 背景常駐
   tailscale funnel status           # 確認公開網址
   ```
3. 公開網址 = `https://<mac-mini>.<tailnet>.ts.net`（Funnel 公開側僅 443/8443/10000，預設 443）。
> Funnel = 公開可達 → **務必 `export APP_TOKEN=...`**（見 ../PHONE-APP.md），否則 apipass/訂閱會被盜用。

### 方式 B：Cloudflare named tunnel（你已擁有自己的網域時）
```bash
cloudflared tunnel login
cloudflared tunnel create imagegen
cloudflared tunnel route dns imagegen img.你的網域
cloudflared tunnel run --url http://localhost:8765 imagegen   # 可做成 launchd 常駐
```
得到 `https://img.你的網域`。（同樣公開 → 設 `APP_TOKEN`）

> 下面 `https://<你的網址>` 兩條路線通用，填方式 A 的 `.ts.net` 或方式 B 的自有網域皆可。

---

## 路線 1：PWABuilder（最簡，免本機 Android 工具鏈）
1. 後端 + tunnel 跑起來，確認 `https://img.你的網域` 能開到 PWA。
2. 開 **https://www.pwabuilder.com** → 貼網址 → 分析 → **Package For Stores → Android**。
3. 選 signing（可讓它幫你產 key，**務必下載保存 keystore**）→ 下載 zip（含 `.apk`/`.aab` + `assetlinks.json`）。
4. 把它給的 `assetlinks.json` 內容貼進 `../static/.well-known/assetlinks.json`（後端已有路由服務它）。
5. 側載 `.apk`（見下）；上架用 `.aab` 傳 Play Console。

## 路線 2：Bubblewrap（本機、可重現、進 git）
需 **Node.js + JDK 17**（Bubblewrap 首次會協助下載 Android SDK）。
```bash
cd cloud/apk
cp twa-manifest.template.json twa-manifest.json      # 把 REPLACE_DOMAIN 換成 img.你的網域
./build.sh https://img.你的網域                       # 裝 bubblewrap → init → build（首次建 keystore）
# 產出： app-release-signed.apk（側載） / app-release-bundle.aab（上架）
bubblewrap fingerprint generateAssetLinks            # 產 assetlinks.json → 貼到 ../static/.well-known/assetlinks.json
```

---

## Digital Asset Links（讓 app 全螢幕、去掉網址列）
1. 拿到簽章金鑰的 SHA256 指紋（PWABuilder zip 內附，或 `bubblewrap fingerprint`）。
2. 複製 `../static/.well-known/assetlinks.json.example` → `assetlinks.json`，填入 `package_name`（`dev.imagegen.twa`）與指紋。
3. 後端 `/.well-known/assetlinks.json` 路由會自動服務它；重開 app 即全螢幕。
> 沒設 assetlinks 也能跑，只是會顯示一條細網址列（Custom Tab fallback）。

## 側載到自己手機
```bash
adb install app-release-signed.apk
# 或：把 .apk 傳到手機 → 點開 → 允許「未知來源」安裝
```

## ⚠️ 提醒
- **keystore 一定要保存**（遺失＝無法再更新同一個 app）。別 commit 進 git。
- 公開網域 = 後端面向全網 → **務必 `APP_TOKEN`**（見 ../PHONE-APP.md）。
- 上 Play Store 需開發者帳號（一次性 $25）+ asset links 設定。純自用側載則免。
