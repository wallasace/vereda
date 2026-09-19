// O app é um arquivo só, então o cache também é simples: guarda a casca e serve
// do cache quando a rede some. Uma chamada não funciona offline, claro — o que
// isto resolve é abrir o app instantaneamente e sobreviver a link instável.
const VERSION = 'vereda-v1';
const CASCA = ['./', './index.html', './manifest.webmanifest',
               './icons/icon-192.png', './icons/icon-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(CASCA)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  // Sinalização e credenciais nunca saem do cache: uma credencial de TURN
  // vencida servida do cache derrubaria a chamada sem explicação.
  const url = new URL(req.url);
  if (url.origin !== location.origin || url.pathname.endsWith('/ice')) return;

  // Rede primeiro para que uma versão nova chegue na hora; cache é o plano B.
  e.respondWith(
    fetch(req)
      .then((res) => {
        const copia = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copia));
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match('./index.html')))
  );
});
