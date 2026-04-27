/* Market page — market windows, clause protection, transactions, reposition draft */
Router.register('#/market/:windowId', async (container, params) => {
    const leagueId = API.getLeagueId();
    const teamId = API.getTeamId();
    const windowId = params.windowId;

    try {
        const window = await API.get(`/leagues/${leagueId}/market/${windowId}`);
        const budget = await API.get(`/teams/${teamId}/market/${windowId}/budget`);
        const clauses = await API.get(`/teams/${teamId}/market/${windowId}/clauses`);
        const transactions = await API.get(`/teams/${teamId}/market/${windowId}/transaction-history`);

        let content = `
            <div class="flex-between mb-2">
                <h2>🏪 Mercado — ${window.market_type}</h2>
                <span class="badge ${['market_open', 'reposition_draft'].includes(window.status) ? 'badge-teal' : 'badge-gold'}">
                    <span class="status-dot ${['market_open', 'reposition_draft'].includes(window.status) ? 'status-active' : 'status-closed'}"></span>
                    ${window.status}
                </span>
            </div>

            <div class="grid grid-3 mb-2">
                <div class="stat-card">
                    <div class="stat-label">Presupuesto</div>
                    <div class="stat-value">${formatMoney(budget.remaining_budget)}</div>
                    <small style="color:var(--text-secondary)">Inicial: ${formatMoney(budget.initial_budget)}</small>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Compras</div>
                    <div class="stat-value">${budget.buys_count}/${budget.max_buys}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Robos Recibidos</div>
                    <div class="stat-value">${budget.sells_count}/${budget.max_sells}</div>
                </div>
            </div>
        `;

        // Clause window phase
        if (window.status === 'clause_window') {
            content += `
                <div class="card mb-2">
                    <div class="card-header">🔐 Protección de Cláusulas</div>
                    <p style="font-size:.85rem;color:var(--text-secondary);margin-bottom:1rem">
                        Distribuye 300M entre tus jugadores. Máx 2 bloqueados (no pueden ser robados).
                    </p>
                    <div id="clauses-form"></div>
                    <button class="btn btn-primary mt-1" id="btn-save-clauses">Guardar Cláusulas</button>
                </div>
            `;
        }

        // Market open phase
        if (window.status === 'market_open') {
            content += `
                <div class="card mb-2">
                    <div class="card-header">🎯 Explorador de Mercado</div>
                    <div class="form-group mb-1">
                        <label>Filtrar por posición:</label>
                        <select id="position-filter" style="width:100%">
                            <option value="">Todos</option>
                            <option value="GK">GK - Portero</option>
                            <option value="DEF">DEF - Defensa</option>
                            <option value="MID">MID - Centrocampista</option>
                            <option value="FWD">FWD - Delantero</option>
                        </select>
                    </div>
                    <div id="available-players" style="max-height:600px;overflow-y:auto"></div>
                </div>
            `;
        }

        // Reposition draft phase
        if (window.status === 'reposition_draft') {
            content += `
                <div class="card mb-2">
                    <div class="card-header">📋 Draft de Reposición</div>
                    <div id="reposition-state"></div>
                    <div id="available-reposition-players" style="max-height:400px;overflow-y:auto"></div>
                </div>
            `;
        }

        // Transaction history
        content += `
            <div class="card">
                <div class="card-header">📊 Historial de Transacciones</div>
                <div style="max-height:300px;overflow-y:auto">
                    ${transactions.length === 0 ? '<p style="color:var(--text-muted)">Sin transacciones</p>' : ''}
                    ${transactions.map(t => `
                        <div style="padding:.5rem;border-bottom:1px solid var(--border);font-size:.85rem">
                            <strong>${t.player_name}</strong> — ${t.direction === 'bought' ? '✅ Comprado' : '❌ Robado'} por ${formatMoney(t.clause_amount_paid)}
                            <div style="color:var(--text-muted);font-size:.75rem">${new Date(t.transaction_date).toLocaleString()}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        container.innerHTML = content;

        // Load clause form
        if (window.status === 'clause_window') {
            await loadClauseForm(leagueId, teamId, windowId, clauses);
        }

        // Load available players
        if (window.status === 'market_open') {
            await loadAvailablePlayers(leagueId, teamId, windowId);
        }

        // Load reposition draft state
        if (window.status === 'reposition_draft') {
            await loadRepositionDraft(leagueId, teamId, windowId);
        }

    } catch (err) {
        container.innerHTML = `<div class="card text-center"><p>Error: ${err.message}</p></div>`;
        console.error(err);
    }
});

