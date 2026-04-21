/* Draft page — real-time with WebSocket + polling fallback */
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
    let ws = null;
    let wsConnected = false;
    let pollTimer = null;
    let alive = true; // track if we're still on this page
    let lastPickCount = state.picks ? state.picks.length : 0;
    let autodraftEnabled = false;

    // Check initial autodraft status
    try {
        const adStatus = await API.get(`/leagues/${leagueId}/draft/autodraft`);
        autodraftEnabled = adStatus.team_autodraft || false;
    } catch {}

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
            <div class="flex-between mb-2">
                <h2>🎯 Draft ${isDone ? '(Completado)' : `— Ronda ${state.current_round}/23`}</h2>
                <div class="flex" style="gap:.5rem;align-items:center">
                    <span class="status-dot ${wsConnected ? 'status-active' : 'status-pending'}"></span>
                    <span style="font-size:.75rem;color:var(--text-muted)">${wsConnected ? 'En vivo' : 'Polling'}</span>
                </div>
            </div>

            ${!isDone ? `
            <div class="draft-turn ${myTurn ? 'my-turn' : ''}">
                <div style="font-size:.9rem;color:var(--text-secondary)">${myTurn ? '🔔 ¡ES TU TURNO!' : 'Esperando a:'}</div>
                <div style="font-size:1.3rem;font-weight:700">${state.current_team_name || '...'}</div>
                <div style="font-size:.85rem;color:var(--text-muted)">Pick ${state.current_pick} de ${state.pick_order.length} · Ronda ${state.current_round}/23</div>
                <div class="flex mt-1" style="justify-content:center;gap:.5rem">
                    ${myTurn ? '<button class="btn btn-outline btn-sm" id="btn-autopick">⚡ Auto-pick (1)</button>' : ''}
                    <button class="btn btn-sm ${autodraftEnabled ? 'btn-gold' : 'btn-outline'}" id="btn-autodraft">
                        🤖 AutoDraft ${autodraftEnabled ? 'ON' : 'OFF'}
                    </button>
                </div>
                ${autodraftEnabled ? '<div style="font-size:.8rem;color:var(--accent-gold);margin-top:.5rem">AutoDraft activado — selección automática inteligente (2-3 GK, 5+ DEF/MID/FWD)</div>' : ''}
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
                        <div id="player-list" style="max-height:500px;overflow-y:auto">
                            ${renderPlayerList(availablePlayers, myTurn && !isDone)}
                        </div>
                    </div>
                </div>
                <div>
                    <div class="card">
                        <div class="flex-between mb-1">
                            <div class="card-header" style="margin:0">Historial de picks</div>
                            <span class="badge badge-teal">${state.picks.length} picks</span>
                        </div>
                        <div class="pick-log" id="pick-log">
                            ${renderPickLog(state.picks)}
                        </div>
                    </div>
                </div>
            </div>
        `;

        bindEvents();
    }

    function renderPlayerList(players, canPick) {
        return players.map(p => `
            <div class="player-card" data-pid="${p.id}">
                <img src="${p.photo}" alt="" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><rect fill=%22%23374151%22 width=%2240%22 height=%2240%22/><text x=%2220%22 y=%2225%22 text-anchor=%22middle%22 fill=%22%239ca3af%22 font-size=%2214%22>⚽</text></svg>'">
                <div class="player-info">
                    <div class="player-name">${p.name}</div>
                    <div class="player-meta">${p.club} · ${p.country_code}</div>
                </div>
                ${posBadge(p.position)}
                <div class="player-value">${formatMoney(p.market_value)}</div>
                ${canPick ? `<button class="btn btn-primary btn-sm pick-btn" data-pid="${p.id}">Pick</button>` : ''}
            </div>
        `).join('');
    }

    function renderPickLog(picks) {
        if (!picks.length) return '<div class="text-center" style="color:var(--text-muted);padding:1rem">Sin picks todavía</div>';
        return picks.slice().reverse().map((p, i) => `
            <div class="pick-log-entry ${i === 0 ? 'pick-new' : ''}">
                <span style="color:var(--text-muted)">R${p.round}P${p.pick}</span>
                <strong>${p.team_name}</strong> → ${p.player_name}
            </div>
        `).join('');
    }

    function bindEvents() {
        container.querySelectorAll('.pick-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                btn.disabled = true;
                btn.textContent = '...';
                try {
                    await API.post(`/leagues/${leagueId}/draft/pick`, { player_id: btn.dataset.pid });
                    showToast('¡Pick realizado!', 'success');
                    await refreshState();
                } catch (err) { showToast(err.message, 'error'); btn.disabled = false; btn.textContent = 'Pick'; }
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
            // Only update the player list, not the whole page
            const list = document.getElementById('player-list');
            if (list) {
                const myTurn = state.current_team_id === API.getTeamId();
                const isDone = state.status === 'completed';
                list.innerHTML = renderPlayerList(availablePlayers, myTurn && !isDone);
                bindPickButtons();
            }
        });

        document.getElementById('btn-autopick')?.addEventListener('click', async () => {
            try {
                await API.post(`/leagues/${leagueId}/draft/autopick`);
                showToast('Auto-pick realizado', 'success');
                await refreshState();
            } catch (err) { showToast(err.message, 'error'); }
        });

        document.getElementById('btn-autodraft')?.addEventListener('click', async () => {
            try {
                const res = await API.post(`/leagues/${leagueId}/draft/autodraft`);
                autodraftEnabled = res.autodraft;
                showToast(autodraftEnabled ? '🤖 AutoDraft activado — el sistema elegirá por ti' : 'AutoDraft desactivado', autodraftEnabled ? 'success' : 'info');
                await refreshState();
            } catch (err) { showToast(err.message, 'error'); }
        });
    }

    function bindPickButtons() {
        container.querySelectorAll('.pick-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                btn.disabled = true;
                btn.textContent = '...';
                try {
                    await API.post(`/leagues/${leagueId}/draft/pick`, { player_id: btn.dataset.pid });
                    showToast('¡Pick realizado!', 'success');
                    await refreshState();
                } catch (err) { showToast(err.message, 'error'); btn.disabled = false; btn.textContent = 'Pick'; }
            });
        });
    }

    async function refreshState() {
        if (!alive) return;
        try {
            const newState = await API.get(`/leagues/${leagueId}/draft`);
            const newPickCount = newState.picks ? newState.picks.length : 0;

            // Only re-render if something actually changed
            if (newPickCount !== lastPickCount || newState.status !== state.status) {
                const hadNewPick = newPickCount > lastPickCount;
                state = newState;
                lastPickCount = newPickCount;
                await loadAvailable();
                render();

                // Notify if it became my turn
                if (state.current_team_id === API.getTeamId() && state.status === 'in_progress') {
                    showToast('🔔 ¡Es tu turno!', 'success');
                }
            }
        } catch (err) {
            console.error('Draft refresh error:', err);
        }
    }

    // --- WebSocket connection with auto-reconnect ---
    function connectWS() {
        if (!alive) return;
        const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        try {
            ws = new WebSocket(`${wsProto}//${location.host}/api/v1/leagues/${leagueId}/draft/ws`);

            ws.onopen = () => {
                wsConnected = true;
                updateConnectionIndicator();
                // Stop polling when WS is connected
                if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
            };

            ws.onmessage = async (evt) => {
                if (!alive) return;
                try {
                    const msg = JSON.parse(evt.data);
                    if (msg.state) {
                        const newPickCount = msg.state.picks ? msg.state.picks.length : 0;
                        if (newPickCount !== lastPickCount || msg.state.status !== state.status) {
                            state = msg.state;
                            lastPickCount = newPickCount;
                            await loadAvailable();
                            render();

                            if (msg.type === 'pick' && msg.pick) {
                                showToast(`${msg.pick.team_name} eligió a ${msg.pick.player_name}`, 'info');
                            }
                            if (state.current_team_id === API.getTeamId() && state.status === 'in_progress') {
                                showToast('🔔 ¡Es tu turno!', 'success');
                            }
                            if (msg.type === 'draft_end') {
                                showToast('🏆 ¡Draft completado!', 'success');
                            }
                        }
                    }
                } catch (e) { console.error('WS message parse error:', e); }
            };

            ws.onclose = () => {
                wsConnected = false;
                updateConnectionIndicator();
                // Reconnect after 3 seconds, also start polling as fallback
                if (alive) {
                    startPolling();
                    setTimeout(connectWS, 3000);
                }
            };

            ws.onerror = () => {
                wsConnected = false;
                ws.close();
            };
        } catch {
            startPolling();
        }
    }

    function updateConnectionIndicator() {
        const dot = container.querySelector('.status-dot');
        const label = container.querySelector('.status-dot + span');
        if (dot) {
            dot.className = `status-dot ${wsConnected ? 'status-active' : 'status-pending'}`;
        }
        if (label) {
            label.textContent = wsConnected ? 'En vivo' : 'Polling';
        }
    }

    function startPolling() {
        if (pollTimer || !alive) return;
        pollTimer = setInterval(async () => {
            if (!alive) { clearInterval(pollTimer); pollTimer = null; return; }
            await refreshState();
        }, 3000);
    }

    // --- Initialize ---
    await loadAvailable();
    render();
    connectWS();
    // Always start polling as a safety net (WS will disable it when connected)
    startPolling();

    // --- Cleanup on page leave ---
    window.addEventListener('hashchange', function cleanup() {
        alive = false;
        if (ws) { ws.close(); ws = null; }
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
        window.removeEventListener('hashchange', cleanup);
    }, { once: true });
});
