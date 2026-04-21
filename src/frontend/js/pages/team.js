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
        const req = FORMATIONS[formation];
        if (counts.GK !== 1) return 'Necesitas exactamente 1 portero titular';
        for (const pos of ['DEF','MID','FWD']) {
            if (counts[pos] !== req[pos]) return `${formation} requiere ${req[pos]} ${pos}, tienes ${counts[pos]}`;
        }
        return null;
    }

    function render() {
        const starters = getStarters();
        const bench = getBench();
        const counts = getPositionCounts();
        const req = FORMATIONS[formation];
        const error = starterIds.size === 11 ? validateFormation() : null;
        const isDirty = true; // always show save button

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

            <div class="grid grid-2">
                <div class="card">
                    <div class="card-header">Titulares (${starterIds.size}/11)</div>
                    <div style="font-size:.8rem;color:var(--text-muted);margin-bottom:.5rem">
                        GK: ${counts.GK}/${1} · DEF: ${counts.DEF}/${req.DEF} · MID: ${counts.MID}/${req.MID} · FWD: ${counts.FWD}/${req.FWD}
                    </div>
                    ${error ? `<div style="color:var(--accent-red);font-size:.85rem;margin-bottom:.5rem">⚠️ ${error}</div>` : ''}
                    ${starters.length === 0 ? '<p style="color:var(--text-muted)">Usa las flechas ↑ del banquillo para añadir titulares</p>' : ''}
                    ${['GK','DEF','MID','FWD'].map(pos => {
                        const posPlayers = starters.filter(p => p.position === pos);
                        if (!posPlayers.length) return '';
                        return `
                            <div class="mb-1"><small style="color:var(--text-muted)">${pos}</small></div>
                            ${posPlayers.map(p => `
                                <div class="player-card">
                                    <img src="${p.photo}" alt="" onerror="this.style.display='none'">
                                    <div class="player-info">
                                        <div class="player-name">
                                            ${p.player_id === captainId ? '🅲 ' : ''}${p.player_id === viceCaptainId ? 'VC ' : ''}${p.name}
                                        </div>
                                        <div class="player-meta">${p.club} · ${p.country_code}</div>
                                    </div>
                                    ${posBadge(p.position)}
                                    <button class="btn btn-sm btn-outline bench-btn" data-pid="${p.player_id}" title="Al banquillo">↓</button>
                                    <button class="btn btn-sm ${p.player_id === captainId ? 'btn-gold' : 'btn-outline'} cap-btn" data-pid="${p.player_id}" title="Capitán">C</button>
                                    <button class="btn btn-sm ${p.player_id === viceCaptainId ? 'btn-primary' : 'btn-outline'} vc-btn" data-pid="${p.player_id}" title="Vice-capitán" style="font-size:.7rem">VC</button>
                                </div>
                            `).join('')}
                        `;
                    }).join('')}
                </div>
                <div class="card">
                    <div class="card-header">Banquillo (${bench.length})</div>
                    ${bench.map(p => `
                        <div class="player-card">
                            <img src="${p.photo}" alt="" onerror="this.style.display='none'">
                            <div class="player-info">
                                <div class="player-name">${p.name}</div>
                                <div class="player-meta">${p.club} · ${p.country_code}</div>
                            </div>
                            ${posBadge(p.position)}
                            <button class="btn btn-sm btn-primary start-btn" data-pid="${p.player_id}" title="Titular">↑</button>
                        </div>
                    `).join('')}
                </div>
            </div>

            <div class="mt-2 text-center flex" style="justify-content:center;gap:1rem">
                <button class="btn btn-gold" id="btn-save-lineup" ${error && starterIds.size === 11 ? 'disabled' : ''}>
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