async function loadClauseForm(leagueId, teamId, windowId, clauses) {
    try {
        const form = document.getElementById('clauses-form');
        if (!form) return;

        form.innerHTML = '<div class="text-center">Cargando...</div>';

        // Get team players
        const team = await API.get(`/teams/${teamId}`);

        form.innerHTML = team.players.map(p => `
            <div style="margin-bottom:1rem;padding-bottom:1rem;border-bottom:1px solid var(--border)">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem">
                    <strong>${p.name} (${p.position})</strong>
                    <input type="checkbox" class="blocked-checkbox" data-pid="${p.player_id}" 
                        ${clauses.some(c => c.player_id === p.player_id && c.is_blocked) ? 'checked' : ''}>
                    <small>Bloqueado</small>
                </div>
                <input type="range" class="clause-slider" data-pid="${p.player_id}" 
                    min="0" max="300000000" step="1000000" style="width:100%"
                    value="${clauses.find(c => c.player_id === p.player_id)?.clause_amount || 0}">
                <div style="display:flex;justify-content:space-between;font-size:.75rem;color:var(--text-secondary)">
                    <span>0M</span>
                    <span class="clause-value" data-pid="${p.player_id}">
                        ${formatMoney(clauses.find(c => c.player_id === p.player_id)?.clause_amount || 0)}
                    </span>
                    <span>300M</span>
                </div>
            </div>
        `).join('');

        // Update displayed values
        document.querySelectorAll('.clause-slider').forEach(slider => {
            slider.addEventListener('input', () => {
                const value = parseInt(slider.value);
                document.querySelector(`.clause-value[data-pid="${slider.dataset.pid}"]`).textContent = formatMoney(value);
            });
        });

        // Save button
        document.getElementById('btn-save-clauses').addEventListener('click', async () => {
            const newClauses = team.players.map(p => ({
                player_id: p.player_id,
                clause_amount: parseInt(document.querySelector(`.clause-slider[data-pid="${p.player_id}"]`).value),
                is_blocked: document.querySelector(`.blocked-checkbox[data-pid="${p.player_id}"]`).checked,
            }));

            try {
                await API.post(`/teams/${teamId}/market/${windowId}/clauses/set`, { clauses: newClauses });
                showToast('Cláusulas guardadas', 'success');
            } catch (err) {
                showToast(err.message, 'error');
            }
        });
    } catch (err) {
        console.error(err);
    }
}

async function loadAvailablePlayers(leagueId, teamId, windowId) {
    try {
        document.getElementById('position-filter').addEventListener('change', async (e) => {
            const position = e.target.value;
            const players = await API.get(`/leagues/${leagueId}/market/${windowId}/available-players${position ? `?position=${position}` : ''}`);
            renderAvailablePlayers(leagueId, teamId, windowId, players);
        });

        const players = await API.get(`/leagues/${leagueId}/market/${windowId}/available-players`);
        renderAvailablePlayers(leagueId, teamId, windowId, players);
    } catch (err) {
        console.error(err);
    }
}

function renderAvailablePlayers(leagueId, teamId, windowId, players) {
    const container = document.getElementById('available-players');
    container.innerHTML = players.map(p => `
        <div class="player-card">
            <img src="${p.photo}" alt="" referrerpolicy="no-referrer" onerror="this.style.display='none'" style="height:60px;width:auto">
            <div class="player-info">
                <div class="player-name">${p.name}</div>
                <div class="player-meta">${p.current_team_name} · ${p.country_code}</div>
                <div style="font-size:.75rem;color:var(--text-secondary)">
                    Cláusula: ${formatMoney(p.clause_amount)} ${p.is_blocked ? '🔒 BLOQUEADO' : ''}
                </div>
            </div>
            <span class="badge badge-small">${p.position}</span>
            <span class="stat-value" style="font-size:1rem">${formatMoney(p.market_value)}</span>
            <button class="btn btn-sm btn-primary" data-pid="${p.player_id}" data-amount="${p.clause_amount}" onclick="buyPlayer('${leagueId}', '${teamId}', '${windowId}', this)">
                Comprar
            </button>
        </div>
    `).join('');
}

