// const CACHE_NAME = 'diabeatit-cache-v3';
// const OFFLINE_URL = '/static/offline.html';
// const CDN_ORIGINS = ['https://cdn.jsdelivr.net'];

// const PRECACHE_URLS = [
//   '/',
//   '/signup',
//   '/forgot_password',
//   '/static/css/base.css',
//   '/static/css/track.css',
//   '/static/css/signup.css',
//   '/static/js/track.js',
//   '/static/js/pwa-register.js',
//   '/manifest.webmanifest',
//   '/static/icons/icon-192.png',
//   '/static/icons/icon-512.png',
//   '/static/icons/apple-touch-icon.png',
//   OFFLINE_URL
// ];

// self.addEventListener('install', function (event) {
//   event.waitUntil(
//     caches.open(CACHE_NAME).then(function (cache) {
//       return cache.addAll(PRECACHE_URLS);
//     })
//   );
//   self.skipWaiting();
// });

// self.addEventListener('activate', function (event) {
//   event.waitUntil(
//     caches.keys().then(function (cacheNames) {
//       return Promise.all(
//         cacheNames
//           .filter(function (cacheName) {
//             return cacheName !== CACHE_NAME;
//           })
//           .map(function (cacheName) {
//             return caches.delete(cacheName);
//           })
//       );
//     })
//   );
//   self.clients.claim();
// });

// self.addEventListener('fetch', function (event) {
//   const request = event.request;
//   if (request.method !== 'GET') {
//     return;
//   }

//   const requestUrl = new URL(request.url);
//   const isCdnAsset = CDN_ORIGINS.includes(requestUrl.origin);
//   if (requestUrl.origin !== self.location.origin && !isCdnAsset) {
//     return;
//   }

//   if (isCdnAsset) {
//     event.respondWith(
//       caches.match(request).then(function (cachedResponse) {
//         if (cachedResponse) {
//           return cachedResponse;
//         }

//         return fetch(request)
//           .then(function (response) {
//             if (!response) {
//               return response;
//             }

//             const responseClone = response.clone();
//             caches.open(CACHE_NAME).then(function (cache) {
//               cache.put(request, responseClone);
//             });
//             return response;
//           })
//           .catch(function () {
//             return undefined;
//           });
//       })
//     );
//     return;
//   }

//   if (request.mode === 'navigate') {
//     event.respondWith(
//       fetch(request)
//         .then(function (response) {
//           const responseClone = response.clone();
//           caches.open(CACHE_NAME).then(function (cache) {
//             cache.put(request, responseClone);
//           });
//           return response;
//         })
//         .catch(function () {
//           return caches.match(request).then(function (cachedPage) {
//             return cachedPage || caches.match(OFFLINE_URL);
//           });
//         })
//     );
//     return;
//   }

//   event.respondWith(
//     caches.match(request).then(function (cachedResponse) {
//       if (cachedResponse) {
//         return cachedResponse;
//       }

//       return fetch(request)
//         .then(function (response) {
//           if (!response || response.status !== 200 || response.type !== 'basic') {
//             return response;
//           }

//           const responseClone = response.clone();
//           caches.open(CACHE_NAME).then(function (cache) {
//             cache.put(request, responseClone);
//           });
//           return response;
//         })
//         .catch(function () {
//           return undefined;
//         });
//     })
//   );
// });

// self.addEventListener('push', function (event) {
//   let payload = {};

//   try {
//     payload = event.data ? event.data.json() : {};
//   } catch (error) {
//     payload = { body: event.data ? event.data.text() : '' };
//   }

//   const title = payload.title || 'DiaBeatIt';
//   const options = {
//     body: payload.body || 'Open DiaBeatIt to review your latest health updates.',
//     icon: payload.icon || '/static/icons/icon-192.png',
//     badge: payload.badge || '/static/icons/icon-192.png',
//     tag: payload.tag || 'diabeatit-push',
//     renotify: true,
//     requireInteraction: true,
//     data: { url: payload.url || '/dashboard' }
//   };

//   event.waitUntil(self.registration.showNotification(title, options));
// });

// self.addEventListener('message', function (event) {
//   if (!event.data || event.data.type !== 'show-notification') {
//     return;
//   }

//   const payload = event.data.payload || {};
//   event.waitUntil(
//     self.registration.showNotification(payload.title || 'DiaBeatIt', {
//       body: payload.body || 'Open DiaBeatIt to review your latest health updates.',
//       icon: payload.icon || '/static/icons/icon-192.png',
//       badge: payload.badge || '/static/icons/icon-192.png',
//       tag: payload.tag || 'diabeatit-push',
//       renotify: true,
//       requireInteraction: true,
//       data: { url: payload.url || '/dashboard' }
//     })
//   );
// });

// self.addEventListener('notificationclick', function (event) {
//   event.notification.close();

//   const targetUrl = (event.notification.data && event.notification.data.url) || '/track';

//   event.waitUntil(
//     clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
//       for (let i = 0; i < clientList.length; i += 1) {
//         const client = clientList[i];
//         if ('focus' in client) {
//           client.focus();
//           if ('navigate' in client) {
//             client.navigate(targetUrl);
//           }
//           return client;
//         }
//       }

//       if (clients.openWindow) {
//         return clients.openWindow(targetUrl);
//       }

//       return undefined;
//     })
//   );
// });

self.addEventListener('install', event => {
  console.log('SW installed');
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  console.log('SW activated');
});

self.addEventListener('push', event => {
  console.log('Push received');

  event.waitUntil(
    self.registration.showNotification('Test', {
      body: 'Push working'
    })
  );
});