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
    let filterCountry = '';
    let searchTerm = '';
    let countries = [];
    let ws = null;
    let wsConnected = false;
    let pollTimer = null;
    let alive = true;
    let lastPickCount = state.picks ? state.picks.length : 0;
    let autodraftEnabled = false;
    let draftQueue = []; // [{id, name, position, ...}, ...]

    // Check initial autodraft + queue status
    try {
        const adStatus = await API.get(`/leagues/${leagueId}/draft/autodraft`);
        autodraftEnabled = adStatus.team_autodraft || false;
    } catch {}

    // Load countries for filter
    try {
        countries = await API.get('/countries');
        countries.sort((a, b) => a.name.localeCompare(b.name));
    } catch { countries = []; }

    async function loadQueue() {
        try {
            draftQueue = await API.get(`/leagues/${leagueId}/draft/queue`);
        } catch { draftQueue = []; }
    }

    async function loadAvailable() {
        const params = new URLSearchParams();
        if (filterPos) params.set('position', filterPos);
        if (filterCountry) params.set('country', filterCountry);
        if (searchTerm) params.set('search', searchTerm);
        availablePlayers = await API.get(`/leagues/${leagueId}/draft/available?${params}`);
    }

    function render() {
        const myTurn = state.current_team_id === API.getTeamId();
        const isDone = state.status === 'completed';
        const myTeamId = API.getTeamId();
        const myPicks = (state.picks || [])
            .filter(p => p.team_id === myTeamId)
            .map(p => ({
                name: p.player_name,
                player_id: p.player_id,
                position: p.position || '?',
                country_code: p.country_code || '',
                club: p.club || '',
            }));

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
                ${autodraftEnabled ? '<div style="font-size:.8rem;color:var(--accent-gold);margin-top:.5rem">AutoDraft activado — selección automática inteligente</div>' : ''}
                ${draftQueue.length > 0 && !autodraftEnabled ? `<div style="font-size:.8rem;color:var(--accent-teal);margin-top:.5rem">📋 Cola activa (${draftQueue.length} jugadores) — auto-pick del siguiente disponible</div>` : ''}
            </div>` : '<div class="card text-center mb-2"><p style="color:var(--accent-gold);font-size:1.2rem">🏆 Draft completado — ¡Gestiona tu equipo!</p></div>'}

            <div class="draft-grid">
                <div class="draft-col-main">
                    <div class="card">
                        <div class="flex-between mb-1">
                            <div class="card-header" style="margin:0">Jugadores disponibles (${availablePlayers.length})</div>
                            <input type="text" id="draft-search" placeholder="Buscar..." style="width:160px" value="${searchTerm}">
                        </div>
                        <div class="filter-bar">
                            ${['', 'GK', 'DEF', 'MID', 'FWD'].map(p =>
                                `<button class="filter-btn ${filterPos === p ? 'active' : ''}" data-pos="${p}">${p || 'Todos'}</button>`
                            ).join('')}
                            <div class="draft-country-wrap" id="draft-country-wrap">
                                <button class="draft-country-btn" id="draft-country-btn">
                                    ${filterCountry ? `<img src="${(countries.find(c=>c.code===filterCountry)||{}).flag||''}" class="draft-flag"> ${(countries.find(c=>c.code===filterCountry)||{}).name||''}` : 'Todos los paises'}
                                </button>
                                <div class="draft-country-dropdown" id="draft-country-dropdown">
                                    <div class="draft-country-option ${!filterCountry ? 'active' : ''}" data-code="">Todos los paises</div>
                                    ${countries.map(c => `
                                        <div class="draft-country-option ${filterCountry === c.code ? 'active' : ''}" data-code="${c.code}">
                                            <img src="${c.flag}" class="draft-flag"> ${c.name}
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                        </div>
                        <div id="player-list" style="max-height:500px;overflow-y:auto">
                            ${renderPlayerList(availablePlayers, myTurn && !isDone, !isDone)}
                        </div>
                    </div>
                </div>
                <div class="draft-col-side">
                    <div class="card mb-2">
                        <div class="flex-between mb-1">
                            <div class="card-header" style="margin:0">📋 Cola de Draft</div>
                            ${draftQueue.length > 0 ? `<button class="btn btn-sm btn-outline" id="btn-clear-queue">Limpiar</button>` : ''}
                        </div>
                        ${draftQueue.length === 0 ? '<p style="color:var(--text-muted);font-size:.85rem;padding:.5rem 0">Añade jugadores con el botón + de la lista para que se pickeen automáticamente en tu turno.</p>' : ''}
                        <div style="max-height:250px;overflow-y:auto">
                            ${draftQueue.map((p, i) => `
                                <div class="player-card queue-item ${!p.available ? 'queue-taken' : ''}">
                                    <span style="color:var(--text-muted);font-size:.8rem;width:20px">${i + 1}</span>
                                    <div class="player-info" style="flex:1;min-width:0">
                                        <div class="player-name" style="font-size:.85rem"><a href="#/player/${p.id}" style="color:inherit;text-decoration:none" onclick="event.stopPropagation()">${p.name}</a></div>
                                        <div class="player-meta">${p.country_code}</div>
                                    </div>
                                    ${posBadge(p.position)}
                                    ${!p.available ? '<span style="font-size:.7rem;color:var(--accent-red)">Tomado</span>' : ''}
                                    <div style="display:flex;flex-direction:column;gap:2px">
                                        <button class="btn btn-sm btn-outline queue-up" data-pid="${p.id}" style="padding:1px 4px;font-size:.7rem" ${i === 0 ? 'disabled' : ''}>▲</button>
                                        <button class="btn btn-sm btn-outline queue-down" data-pid="${p.id}" style="padding:1px 4px;font-size:.7rem" ${i === draftQueue.length - 1 ? 'disabled' : ''}>▼</button>
                                    </div>
                                    <button class="btn btn-sm btn-outline queue-remove" data-pid="${p.id}" style="padding:2px 6px" title="Quitar">✕</button>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                    <div class="card mb-2">
                        <div class="flex-between mb-1">
                            <div class="card-header" style="margin:0">Historial de picks</div>
                            <span class="badge badge-teal">${state.picks.length} picks</span>
                        </div>
                        <div class="pick-log" id="pick-log">
                            ${renderPickLog(state.picks)}
                        </div>
                    </div>
                    <div class="card">
                        <div class="card-header">Mi equipo (${myPicks.length}/23)</div>
                        ${['GK','DEF','MID','FWD'].map(pos => {
                            const pp = myPicks.filter(p => p.position === pos);
                            if (!pp.length) return '';
                            return `<div style="margin-bottom:.5rem">
                                <small style="color:var(--text-muted)">${pos} (${pp.length})</small>
                                ${pp.map(p => `<div style="font-size:.8rem;padding:.15rem 0;display:flex;align-items:center;gap:.4rem">
                                    ${posBadge(pos)} <span>${p.name}</span> <span style="color:var(--text-muted);font-size:.75rem">${p.country_code}</span>
                                </div>`).join('')}
                            </div>`;
                        }).join('')}
                        ${myPicks.length === 0 ? '<p style="color:var(--text-muted);font-size:.85rem">Sin picks todavía</p>' : ''}
                    </div>
                </div>
            </div>
        `;

        bindEvents();
    }

    function renderPlayerList(players, canPick, canQueue) {
        const queuedIds = new Set(draftQueue.map(p => p.id));
        return players.map(p => {
            const inQueue = queuedIds.has(p.id);
            return `
            <div class="player-card" data-pid="${p.id}">
                <img src="${p.photo}" alt="" referrerpolicy="no-referrer" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><rect fill=%22%23374151%22 width=%2240%22 height=%2240%22/><text x=%2220%22 y=%2225%22 text-anchor=%22middle%22 fill=%22%239ca3af%22 font-size=%2214%22>⚽</text></svg>'">
                <div class="player-info">
                    <div class="player-name"><a href="#/player/${p.id}" style="color:inherit;text-decoration:none">${p.name}</a></div>
                    <div class="player-meta">${p.country_code} · ${p.club}</div>
                </div>
                ${posBadge(p.position)}
                <span class="player-ovr">${p.strength || ''}</span>
                <div class="player-value">${formatMoney(p.market_value)}</div>
                ${canQueue ? `<button class="btn btn-sm ${inQueue ? 'btn-teal' : 'btn-outline'} queue-add-btn" data-pid="${p.id}" title="${inQueue ? 'En cola' : 'Añadir a cola'}">${inQueue ? '✓' : '+'}</button>` : ''}
                ${canPick ? `<button class="btn btn-primary btn-sm pick-btn" data-pid="${p.id}">Pick</button>` : ''}
            </div>`;
        }).join('');
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
            const list = document.getElementById('player-list');
            if (list) {
                const myTurn = state.current_team_id === API.getTeamId();
                const isDone = state.status === 'completed';
                list.innerHTML = renderPlayerList(availablePlayers, myTurn && !isDone, !isDone);
                bindPickButtons();
                bindQueueAddButtons();
            }
        });

        document.getElementById('draft-country-btn')?.addEventListener('click', (e) => {
            e.stopPropagation();
            document.getElementById('draft-country-dropdown')?.classList.toggle('open');
        });
        document.querySelectorAll('.draft-country-option').forEach(opt => {
            opt.addEventListener('click', async () => {
                filterCountry = opt.dataset.code;
                document.getElementById('draft-country-dropdown')?.classList.remove('open');
                await loadAvailable();
                render();
            });
        });
        document.addEventListener('click', () => {
            document.getElementById('draft-country-dropdown')?.classList.remove('open');
        }, { once: true });

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
                render();
                await refreshState();
            } catch (err) { showToast(err.message, 'error'); }
        });

        // Queue: add from player list
        container.querySelectorAll('.queue-add-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const pid = btn.dataset.pid;
                const inQueue = draftQueue.some(p => p.id === pid);
                try {
                    if (inQueue) {
                        await API.post(`/leagues/${leagueId}/draft/queue/remove`, { player_id: pid });
                    } else {
                        await API.post(`/leagues/${leagueId}/draft/queue/add`, { player_id: pid });
                    }
                    await loadQueue();
                    render();
                } catch (err) { showToast(err.message, 'error'); }
            });
        });

        // Queue: remove
        container.querySelectorAll('.queue-remove').forEach(btn => {
            btn.addEventListener('click', async () => {
                try {
                    await API.post(`/leagues/${leagueId}/draft/queue/remove`, { player_id: btn.dataset.pid });
                    await loadQueue();
                    render();
                } catch (err) { showToast(err.message, 'error'); }
            });
        });

        // Queue: move up/down
        container.querySelectorAll('.queue-up').forEach(btn => {
            btn.addEventListener('click', async () => {
                const q = draftQueue.map(p => p.id);
                const idx = q.indexOf(btn.dataset.pid);
                if (idx > 0) { [q[idx], q[idx-1]] = [q[idx-1], q[idx]]; }
                try {
                    await API.post(`/leagues/${leagueId}/draft/queue/reorder`, { queue: q });
                    await loadQueue();
                    render();
                } catch (err) { showToast(err.message, 'error'); }
            });
        });
        container.querySelectorAll('.queue-down').forEach(btn => {
            btn.addEventListener('click', async () => {
                const q = draftQueue.map(p => p.id);
                const idx = q.indexOf(btn.dataset.pid);
                if (idx < q.length - 1) { [q[idx], q[idx+1]] = [q[idx+1], q[idx]]; }
                try {
                    await API.post(`/leagues/${leagueId}/draft/queue/reorder`, { queue: q });
                    await loadQueue();
                    render();
                } catch (err) { showToast(err.message, 'error'); }
            });
        });

        // Queue: clear
        document.getElementById('btn-clear-queue')?.addEventListener('click', async () => {
            try {
                await API.post(`/leagues/${leagueId}/draft/queue/clear`);
                await loadQueue();
                render();
                showToast('Cola vaciada', 'info');
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

    function bindQueueAddButtons() {
        container.querySelectorAll('.queue-add-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const pid = btn.dataset.pid;
                const inQueue = draftQueue.some(p => p.id === pid);
                try {
                    if (inQueue) {
                        await API.post(`/leagues/${leagueId}/draft/queue/remove`, { player_id: pid });
                    } else {
                        await API.post(`/leagues/${leagueId}/draft/queue/add`, { player_id: pid });
                    }
                    await loadQueue();
                    render();
                } catch (err) { showToast(err.message, 'error'); }
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
                await loadQueue();
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
                            await loadQueue();
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
    await loadQueue();
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
