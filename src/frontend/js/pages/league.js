/* League dashboard page */
async function renderLeaguePage(container) {
    const leagueId = API.getLeagueId();
    const league = await API.get(`/leagues/${leagueId}`);
    const isComm = API.isCommissioner();

    localStorage.setItem('wcf_team_name', league.teams.find(t => t.id === API.getTeamId())?.team_name || '');
    document.getElementById('nav-team-name').textContent = localStorage.getItem('wcf_team_name');

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
                <div class="flex mt-1" style="justify-content:center;gap:.5rem">
                    <button class="btn btn-sm btn-outline" id="btn-copy-code">📋 Copiar código</button>
                    <button class="btn btn-sm btn-primary" id="btn-share">📤 Compartir</button>
                </div>
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
                            <td>${t.team_name} ${t.id === league.commissioner_team_id ? '👑' : ''}</td>
                            <td>${t.owner_nick}</td>
                            <td class="money">${formatMoney(t.budget)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>

        ${isComm ? `
        <div class="card">
            <div class="card-header">Panel del Comisionado</div>
            <div class="flex flex-wrap">
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
            </div>
        </div>
        ` : ''}
    `;

    document.getElementById('league-code')?.addEventListener('click', () => {
        navigator.clipboard?.writeText(league.code);
        showToast('Código copiado', 'success');
    });

    document.getElementById('btn-copy-code')?.addEventListener('click', () => {
        navigator.clipboard?.writeText(league.code);
        showToast('Código copiado', 'success');
    });

    document.getElementById('btn-share')?.addEventListener('click', () => {
        const shareUrl = `${location.origin}/#/?code=${league.code}`;
        const shareText = `⚽ Únete a mi liga de WC Fantasy 2026 "${league.name}"!\n\nCódigo: ${league.code}\n\n${shareUrl}`;

        if (navigator.share) {
            navigator.share({ title: 'WC Fantasy 2026', text: shareText, url: shareUrl }).catch(() => {});
        } else {
            navigator.clipboard?.writeText(shareText);
            showToast('Enlace copiado al portapapeles', 'success');
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
}
