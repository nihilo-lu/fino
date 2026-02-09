/**
 * 投资追踪器 PWA Service Worker
 * 提供离线缓存与安装支持
 */

const CACHE_NAME = 'fino-investment-tracker-v1';
const STATIC_ASSETS = [
  '/',
  '/frontend/index.html',
  '/frontend/css/styles.css',
  '/frontend/js/vue/main.js',
  '/frontend/js/vue/App.js',
  '/manifest.json',
  '/frontend/icons/icon-192.png',
  '/frontend/icons/icon-512.png'
];

// 安装：缓存静态资源
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('SW: 部分资源缓存失败', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// 激活：清理旧缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

//  fetch：网络优先，失败时回退到缓存
self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.url.startsWith('http') && !request.url.includes('/api/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match('/frontend/index.html')))
    );
  }
});
