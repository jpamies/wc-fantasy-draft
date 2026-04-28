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
        const team = await API.get(`/teams/${teamId}`);

        // Squad composition limits (mirror backend draft rules)
        const SQUAD_LIMITS = { GK: { min: 2, max: 3 }, DEF: { min: 5, max: 8 }, MID: { min: 5, max: 8 }, FWD: { min: 5, max: 8 } };
        const SQUAD_MAX = 23;
        const counts = { GK: 0, DEF: 0, MID: 0, FWD: 0 };
        (team.players || []).forEach(p => { if (counts[p.position] !== undefined) counts[p.position] += 1; });
        const total = counts.GK + counts.DEF + counts.MID + counts.FWD;
        // Expose to renderAvailablePlayers + buyPlayer for client-side validation
        window._marketSquadCounts = counts;
        window._marketSquadTotal = total;
        window._marketSquadLimits = SQUAD_LIMITS;
        window._marketSquadMax = SQUAD_MAX;

        const positionPill = (pos) => {
            const c = counts[pos];
            const lim = SQUAD_LIMITS[pos];
            const full = c >= lim.max;
            const low = c < lim.min;
            const color = full ? 'var(--danger)' : (low ? 'var(--accent-gold)' : 'var(--accent-teal)');
            return `<span style="display:inline-flex;align-items:center;gap:.25rem;padding:.2rem .5rem;border-radius:6px;background:var(--bg-secondary);font-size:.8rem">
                <strong>${pos}</strong>
                <span style="color:${color};font-weight:600">${c}/${lim.max}</span>
            </span>`;
        };

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

            <div class="card mb-2" style="padding:.75rem">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem">
                    <div style="font-weight:600">
                        👥 Plantilla: <span style="color:${total >= SQUAD_MAX ? 'var(--danger)' : 'var(--accent-teal)'}">${total}/${SQUAD_MAX}</span>
                    </div>
                    <div style="display:flex;gap:.4rem;flex-wrap:wrap">
                        ${positionPill('GK')}
                        ${positionPill('DEF')}
                        ${positionPill('MID')}
                        ${positionPill('FWD')}
                    </div>
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
    // Backend returns country_flag as either an http(s) URL (flagcdn.com)
    // or an empty string. Render <img> when URL, fall back to emoji otherwise.
    const f = player.country_flag;
    if (f && /^https?:\/\//i.test(f)) {
        return `<img src="${f}" alt="${player.country_code || ''}" referrerpolicy="no-referrer" style="width:24px;height:auto;border-radius:2px;display:inline-block;vertical-align:middle">`;
    }
    if (f) return `<span style="font-size:1.4rem;line-height:1">${f}</span>`;
    const iso2 = ISO3_TO_ISO2[player.country_code];
    if (!iso2 || iso2.length !== 2) return '';
    const A = 0x1F1E6;
    const emoji = String.fromCodePoint(A + iso2.charCodeAt(0) - 65, A + iso2.charCodeAt(1) - 65);
    return `<span style="font-size:1.4rem;line-height:1">${emoji}</span>`;
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

        // Group players by position. Order: GK, DEF, MID, FWD.
        const POSITION_ORDER = [
            { key: 'GK',  label: 'Porteros',        icon: '🧤' },
            { key: 'DEF', label: 'Defensas',        icon: '🛡️' },
            { key: 'MID', label: 'Centrocampistas', icon: '⚙️' },
            { key: 'FWD', label: 'Delanteros',      icon: '⚽' },
        ];

        const byPosition = {};
        for (const p of team.players) {
            const k = p.position || 'MID';
            (byPosition[k] = byPosition[k] || []).push(p);
        }
        // Within each position: starters first, then by market_value desc
        for (const k of Object.keys(byPosition)) {
            byPosition[k].sort((a, b) => {
                if (a.is_starter !== b.is_starter) return b.is_starter - a.is_starter;
                return (b.market_value || 0) - (a.market_value || 0);
            });
        }

        const clauseFor = (pid) => clauses.find(c => c.player_id === pid);

        const cardHtml = (p) => {
            const c = clauseFor(p.player_id);
            const amount = c?.clause_amount || 0;
            const blocked = !!c?.is_blocked;
            const flag = flagFor(p);
            const points = p.total_points ?? 0;
            const alive = p.is_alive !== false; // default true if backend hasn't shipped yet
            const aliveDot = alive
                ? `<span title="Sigue en el torneo" aria-label="alive" style="display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--accent-teal,#22c55e);box-shadow:0 0 4px var(--accent-teal,#22c55e);margin-right:.3rem;vertical-align:middle"></span>`
                : `<span title="Eliminado del torneo" aria-label="eliminated" style="display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--text-muted,#777);margin-right:.3rem;vertical-align:middle"></span>`;
            const eliminatedTag = !alive
                ? ` <span style="color:var(--text-muted);font-size:.65rem;font-style:italic" title="Su selección está eliminada">· eliminado</span>`
                : '';
            const cardOpacity = alive ? '' : 'opacity:.75;';
            return `
            <div class="card clause-card" data-pid="${p.player_id}" data-pos="${p.position}" data-amount="${amount}" data-blocked="${blocked ? '1' : '0'}"
                style="padding:.75rem;display:flex;flex-direction:column;gap:.5rem;${cardOpacity}">
                <div style="display:flex;align-items:center;gap:.5rem">
                    <div style="flex:0 0 auto;position:relative">${flag}</div>
                    <div style="flex:1;min-width:0">
                        <div style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${p.name}">${aliveDot}${p.name}</div>
                        <div style="font-size:.7rem;color:var(--text-muted)">${p.country_code} · ${p.club || ''}${eliminatedTag}</div>
                    </div>
                    <span class="badge ${positionBadgeClass(p.position)} badge-small">${p.position}</span>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;font-size:.8rem;flex-wrap:wrap;gap:.4rem">
                    <span style="color:var(--text-muted)">Valor: ${formatMoney(p.market_value || 0)}</span>
                    <span style="color:var(--accent-teal);font-weight:600">⭐ ${points} pts</span>
                    <label class="lock-toggle" style="display:flex;align-items:center;gap:.25rem;cursor:pointer">
                        <input type="checkbox" class="blocked-checkbox" data-pid="${p.player_id}" ${blocked ? 'checked' : ''}>
                        <span>🔒 Bloqueo</span>
                    </label>
                </div>
                <div class="clause-presets" data-pid="${p.player_id}" style="display:flex;flex-wrap:wrap;gap:.25rem;${blocked ? 'opacity:.4;pointer-events:none' : ''}">
                    ${CLAUSE_PRESETS.map(preset => `
                        <button type="button" class="btn btn-sm preset-btn ${(!blocked && preset.v === amount) ? 'btn-primary' : 'btn-outline'}"
                            data-pid="${p.player_id}" data-value="${preset.v}"
                            ${blocked ? 'disabled' : ''}
                            style="flex:1;min-width:48px;padding:.3rem .25rem;font-size:.75rem">
                            ${preset.label}
                        </button>
                    `).join('')}
                </div>
            </div>`;
        };

        const groupHtml = (g) => {
            const list = byPosition[g.key] || [];
            if (!list.length) return '';
            // Compute group totals (initial render, refreshed by recalc())
            const groupTotal = list.reduce((s, p) => s + (clauseFor(p.player_id)?.clause_amount || 0), 0);
            const groupBlocked = list.filter(p => clauseFor(p.player_id)?.is_blocked).length;
            return `
                <details class="clause-group" data-pos="${g.key}" open style="margin-bottom:.75rem;border:1px solid var(--border);border-radius:6px">
                    <summary style="cursor:pointer;padding:.6rem .75rem;display:flex;justify-content:space-between;align-items:center;background:var(--bg-secondary);border-radius:6px;list-style:none">
                        <span style="font-weight:600">${g.icon} ${g.label} <span style="color:var(--text-muted);font-weight:400">(${list.length})</span></span>
                        <span style="font-size:.85rem;color:var(--text-muted)">
                            <span class="group-total" data-pos="${g.key}">${formatMoney(groupTotal)}</span>
                            · 🔒 <span class="group-blocked" data-pos="${g.key}">${groupBlocked}</span>
                        </span>
                    </summary>
                    <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:.75rem;padding:.75rem">
                        ${list.map(cardHtml).join('')}
                    </div>
                </details>
            `;
        };

        form.innerHTML = `
            <div id="clauses-summary" style="position:sticky;top:0;z-index:5;margin-bottom:1rem;padding:.75rem;background:var(--bg-secondary);border-radius:6px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:.5rem">
                <div><strong>Total asignado:</strong> <span id="clauses-total">0</span> / ${formatMoney(protectBudget)}</div>
                <div><strong>Bloqueados:</strong> <span id="clauses-blocked">0</span> / ${MAX_BLOCKED}</div>
                <div><strong>Restante:</strong> <span id="clauses-remaining">${formatMoney(protectBudget)}</span></div>
            </div>
            ${POSITION_ORDER.map(groupHtml).join('')}
        `;

        const recalc = () => {
            let total = 0;
            let blockedCount = 0;
            const groupTotals = { GK: 0, DEF: 0, MID: 0, FWD: 0 };
            const groupBlocked = { GK: 0, DEF: 0, MID: 0, FWD: 0 };
            document.querySelectorAll('.clause-card').forEach(card => {
                const blk = card.dataset.blocked === '1';
                // Blocked players don't consume the protect_budget.
                const amt = blk ? 0 : parseInt(card.dataset.amount || '0', 10);
                total += amt;
                if (blk) blockedCount += 1;
                const pos = card.dataset.pos;
                if (pos in groupTotals) {
                    groupTotals[pos] += amt;
                    if (blk) groupBlocked[pos] += 1;
                }
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
            // Update group summaries
            document.querySelectorAll('.group-total').forEach(el => {
                el.textContent = formatMoney(groupTotals[el.dataset.pos] || 0);
            });
            document.querySelectorAll('.group-blocked').forEach(el => {
                el.textContent = groupBlocked[el.dataset.pos] || 0;
            });
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
                // When blocked: clear amount, deselect/disable preset buttons.
                // When unblocked: re-enable preset buttons (amount stays at 0).
                const presets = form.querySelector(`.clause-presets[data-pid="${pid}"]`);
                if (cb.checked) {
                    card.dataset.amount = '0';
                    if (presets) {
                        presets.style.opacity = '.4';
                        presets.style.pointerEvents = 'none';
                    }
                    form.querySelectorAll(`.preset-btn[data-pid="${pid}"]`).forEach(b => {
                        b.disabled = true;
                        b.classList.remove('btn-primary');
                        b.classList.add('btn-outline');
                    });
                } else {
                    if (presets) {
                        presets.style.opacity = '';
                        presets.style.pointerEvents = '';
                    }
                    form.querySelectorAll(`.preset-btn[data-pid="${pid}"]`).forEach(b => {
                        b.disabled = false;
                    });
                }
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
                // Reload to reflect any normalization (blocked → amount=0)
                const fresh = await API.get(`/teams/${teamId}/market/${windowId}/clauses`);
                await loadClauseForm(leagueId, teamId, windowId, fresh, win);
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
    const counts = window._marketSquadCounts || { GK: 0, DEF: 0, MID: 0, FWD: 0 };
    const total = window._marketSquadTotal ?? 0;
    const limits = window._marketSquadLimits || { GK: { max: 3 }, DEF: { max: 8 }, MID: { max: 8 }, FWD: { max: 8 } };
    const SQUAD_MAX = window._marketSquadMax ?? 23;

    container.innerHTML = players.map(p => {
        const isOwn = p.current_team_id === teamId;
        const squadFull = total >= SQUAD_MAX;
        const positionFull = (counts[p.position] || 0) >= (limits[p.position]?.max ?? 99);
        const blocked = !!p.is_blocked;
        let label = 'Comprar';
        let title = '';
        if (isOwn) { label = 'Tuyo'; }
        else if (blocked) { label = '🔒 Bloqueado'; title = 'El propietario lo ha bloqueado'; }
        else if (squadFull) { label = '🚫 Plantilla llena'; title = `Tienes ${total}/${SQUAD_MAX}`; }
        else if (positionFull) { label = `🚫 ${p.position} al máximo`; title = `${counts[p.position]}/${limits[p.position].max} en ${p.position}`; }
        const disabled = isOwn || blocked || squadFull || positionFull;
        return `
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
                ${disabled ? 'disabled' : ''} ${title ? `title="${title}"` : ''}
                onclick="window.buyPlayer('${leagueId}', '${teamId}', '${windowId}', this)">
                ${label}
            </button>
        </div>`;
    }).join('');
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