async function buyPlayer(leagueId, teamId, windowId, btn) {
    const playerId = btn.dataset.pid;
    const amount = parseInt(btn.dataset.amount);

    if (!confirm(`¿Comprar este jugador por ${formatMoney(amount)}?`)) return;

    try {
        await API.post(`/teams/${teamId}/market/${windowId}/buy-player`, { player_id: playerId });
        showToast('¡Jugador comprado!', 'success');
        Router.handleRoute();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function loadRepositionDraft(leagueId, teamId, windowId) {
    try {
        const state = await API.get(`/leagues/${leagueId}/market/${windowId}/reposition-draft-state`);
        const stateContainer = document.getElementById('reposition-state');

        stateContainer.innerHTML = `
            <div class="grid grid-3 mb-2">
                <div class="stat-card">
                    <div class="stat-label">Tu Turno</div>
                    <div class="stat-value">${state.current_turn_team_id === teamId ? '✅ TÚ' : '⏳'}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Tu Plantilla</div>
                    <div class="stat-value">${state.leaderboard.find(l => l.team_id === teamId)?.players_count || 0}/23</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Disponibles</div>
                    <div class="stat-value">${state.remaining_available_players}</div>
                </div>
            </div>

            <div style="margin-bottom:1rem">
                <h4>Orden del Draft</h4>
                <table style="width:100%;font-size:.85rem">
                    <thead><tr><th>Equipo</th><th>Presupuesto</th><th>Jugadores</th></tr></thead>
                    <tbody>
                        ${state.draft_order.map((e, i) => `
                            <tr style="${e.team_id === state.current_turn_team_id ? 'background:var(--bg-secondary)' : ''}">
                                <td><strong>${e.team_name}</strong></td>
                                <td>${formatMoney(e.remaining_budget)}</td>
                                <td>${e.players_count} (${e.gk_count}GK ${e.def_count}DEF ${e.mid_count}MID ${e.fwd_count}FWD)</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;

        // Load available players for reposition
        const players = await API.get(`/leagues/${leagueId}/market/${windowId}/reposition-available-players`);
        const container = document.getElementById('available-reposition-players');

        container.innerHTML = `
            <h4>Jugadores Disponibles (sin minutos)</h4>
            <div class="grid grid-2">
                ${players.map(p => `
                    <div class="player-card">
                        <img src="${p.photo}" alt="" referrerpolicy="no-referrer" onerror="this.style.display='none'" style="height:50px;width:auto">
                        <div>
                            <strong>${p.name}</strong>
                            <div style="font-size:.75rem;color:var(--text-secondary)">${p.country_code} · ${p.position}</div>
                        </div>
                        <button class="btn btn-sm btn-primary" ${state.current_turn_team_id !== teamId ? 'disabled' : ''} 
                            onclick="makeRepositionPick('${leagueId}', '${teamId}', '${windowId}', '${p.player_id}')">
                            Elegir
                        </button>
                    </div>
                `).join('')}
            </div>
            ${state.current_turn_team_id === teamId ? `
                <button class="btn btn-outline mt-1" onclick="makeRepositionPick('${leagueId}', '${teamId}', '${windowId}', null)">
                    Pasar Turno
                </button>
            ` : ''}
        `;
    } catch (err) {
        console.error(err);
    }
}

async function makeRepositionPick(leagueId, teamId, windowId, playerId) {
    try {
        await API.post(`/teams/${teamId}/market/${windowId}/reposition-draft-pick`, { player_id: playerId });
        showToast(playerId ? '¡Jugador elegido!' : 'Turno pasado', 'success');
        Router.handleRoute();
    } catch (err) {
        showToast(err.message, 'error');
    }
}
