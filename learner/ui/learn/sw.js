/**
 * The learner's page, kept on the device so it opens with no network.
 *
 * Only the page itself is cached here: what it teaches is kept by the page, in IndexedDB, as
 * a package the learner chose to keep. API calls are never answered from this cache: an old
 * answer from the server, served as though it were fresh, is worse than an honest "offline".
 */
const SHELL = "urithi-learn-v3";
const FILES = ["./", "index.html", "learn.css", "learn.js", "manifest.webmanifest", "/shared/audio.js", "/shared/urithi.css", "/shared/theme.js",
  "/shared/tree.js", "/shared/teleprompter.js", "/shared/live.js", "/shared/keys.js"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((cache) => cache.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.pathname.startsWith("/api/")) return;
  // Network first, so a new version is used as soon as it exists; the cache when offline.
  event.respondWith(fetch(event.request)
    .then((response) => {
      const copy = response.clone();
      caches.open(SHELL).then((cache) => cache.put(event.request, copy));
      return response;
    })
    .catch(() => caches.match(event.request, { ignoreSearch: true })));
});
