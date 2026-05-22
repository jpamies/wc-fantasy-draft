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

    _guardDirty() {
        if (window.__wcfClauseDirty) {
            return confirm('Tienes cambios en las cláusulas sin guardar. ¿Salir de todas formas?');
        }
        return true;
    },

    async navigate(hash) {
        if (!hash || hash === '#') hash = '#/';
        if (!this._guardDirty()) return;
        window.__wcfClauseDirty = false;
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
        window.addEventListener('hashchange', (e) => {
            if (window.__wcfClauseDirty) {
                // Restore previous hash and ask
                const prev = e.oldURL.split('#')[1] || '/';
                if (!this._guardDirty()) {
                    // Revert navigation by restoring old hash without triggering another change
                    history.replaceState(null, '', '#' + prev);
                    return;
                }
                window.__wcfClauseDirty = false;
            }
            this.handleRoute();
        });
        this.handleRoute();
    }
};
