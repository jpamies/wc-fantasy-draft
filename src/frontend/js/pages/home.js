/* Home page — create or join league */
Router.register('#/', async (container) => {
    if (API.isLoggedIn()) {
        // Show league dashboard
        await renderLeaguePage(container);
        return;
    }

    container.innerHTML = `
        <div class="hero">
            <h1>⚽ WC Fantasy 2026</h1>
            <p>Fantasy football con draft, clausulazos y mercado de traspasos para el Mundial 2026</p>
        </div>
        <div class="auth-panels">
            <div class="card">
                <div class="card-header">Crear Liga</div>
                <form id="form-create">
                    <div class="form-group">
                        <label>Nombre de la liga</label>
                        <input type="text" id="create-league-name" required placeholder="La Liga de los Cracks">
                    </div>
                    <div class="form-group">
                        <label>Tu nickname</label>
                        <input type="text" id="create-nick" required placeholder="Tu nombre">
                    </div>
                    <div class="form-group">
                        <label>Nombre de tu equipo</label>
                        <input type="text" id="create-team" required placeholder="FC Fantasía">
                    </div>
                    <button type="submit" class="btn btn-gold" style="width:100%">Crear Liga</button>
                </form>
            </div>
            <div class="card">
                <div class="card-header">Unirse a Liga</div>
                <form id="form-join">
                    <div class="form-group">
                        <label>Código de la liga</label>
                        <input type="text" id="join-code" required placeholder="ABC123" maxlength="6" style="text-transform:uppercase">
                    </div>
                    <div class="form-group">
                        <label>Tu nickname</label>
                        <input type="text" id="join-nick" required placeholder="Tu nombre">
                    </div>
                    <div class="form-group">
                        <label>Nombre de tu equipo</label>
                        <input type="text" id="join-team" required placeholder="FC Fantasía">
                    </div>
                    <button type="submit" class="btn btn-primary" style="width:100%">Unirse</button>
                </form>
                <hr style="border-color:var(--border);margin:1rem 0">
                <form id="form-recover">
                    <div class="form-group">
                        <label>¿Ya tienes equipo? Recuperar sesión</label>
                        <input type="text" id="recover-code" required placeholder="Código liga" maxlength="6" style="text-transform:uppercase">
                    </div>
                    <div class="form-group">
                        <input type="text" id="recover-nick" required placeholder="Tu nickname">
                    </div>
                    <button type="submit" class="btn btn-outline" style="width:100%">Recuperar</button>
                </form>
            </div>
        </div>
    `;

    document.getElementById('form-create').onsubmit = async (e) => {
        e.preventDefault();
        try {
            const league = await API.post('/leagues', { name: document.getElementById('create-league-name').value });
            const auth = await API.post('/auth/join', {
                league_code: league.code,
                nickname: document.getElementById('create-nick').value,
                team_name: document.getElementById('create-team').value,
            });
            loginWith(auth);
            showToast(`Liga creada. Código: ${league.code}`, 'success');
        } catch (err) { showToast(err.message, 'error'); }
    };

    document.getElementById('form-join').onsubmit = async (e) => {
        e.preventDefault();
        try {
            const auth = await API.post('/auth/join', {
                league_code: document.getElementById('join-code').value.toUpperCase(),
                nickname: document.getElementById('join-nick').value,
                team_name: document.getElementById('join-team').value,
            });
            loginWith(auth);
            showToast('¡Te has unido a la liga!', 'success');
        } catch (err) { showToast(err.message, 'error'); }
    };

    document.getElementById('form-recover').onsubmit = async (e) => {
        e.preventDefault();
        try {
            const auth = await API.post('/auth/recover', {
                league_code: document.getElementById('recover-code').value.toUpperCase(),
                nickname: document.getElementById('recover-nick').value,
            });
            loginWith(auth);
            showToast('Sesión recuperada', 'success');
        } catch (err) { showToast(err.message, 'error'); }
    };
});

function loginWith(auth) {
    API.setToken(auth.token);
    API.setTeamId(auth.team_id);
    API.setLeagueId(auth.league_id);
    API.setCommissioner(auth.is_commissioner);
    document.getElementById('main-nav').classList.remove('hidden');
    Router.handleRoute();
}
