/* App initialization with Clerk auth */
(async function() {
    // Initialize Clerk
    try {
        if (window.Clerk) {
            await window.Clerk.load();
            // Listen for sign-in/sign-out to refresh the page
            window.Clerk.addListener(({ user }) => {
                if (user && !API.isLoggedIn()) {
                    // Just signed in — refresh to show league forms
                    Router.handleRoute();
                }
            });
        }
    } catch (e) {
        console.error('Clerk failed to load:', e);
    }

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
        nav.classList.add('hidden');
        if (window.Clerk?.user) {
            await window.Clerk.signOut();
        }
        Router.navigate('#/');
    });

    // Start router
    Router.init();
})();
