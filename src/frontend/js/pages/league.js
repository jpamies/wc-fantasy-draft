/* League dashboard page */
async function renderLeaguePage(container) {
    const leagueId = API.getLeagueId();
    const league = await API.get(`/leagues/${leagueId}`);
    const isComm = API.isCommissioner();

    localStorage.setItem('wcf_team_name', league.teams.find(t => t.id === API.getTeamId())?.team_name || '');
    const displayName = localStorage.getItem('wcf_display_name') || window.getClerkUser?.()?.name || '';
    document.getElementById('nav-team-name').textContent = displayName || localStorage.getItem('wcf_team_name');

    const statusLabels = {
        setup: '⚙️ Configuración', draft_pending: '📋 Draft pendiente',
        draft_in_progress: '🔄 Draft en curso', active: '✅ Activa', completed: '🏆 Finalizada'
    };

    container.innerHTML = `
        <div class="flex-between mb-2">
            <h2>${league.name}</h2>
            <span class="badge badge-teal">${statusLabels[league.status] || league.status}</span>
        </div>
        <div class="grid grid-3 mb-2">
            <div class="card text-center">
                <div style="font-size:.85rem;color:var(--text-secondary)">Código de liga</div>
                <div class="league-code" id="league-code" title="Click para copiar">${league.code}</div>
                <button class="btn btn-sm btn-primary mt-1" id="btn-share">📤 Compartir liga</button>
            </div>
            <div class="card text-center">
                <div style="font-size:.85rem;color:var(--text-secondary)">Equipos</div>
                <div style="font-size:1.5rem;font-weight:700">${league.teams.length} / ${league.max_teams}</div>
            </div>
            <div class="card text-center">
                <div style="font-size:.85rem;color:var(--text-secondary)">Presupuesto inicial</div>
                <div class="money" style="font-size:1.2rem">${formatMoney(league.initial_budget)}</div>
            </div>
        </div>

        <div class="card mb-2">
            <div class="card-header">Equipos</div>
            <table>
                <thead><tr><th>Equipo</th><th>Manager</th><th>Presupuesto</th></tr></thead>
                <tbody>
                    ${league.teams.map(t => `
                        <tr class="${t.id === API.getTeamId() ? 'rank-1' : ''}">
                            <td>${t.team_name} ${t.id === league.commissioner_team_id ? '👑' : ''} ${t.owner_nick?.startsWith('bot_') ? '🤖' : ''}</td>
                            <td>${t.display_name || t.owner_nick}</td>
                            <td class="money">${formatMoney(t.budget)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>

        ${isComm ? `
        <div class="card">
            <div class="card-header">Panel del Comisionado</div>
            <div class="flex flex-wrap" style="gap:.5rem;align-items:center">
                ${league.status === 'setup' || league.status === 'draft_pending' ? `
                    <button class="btn btn-gold" id="btn-start-draft" ${league.teams.length < 2 ? 'disabled title="Mínimo 2 equipos"' : ''}>
                        🎯 Iniciar Draft
                    </button>
                ` : ''}
                ${league.status === 'active' ? `
                    <button class="btn btn-primary" id="btn-toggle-window">
                        ${league.transfer_window_open ? '🔒 Cerrar Mercado' : '🔓 Abrir Mercado'}
                    </button>
                ` : ''}
                <button class="btn btn-outline" id="btn-config" style="font-size:.85rem">⚙️ Configuración</button>
                <button class="btn" id="btn-delete-league" style="background:var(--accent-red,#e74c3c);color:#fff;margin-left:auto;font-size:.85rem">
                    🗑️ Eliminar
                </button>
            </div>
        </div>

        <div class="card mt-1" id="config-panel" style="display:none">
            <div class="card-header">⚙️ Configuración de desarrollo</div>
            
            ${league.status === 'setup' || league.status === 'draft_pending' ? `
            <div style="margin-bottom:1rem">
                <div style="font-weight:600;margin-bottom:.5rem">🤖 Bots</div>
                <div class="flex" style="gap:.5rem;align-items:center">
                    <label style="font-size:.85rem">Añadir</label>
                    <input type="number" id="bot-count" min="1" max="10" value="3" style="width:60px">
                    <button class="btn btn-sm btn-primary" id="btn-add-bots">➕ Añadir bots</button>
                    <button class="btn btn-sm" id="btn-remove-bots" style="background:var(--accent-red);color:#fff;font-size:.8rem">🗑️ Quitar bots</button>
                </div>
                <div style="font-size:.75rem;color:var(--text-muted);margin-top:.3rem">Los bots tienen autodraft activado. Se eliminan al resetear la liga.</div>
            </div>
            ` : ''}

            <div>
                <div style="font-weight:600;margin-bottom:.5rem">🔄 Resetear Liga</div>
                <div style="font-size:.85rem;color:var(--text-secondary);margin-bottom:.5rem">
                    Vuelve al estado inicial: elimina draft, jugadores, alineaciones, puntuaciones y bots. Los usuarios se mantienen.
                </div>
                <button class="btn btn-sm" id="btn-reset-league" style="background:var(--accent-red);color:#fff">↺ Resetear Liga</button>
            </div>
        </div>
        ` : `
        <div style="text-align:right;margin-top:1rem">
            <button class="btn" id="btn-leave-league" style="background:var(--accent-red,#e74c3c);color:#fff;font-size:.85rem">
                🚪 Salir de la Liga
            </button>
        </div>
        `}

        <div style="text-align:center;margin-top:1rem">
            <button class="btn btn-sm" id="btn-switch-league" style="opacity:.7">↩️ Cambiar de liga</button>
        </div>
    `;

    document.getElementById('league-code')?.addEventListener('click', () => {
        navigator.clipboard?.writeText(league.code);
        showToast('Código copiado', 'success');
    });

    document.getElementById('btn-share')?.addEventListener('click', () => {
        const shareUrl = `${location.origin}/#/?code=${league.code}`;
        const shareText = `⚽🏆 ¡Únete a mi liga de WC Fantasy 2026!\n\n🏟️ Liga: *${league.name}*\n🔑 Código: *${league.code}*\n\n👉 ${shareUrl}\n\n¡Te espero! 🔥⚽`;

        if (navigator.share) {
            navigator.share({ text: shareText }).catch(() => {});
        } else {
            navigator.clipboard?.writeText(shareText);
            showToast('Mensaje copiado al portapapeles', 'success');
        }
    });

    document.getElementById('btn-start-draft')?.addEventListener('click', async () => {
        try {
            await API.post(`/leagues/${leagueId}/draft/start`);
            showToast('¡Draft iniciado!', 'success');
            Router.navigate('#/draft');
        } catch (err) { showToast(err.message, 'error'); }
    });

    document.getElementById('btn-toggle-window')?.addEventListener('click', async () => {
        try {
            const action = league.transfer_window_open ? 'close-window' : 'open-window';
            await API.post(`/leagues/${leagueId}/admin/${action}`);
            showToast(league.transfer_window_open ? 'Mercado cerrado' : 'Mercado abierto', 'success');
            renderLeaguePage(container);
        } catch (err) { showToast(err.message, 'error'); }
    });

    document.getElementById('btn-leave-league')?.addEventListener('click', async () => {
        if (!confirm('¿Seguro que quieres salir de esta liga? Perderás tu equipo y jugadores.')) return;
        try {
            await API.delete(`/leagues/${leagueId}/leave`);
            API.logout();
            localStorage.removeItem('wcf_last_league_code');
            document.getElementById('main-nav').classList.add('hidden');
            showToast('Has salido de la liga', 'success');
            Router.navigate('#/');
        } catch (err) { showToast(err.message, 'error'); }
    });

    document.getElementById('btn-config')?.addEventListener('click', () => {
        const panel = document.getElementById('config-panel');
        if (panel) panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    });

    document.getElementById('btn-add-bots')?.addEventListener('click', async () => {
        const count = parseInt(document.getElementById('bot-count')?.value || '3');
        try {
            const res = await API.post(`/leagues/${leagueId}/admin/add-bots`, { count });
            showToast(`${res.bots_created} bots añadidos`, 'success');
            renderLeaguePage(container);
        } catch (err) { showToast(err.message, 'error'); }
    });

    document.getElementById('btn-remove-bots')?.addEventListener('click', async () => {
        try {
            const res = await API.delete(`/leagues/${leagueId}/admin/bots`);
            showToast(`${res.bots_removed} bots eliminados`, 'success');
            renderLeaguePage(container);
        } catch (err) { showToast(err.message, 'error'); }
    });

    document.getElementById('btn-reset-league')?.addEventListener('click', async () => {
        if (!confirm('⚠️ ¿Resetear la liga? Se borrarán draft, jugadores, alineaciones, puntuaciones y bots. Los usuarios se mantienen.')) return;
        try {
            await API.post(`/leagues/${leagueId}/admin/reset`);
            showToast('Liga reseteada', 'success');
            renderLeaguePage(container);
        } catch (err) { showToast(err.message, 'error'); }
    });

    document.getElementById('btn-delete-league')?.addEventListener('click', async () => {
        if (!confirm('⚠️ ¿Eliminar esta liga? Se borrarán TODOS los equipos y datos. Esta acción no se puede deshacer.')) return;
        try {
            await API.delete(`/leagues/${leagueId}`);
            API.logout();
            localStorage.removeItem('wcf_last_league_code');
            document.getElementById('main-nav').classList.add('hidden');
            showToast('Liga eliminada', 'success');
            Router.navigate('#/');
        } catch (err) { showToast(err.message, 'error'); }
    });

    document.getElementById('btn-switch-league')?.addEventListener('click', () => {
        API.logout();
        document.getElementById('main-nav').classList.add('hidden');
        Router.navigate('#/');
    });
}
