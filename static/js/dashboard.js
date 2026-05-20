document.addEventListener('DOMContentLoaded', () => {
    const streakCard = document.getElementById('streakCard');
    const streakPopup = document.getElementById('streakPopup');
    const streakPopupText = document.getElementById('streakPopupText');
    const connectionBanner = document.getElementById('dashboardConnectionBanner');
    const connectionMessage = document.getElementById('dashboardConnectionMessage');

    function updateConnectionBanner() {
        if (!connectionBanner || !connectionMessage) {
            return;
        }

        const lastUpdatedRaw = connectionBanner.dataset.lastUpdated || '';
        let lastUpdatedText = '';

        if (lastUpdatedRaw) {
            try {
                lastUpdatedText = new Intl.DateTimeFormat(undefined, {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit'
                }).format(new Date(lastUpdatedRaw));
            } catch (error) {
                lastUpdatedText = lastUpdatedRaw;
            }
        }

        if (window.navigator.onLine) {
            connectionBanner.classList.remove('alert-warning');
            connectionBanner.classList.add('alert-info');
            connectionMessage.textContent = lastUpdatedText
                ? `Online. Dashboard data last refreshed on ${lastUpdatedText}.`
                : 'Online. Dashboard data is current.';
        } else {
            connectionBanner.classList.remove('alert-info');
            connectionBanner.classList.add('alert-warning');
            connectionMessage.textContent = lastUpdatedText
                ? `Offline mode active. Showing the last synced dashboard data from ${lastUpdatedText}.`
                : 'Offline mode active. Showing the last synced dashboard data.';
        }
    }

    updateConnectionBanner();
    window.addEventListener('online', updateConnectionBanner);
    window.addEventListener('offline', updateConnectionBanner);

    if (!streakCard || !streakPopup || !streakPopupText) {
        return;
    }

    const userId = streakCard.dataset.userId;
    const streakValue = Number.parseInt(streakCard.dataset.streak || '0', 10);

    if (!userId || Number.isNaN(streakValue) || streakValue <= 0) {
        return;
    }

    const milestones = [
        { days: 7, message: '7-day streak unlocked. Keep the fire alive.' },
        { days: 30, message: '1-month streak unlocked. Your flame just leveled up.' },
        { days: 90, message: '3-month streak unlocked. You are on elite consistency.' },
        { days: 180, message: '6-month streak unlocked. Outstanding discipline.' }
    ];

    let reached = null;
    for (const milestone of milestones) {
        if (streakValue >= milestone.days) {
            reached = milestone;
        }
    }

    if (!reached) {
        return;
    }

    const storageKey = `diabeatit.streak.popup.user.${userId}.milestone.${reached.days}`;
    let alreadyShown = false;

    try {
        alreadyShown = localStorage.getItem(storageKey) === '1';
    } catch (error) {
        alreadyShown = false;
    }

    if (alreadyShown) {
        return;
    }

    streakPopupText.textContent = reached.message;
    streakPopup.classList.add('show');

    try {
        localStorage.setItem(storageKey, '1');
    } catch (error) {
        // noop
    }

    window.setTimeout(() => {
        streakPopup.classList.remove('show');
    }, 3800);
});
