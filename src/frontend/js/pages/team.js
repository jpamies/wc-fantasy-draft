/* Team management page */
Router.register('#/team', async (container) => {
    const teamId = API.getTeamId();
    const team = await API.get(`/teams/${teamId}`);

    // Local state
    let starterIds = new Set(team.players.filter(p => p.is_starter).map(p => p.player_id));
    let captainId = team.players.find(p => p.is_captain)?.player_id || '';
    let viceCaptainId = team.players.find(p => p.is_vice_captain)?.player_id || '';

    // Position limits: {min, max}
    const POS_LIMITS = {GK: {min:1, max:1}, DEF: {min:3, max:5}, MID: {min:2, max:5}, FWD: {min:1, max:3}};
    const POS_ORDER = {GK:0, DEF:1, MID:2, FWD:3};
    const POS_LABELS = {GK:'Portero', DEF:'Defensa', MID:'Mediocampo', FWD:'Delantera'};

    const playerMap = {};
    team.players.forEach(p => { playerMap[p.player_id] = p; });

    function getStarters() { return team.players.filter(p => starterIds.has(p.player_id)); }
    function getBench() { return team.players.filter(p => !starterIds.has(p.player_id)); }

    function getPositionCounts() {
        const counts = {GK:0, DEF:0, MID:0, FWD:0};
        starterIds.forEach(id => { const p = playerMap[id]; if (p) counts[p.position]++; });
        return counts;
    }

    function getDetectedFormation() {
        const c = getPositionCounts();
        return `${c.DEF}-${c.MID}-${c.FWD}`;
    }

    function canAddPosition(pos) {
        if (starterIds.size >= 11) return false;
        const counts = getPositionCounts();
        return counts[pos] < POS_LIMITS[pos].max;
    }

    function getBlockReason(pos) {
        if (starterIds.size >= 11) return 'Ya tienes 11 titulares';
        const counts = getPositionCounts();
        if (counts[pos] >= POS_LIMITS[pos].max) return `Máx ${POS_LIMITS[pos].max} ${POS_LABELS[pos]}`;
        return '';
    }

    function validateLineup() {
        const counts = getPositionCounts();
        const warnings = [];
        if (starterIds.size < 11) warnings.push(`${starterIds.size}/11 titulares`);
        for (const [pos, lim] of Object.entries(POS_LIMITS)) {
            if (counts[pos] < lim.min && starterIds.size === 11) warnings.push(`Mín ${lim.min} ${POS_LABELS[pos]}`);
            if (counts[pos] > lim.max) warnings.push(`Máx ${lim.max} ${POS_LABELS[pos]}`);
        }
        return warnings.length ? warnings.join(' · ') : null;
    }

    function renderPlayerChip(p, actions) {
        const pts = p.total_points || 0;
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
                <span style="font-weight:700;color:var(--accent-teal);min-width:30px;text-align:right;font-size:.9rem" title="Puntos acumulados">${pts > 0 ? pts : ''}</span>
                <div class="chip-actions">${actions}</div>
            </div>`;
    }

    function renderPitch(starters) {
        const byPos = {GK:[], DEF:[], MID:[], FWD:[]};
        starters.forEach(p => byPos[p.position].push(p));
        const rows = ['FWD','MID','DEF','GK'];

        return `
            <div class="pitch">
                ${rows.map(pos => {
                    const players = byPos[pos];
                    if (!players.length && pos !== 'GK') return '';
                    return `<div class="pitch-row">
                        ${players.map(p => `
                            <div class="pitch-player filled" title="${p.name} — ${p.club}">
                                <img src="${p.photo}" alt="" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><rect fill=%22%23374151%22 width=%2240%22 height=%2240%22 rx=%2220%22/><text x=%2220%22 y=%2225%22 text-anchor=%22middle%22 fill=%22%239ca3af%22 font-size=%2214%22>⚽</text></svg>'">
                                <span class="pitch-name">${p.name.split(' ').pop()}</span>
                                ${p.player_id === captainId ? '<span class="pitch-badge cap">C</span>' : ''}
                                ${p.player_id === viceCaptainId ? '<span class="pitch-badge vc">VC</span>' : ''}
                            </div>
                        `).join('')}
                        ${players.length === 0 ? `<div class="pitch-player empty"><span class="pitch-name">${pos}</span></div>` : ''}
                    </div>`;
                }).join('')}
            </div>`;
    }

    function render() {
        const starters = getStarters();
        const bench = getBench().sort((a,b) => POS_ORDER[a.position] - POS_ORDER[b.position] || b.market_value - a.market_value);
        const counts = getPositionCounts();
        const error = validateLineup();
        const detected = getDetectedFormation();

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
                    <div style="font-size:1.5rem;font-weight:700;color:var(--accent-gold)">${starterIds.size === 11 ? detected : '—'}</div>
                </div>
                <div class="card text-center">
                    <div style="font-size:.85rem;color:var(--text-secondary)">Valor total</div>
                    <div class="player-value" style="font-size:1.2rem">${formatMoney(team.players.reduce((s,p) => s + p.market_value, 0))}</div>
                </div>
            </div>

            <!-- Tactical field -->
            <div class="card mb-2">
                <div class="flex-between mb-1">
                    <div class="card-header" style="margin:0">Alineación táctica</div>
                    <div style="font-size:.8rem;color:var(--text-muted)">
                        ${Object.entries(POS_LIMITS).map(([pos, lim]) => {
                            const c = counts[pos];
                            const ok = c >= lim.min && c <= lim.max;
                            const color = c === 0 ? 'var(--text-muted)' : ok ? 'var(--accent-green)' : 'var(--accent-red)';
                            return `<span style="color:${color}">${pos}: ${c}</span><span style="color:var(--text-muted)"> (${lim.min}-${lim.max})</span>`;
                        }).join(' · ')}
                    </div>
                </div>
                ${error && starterIds.size === 11 ? `<div style="color:var(--accent-red);font-size:.85rem;margin-bottom:.5rem">⚠️ ${error}</div>` : ''}
                ${error && starterIds.size < 11 ? `<div style="color:var(--accent-gold);font-size:.85rem;margin-bottom:.5rem">💡 ${error}</div>` : ''}
                ${renderPitch(starters)}
            </div>

            <div class="grid grid-2">
                <div class="card">
                    <div class="card-header">Titulares (${starterIds.size}/11)</div>
                    ${starters.length === 0 ? '<p style="color:var(--text-muted)">Usa ↑ del banquillo para añadir titulares</p>' : ''}
                    ${['GK','DEF','MID','FWD'].map(pos => {
                        const posPlayers = starters.filter(p => p.position === pos);
                        if (!posPlayers.length) return '';
                        return `
                            <div class="pos-section"><small>${POS_LABELS[pos]} (${posPlayers.length})</small></div>
                            ${posPlayers.map(p => renderPlayerChip(p, `
                                <button class="btn btn-sm btn-outline bench-btn" data-pid="${p.player_id}" title="Al banquillo">↓</button>
                                <button class="btn btn-sm ${p.player_id === captainId ? 'btn-gold' : 'btn-outline'} cap-btn" data-pid="${p.player_id}" title="Capitán">C</button>
                                <button class="btn btn-sm ${p.player_id === viceCaptainId ? 'btn-primary' : 'btn-outline'} vc-btn" data-pid="${p.player_id}" title="Vice-capitán" style="font-size:.7rem">VC</button>
                            `)).join('')}
                        `;
                    }).join('')}
                </div>

                <div class="card">
                    <div class="card-header">Banquillo (${bench.length})</div>
                    ${['GK','DEF','MID','FWD'].map(pos => {
                        const posPlayers = bench.filter(p => p.position === pos);
                        if (!posPlayers.length) return '';
                        const allowed = canAddPosition(pos);
                        const reason = getBlockReason(pos);
                        return `
                            <div class="pos-section"><small>${POS_LABELS[pos]}</small></div>
                            ${posPlayers.map(p => renderPlayerChip(p, `
                                <button class="btn btn-sm ${allowed ? 'btn-primary' : 'btn-outline'} start-btn" data-pid="${p.player_id}" title="${reason || 'Titular'}" ${allowed ? '' : 'disabled'}>↑</button>
                            `)).join('')}
                        `;
                    }).join('')}
                </div>
            </div>

            <div class="mt-2 text-center flex" style="justify-content:center;gap:1rem">
                <button class="btn btn-gold" id="btn-save-lineup">
                    💾 Guardar alineación
                </button>
                ${starterIds.size < 11 ? `<span style="color:var(--accent-gold);font-size:.85rem">⚡ ${11 - starterIds.size} huecos — menos puntos en jornada</span>` : ''}
            </div>
        `;

        // Bind events
        container.querySelectorAll('.bench-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                starterIds.delete(btn.dataset.pid);
                if (captainId === btn.dataset.pid) captainId = '';
                if (viceCaptainId === btn.dataset.pid) viceCaptainId = '';
                render();
            });
        });
        container.querySelectorAll('.start-btn').forEach(btn => {
            btn.addEventListener('click', () => { starterIds.add(btn.dataset.pid); render(); });
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
        document.getElementById('btn-save-lineup')?.addEventListener('click', async () => {
            const starterList = [...starterIds];
            const payload = { formation: getDetectedFormation() };
            payload.starters = starterList;
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
