/* App initialization with Clerk auth */

// Global promise — resolves when Clerk is fully loaded (UI included)
window.clerkReady = (async function initClerk() {
    try {
        // Wait for the Clerk script to define window.Clerk
        for (let i = 0; i < 50 && !window.Clerk; i++) {
            await new Promise(r => setTimeout(r, 100));
        }
        if (!window.Clerk) return;
        await window.Clerk.load();
        window.Clerk.addListener(({ user }) => {
            if (user && !API.isLoggedIn()) {
                Router.handleRoute();
            }
        });
    } catch (e) {
        console.error('Clerk failed to load:', e);
    }
})();

(async function() {
    const notificationPrefKey = 'wcf_browser_notifications_enabled';

    async function loadRuntimeVersion() {
        const el = document.getElementById('app-version');
        if (!el) return;
        try {
            const res = await fetch('/api/v1/health', { cache: 'no-store' });
            if (!res.ok) throw new Error('health failed');
            const data = await res.json();
            const version = data.version || 'unknown';
            const build = data.build || 'unknown';
            el.textContent = `version: ${version} (${String(build).slice(0, 8)})`;
        } catch {
            el.textContent = 'version: unavailable';
        }
    }

    await loadRuntimeVersion();

    // Helper to get Clerk user info
    window.getClerkUser = () => {
        const user = window.Clerk?.user;
        if (!user) return null;
        return {
            id: user.id,
            name: user.fullName || user.firstName || user.username || 'Player',
            email: user.primaryEmailAddress?.emailAddress || '',
            avatar: user.imageUrl || '',
        };
    };

    // Setup nav visibility
    const nav = document.getElementById('main-nav');
    if (API.isLoggedIn()) {
        nav.classList.remove('hidden');
        document.getElementById('nav-team-name').textContent = localStorage.getItem('wcf_team_name') || '';
        const avatar = document.getElementById('nav-avatar');
        const clerkUser = getClerkUser();
        if (clerkUser?.avatar) {
            avatar.src = clerkUser.avatar;
            avatar.style.display = 'block';
        }
        // Show admin link for commissioners
        if (API.isCommissioner()) {
            const navLinks = document.getElementById('nav-links');
            if (navLinks && !navLinks.querySelector('[data-page="admin-market"]')) {
                const a = document.createElement('a');
                a.href = '#/admin/market';
                a.dataset.page = 'admin-market';
                a.textContent = '⚙️ Admin';
                navLinks.appendChild(a);
            }
        }

            const notifBtn = document.getElementById('btn-notifications');
            if (notifBtn) {
                const syncNotificationButton = () => {
                    if (!supportsBrowserNotifications()) {
                        notifBtn.style.display = 'none';
                        return;
                    }
                    notifBtn.style.display = 'inline-flex';
                    const permission = getBrowserNotificationPermission();
                    const enabled = permission === 'granted' && localStorage.getItem(notificationPrefKey) === 'true';
                    notifBtn.textContent = enabled ? '🔔 ON' : permission === 'denied' ? '🔕 BLOQUEADAS' : '🔔 OFF';
                    notifBtn.classList.toggle('btn-gold', enabled);
                    notifBtn.classList.toggle('btn-outline', !enabled);
                };

                syncNotificationButton();
                notifBtn.addEventListener('click', async () => {
                    if (!supportsBrowserNotifications()) {
                        showToast('Tu navegador no soporta notificaciones', 'error');
                        return;
                    }
                    const permission = await requestBrowserNotifications();
                    const enabled = permission === 'granted';
                    localStorage.setItem(notificationPrefKey, String(enabled));
                    syncNotificationButton();
                    if (enabled) {
                        showToast('Notificaciones activadas en el navegador', 'success');
                        notifyBrowser('WC Fantasy', { body: 'Notificaciones activadas', tag: 'global-notifications' });
                    } else if (permission === 'denied') {
                        showToast('Notificaciones bloqueadas por el navegador', 'error');
                    } else {
                        showToast('Notificaciones no activadas', 'info');
                    }
                });
            }
    }

    // Logout — sign out of both Clerk and our app
    document.getElementById('btn-logout').addEventListener('click', async () => {
        API.logout();
        localStorage.removeItem('wcf_last_league_code');
        localStorage.removeItem('wcf_display_name');
        nav.classList.add('hidden');
        if (window.Clerk?.user) {
            await window.Clerk.signOut();
        }
        window.location.hash = '#/';
        window.location.reload();
    });

    // Mobile nav toggle
    document.getElementById('nav-toggle').addEventListener('click', () => {
        document.getElementById('nav-links').classList.toggle('open');
    });
    // Close menu on link click (mobile)
    document.querySelectorAll('.nav-links a').forEach(a => {
        a.addEventListener('click', () => {
            document.getElementById('nav-links').classList.remove('open');
        });
    });

    // Start router
    Router.init();
})();
