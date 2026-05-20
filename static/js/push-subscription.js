/**
 * Push Subscription Management
 * 
 * State priority (REAL STATE - SERVICE WORKER SUBSCRIPTION):
 * 1. Actual service worker subscription (ground truth)
 * 2. Backend stored state (secondary)
 * 
 * Handles:
 * - Lazy loading on first user action
 * - Syncing subscriptions on page load
 * - Enabling/disabling notifications
 * - Managing VAPID key and subscription
 * - CRITICAL: Preventing duplicate subscription attempts and AbortError
 */

const PushSubscriptionManager = (function () {
  const VAPID_PUBLIC_KEY = null; // Will be fetched from config endpoint
  let registration = null;
  let currentSubscription = null;
  let isInitialized = false;
  
  // Guard against duplicate subscription attempts
  let isSubscribing = false;
  let isUnsubscribing = false;

  /**
   * Initialize the push subscription manager.
   * Called once on page load to sync existing subscription.
   */
  async function init() {
    if (isInitialized) return;
    isInitialized = true;

    // Fetch VAPID public key from backend
    try {
      const configResp = await fetch('/api/push-config', { credentials: 'include' });
      if (!configResp.ok) {
        console.warn('[Push] Failed to fetch push config:', configResp.status);
        return;
      }
      const config = await configResp.json();
      if (!config.vapid_public_key) {
        console.warn('[Push] No VAPID public key in config');
        return;
      }
      window.VAPID_PUBLIC_KEY = config.vapid_public_key;
    } catch (err) {
      console.warn('[Push] Error fetching push config:', err);
      return;
    }

    // Register service worker
    if (!('serviceWorker' in navigator)) {
      console.warn('[Push] Service workers not supported');
      return;
    }

    try {
      registration = await navigator.serviceWorker.register('/service-worker.js', {
        scope: '/',
        updateViaCache: 'none'
      });
    } catch (err) {
      console.error('[Push] Service Worker registration failed:', err);
      return;
    }

    // Sync existing subscription with backend
    try {
      await syncSubscription();
    } catch (err) {
      console.warn('[Push] Failed to sync subscription:', err);
    }

    // Update UI status
    await updateUIStatus();
  }

  /**
   * Get or create push subscription.
   * Called when user enables notifications.
   * 
   * CRITICAL: Includes duplicate prevention and service worker readiness check.
   */
  async function getOrCreateSubscription() {
    if (!registration) {
      throw new Error('Service Worker not registered');
    }

    if (!window.VAPID_PUBLIC_KEY) {
      throw new Error('VAPID public key not available');
    }

    // Wait for service worker to be ready before subscribing
    registration = await navigator.serviceWorker.ready;

    let subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      currentSubscription = subscription;
      return subscription;
    }

    await new Promise(resolve => setTimeout(resolve, 300));

    const convertedKey = urlBase64ToUint8Array(window.VAPID_PUBLIC_KEY);
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: convertedKey
    });

    currentSubscription = subscription;
    return subscription;
  }

  /**
   * Check if there's an actual push subscription in service worker.
   * This checks REAL state, not backend claim.
   * Used by UI to validate backend state before accepting it.
   */
  async function hasRealSubscription() {
    try {
      if (!registration) {
        return false;
      }

      const subscription = await registration.pushManager.getSubscription();
      return subscription !== null;
    } catch (err) {
      console.error('[Push] Failed to check real subscription:', err);
      return false;
    }
  }

  /**
   * Sync current subscription with backend.
   * Called on every page load to ensure subscription is up-to-date.
   */
  async function syncSubscription() {
    if (!registration) {
      return;
    }

    const subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      return;
    }
    try {
      const resp = await fetch('/push/sync-subscription', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(subscription.toJSON())
      });

      if (resp.ok) {
        currentSubscription = subscription;
      } else {
        console.warn('[Push] Sync failed:', resp.status);
      }
    } catch (err) {
      console.error('[Push] Sync error:', err);
    }
  }

  /**
   * Enable push notifications.
   * CRITICAL: Includes guard against duplicate subscription attempts.
   */
  async function enable() {
    // Guard: prevent multiple simultaneous enable attempts (prevents AbortError)
    if (isSubscribing) {
      console.warn('[Push] Already subscribing, ignoring duplicate enable call');
      return false;
    }

    isSubscribing = true;

    try {
      // Request permission
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        console.warn('[Push] Notification permission denied:', permission);
        throw new Error('Permission denied');
      }

      // Get or create subscription
      const subscription = await getOrCreateSubscription();

      // Send to backend
      const resp = await fetch('/push/subscribe', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(subscription.toJSON())
      });

      if (!resp.ok) {
        throw new Error(`Subscription save failed: ${resp.status}`);
      }

      await updateUIStatus();
      return true;
    } catch (err) {
      console.error('[Push] Failed to enable notifications:', err);
      throw err;
    } finally {
      isSubscribing = false;
    }
  }

  /**
   * Disable push notifications.
   * CRITICAL: Includes guard against duplicate unsubscribe attempts.
   */
  async function disable() {
    // Guard: prevent multiple simultaneous disable attempts
    if (isUnsubscribing) {
      console.warn('[Push] Already unsubscribing, ignoring duplicate disable call');
      return false;
    }

    isUnsubscribing = true;

    try {
      if (!registration) {
        throw new Error('Service Worker not registered');
      }

      const subscription = await registration.pushManager.getSubscription();
      if (!subscription) {
        await updateUIStatus();
        return true;
      }

      // Unsubscribe from push manager
      await subscription.unsubscribe();

      // Notify backend
      const resp = await fetch('/push/unsubscribe', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(subscription.toJSON())
      });

      if (!resp.ok) {
        console.warn('[Push] Backend unsubscribe failed:', resp.status);
      }

      currentSubscription = null;
      await updateUIStatus();
      return true;
    } catch (err) {
      console.error('[Push] Failed to disable notifications:', err);
      throw err;
    } finally {
      isUnsubscribing = false;
    }
  }

  /**
   * Get current subscription status.
   */
  async function getStatus() {
    try {
      const resp = await fetch('/push/status', { credentials: 'include' });
      if (!resp.ok) {
        return { enabled: false };
      }
      return await resp.json();
    } catch (err) {
      console.error('[Push] Status check failed:', err);
      return { enabled: false };
    }
  }

  /**
   * Update UI elements to reflect current status.
   */
  async function updateUIStatus() {
    // Prefer the REAL browser subscription state over backend claims
    const bell = document.getElementById('notification-bell');
    const toggle = document.getElementById('notifications-toggle');
    if (!bell) return;

    const badge = document.getElementById('notification-badge');

    let realSubscriptionExists = false;
    try {
      realSubscriptionExists = await hasRealSubscription();
    } catch (err) {
      console.warn('[Push] Error checking real subscription state:', err);
    }

    // Only show enabled if the browser actually has a subscription.
    const enabled = Boolean(realSubscriptionExists);

    bell.classList.toggle('enabled', enabled);
    bell.title = enabled ? 'Notifications enabled' : 'Notifications disabled';
    if (toggle) toggle.checked = enabled;

    if (badge) {
      if (enabled) {
        badge.textContent = 'ON';
        badge.classList.add('show');
      } else {
        badge.textContent = '0';
        badge.classList.remove('show');
      }
    }
  }

  /**
   * Convert URL-safe Base64 to Uint8Array.
   */
  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding)
      .replace(/\-/g, '+')
      .replace(/_/g, '/');

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  /**
   * Public API
   */
  return {
    init,
    enable,
    disable,
    getStatus,
    updateUIStatus,
    syncSubscription,
    hasRealSubscription  // NEW: Check actual subscription status
  };
})();

// Auto-initialize on DOMContentLoaded
document.addEventListener('DOMContentLoaded', function () {
  PushSubscriptionManager.init().catch(err => {
    console.warn('[Push] Initialization error:', err);
  });
});
