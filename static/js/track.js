        (function () {
            const trackForm = document.getElementById('trackForm');
            const entryTypeInput = document.getElementById('entryType');
            const statusBanner = document.getElementById('trackOfflineStatus');
            const tabButtons = document.querySelectorAll('#trackTab button[data-bs-toggle="tab"]');
            const activityFieldIds = ['activity-date', 'activity-type', 'duration', 'bp-systolic', 'alcohol-consumption', 'screen-time'];
            const queueStorageKey = 'diabeatit-track-queue-v1';
            let syncInProgress = false;

            function setStatus(message, variant) {
                if (!statusBanner) {
                    return;
                }

                statusBanner.textContent = message;
                statusBanner.classList.remove('d-none', 'alert-warning', 'alert-info', 'alert-success', 'alert-danger');
                statusBanner.classList.add(variant || 'alert-info');
            }

            function clearStatus() {
                if (!statusBanner) {
                    return;
                }

                statusBanner.textContent = '';
                statusBanner.classList.add('d-none');
                statusBanner.classList.remove('alert-warning', 'alert-info', 'alert-success', 'alert-danger');
            }

            function getQueuedEntries() {
                try {
                    return JSON.parse(window.localStorage.getItem(queueStorageKey) || '[]');
                } catch (error) {
                    return [];
                }
            }

            function saveQueuedEntries(entries) {
                window.localStorage.setItem(queueStorageKey, JSON.stringify(entries));
            }

            function buildPayload(formElement) {
                const formData = new window.FormData(formElement);
                const payload = {};

                formData.forEach(function (value, key) {
                    payload[key] = value;
                });

                return payload;
            }

            function enqueueCurrentEntry() {
                const payload = buildPayload(trackForm);
                const queuedEntries = getQueuedEntries();

                queuedEntries.push({
                    id: `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
                    createdAt: new Date().toISOString(),
                    payload: payload
                });

                saveQueuedEntries(queuedEntries);
                setStatus('You are offline. This entry was saved on this device and will sync automatically when you are back online.', 'alert-warning');
            }

            function toFormData(payload) {
                const formData = new window.FormData();

                Object.keys(payload).forEach(function (key) {
                    formData.append(key, payload[key]);
                });

                return formData;
            }

            async function syncQueuedEntries() {
                if (!window.navigator.onLine || syncInProgress) {
                    return;
                }

                const queuedEntries = getQueuedEntries();
                if (!queuedEntries.length) {
                    clearStatus();
                    return;
                }

                syncInProgress = true;
                let syncedCount = 0;
                const remainingEntries = [];

                for (let index = 0; index < queuedEntries.length; index += 1) {
                    const queuedEntry = queuedEntries[index];

                    try {
                        const response = await window.fetch(trackForm.action || window.location.href, {
                            method: 'POST',
                            body: toFormData(queuedEntry.payload),
                            credentials: 'same-origin'
                        });

                        if (response.ok && response.redirected) {
                            syncedCount += 1;
                        } else {
                            remainingEntries.push(queuedEntry);
                        }
                    } catch (error) {
                        remainingEntries.push(queuedEntry);
                    }
                }

                saveQueuedEntries(remainingEntries);
                syncInProgress = false;

                if (syncedCount > 0) {
                    setStatus(`${syncedCount} queued entr${syncedCount === 1 ? 'y was' : 'ies were'} synced successfully.`, 'alert-success');
                    window.setTimeout(function () {
                        if (!getQueuedEntries().length && window.navigator.onLine) {
                            clearStatus();
                        }
                    }, 4000);
                } else if (remainingEntries.length > 0) {
                    setStatus('Some queued entries could not be synced yet. They will stay saved on this device.', 'alert-warning');
                }
            }

            function setActivityRequired(isRequired) {
                activityFieldIds.forEach((fieldId) => {
                    const field = document.getElementById(fieldId);
                    if (!field) {
                        return;
                    }
                    field.required = isRequired;
                });
            }

            function refreshRequiredState() {
                const activeTab = document.querySelector('#trackTab button.active');
                const activeTabId = activeTab ? activeTab.id.replace('-tab', '') : '';
                setActivityRequired(activeTabId === 'activity');
            }

            trackForm.addEventListener('submit', function (event) {
                const activeTab = document.querySelector('#trackTab button.active');
                if (activeTab) {
                    entryTypeInput.value = activeTab.id.replace('-tab', '');
                }

                refreshRequiredState();

                if (!trackForm.checkValidity()) {
                    event.preventDefault();
                    trackForm.reportValidity();
                    return;
                }

                if (!window.navigator.onLine) {
                    event.preventDefault();
                    enqueueCurrentEntry();
                    trackForm.reset();
                    entryTypeInput.value = activeTab ? activeTab.id.replace('-tab', '') : 'glucose';
                    refreshRequiredState();
                }
            });

            refreshRequiredState();

            tabButtons.forEach(button => {
                button.addEventListener('shown.bs.tab', function (event) {
                    entryTypeInput.value = event.target.id.replace('-tab', '');
                    refreshRequiredState();
                });
            });

            window.addEventListener('online', function () {
                setStatus('Connection restored. Syncing saved tracking entries...', 'alert-info');
                syncQueuedEntries();
            });

            window.addEventListener('offline', function () {
                const queuedCount = getQueuedEntries().length;
                setStatus(queuedCount
                    ? `You are offline. ${queuedCount} saved entr${queuedCount === 1 ? 'y is' : 'ies are'} waiting to sync.`
                    : 'You are offline. New track entries will be saved on this device until you reconnect.',
                    'alert-warning');
            });

            if (!window.navigator.onLine) {
                const queuedCount = getQueuedEntries().length;
                setStatus(queuedCount
                    ? `You are offline. ${queuedCount} saved entr${queuedCount === 1 ? 'y is' : 'ies are'} waiting to sync.`
                    : 'You are offline. New track entries will be saved on this device until you reconnect.',
                    'alert-warning');
            } else {
                syncQueuedEntries();
            }
        })();
