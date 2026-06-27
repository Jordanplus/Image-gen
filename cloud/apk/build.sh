#!/usr/bin/env bash
# 用 Bubblewrap 把 PWA 包成 TWA 的 APK/AAB（底層仍是 cloud/static 那個 PWA、零原生碼）。
#
# 前提：
#   - 一個「穩定」公開 HTTPS 網域指向後端（named Cloudflare Tunnel；別用每次變動的臨時 URL）。
#   - Node.js（Bubblewrap 為 npm 套件）+ JDK 17；Bubblewrap 首次會協助下載 Android SDK。
#
# 用法：
#   ./build.sh https://your.domain
set -euo pipefail
DOMAIN="${1:?用法: ./build.sh https://your.domain （穩定公開 HTTPS 網域）}"
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE"

command -v bubblewrap >/dev/null 2>&1 || { echo "[apk] 安裝 @bubblewrap/cli ..."; npm i -g @bubblewrap/cli; }

if [ ! -f twa-manifest.json ]; then
  echo "[apk] 從 $DOMAIN/manifest.webmanifest 初始化（互動式，依提示回答；package 用 dev.imagegen.twa）..."
  bubblewrap init --manifest "$DOMAIN/manifest.webmanifest"
fi

echo "[apk] build ..."
bubblewrap build      # 產 app-release-signed.apk + app-release-bundle.aab；首次會建 keystore

echo ""
echo "[apk] ✅ 完成：app-release-signed.apk（側載）/ app-release-bundle.aab（上架）"
echo "[apk] 取得 Digital Asset Links（全螢幕、去掉網址列）："
echo "      bubblewrap fingerprint generateAssetLinks"
echo "      → 把輸出貼進 ../static/.well-known/assetlinks.json（後端已有 /.well-known/assetlinks.json 路由）"
echo "[apk] 側載： adb install app-release-signed.apk   （或把 apk 傳到手機點開、開啟未知來源安裝）"
