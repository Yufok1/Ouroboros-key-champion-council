var CACHE_NAME = 'champion-council-v133b';
var STATIC_ASSETS = [
    '/static/vscode-shim.js?v=25',
    '/static/svg-pan-zoom.min.js',
    '/static/peerjs.min.js',
    '/static/three.min.js',
    '/static/OrbitControls.js',
    '/static/TransformControls.js',
    '/static/CSS2DRenderer.js',
    '/static/GLTFLoader.js',
    '/static/Water.js',
    '/static/rapier3d-compat/rapier.es.js',
    '/static/rapier3d-compat/rapier_wasm3d.js',
    '/static/rapier3d-compat/rapier_wasm3d_bg.wasm',
    '/static/main.js?v=133b',
    '/static/manifest.json',
    '/static/icon.svg',
    '/static/assets/packs/index.json',
    '/static/assets/waternormals.jpg'
];

self.addEventListener('install', function (event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function (cache) {
            return cache.addAll(STATIC_ASSETS);
        }).then(function () {
            return self.skipWaiting();
        })
    );
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (cacheNames) {
            return Promise.all(
                cacheNames.filter(function (name) {
                    return name !== CACHE_NAME;
                }).map(function (name) {
                    return caches.delete(name);
                })
            );
        }).then(function () {
            return self.clients.claim();
        })
    );
});

self.addEventListener('fetch', function (event) {
    if (!event.request || event.request.method !== 'GET') return;
    var requestUrl = new URL(event.request.url);
    if (requestUrl.origin !== self.location.origin) return;
    if (
        event.request.mode === 'navigate' ||
        requestUrl.pathname === '/' ||
        requestUrl.pathname === '/panel' ||
        requestUrl.pathname === '/static/panel.html' ||
        requestUrl.pathname.indexOf('/panel-live/') === 0
    ) {
        event.respondWith(fetch(event.request));
        return;
    }
    if (requestUrl.pathname.indexOf('/api/') === 0 || requestUrl.pathname.indexOf('/mcp/') === 0) {
        event.respondWith(fetch(event.request));
        return;
    }
    if (requestUrl.pathname === '/static/main.js' || requestUrl.pathname === '/static/sw.js') {
        event.respondWith(
            fetch(event.request).then(function (response) {
                if (!response || response.status !== 200 || response.type !== 'basic') return response;
                var copy = response.clone();
                caches.open(CACHE_NAME).then(function (cache) {
                    cache.put(event.request, copy);
                });
                return response;
            }).catch(function () {
                return caches.match(event.request).then(function (cached) {
                    if (cached) return cached;
                    var normalizedDynamic = new URL(event.request.url);
                    normalizedDynamic.search = '';
                    return caches.match(normalizedDynamic.toString());
                });
            })
        );
        return;
    }
    if (requestUrl.pathname.indexOf('/static/assets/packs/') === 0 && /\.json$/i.test(requestUrl.pathname)) {
        event.respondWith(
            fetch(event.request).then(function (response) {
                if (!response || response.status !== 200 || response.type !== 'basic') return response;
                var normalizedPack = new URL(event.request.url);
                normalizedPack.search = '';
                var copy = response.clone();
                caches.open(CACHE_NAME).then(function (cache) {
                    cache.put(normalizedPack.toString(), copy);
                });
                return response;
            }).catch(function () {
                var fallbackUrl = new URL(event.request.url);
                fallbackUrl.search = '';
                return caches.match(fallbackUrl.toString()).then(function (fallback) {
                    return fallback || caches.match(event.request);
                });
            })
        );
        return;
    }
    event.respondWith(
        caches.match(event.request).then(function (exact) {
            if (exact) return exact;
            var normalized = new URL(event.request.url);
            normalized.search = '';
            return caches.match(normalized.toString()).then(function (fallback) {
                if (fallback) return fallback;
                return fetch(event.request).then(function (response) {
                    if (!response || response.status !== 200 || response.type !== 'basic') return response;
                    var copy = response.clone();
                    caches.open(CACHE_NAME).then(function (cache) {
                        var contentType = String(response.headers.get('content-type') || '').toLowerCase();
                        if (contentType.indexOf('text/html') === -1) {
                            cache.put(normalized.toString(), copy);
                        }
                    });
                    return response;
                });
            });
        })
    );
});
