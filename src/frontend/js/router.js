/* Hash-based SPA router with dynamic :param support */
const Router = {
    routes: [],
    register(pattern, renderFn) {
        // Convert pattern like '#/player/:id' into a regex
        const paramNames = [];
        const regexStr = pattern.replace(/:([a-zA-Z_]+)/g, (_, name) => {
            paramNames.push(name);
            return '([^/]+)';
        });
        this.routes.push({ pattern, regex: new RegExp('^' + regexStr + '$'), paramNames, renderFn });
    },

    _match(hash) {
        for (const route of this.routes) {
            const m = hash.match(route.regex);
            if (m) {
                const params = {};
                route.paramNames.forEach((name, i) => { params[name] = m[i + 1]; });
                return { renderFn: route.renderFn, params };
            }
        }
        return null;
    },

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

        // Find matching route (supports :param patterns)
        const match = this._match(base);
        if (match) {
            const container = document.getElementById('page-content');
            container.innerHTML = '<div class="text-center mt-2">Cargando...</div>';
            try {
                await match.renderFn(container, match.params);
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
