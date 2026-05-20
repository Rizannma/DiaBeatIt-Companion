/**
 * Notification Bell UI Component
 *
 * State priority (SOURCE OF TRUTH order):
 * 1. Service Worker subscription (actual push registration) - REAL STATE
 * 2. Backend stored state (server confirmation)
 * 3. In-memory isSubscribed (never source of truth, derived state)
 * 
 * Key principles:
 * - Backend cannot override user choice without confirmation
 * - Always validate against actual service worker subscription
 * - Prevent duplicate subscribe attempts
 */

const NotificationBellUI = (function () {
  const bellSelector = '#notification-bell';
  const badgeSelector = '#notification-badge';
  
  // App-level subscription state (derived from real state, not source of truth)
  let isSubscribed = false;
  
  // Async operation lock - prevents race conditions from multiple clicks
  let isProcessing = false;

  async function init() {
    const bell = document.querySelector(bellSelector);
    const badge = document.querySelector(badgeSelector);

    if (!bell) {
      console.warn('[NotificationBell] Bell element not found');
      return;
    }

    // Step 1: Check ACTUAL subscription via service worker (real ground truth)
    const realSubscriptionExists = await checkRealSubscription();

    // Step 3: Sync with backend ONLY if it matches real subscription
    // This prevents backend from overriding user's disabled choice
    await syncSubscriptionStateWithValidation(badge, realSubscriptionExists);

    bell.addEventListener('click', function () {
      handleBellClick(bell, badge).catch(err => {
        console.error('[NotificationBell] Click handler failed:', err);
      });
    });

  }

  /**
   * Check if there's an actual push subscription via service worker.
   * This is the REAL state, not what backend claims.
   */
  async function checkRealSubscription() {
    try {
      const hasSubscription = await PushSubscriptionManager.hasRealSubscription();
      return hasSubscription;
    } catch (err) {
      console.warn('[NotificationBell] Failed to check real subscription:', err);
      return false;
    }
  }

  /**
   * Sync subscription state with backend, validating against real subscription.
   * KEY: Backend state is only accepted if it matches the real subscription status.
   * This prevents backend from overriding user's disabled choice.
   */
  async function syncSubscriptionStateWithValidation(badge, realSubscriptionExists) {
    try {
      const status = await PushSubscriptionManager.getStatus();
      const backendEnabled = Boolean(status.enabled);
      
      
      // CRITICAL: Only trust backend if it matches reality
      // If backend says enabled but no real subscription, keep the real browser state
      // If backend says disabled but real subscription exists, restore real state
      const consistentState = backendEnabled === realSubscriptionExists;
      
      if (!consistentState) {
        console.warn('[NotificationBell] Backend state inconsistent with real subscription. Using real state:', realSubscriptionExists);
        isSubscribed = realSubscriptionExists;
      } else {
        isSubscribed = backendEnabled;
      }
      
      updateBellUIState(isSubscribed, badge);
    } catch (err) {
      console.warn('[NotificationBell] Failed to sync state:', err);
      updateBellUIState(isSubscribed, badge);
    }
  }

  /**
   * Handle bell click - decides whether to enable or disable based on isSubscribed state.
   * Includes race condition prevention with processing lock.
   */
  async function handleBellClick(bell, badge) {
    // Prevent multiple simultaneous operations
    if (isProcessing) {
      return;
    }

    if (!isSubscribed) {
      // ENABLE FLOW: notifications are currently disabled
      await enableNotifications(bell, badge);
    } else {
      // DISABLE FLOW: notifications are currently enabled
      const confirmDisable = window.confirm('Do you want to disable notifications?');
      if (confirmDisable) {
        await disableNotifications(bell, badge);
      }
    }
  }

  async function enableNotifications(bell, badge) {
    isProcessing = true;
    try {
      const success = await PushSubscriptionManager.enable();
      if (success) {
        // Verify actual subscription exists after enable
        const realSubscriptionExists = await checkRealSubscription();
        if (realSubscriptionExists) {
          // Only mark as subscribed if real subscription confirmed
          isSubscribed = true;
          updateBellUIState(true, badge, 'Notifications enabled');
        } else {
          console.warn('[NotificationBell] Enable claimed success but no real subscription. Syncing state...');
          await syncSubscriptionStateWithValidation(badge, realSubscriptionExists);
        }
      } else {
        // Enable returned false - sync state from backend
        const realSubscriptionExists = await checkRealSubscription();
        await syncSubscriptionStateWithValidation(badge, realSubscriptionExists);
      }
    } catch (err) {
      console.warn('[NotificationBell] Enable failed:', err);
      const realSubscriptionExists = await checkRealSubscription();
      await syncSubscriptionStateWithValidation(badge, realSubscriptionExists);
    } finally {
      // Always release the processing lock
      isProcessing = false;
    }
  }

  async function disableNotifications(bell, badge) {
    isProcessing = true;
    try {
      const success = await PushSubscriptionManager.disable();
      if (success) {
        // Verify actual subscription is gone after disable
        const realSubscriptionExists = await checkRealSubscription();
        if (!realSubscriptionExists) {
          // Only mark as unsubscribed if real subscription is gone
          isSubscribed = false;
          updateBellUIState(false, badge, 'Notifications disabled');
        } else {
          console.warn('[NotificationBell] Disable claimed success but subscription still exists. Syncing state...');
          await syncSubscriptionStateWithValidation(badge, realSubscriptionExists);
        }
      } else {
        // Disable returned false - sync state from backend
        const realSubscriptionExists = await checkRealSubscription();
        await syncSubscriptionStateWithValidation(badge, realSubscriptionExists);
      }
    } catch (err) {
      console.warn('[NotificationBell] Disable failed:', err);
      const realSubscriptionExists = await checkRealSubscription();
      await syncSubscriptionStateWithValidation(badge, realSubscriptionExists);
    } finally {
      // Always release the processing lock
      isProcessing = false;
    }
  }

  function updateBellUIState(enabled, badge, title) {
    const bell = document.querySelector(bellSelector);
    const badgeEl = badge || document.querySelector(badgeSelector);

    if (!bell) {
      return;
    }

    // UI state depends ONLY on isSubscribed (our single source of truth)
    bell.classList.toggle('enabled', Boolean(enabled));
    bell.title = title || (enabled ? 'Notifications enabled' : 'Notifications disabled');

    if (badgeEl) {
      if (enabled) {
        badgeEl.textContent = 'ON';
        badgeEl.classList.add('show');
      } else {
        badgeEl.textContent = '0';
        badgeEl.classList.remove('show');
      }
    }
  }

  return {
    init
  };
})();

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function () {
  NotificationBellUI.init();
});
