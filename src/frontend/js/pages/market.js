/* Market page — market windows, clause protection, transactions, reposition draft */

// List view: #/market
Router.register('#/market', async (container) => {
    const leagueId = API.getLeagueId();
    const teamId = API.getTeamId();
    const currentTeam = API.getCurrentTeam();

    try {
        const windows = await API.get(`/leagues/${leagueId}/market-windows`);

        const adminLink = currentTeam?.is_commissioner
            ? `<a href="#/admin/market" class="btn btn-primary">⚙️ Gestionar Mercados</a>` : '';

        const statusBadge = (s) => {
            const map = {
                pending: { cls: 'badge-gold', txt: 'Pendiente' },
                clause_window: { cls: 'badge-teal', txt: 'Cláusulas' },
                market_open: { cls: 'badge-teal', txt: 'Abierto' },
                market_closed: { cls: 'badge-gold', txt: 'Cerrado' },
                reposition_draft: { cls: 'badge-teal', txt: 'Reposición' },
                completed: { cls: 'badge-muted', txt: 'Finalizado' },
            };
            const m = map[s] || { cls: 'badge-muted', txt: s };
            return `<span class="badge ${m.cls}">${m.txt}</span>`;
        };

        // Find the next protectable window: first one not yet open for buying.
        // Order: clause_window (active) > pending (next up). Skips market_open/closed/completed.
        const protectable = (windows || []).find(w => w.status === 'clause_window')
            || (windows || []).find(w => w.status === 'pending');

        const headerHtml = `
            <div class="flex-between mb-2">
                <h2>🏪 Mercados</h2>
                ${adminLink}
            </div>
        `;

        if (!windows || windows.length === 0) {
            container.innerHTML = `
                ${headerHtml}
                <div class="card text-center">
                    <p style="color:var(--text-muted)">No hay mercados creados aún.</p>
                    ${currentTeam?.is_commissioner ? '<p>Crea uno desde la página de administración.</p>' : ''}
                </div>
            `;
            return;
        }

        // Clause protection block — shown ABOVE the windows list whenever there
        // is a protectable window (pending or clause_window). Reuses the same
        // form used inside the per-window detail page.
        let clausesHtml = '';
        if (teamId && protectable) {
            const phaseLabel = protectable.phase || protectable.market_type || '';
            const stateLabel = protectable.status === 'clause_window'
                ? 'Cláusulas activas'
                : 'Próximo mercado';
            clausesHtml = `
                <div class="card mb-2">
                    <div class="card-header">🔐 Protección de Cláusulas — ${stateLabel} (${phaseLabel})</div>
                    <p style="font-size:.85rem;color:var(--text-secondary);margin-bottom:1rem">
                        Distribuye ${formatMoney(protectable.protect_budget)} entre tus jugadores. Máx 2 bloqueados (no pueden ser robados).
                        Las cláusulas guardadas se aplicarán en la siguiente ventana de mercado.
                    </p>
                    <div id="clauses-form"></div>
                    <button class="btn btn-primary mt-1" id="btn-save-clauses">Guardar Cláusulas</button>
                </div>
            `;
        }

        container.innerHTML = `
            ${headerHtml}
            ${clausesHtml}
            <div class="card">
                <div class="card-header">📋 Ventanas de Mercado</div>
                <table style="width:100%;font-size:.9rem">
                    <thead>
                        <tr>
                            <th>Fase</th><th>Tipo</th><th>Estado</th><th>Inicio</th><th>Acción</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${windows.map(w => `
                            <tr>
                                <td>${w.phase}</td>
                                <td>${w.market_type || '—'}</td>
                                <td>${statusBadge(w.status)}</td>
                                <td>${w.clause_window_start ? formatMadrid(w.clause_window_start) : '—'}</td>
                                <td><a href="#/market/${w.id}" class="btn btn-sm btn-primary">Abrir</a></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;

        // Load the clause form using the existing helper (works for both
        // pending and clause_window — backend allows save in any state).
        if (teamId && protectable) {
            const clauses = await API.get(`/teams/${teamId}/market/${protectable.id}/clauses`);
            await loadClauseForm(leagueId, teamId, protectable.id, clauses, protectable);
        }
    } catch (err) {
        container.innerHTML = `<div class="card text-center"><p>Error: ${err.message}</p></div>`;
        console.error(err);
    }
});

