/* AudioBookRequest Service Worker */
(() => {
  const VERSION = 'abr-sw-v1';
  const toPath = (p) => {
    try {
      const base = new URL(self.registration.scope).pathname.replace(/\/$/, '');
      return `${base}${p.startsWith('/') ? p : '/' + p}`;
    } catch {
      return p;
    }
  };

  const CORE_ASSETS = [
    '/',
    '/static/globals.css',
    '/static/htmx.js',
    '/static/htmx-preload.js',
    '/static/alpine.js',
    '/static/toastify.js',
    '/static/toastify.css',
    '/static/favicon.svg',
    '/static/favicon-32x32.png',
    '/static/favicon-16x16.png',
    '/static/apple-touch-icon.png',
    '/static/android-chrome-192x192.png',
    '/static/android-chrome-512x512.png',
    '/static/site.webmanifest'
  ].map(toPath);

  self.addEventListener('install', (event) => {
    event.waitUntil(
      caches.open(VERSION).then((cache) => cache.addAll(CORE_ASSETS)).catch(() => void 0)
    );
    self.skipWaiting();
  });

  self.addEventListener('activate', (event) => {
    event.waitUntil(
      caches.keys().then((keys) => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim())
    );
  });

  const isHTMLRequest = (request) => {
    return request.mode === 'navigate' || (request.headers.get('accept') || '').includes('text/html');
  };

  self.addEventListener('fetch', (event) => {
    const req = event.request;
    const url = new URL(req.url);

    // Only handle same-origin
    if (url.origin !== self.location.origin) return;

    if (isHTMLRequest(req)) {
      // Network-first for HTML navigations
      event.respondWith(
        fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(VERSION).then((cache) => cache.put(req, copy));
          return res;
        }).catch(() => caches.match(req))
      );
      return;
    }

    // Cache-first for static assets
    if (url.pathname.startsWith(toPath('/static'))) {
      event.respondWith(
        caches.match(req).then((cached) => {
          const fetchPromise = fetch(req).then((networkRes) => {
            if (networkRes && networkRes.status === 200) {
              const copy = networkRes.clone();
              caches.open(VERSION).then((cache) => cache.put(req, copy));
            }
            return networkRes;
          }).catch(() => cached);
          return cached || fetchPromise;
        })
      );
      return;
    }
  });
})();
