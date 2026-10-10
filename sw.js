// BeerSniffer service worker
// - Shell (forside, logo, fonts): network-first for HTML, cache-first for statiske filer
// - data.json?v=<version>: cache-first (URL'en ændrer sig ved hver build, så den er altid frisk)
// Bump CACHE hvis du ændrer strategi.
const CACHE = 'bs-v1';
const SHELL = ['/', '/logo.png', '/logo-hero.png', '/fonts/bebas-neue-latin-400-normal.woff2', '/fonts/dm-sans-latin-wght-normal.woff2'];

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE)
            .then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => {}))))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys()
            .then(keys => Promise.all(keys.filter(k => k.startsWith('bs-') && k !== CACHE).map(k => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', e => {
    const req = e.request;
    if (req.method !== 'GET') return;
    const url = new URL(req.url);
    if (url.origin !== location.origin) return;           // gtag, Cookiebot m.m. røres ikke

    // data.json: cache-first pr. versions-URL; ryd gamle versioner
    if (url.pathname === '/data.json') {
        e.respondWith((async () => {
            const c = await caches.open(CACHE);
            const hit = await c.match(req);
            if (hit) return hit;
            try {
                const res = await fetch(req);
                if (res.ok) {
                    const old = await c.keys();
                    await Promise.all(old.filter(k => new URL(k.url).pathname === '/data.json').map(k => c.delete(k)));
                    await c.put(req, res.clone());
                }
                return res;
            } catch (err) {
                const any = await c.match(req, { ignoreSearch: true });
                if (any) return any;
                throw err;
            }
        })());
        return;
    }

    // Sider: netværk først, cache som fallback (offline)
    if (req.mode === 'navigate') {
        e.respondWith((async () => {
            try {
                const res = await fetch(req);
                if (res.ok && url.pathname === '/') {
                    const c = await caches.open(CACHE);
                    c.put('/', res.clone());
                }
                return res;
            } catch (err) {
                return (await caches.match(req)) || (await caches.match('/')) || Response.error();
            }
        })());
        return;
    }

    // Statiske filer i shell: cache-first
    if (SHELL.includes(url.pathname)) {
        e.respondWith(caches.match(req).then(hit => hit || fetch(req)));
    }
});