// Detail view: #/market/:windowId
Router.register('#/market/:windowId', async (container, params) => {
    const leagueId = API.getLeagueId();
    const teamId = API.getTeamId();
    const windowId = params.windowId;

    try {
        const win = await API.get(`/leagues/${leagueId}/market/${windowId}`);
        const budget = await API.get(`/teams/${teamId}/market/${windowId}/budget`);
        const clauses = await API.get(`/teams/${teamId}/market/${windowId}/clauses`);
        const transactions = await API.get(`/teams/${teamId}/market/${windowId}/transaction-history`);

        let content = `
            <div class="flex-between mb-2">
                <h2>🏪 Mercado — ${win.market_type || win.phase}</h2>
                <span class="badge ${['market_open', 'reposition_draft'].includes(win.status) ? 'badge-teal' : 'badge-gold'}">
                    <span class="status-dot ${['market_open', 'reposition_draft'].includes(win.status) ? 'status-active' : 'status-closed'}"></span>
                    ${win.status}
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
        if (win.status === 'clause_window') {
            content += `
                <div class="card mb-2">
                    <div class="card-header">🔐 Protección de Cláusulas</div>
                    <p style="font-size:.85rem;color:var(--text-secondary);margin-bottom:1rem">
                        Distribuye ${formatMoney(win.protect_budget)} entre tus jugadores. Máx 2 bloqueados (no pueden ser robados).
                    </p>
                    <div id="clauses-form"></div>
                    <button class="btn btn-primary mt-1" id="btn-save-clauses">Guardar Cláusulas</button>
                </div>
            `;
        }

        // Market open phase
        if (win.status === 'market_open') {
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
        if (win.status === 'reposition_draft') {
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
                            <div style="color:var(--text-muted);font-size:.75rem">${formatMadrid(t.transaction_date)}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        container.innerHTML = content;

        // Load clause form
        if (win.status === 'clause_window') {
            await loadClauseForm(leagueId, teamId, windowId, clauses, win);
        }

        // Load available players
        if (win.status === 'market_open') {
            await loadAvailablePlayers(leagueId, teamId, windowId);
        }

        // Load reposition draft state
        if (win.status === 'reposition_draft') {
            await loadRepositionDraft(leagueId, teamId, windowId);
        }

    } catch (err) {
        container.innerHTML = `<div class="card text-center"><p>Error: ${err.message}</p></div>`;
        console.error(err);
    }
});

// Preset clause amounts (in millions of EUR)
const CLAUSE_PRESETS = [
    { v: 0, label: 'SELL' },
    { v: 1_000_000, label: '1M' },
    { v: 5_000_000, label: '5M' },
    { v: 15_000_000, label: '15M' },
    { v: 25_000_000, label: '25M' },
    { v: 50_000_000, label: '50M' },
    { v: 80_000_000, label: '80M' },
];

// Convert ISO-3 country code to ISO-2 for flag emoji rendering (fallback when flag string missing)
const ISO3_TO_ISO2 = {
    ARG:'AR', AUS:'AU', AUT:'AT', BEL:'BE', BRA:'BR', CAN:'CA', CHL:'CL', CHN:'CN', CIV:'CI',
    CMR:'CM', COL:'CO', CRC:'CR', CRO:'HR', CZE:'CZ', DEN:'DK', ECU:'EC', EGY:'EG', ENG:'GB-ENG',
    ESP:'ES', FRA:'FR', GER:'DE', GHA:'GH', GRE:'GR', HON:'HN', IRN:'IR', ISL:'IS', ITA:'IT',
    JPN:'JP', KOR:'KR', KSA:'SA', MAR:'MA', MEX:'MX', NED:'NL', NGA:'NG', NOR:'NO', NZL:'NZ',
    PAR:'PY', PER:'PE', POL:'PL', POR:'PT', QAT:'QA', RSA:'ZA', RUS:'RU', SCO:'GB-SCT', SEN:'SN',
    SRB:'RS', SUI:'CH', SVK:'SK', SWE:'SE', TUN:'TN', TUR:'TR', UAE:'AE', UKR:'UA', URU:'UY',
    USA:'US', UZB:'UZ', WAL:'GB-WLS',
};

function flagFor(player) {
    if (player.country_flag) return player.country_flag;
    const iso2 = ISO3_TO_ISO2[player.country_code];
    if (!iso2 || iso2.length !== 2) return '';
    // Convert ISO-2 to regional indicator emoji
    const A = 0x1F1E6;
    return String.fromCodePoint(A + iso2.charCodeAt(0) - 65, A + iso2.charCodeAt(1) - 65);
}

function positionBadgeClass(pos) {
    return ({ GK:'badge-gold', DEF:'badge-teal', MID:'badge-muted', FWD:'badge-teal' })[pos] || 'badge-muted';
}

async function loadClauseForm(leagueId, teamId, windowId, clauses, win) {
    try {
        const form = document.getElementById('clauses-form');
        if (!form) return;

        form.innerHTML = '<div class="text-center">Cargando...</div>';

        const team = await API.get(`/teams/${teamId}`);
        const protectBudget = win.protect_budget;
        const MAX_BLOCKED = 2;

        // Sort: starters first, then by market_value desc
        const players = [...team.players].sort((a, b) => {
            if (a.is_starter !== b.is_starter) return b.is_starter - a.is_starter;
            return (b.market_value || 0) - (a.market_value || 0);
        });

        const clauseFor = (pid) => clauses.find(c => c.player_id === pid);

        form.innerHTML = `
            <div id="clauses-summary" style="position:sticky;top:0;z-index:5;margin-bottom:1rem;padding:.75rem;background:var(--bg-secondary);border-radius:6px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:.5rem">
                <div><strong>Total asignado:</strong> <span id="clauses-total">0</span> / ${formatMoney(protectBudget)}</div>
                <div><strong>Bloqueados:</strong> <span id="clauses-blocked">0</span> / ${MAX_BLOCKED}</div>
                <div><strong>Restante:</strong> <span id="clauses-remaining">${formatMoney(protectBudget)}</span></div>
            </div>
            <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:.75rem">
            ${players.map(p => {
                const c = clauseFor(p.player_id);
                const amount = c?.clause_amount || 0;
                const blocked = !!c?.is_blocked;
                const flag = flagFor(p);
                return `
                <div class="card clause-card" data-pid="${p.player_id}" data-amount="${amount}" data-blocked="${blocked ? '1' : '0'}"
                    style="padding:.75rem;display:flex;flex-direction:column;gap:.5rem">
                    <div style="display:flex;align-items:center;gap:.5rem">
                        <div style="font-size:1.5rem;line-height:1">${flag}</div>
                        <div style="flex:1;min-width:0">
                            <div style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${p.name}">${p.name}</div>
                            <div style="font-size:.7rem;color:var(--text-muted)">${p.country_code} · ${p.club || ''}</div>
                        </div>
                        <span class="badge ${positionBadgeClass(p.position)} badge-small">${p.position}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;font-size:.8rem">
                        <span style="color:var(--text-muted)">Valor: ${formatMoney(p.market_value || 0)}</span>
                        <label class="lock-toggle" style="display:flex;align-items:center;gap:.25rem;cursor:pointer">
                            <input type="checkbox" class="blocked-checkbox" data-pid="${p.player_id}" ${blocked ? 'checked' : ''}>
                            <span>🔒 Bloqueo</span>
                        </label>
                    </div>
                    <div class="clause-presets" data-pid="${p.player_id}" style="display:flex;flex-wrap:wrap;gap:.25rem">
                        ${CLAUSE_PRESETS.map(preset => `
                            <button type="button" class="btn btn-sm preset-btn ${preset.v === amount ? 'btn-primary' : 'btn-outline'}"
                                data-pid="${p.player_id}" data-value="${preset.v}"
                                style="flex:1;min-width:48px;padding:.3rem .25rem;font-size:.75rem">
                                ${preset.label}
                            </button>
                        `).join('')}
                    </div>
                </div>`;
            }).join('')}
            </div>
        `;

        const recalc = () => {
            let total = 0;
            let blockedCount = 0;
            document.querySelectorAll('.clause-card').forEach(card => {
                total += parseInt(card.dataset.amount || '0', 10);
                if (card.dataset.blocked === '1') blockedCount += 1;
            });
            const totalEl = document.getElementById('clauses-total');
            const blockedEl = document.getElementById('clauses-blocked');
            const remainingEl = document.getElementById('clauses-remaining');
            const remaining = protectBudget - total;
            if (totalEl) {
                totalEl.textContent = formatMoney(total);
                totalEl.style.color = total > protectBudget ? 'var(--danger)' : '';
            }
            if (blockedEl) {
                blockedEl.textContent = blockedCount;
                blockedEl.style.color = blockedCount > MAX_BLOCKED ? 'var(--danger)' : '';
            }
            if (remainingEl) {
                remainingEl.textContent = formatMoney(Math.max(0, remaining));
                remainingEl.style.color = remaining < 0 ? 'var(--danger)' : '';
            }
            // Disable unchecked lock checkboxes when limit reached
            const limitReached = blockedCount >= MAX_BLOCKED;
            document.querySelectorAll('.blocked-checkbox').forEach(cb => {
                if (!cb.checked) cb.disabled = limitReached;
                else cb.disabled = false;
            });
        };

        // Preset button click → set amount, update card, refresh visuals
        form.querySelectorAll('.preset-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const pid = btn.dataset.pid;
                const value = parseInt(btn.dataset.value, 10);
                const card = form.querySelector(`.clause-card[data-pid="${pid}"]`);
                card.dataset.amount = String(value);
                // Update visual: highlight only the chosen preset in this card
                form.querySelectorAll(`.preset-btn[data-pid="${pid}"]`).forEach(b => {
                    const isActive = parseInt(b.dataset.value, 10) === value;
                    b.classList.toggle('btn-primary', isActive);
                    b.classList.toggle('btn-outline', !isActive);
                });
                recalc();
            });
        });

        // Lock checkbox
        form.querySelectorAll('.blocked-checkbox').forEach(cb => {
            cb.addEventListener('change', () => {
                const pid = cb.dataset.pid;
                const card = form.querySelector(`.clause-card[data-pid="${pid}"]`);
                card.dataset.blocked = cb.checked ? '1' : '0';
                recalc();
            });
        });

        recalc();

        // Save button
        document.getElementById('btn-save-clauses').addEventListener('click', async () => {
            const newClauses = team.players.map(p => {
                const card = form.querySelector(`.clause-card[data-pid="${p.player_id}"]`);
                return {
                    player_id: p.player_id,
                    clause_amount: parseInt(card?.dataset.amount || '0', 10),
                    is_blocked: card?.dataset.blocked === '1',
                };
            });

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
            <img src="${p.photo || ''}" alt="" referrerpolicy="no-referrer" onerror="this.style.display='none'" style="height:60px;width:auto">
            <div class="player-info">
                <div class="player-name">${p.name}</div>
                <div class="player-meta">${p.current_team_name} · ${p.country_code}</div>
                <div style="font-size:.75rem;color:var(--text-secondary)">
                    Cláusula: ${formatMoney(p.clause_amount)} ${p.is_blocked ? '🔒 BLOQUEADO' : ''}
                </div>
            </div>
            <span class="badge badge-small">${p.position}</span>
            <span class="stat-value" style="font-size:1rem">${formatMoney(p.market_value)}</span>
            <button class="btn btn-sm btn-primary" data-pid="${p.player_id}" data-amount="${p.clause_amount}"
                ${(p.is_blocked || p.current_team_id === teamId) ? 'disabled' : ''}
                onclick="window.buyPlayer('${leagueId}', '${teamId}', '${windowId}', this)">
                ${p.current_team_id === teamId ? 'Tuyo' : 'Comprar'}
            </button>
        </div>
    `).join('');
}

window.buyPlayer = async function(leagueId, teamId, windowId, btn) {
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
};

async function loadRepositionDraft(leagueId, teamId, windowId) {
    try {
        const state = await API.get(`/leagues/${leagueId}/market/${windowId}/reposition-draft-state`);
        const stateContainer = document.getElementById('reposition-state');

        const myEntry = state.leaderboard.find(l => l.team_id === teamId);

        stateContainer.innerHTML = `
            <div class="grid grid-3 mb-2">
                <div class="stat-card">
                    <div class="stat-label">Tu Turno</div>
                    <div class="stat-value">${state.current_turn_team_id === teamId ? '✅ TÚ' : '⏳'}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Tu Plantilla</div>
                    <div class="stat-value">${myEntry?.players_count || 0}/23</div>
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
                        ${state.draft_order.map(e => `
                            <tr style="${e.team_id === state.current_turn_team_id ? 'background:var(--bg-secondary)' : ''}">
                                <td><strong>${e.team_name}</strong>${e.team_id === teamId ? ' (TÚ)' : ''}</td>
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

        const isMyTurn = state.current_turn_team_id === teamId;

        container.innerHTML = `
            <h4>Jugadores Disponibles (sin minutos)</h4>
            ${!isMyTurn ? '<p style="color:var(--text-muted);font-size:.85rem">⏳ Esperando turno…</p>' : ''}
            <div class="grid grid-2">
                ${players.slice(0, 50).map(p => `
                    <div class="player-card">
                        <img src="${p.photo || ''}" alt="" referrerpolicy="no-referrer" onerror="this.style.display='none'" style="height:50px;width:auto">
                        <div>
                            <strong>${p.name}</strong>
                            <div style="font-size:.75rem;color:var(--text-secondary)">${p.country_code} · ${p.position}</div>
                        </div>
                        <button class="btn btn-sm btn-primary" ${isMyTurn ? '' : 'disabled'}
                            onclick="window.makeRepositionPick('${leagueId}', '${teamId}', '${windowId}', '${p.player_id}')">
                            Elegir
                        </button>
                    </div>
                `).join('')}
            </div>
            ${players.length > 50 ? `<p style="color:var(--text-muted);font-size:.85rem;margin-top:.5rem">Mostrando 50 de ${players.length}…</p>` : ''}
            ${isMyTurn ? `
                <button class="btn btn-outline mt-1" onclick="window.makeRepositionPick('${leagueId}', '${teamId}', '${windowId}', null)">
                    Pasar Turno
                </button>
            ` : ''}
        `;
    } catch (err) {
        console.error(err);
    }
}

window.makeRepositionPick = async function(leagueId, teamId, windowId, playerId) {
    try {
        await API.post(`/teams/${teamId}/market/${windowId}/reposition-draft-pick`, { player_id: playerId });
        showToast(playerId ? '¡Jugador elegido!' : 'Turno pasado', 'success');
        Router.handleRoute();
    } catch (err) {
        showToast(err.message, 'error');
    }
};

