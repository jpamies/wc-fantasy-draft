/* Hash-based SPA router */
const Router = {
    routes: {},
    register(hash, renderFn) { this.routes[hash] = renderFn; },

    async navigate(hash) {
        if (!hash || hash === '#') hash = '#/';
        window.location.hash = hash;
    },

    async handleRoute() {
        let hash = window.location.hash || '#/';
        // Strip query params for matching
        const base = hash.split('?')[0];

        // If not logged in, always show home
        if (!API.isLoggedIn() && base !== '#/') {
            window.location.hash = '#/';
            return;
        }

        // Find matching route
        const renderFn = this.routes[base];
        if (renderFn) {
            const container = document.getElementById('page-content');
            container.innerHTML = '<div class="text-center mt-2">Cargando...</div>';
            try {
                await renderFn(container);
            } catch (e) {
                container.innerHTML = `<div class="card text-center mt-2"><p>Error: ${e.message}</p></div>`;
                console.error(e);
            }
        } else {
            document.getElementById('page-content').innerHTML = '<div class="text-center mt-2">Página no encontrada</div>';
        }

        // Update active nav link
        document.querySelectorAll('.nav-links a').forEach(a => {
            a.classList.toggle('active', a.getAttribute('href') === base);
        });
    },

    init() {
        window.addEventListener('hashchange', () => this.handleRoute());
        this.handleRoute();
    }
};
