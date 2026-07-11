// Minimal service worker — required for PWA installability.
// Intentionally does no caching: this app depends entirely on live
// NVIDIA API calls, so there is no meaningful offline mode to support.
self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', () => {
  // No-op: all requests pass through to the network as normal.
});
