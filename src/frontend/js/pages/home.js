/* Home page — Clerk auth + create or join league */
Router.register('#/', async (container) => {
    if (API.isLoggedIn()) {
        await renderLeaguePage(container);
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
                window.Clerk.openSignIn({
                    afterSignInUrl: window.location.href,
                    afterSignUpUrl: window.location.href,
                });
            }
        });
        return;
    }

    // Signed in with Clerk — show league create/join (auto-recover if possible)
    const nickname = clerkUser.name;
    const clerkId = clerkUser.id;

    // Try auto-recover: check if this Clerk user already has a team
    if (prefilledCode) {
        // Don't auto-recover if they came with a code link — let them join
    } else {
        const savedCode = localStorage.getItem('wcf_last_league_code');
        if (savedCode) {
            try {
                const auth = await API.post('/auth/recover', { league_code: savedCode, nickname: clerkId });
                loginWith(auth);
                localStorage.setItem('wcf_last_league_code', savedCode);
                return;
            } catch {} // Not found, show normal form
        }
    }

    container.innerHTML = `
        <div class="hero">
            <h1>⚽ WC Fantasy 2026</h1>
            <p>Bienvenido, <strong>${nickname}</strong>!</p>
            ${clerkUser.avatar ? `<img src="${clerkUser.avatar}" style="width:48px;height:48px;border-radius:50%;margin-top:.5rem">` : ''}
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
            });
            loginWith(auth);
            localStorage.setItem('wcf_last_league_code', code);
            localStorage.setItem('wcf_display_name', nickname);
            showToast('¡Te has unido a la liga!', 'success');
        } catch (err) { showToast(err.message, 'error'); }
    };
});

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
