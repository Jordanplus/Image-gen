// 最小 service worker：讓 PWA 可安裝（獨立視窗/圖示）+ app shell 離線可開。
// 注意：Service Worker 只在安全來源（HTTPS 或 localhost）註冊；
// Tailscale 純 http IP 不算安全來源 → 用 `tailscale serve` 或 Cloudflare Tunnel 提供 HTTPS。
const CACHE = 'imagegen-v1';

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(['/', '/manifest.webmanifest'])));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const u = new URL(e.request.url);
  // API 與產出圖一律走網路（不快取，避免拿到舊結果）
  if (u.pathname.startsWith('/generate') || u.pathname.startsWith('/img/')) return;
  // app shell：cache-first，離線也能開介面
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
