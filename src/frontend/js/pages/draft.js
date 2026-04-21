/* Draft page — real-time with WebSocket */
Router.register('#/draft', async (container) => {
    const leagueId = API.getLeagueId();
    let state;
    try {
        state = await API.get(`/leagues/${leagueId}/draft`);
    } catch {
        container.innerHTML = '<div class="card text-center mt-2"><p>No hay draft activo en esta liga.</p></div>';
        return;
    }

    let availablePlayers = [];
    let filterPos = '';
    let searchTerm = '';

    async function loadAvailable() {
        const params = new URLSearchParams();
        if (filterPos) params.set('position', filterPos);
        if (searchTerm) params.set('search', searchTerm);
        availablePlayers = await API.get(`/leagues/${leagueId}/draft/available?${params}`);
    }

    function render() {
        const myTurn = state.current_team_id === API.getTeamId();
        const isDone = state.status === 'completed';

        container.innerHTML = `
            <h2 class="mb-2">🎯 Draft ${isDone ? '(Completado)' : `— Ronda ${state.current_round}/23`}</h2>

            ${!isDone ? `
            <div class="draft-turn ${myTurn ? 'my-turn' : ''}">
                <div style="font-size:.9rem;color:var(--text-secondary)">${myTurn ? '¡ES TU TURNO!' : 'Turno de:'}</div>
                <div style="font-size:1.3rem;font-weight:700">${state.current_team_name || '...'}</div>
                <div style="font-size:.85rem;color:var(--text-muted)">Pick ${state.current_pick} of ${state.pick_order.length}</div>
                ${myTurn ? '<button class="btn btn-outline btn-sm mt-1" id="btn-autopick">⚡ Auto-pick</button>' : ''}
            </div>` : '<div class="card text-center mb-2"><p style="color:var(--accent-gold);font-size:1.2rem">🏆 Draft completado — ¡Gestiona tu equipo!</p></div>'}

            <div class="grid" style="grid-template-columns: 1fr 350px;">
                <div>
                    <div class="card">
                        <div class="flex-between mb-1">
                            <div class="card-header" style="margin:0">Jugadores disponibles (${availablePlayers.length})</div>
                            <input type="text" id="draft-search" placeholder="Buscar..." style="width:200px" value="${searchTerm}">
                        </div>
                        <div class="filter-bar">
                            ${['', 'GK', 'DEF', 'MID', 'FWD'].map(p =>
                                `<button class="filter-btn ${filterPos === p ? 'active' : ''}" data-pos="${p}">${p || 'Todos'}</button>`
                            ).join('')}
                        </div>
                        <div style="max-height:500px;overflow-y:auto">
                            ${availablePlayers.map(p => `
                                <div class="player-card" data-pid="${p.id}">
                                    <img src="${p.photo}" alt="" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><rect fill=%22%23374151%22 width=%2240%22 height=%2240%22/><text x=%2220%22 y=%2225%22 text-anchor=%22middle%22 fill=%22%239ca3af%22 font-size=%2214%22>⚽</text></svg>'">
                                    <div class="player-info">
                                        <div class="player-name">${p.name}</div>
                                        <div class="player-meta">${p.club} · ${p.country_code}</div>
                                    </div>
                                    ${posBadge(p.position)}
                                    <div class="player-value">${formatMoney(p.market_value)}</div>
                                    ${myTurn && !isDone ? `<button class="btn btn-primary btn-sm pick-btn" data-pid="${p.id}">Pick</button>` : ''}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
                <div>
                    <div class="card">
                        <div class="card-header">Historial de picks</div>
                        <div class="pick-log">
                            ${state.picks.slice().reverse().map(p => `
                                <div class="pick-log-entry">
                                    <span style="color:var(--text-muted)">R${p.round}P${p.pick}</span>
                                    <strong>${p.team_name}</strong> → ${p.player_name}
                                </div>
                            `).join('')}
                            ${state.picks.length === 0 ? '<div class="text-center" style="color:var(--text-muted);padding:1rem">Sin picks todavía</div>' : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Event listeners
        container.querySelectorAll('.pick-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const pid = btn.dataset.pid;
                try {
                    await API.post(`/leagues/${leagueId}/draft/pick`, { player_id: pid });
                    showToast('¡Pick realizado!', 'success');
                    state = await API.get(`/leagues/${leagueId}/draft`);
                    await loadAvailable();
                    render();
                } catch (err) { showToast(err.message, 'error'); }
            });
        });

        container.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                filterPos = btn.dataset.pos;
                await loadAvailable();
                render();
            });
        });

        document.getElementById('draft-search')?.addEventListener('input', async (e) => {
            searchTerm = e.target.value;
            await loadAvailable();
            render();
        });

        document.getElementById('btn-autopick')?.addEventListener('click', async () => {
            try {
                await API.post(`/leagues/${leagueId}/draft/autopick`);
                showToast('Auto-pick realizado', 'success');
                state = await API.get(`/leagues/${leagueId}/draft`);
                await loadAvailable();
                render();
            } catch (err) { showToast(err.message, 'error'); }
        });
    }

    await loadAvailable();
    render();

    // WebSocket for real-time updates
    const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    let ws;
    try {
        ws = new WebSocket(`${wsProto}//${location.host}/api/v1/leagues/${leagueId}/draft/ws`);
        ws.onmessage = async (evt) => {
            const msg = JSON.parse(evt.data);
            if (msg.state) {
                state = msg.state;
                await loadAvailable();
                render();
                if (msg.type === 'pick' && msg.pick) {
                    showToast(`${msg.pick.team_name} eligió a ${msg.pick.player_name}`, 'info');
                }
            }
        };
        ws.onerror = () => {};
    } catch {}

    // Cleanup on page leave
    const origHandler = Router.handleRoute.bind(Router);
    const cleanup = () => { ws?.close(); };
    window.addEventListener('hashchange', cleanup, { once: true });
});
