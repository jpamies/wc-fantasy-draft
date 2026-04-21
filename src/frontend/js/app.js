/* App initialization */
(function() {
    // Setup nav visibility
    const nav = document.getElementById('main-nav');
    if (API.isLoggedIn()) {
        nav.classList.remove('hidden');
        document.getElementById('nav-team-name').textContent = localStorage.getItem('wcf_team_name') || '';
    }

    // Logout
    document.getElementById('btn-logout').addEventListener('click', () => {
        API.logout();
        nav.classList.add('hidden');
        Router.navigate('#/');
    });

    // Start router
    Router.init();
})();
