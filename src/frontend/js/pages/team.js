/* Team management page */
Router.register('#/team', async (container) => {
    const teamId = API.getTeamId();
    const team = await API.get(`/teams/${teamId}`);

    // Local state — work in memory, save only on button click
    let starterIds = new Set(team.players.filter(p => p.is_starter).map(p => p.player_id));
    let captainId = team.players.find(p => p.is_captain)?.player_id || '';
    let viceCaptainId = team.players.find(p => p.is_vice_captain)?.player_id || '';
    let formation = team.formation || '4-3-3';

    const FORMATIONS = {
        '4-3-3': {GK:1, DEF:4, MID:3, FWD:3},
        '4-4-2': {GK:1, DEF:4, MID:4, FWD:2},
        '3-5-2': {GK:1, DEF:3, MID:5, FWD:2},
        '3-4-3': {GK:1, DEF:3, MID:4, FWD:3},
        '5-3-2': {GK:1, DEF:5, MID:3, FWD:2},
        '5-4-1': {GK:1, DEF:5, MID:4, FWD:1},
        '4-5-1': {GK:1, DEF:4, MID:5, FWD:1},
    };

    // Build a player map for quick lookup
    const playerMap = {};
    team.players.forEach(p => { playerMap[p.player_id] = p; });

    function getStarters() { return team.players.filter(p => starterIds.has(p.player_id)); }
    function getBench() { return team.players.filter(p => !starterIds.has(p.player_id)); }

    function getPositionCounts() {
        const counts = {GK:0, DEF:0, MID:0, FWD:0};
        starterIds.forEach(id => { const p = playerMap[id]; if (p) counts[p.position]++; });
        return counts;
    }

    function validateFormation() {
        if (starterIds.size !== 11) return `Necesitas 11 titulares (tienes ${starterIds.size})`;
        const counts = getPositionCounts();
        if (counts.GK < 1) return 'Necesitas al menos 1 portero titular';
        return null; // Formation is advisory, not enforced
    }

    function getFormationWarning() {
        if (starterIds.size !== 11) return null;
        const counts = getPositionCounts();
        const req = FORMATIONS[formation];
        const mismatches = [];
        if (counts.GK !== 1) mismatches.push(`GK: ${counts.GK}/1`);
        for (const pos of ['DEF','MID','FWD']) {
            if (counts[pos] !== req[pos]) mismatches.push(`${pos}: ${counts[pos]}/${req[pos]}`);
        }
        return mismatches.length ? `Formación ${formation} sugiere: ${mismatches.join(', ')}` : null;
    }

    const POS_ORDER = {GK:0, DEF:1, MID:2, FWD:3};
    const POS_LABELS = {GK:'Portero', DEF:'Defensa', MID:'Mediocampo', FWD:'Delantera'};

    function renderPlayerChip(p, actions) {
        return `
            <div class="player-chip">
                <img src="${p.photo}" alt="" onerror="this.style.display='none'">
                <div class="player-chip-info">
                    <div class="player-name">
                        ${p.player_id === captainId ? '<span class="chip-badge cap">C</span>' : ''}${p.player_id === viceCaptainId ? '<span class="chip-badge vc">VC</span>' : ''}${p.name}
                    </div>
                    <div class="player-meta">${p.club}</div>
                </div>
                ${posBadge(p.position)}
                <div class="chip-actions">${actions}</div>
            </div>`;
    }

    function renderFormationField(starters) {
        const req = FORMATIONS[formation];
        const byPos = {GK:[], DEF:[], MID:[], FWD:[]};
        starters.forEach(p => byPos[p.position].push(p));

        // Render rows: FWD at top, GK at bottom (like a real pitch view)
        const rows = ['FWD','MID','DEF','GK'];
        return `
            <div class="pitch">
                ${rows.map(pos => {
                    const players = byPos[pos];
                    const needed = pos === 'GK' ? 1 : req[pos];
                    const slots = [];
                    for (let i = 0; i < needed; i++) {
                        if (players[i]) {
                            const p = players[i];
                            slots.push(`
                                <div class="pitch-player filled" title="${p.name} — ${p.club}">
                                    <img src="${p.photo}" alt="" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><rect fill=%22%23374151%22 width=%2240%22 height=%2240%22 rx=%2220%22/><text x=%2220%22 y=%2225%22 text-anchor=%22middle%22 fill=%22%239ca3af%22 font-size=%2214%22>⚽</text></svg>'">
                                    <span class="pitch-name">${p.name.split(' ').pop()}</span>
                                    ${p.player_id === captainId ? '<span class="pitch-badge cap">C</span>' : ''}
                                    ${p.player_id === viceCaptainId ? '<span class="pitch-badge vc">VC</span>' : ''}
                                </div>`);
                        } else {
                            slots.push(`<div class="pitch-player empty"><span class="pitch-name">${pos}</span></div>`);
                        }
                    }
                    // Extra players beyond formation (overflow)
                    for (let i = needed; i < players.length; i++) {
                        const p = players[i];
                        slots.push(`
                            <div class="pitch-player filled overflow" title="${p.name} (extra)">
                                <img src="${p.photo}" alt="" onerror="this.style.display='none'">
                                <span class="pitch-name">${p.name.split(' ').pop()}</span>
                            </div>`);
                    }
                    return `<div class="pitch-row">${slots.join('')}</div>`;
                }).join('')}
            </div>`;
    }

    function render() {
        const starters = getStarters();
        const bench = getBench().sort((a,b) => POS_ORDER[a.position] - POS_ORDER[b.position] || b.market_value - a.market_value);
        const counts = getPositionCounts();
        const req = FORMATIONS[formation];
        const error = starterIds.size === 11 ? validateFormation() : null;

        container.innerHTML = `
            <div class="flex-between mb-2">
                <h2>🏟️ ${team.team_name}</h2>
                <div class="money">${formatMoney(team.budget)}</div>
            </div>
            <div class="grid grid-3 mb-2">
                <div class="card text-center">
                    <div style="font-size:.85rem;color:var(--text-secondary)">Jugadores</div>
                    <div style="font-size:1.5rem;font-weight:700">${team.players.length}/23</div>
                </div>
                <div class="card text-center">
                    <div style="font-size:.85rem;color:var(--text-secondary)">Formación</div>
                    <select id="formation-select" style="font-size:1.2rem;font-weight:700;text-align:center">
                        ${Object.keys(FORMATIONS).map(f =>
                            `<option value="${f}" ${f === formation ? 'selected' : ''}>${f}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="card text-center">
                    <div style="font-size:.85rem;color:var(--text-secondary)">Valor total</div>
                    <div class="player-value" style="font-size:1.2rem">${formatMoney(team.players.reduce((s,p) => s + p.market_value, 0))}</div>
                </div>
            </div>

            <!-- Tactical field view -->
            <div class="card mb-2">
                <div class="flex-between mb-1">
                    <div class="card-header" style="margin:0">Alineación táctica</div>
                    <div style="font-size:.8rem;color:var(--text-muted)">
                        GK: ${counts.GK}/1 · DEF: ${counts.DEF}/${req.DEF} · MID: ${counts.MID}/${req.MID} · FWD: ${counts.FWD}/${req.FWD}
                    </div>
                </div>
                ${error ? `<div style="color:var(--accent-red);font-size:.85rem;margin-bottom:.5rem">⚠️ ${error}</div>` : ''}
                ${!error && getFormationWarning() ? `<div style="color:var(--accent-gold);font-size:.8rem;margin-bottom:.5rem">💡 ${getFormationWarning()}</div>` : ''}
                ${renderFormationField(starters)}
            </div>

            <div class="grid grid-2">
                <!-- Starter list with actions -->
                <div class="card">
                    <div class="card-header">Titulares (${starterIds.size}/11)</div>
                    ${starters.length === 0 ? '<p style="color:var(--text-muted)">Usa ↑ del banquillo para añadir titulares</p>' : ''}
                    ${['GK','DEF','MID','FWD'].map(pos => {
                        const posPlayers = starters.filter(p => p.position === pos);
                        if (!posPlayers.length) return '';
                        return `
                            <div class="pos-section"><small>${POS_LABELS[pos]}</small></div>
                            ${posPlayers.map(p => renderPlayerChip(p, `
                                <button class="btn btn-sm btn-outline bench-btn" data-pid="${p.player_id}" title="Al banquillo">↓</button>
                                <button class="btn btn-sm ${p.player_id === captainId ? 'btn-gold' : 'btn-outline'} cap-btn" data-pid="${p.player_id}" title="Capitán">C</button>
                                <button class="btn btn-sm ${p.player_id === viceCaptainId ? 'btn-primary' : 'btn-outline'} vc-btn" data-pid="${p.player_id}" title="Vice-capitán" style="font-size:.7rem">VC</button>
                            `)).join('')}
                        `;
                    }).join('')}
                </div>

                <!-- Bench sorted by position -->
                <div class="card">
                    <div class="card-header">Banquillo (${bench.length})</div>
                    ${['GK','DEF','MID','FWD'].map(pos => {
                        const posPlayers = bench.filter(p => p.position === pos);
                        if (!posPlayers.length) return '';
                        return `
                            <div class="pos-section"><small>${POS_LABELS[pos]}</small></div>
                            ${posPlayers.map(p => renderPlayerChip(p, `
                                <button class="btn btn-sm btn-primary start-btn" data-pid="${p.player_id}" title="Titular">↑</button>
                            `)).join('')}
                        `;
                    }).join('')}
                </div>
            </div>

            <div class="mt-2 text-center flex" style="justify-content:center;gap:1rem">
                <button class="btn btn-gold" id="btn-save-lineup" ${error ? 'disabled' : ''}>
                    💾 Guardar alineación
                </button>
                ${starterIds.size !== 11 ? `<span style="color:var(--text-muted);font-size:.85rem">Selecciona ${11 - starterIds.size} titular(es) más</span>` : ''}
            </div>
        `;

        // --- Bind events (all work on local state, no server call) ---

        container.querySelectorAll('.bench-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                starterIds.delete(btn.dataset.pid);
                if (captainId === btn.dataset.pid) captainId = '';
                if (viceCaptainId === btn.dataset.pid) viceCaptainId = '';
                render();
            });
        });

        container.querySelectorAll('.start-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                starterIds.add(btn.dataset.pid);
                render();
            });
        });

        container.querySelectorAll('.cap-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                captainId = btn.dataset.pid;
                if (viceCaptainId === captainId) viceCaptainId = '';
                render();
            });
        });

        container.querySelectorAll('.vc-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                viceCaptainId = btn.dataset.pid;
                if (captainId === viceCaptainId) captainId = '';
                render();
            });
        });

        document.getElementById('formation-select')?.addEventListener('change', (e) => {
            formation = e.target.value;
            render();
        });

        document.getElementById('btn-save-lineup')?.addEventListener('click', async () => {
            const starterList = [...starterIds];
            const payload = { formation };
            if (starterList.length === 11) payload.starters = starterList;
            if (captainId) payload.captain = captainId;
            if (viceCaptainId) payload.vice_captain = viceCaptainId;
            try {
                await API.patch(`/teams/${teamId}/lineup`, payload);
                showToast('✅ Alineación guardada', 'success');
            } catch (err) { showToast(err.message, 'error'); }
        });
    }

    render();
});
