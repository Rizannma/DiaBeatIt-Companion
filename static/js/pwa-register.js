// Lightweight shim: delegate PWA registration and subscription management
// to PushSubscriptionManager (if present). This avoids duplicate registration
// logic and reliance on an undefined `window.diabeatitPushConfig`.

(function () {
  if (!('serviceWorker' in navigator)) return;

  // If the newer PushSubscriptionManager is loaded, let it handle SW/register/subscription.
  if (typeof PushSubscriptionManager !== 'undefined' && typeof PushSubscriptionManager.init === 'function') {
    // Init may already be called by push-subscription.js, but calling again is safe.
    document.addEventListener('DOMContentLoaded', function () {
      try {
        PushSubscriptionManager.init && PushSubscriptionManager.init().catch(function (err) {
          console.warn('[PWA] PushSubscriptionManager.init failed:', err);
        });
      } catch (e) {
        console.warn('[PWA] PushSubscriptionManager.init threw:', e);
      }
    });
    return;
  }

  // Fallback: register the service worker so `navigator.serviceWorker.ready` works for manual checks.
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/service-worker.js', { scope: '/' })
      .catch(function (error) {
        console.warn('[PWA] Service worker registration failed (fallback):', error);
      });
  });
})();