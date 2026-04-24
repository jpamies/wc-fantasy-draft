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
