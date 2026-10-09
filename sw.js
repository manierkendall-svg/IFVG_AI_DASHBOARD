self.addEventListener("install", (event) => {
  event.waitUntil(caches.open("vision-brain-v1").then((cache) => cache.addAll(["/", "/static/styles.css", "/static/app.js"])));
});

self.addEventListener("fetch", (event) => {
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
