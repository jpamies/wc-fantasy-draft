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
    const playerNotifStatePrefix = 'wcf_player_notif_state';
    const activeMatchdayKey = 'wcf_notif_active_matchday';
    const lineupWarningPrefix = 'wcf_notif_lineup_warning';
    let playerNotifTimer = null;

    function browserNotificationsEnabled() {
        return supportsBrowserNotifications()
            && getBrowserNotificationPermission() === 'granted'
            && localStorage.getItem(notificationPrefKey) === 'true';
    }

    async function checkMyPlayersNotifications() {
        if (!API.isLoggedIn() || !browserNotificationsEnabled()) return;

        const teamId = API.getTeamId();
        if (!teamId) return;

        try {
            const matchdays = await API.get('/scoring/matchdays');
            const active = (matchdays || []).find(md => md.status === 'active');
            const previousActiveId = localStorage.getItem(activeMatchdayKey);

            if (active && previousActiveId !== active.id) {
                notifyBrowser('WC Fantasy - jornada en directo', {
                    body: `Ha comenzado ${active.name || active.id}`,
                    tag: `matchday-start-${active.id}`,
                    data: { type: 'matchday-start', matchday: active.id },
                });
            }

            if (!active && previousActiveId) {
                const previous = (matchdays || []).find(md => md.id === previousActiveId);
                if (previous && previous.status === 'completed') {
                    notifyBrowser('WC Fantasy - jornada finalizada', {
                        body: `${previous.name || previous.id} ha terminado`,
                        tag: `matchday-end-${previous.id}`,
                        data: { type: 'matchday-end', matchday: previous.id },
                    });
                }
            }

            if (active) localStorage.setItem(activeMatchdayKey, active.id);
            else localStorage.removeItem(activeMatchdayKey);

            if (!active) return;

            const lineup = await API.get(`/teams/${teamId}/lineup-5/${active.id}`);
            const starters = Object.values(lineup.starters || {}).filter(Boolean);
            const stateKey = `${playerNotifStatePrefix}:${teamId}:${active.id}`;
            const warningKey = `${lineupWarningPrefix}:${teamId}:${active.id}`;

            if (starters.length < 5 && localStorage.getItem(warningKey) !== '1') {
                notifyBrowser('WC Fantasy - alineacion incompleta', {
                    body: `Tienes ${starters.length}/5 titulares para ${active.name || active.id}`,
                    tag: `lineup-incomplete-${active.id}`,
                    data: { type: 'lineup-incomplete', matchday: active.id, starters: starters.length },
                });
                localStorage.setItem(warningKey, '1');
            }

            let previous = {};
            try {
                previous = JSON.parse(localStorage.getItem(stateKey) || '{}');
            } catch {
                previous = {};
            }

            // First observation for this matchday acts as baseline to avoid spam.
            const hadPrevious = Object.keys(previous).length > 0;
            const current = {};

            for (const p of starters) {
                const prev = previous[p.player_id];
                const currPoints = Number(p.matchday_points || 0);
                const currPlayed = Boolean(p.country_played);

                current[p.player_id] = {
                    matchday_points: currPoints,
                    country_played: currPlayed,
                    name: p.name || 'Jugador',
                };

                if (!hadPrevious || !prev) continue;

                if (!prev.country_played && currPlayed) {
                    notifyBrowser('WC Fantasy - jugador en juego', {
                        body: `${p.name} ya ha empezado su partido`,
                        tag: `player-live-${active.id}-${p.player_id}`,
                        data: { type: 'player-live', matchday: active.id, player_id: p.player_id },
                    });
                }

                const prevPoints = Number(prev.matchday_points || 0);
                if (currPoints > prevPoints) {
                    const delta = currPoints - prevPoints;
                    notifyBrowser('WC Fantasy - puntos para tu equipo', {
                        body: `${p.name}: +${delta} pts (total jornada: ${currPoints})`,
                        tag: `player-points-${active.id}-${p.player_id}-${currPoints}`,
                        data: { type: 'player-points', matchday: active.id, player_id: p.player_id, delta },
                    });
                } else if (currPoints < prevPoints) {
                    const delta = currPoints - prevPoints;
                    notifyBrowser('WC Fantasy - ajuste de puntos', {
                        body: `${p.name}: ${delta} pts (total jornada: ${currPoints})`,
                        tag: `player-points-adjust-${active.id}-${p.player_id}-${currPoints}`,
                        data: { type: 'player-points-adjust', matchday: active.id, player_id: p.player_id, delta },
                    });
                }
            }

            localStorage.setItem(stateKey, JSON.stringify(current));
        } catch (err) {
            console.debug('Player notification poll failed:', err?.message || err);
        }
    }

    function startPlayerNotificationMonitor() {
        if (playerNotifTimer) return;

        // Prime baseline quickly after login, then keep checking for live changes.
        checkMyPlayersNotifications();
        playerNotifTimer = setInterval(checkMyPlayersNotifications, 45000);
    }

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
                        checkMyPlayersNotifications();
                    } else if (permission === 'denied') {
                        showToast('Notificaciones bloqueadas por el navegador', 'error');
                    } else {
                        showToast('Notificaciones no activadas', 'info');
                    }
                });
            }

            startPlayerNotificationMonitor();
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
