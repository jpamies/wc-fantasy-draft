/* Home page — Clerk auth + create or join league */
Router.register('#/', async (container) => {
    if (API.isLoggedIn()) {
        try {
            await renderLeaguePage(container);
        } catch (err) {
            console.error('League page failed to render, falling back to join/create UI:', err);
            const clerkUser = window.getClerkUser?.();
            const nickname = clerkUser?.name || '';
            const clerkId = clerkUser?.id || '';
            API.logout();
            if (clerkId) {
                showCreateJoinForms(container, nickname, clerkId, '');
            } else {
                container.innerHTML = `
                    <div class="card text-center mt-2">
                        <p style="color:var(--text-secondary)">No se ha podido cargar la liga. Vuelve a iniciar sesión o crea una nueva.</p>
                    </div>
                `;
            }
        }
        return;
    }

    const hashParams = new URLSearchParams(window.location.hash.split('?')[1] || '');
    const prefilledCode = (hashParams.get('code') || '').toUpperCase();
    const clerkUser = window.getClerkUser?.();

    // Not signed in with Clerk — show sign-in
    if (!clerkUser) {
        container.innerHTML = `
            <div class="hero">
                <h1>⚽ WC Fantasy 2026</h1>
                <p>Fantasy football con draft, clausulazos y mercado de traspasos para el Mundial 2026</p>
            </div>
            <div style="max-width:400px;margin:2rem auto">
                <div class="card text-center">
                    <div class="card-header">Iniciar sesión</div>
                    <p style="color:var(--text-secondary);margin-bottom:1rem">Inicia sesión con tu cuenta de Google o GitHub para jugar</p>
                    <button class="btn btn-gold" id="btn-clerk-login" style="width:100%;font-size:1rem;padding:.75rem">
                        🔐 Iniciar sesión
                    </button>
                </div>
            </div>
        `;
        document.getElementById('btn-clerk-login')?.addEventListener('click', async () => {
            await window.clerkReady;
            if (window.Clerk) {
                try {
                    window.Clerk.openSignIn({
                        afterSignInUrl: window.location.href,
                        afterSignUpUrl: window.location.href,
                    });
                } catch {
                    window.Clerk.redirectToSignIn({ redirectUrl: window.location.href });
                }
            }
        });
        return;
    }

    // Signed in with Clerk
    const nickname = clerkUser.name;
    const clerkId = clerkUser.id;

    // Fetch user's existing leagues
    let myLeagues = [];
    try {
        myLeagues = await API.get(`/my-leagues?nickname=${encodeURIComponent(clerkId)}`);
    } catch {}

    // No leagues — show create/join forms
    if (myLeagues.length === 0) {
        showCreateJoinForms(container, nickname, clerkId, '');
        return;
    }

    // Single league per user: if one already exists, always auto-enter it.
    if (myLeagues.length >= 1) {
        const lg = myLeagues[0];
        try {
            const auth = await API.post('/auth/recover', { league_code: lg.league_code, nickname: clerkId });
            loginWith(auth);
            localStorage.setItem('wcf_last_league_code', lg.league_code);
            localStorage.setItem('wcf_display_name', nickname);
            return;
        } catch {}
    }

    // If there is no league yet, allow create/join (supports invite link code).
    showCreateJoinForms(container, nickname, clerkId, prefilledCode);
});

function showCreateJoinForms(container, nickname, clerkId, prefilledCode) {
    const clerkUser = window.getClerkUser?.();
    container.innerHTML = `
        <div class="hero">
            <h1>⚽ WC Fantasy 2026</h1>
            <p>Bienvenido, <strong>${nickname}</strong>!</p>
            ${clerkUser?.avatar ? `<img src="${clerkUser.avatar}" style="width:48px;height:48px;border-radius:50%;margin-top:.5rem">` : ''}
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
                        <input type="text" id="join-code" required placeholder="ABC123" maxlength="6" style="text-transform:uppercase" value="${prefilledCode}">
                    </div>
                    ${prefilledCode ? '<div style="font-size:.85rem;color:var(--accent-teal);margin-bottom:.75rem">✅ Código de liga pre-rellenado</div>' : ''}
                    <div class="form-group">
                        <label>Nombre de tu equipo</label>
                        <input type="text" id="join-team" required placeholder="FC Fantasía">
                    </div>
                    <button type="submit" class="btn btn-primary" style="width:100%">Unirse</button>
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
                nickname: clerkId,
                team_name: document.getElementById('create-team').value,
                display_name: nickname,
            });
            loginWith(auth);
            localStorage.setItem('wcf_last_league_code', league.code);
            localStorage.setItem('wcf_display_name', nickname);
            showToast(`Liga creada. Código: ${league.code}`, 'success');
        } catch (err) { showToast(err.message, 'error'); }
    };

    document.getElementById('form-join').onsubmit = async (e) => {
        e.preventDefault();
        const code = document.getElementById('join-code').value.toUpperCase();
        try {
            const auth = await API.post('/auth/join', {
                league_code: code,
                nickname: clerkId,
                team_name: document.getElementById('join-team').value,
                display_name: nickname,
            });
            loginWith(auth);
            localStorage.setItem('wcf_last_league_code', code);
            localStorage.setItem('wcf_display_name', nickname);
            showToast('¡Te has unido a la liga!', 'success');
        } catch (err) { showToast(err.message, 'error'); }
    };
}

function loginWith(auth) {
    API.setToken(auth.token);
    API.setTeamId(auth.team_id);
    API.setLeagueId(auth.league_id);
    API.setCommissioner(auth.is_commissioner);
    document.getElementById('main-nav').classList.remove('hidden');
    const clerkUser = window.getClerkUser?.();
    if (clerkUser?.avatar) {
        const avatar = document.getElementById('nav-avatar');
        avatar.src = clerkUser.avatar;
        avatar.style.display = 'block';
    }
    Router.handleRoute();
}
