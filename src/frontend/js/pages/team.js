/* Team management page — per-matchday lineups */
Router.register('#/team', async (container) => {
    const teamId = API.getTeamId();
    const team = await API.get(`/teams/${teamId}`);

    // Get matchdays to show tabs
    let matchdays = [];
    try {
        const allMd = await API.get('/scoring/matchdays');
        // Show: active + upcoming first, then last completed as fallback
        const active = allMd.filter(md => md.status === 'active' || md.status === 'upcoming');
        const completed = allMd.filter(md => md.status === 'completed');
        if (active.length > 0) {
            matchdays = active.slice(0, 3);
        } else if (completed.length > 0) {
            // All completed — show last 2 so user can review
            matchdays = completed.slice(-2);
        }
        // If nothing, show all available
        if (matchdays.length === 0 && allMd.length > 0) {
            matchdays = allMd.slice(0, 3);
        }
    } catch {}

    const POS_LIMITS = {GK: {min:1, max:1}, DEF: {min:3, max:5}, MID: {min:2, max:5}, FWD: {min:1, max:3}};
    const POS_ORDER = {GK:0, DEF:1, MID:2, FWD:3};
    const POS_LABELS = {GK:'Portero', DEF:'Defensa', MID:'Mediocampo', FWD:'Delantera'};

    // Show team header
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
                <div style="font-size:.85rem;color:var(--text-secondary)">Puntos totales</div>
                <div style="font-size:1.5rem;font-weight:700;color:var(--accent-teal)">${team.players.reduce((s,p) => s + (p.total_points || 0), 0)}</div>
            </div>
            <div class="card text-center">
                <div style="font-size:.85rem;color:var(--text-secondary)">Valor total</div>
                <div class="player-value" style="font-size:1.2rem">${formatMoney(team.players.reduce((s,p) => s + p.market_value, 0))}</div>
            </div>
        </div>
        ${matchdays.length > 0 ? `
        <div class="flex mb-2" style="gap:.5rem;border-bottom:2px solid var(--border);padding-bottom:.5rem">
            ${matchdays.map((md, i) => `
                <button class="btn ${i === 0 ? 'btn-gold' : 'btn-outline'} md-tab" data-mdid="${md.id}" style="font-size:.85rem">
                    ${md.name.length > 20 ? md.name.substring(0, 20) + '…' : md.name}
                    <span class="badge ${md.status === 'completed' ? 'badge-teal' : 'badge-gold'}" style="font-size:.7rem;margin-left:.3rem">${md.status === 'upcoming' ? '📋' : md.status === 'active' ? '🔴' : '✅'}</span>
                </button>
            `).join('')}
        </div>
        <div id="matchday-lineup-area"></div>
        ` : `
        <div class="card text-center" style="color:var(--text-muted)">
            <p>No hay jornadas disponibles. La alineación por jornada estará disponible cuando se creen jornadas.</p>
        </div>
        <div id="matchday-lineup-area"></div>
        `}
    `;

    async function loadMatchdayLineup(mdId) {
        const area = document.getElementById('matchday-lineup-area');
        if (!area) return;

        // Highlight active tab
        container.querySelectorAll('.md-tab').forEach(btn => {
            btn.className = btn.dataset.mdid === mdId ? 'btn btn-gold md-tab' : 'btn btn-outline md-tab';
        });

        let lineup;
        try {
            lineup = await API.get(`/teams/${teamId}/matchday-lineup/${mdId}`);
        } catch {
            area.innerHTML = '<div class="card text-center"><p style="color:var(--text-muted)">Error cargando alineación</p></div>';
            return;
        }

        let starterIds = new Set(lineup.players.filter(p => p.is_starter).map(p => p.player_id));
        let captainId = lineup.players.find(p => p.is_captain)?.player_id || '';
        let viceCaptainId = lineup.players.find(p => p.is_vice_captain)?.player_id || '';

        const playerMap = {};
        lineup.players.forEach(p => { playerMap[p.player_id] = p; });

        function getStarters() { return lineup.players.filter(p => starterIds.has(p.player_id)); }
        function getBench() { return lineup.players.filter(p => !starterIds.has(p.player_id)); }
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
            return getPositionCounts()[pos] < POS_LIMITS[pos].max;
        }

        function validateGK() {
            return getPositionCounts().GK >= 1;
        }

        function renderChip(p, actions) {
            const pts = p.total_points || 0;
            const locked = p.locked;
            return `
                <div class="player-chip" style="${locked ? 'opacity:.7;' : ''}">
                    <img src="${p.photo}" alt="" referrerpolicy="no-referrer" onerror="this.style.display='none'">
                    <div class="player-chip-info">
                        <div class="player-name">
                            ${p.player_id === captainId ? '<span class="chip-badge cap">C</span>' : ''}
                            ${p.player_id === viceCaptainId ? '<span class="chip-badge vc">VC</span>' : ''}
                            ${p.name} ${locked ? '🔒' : ''}
                        </div>
                        <div class="player-meta">${p.country_code} · ${p.club}</div>
                    </div>
                    ${posBadge(p.position)}
                    <span style="font-weight:700;color:var(--accent-teal);min-width:30px;text-align:right;font-size:.9rem">${pts > 0 ? pts : ''}</span>
                    <div class="chip-actions">${actions}</div>
                </div>`;
        }

        function render() {
            const starters = getStarters();
            const bench = getBench().sort((a,b) => POS_ORDER[a.position] - POS_ORDER[b.position]);
            const counts = getPositionCounts();

            area.innerHTML = `
                <div class="card mb-2">
                    <div class="flex-between mb-1">
                        <div class="card-header" style="margin:0">Formación: ${starterIds.size === 11 ? getDetectedFormation() : '—'}</div>
                        <div style="font-size:.8rem;color:var(--text-muted)">
                            ${Object.entries(POS_LIMITS).map(([pos, lim]) => {
                                const c = counts[pos];
                                const color = c === 0 ? 'var(--text-muted)' : (c >= lim.min && c <= lim.max) ? 'var(--accent-green)' : 'var(--accent-red)';
                                return `<span style="color:${color}">${pos}:${c}</span>`;
                            }).join(' ')}
                        </div>
                    </div>
                </div>

                ${starterIds.size > 0 && !validateGK() ? '<div style="color:var(--accent-red);font-size:.85rem;margin-bottom:.5rem;text-align:center">⚠️ Necesitas al menos 1 portero (GK) titular</div>' : ''}

                <div class="grid grid-2">
                    <div class="card">
                        <div class="card-header">Titulares (${starterIds.size}/11)</div>
                        ${['GK','DEF','MID','FWD'].map(pos => {
                            const posPlayers = starters.filter(p => p.position === pos);
                            if (!posPlayers.length) return '';
                            return `
                                <div class="pos-section"><small>${POS_LABELS[pos]} (${posPlayers.length})</small></div>
                                ${posPlayers.map(p => renderChip(p, `
                                    <button class="btn btn-sm btn-outline bench-btn" data-pid="${p.player_id}" title="Al banquillo">↓</button>
                                    <button class="btn btn-sm ${p.player_id === captainId ? 'btn-gold' : 'btn-outline'} cap-btn" data-pid="${p.player_id}" title="Capitán"${p.locked ? ' disabled' : ''}>C</button>
                                    <button class="btn btn-sm ${p.player_id === viceCaptainId ? 'btn-primary' : 'btn-outline'} vc-btn" data-pid="${p.player_id}" title="Vice" style="font-size:.7rem"${p.locked ? ' disabled' : ''}>VC</button>
                                `)).join('')}
                            `;
                        }).join('')}
                    </div>
                    <div class="card">
                        <div class="card-header">Banquillo (${bench.length})</div>
                        ${['GK','DEF','MID','FWD'].map(pos => {
                            const posPlayers = bench.filter(p => p.position === pos);
                            if (!posPlayers.length) return '';
                            return `
                                <div class="pos-section"><small>${POS_LABELS[pos]}</small></div>
                                ${posPlayers.map(p => {
                                    const canPromote = canAddPosition(pos) && !p.locked;
                                    return renderChip(p, `
                                        <button class="btn btn-sm ${canPromote ? 'btn-primary' : 'btn-outline'} start-btn" data-pid="${p.player_id}"
                                            ${canPromote ? '' : 'disabled'}
                                            title="${p.locked ? 'Partido ya empezado' : !canAddPosition(pos) ? 'Posición llena' : 'Titular'}">
                                            ${p.locked ? '🔒' : '↑'}
                                        </button>
                                    `);
                                }).join('')}
                            `;
                        }).join('')}
                    </div>
                </div>

                <div class="mt-2 text-center">
                    <button class="btn btn-gold" id="btn-save-md-lineup">💾 Guardar alineación</button>
                </div>
            `;

            // Events
            area.querySelectorAll('.bench-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    starterIds.delete(btn.dataset.pid);
                    if (captainId === btn.dataset.pid) captainId = '';
                    if (viceCaptainId === btn.dataset.pid) viceCaptainId = '';
                    render();
                });
            });
            area.querySelectorAll('.start-btn').forEach(btn => {
                btn.addEventListener('click', () => { starterIds.add(btn.dataset.pid); render(); });
            });
            area.querySelectorAll('.cap-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    captainId = btn.dataset.pid;
                    if (viceCaptainId === captainId) viceCaptainId = '';
                    render();
                });
            });
            area.querySelectorAll('.vc-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    viceCaptainId = btn.dataset.pid;
                    if (captainId === viceCaptainId) captainId = '';
                    render();
                });
            });
            document.getElementById('btn-save-md-lineup')?.addEventListener('click', async () => {
                if (starterIds.size === 11 && !validateGK()) {
                    showToast('⚠️ Necesitas al menos 1 portero (GK) titular', 'error');
                    return;
                }
                const payload = { starters: [...starterIds] };
                if (captainId) payload.captain = captainId;
                if (viceCaptainId) payload.vice_captain = viceCaptainId;
                try {
                    await API.patch(`/teams/${teamId}/matchday-lineup/${mdId}`, payload);
                    showToast('✅ Alineación guardada', 'success');
                } catch (err) { showToast(err.message, 'error'); }
            });
        }

        render();
    }

    // Tab switching
    container.querySelectorAll('.md-tab').forEach(btn => {
        btn.addEventListener('click', () => loadMatchdayLineup(btn.dataset.mdid));
    });

    // Load first tab
    if (matchdays.length > 0) {
        loadMatchdayLineup(matchdays[0].id);
    } else if (team.players.length > 0) {
        // No matchdays — show default roster as read-only
        const area = document.getElementById('matchday-lineup-area');
        if (area) {
            area.innerHTML = `
                <div class="card">
                    <div class="card-header">Plantilla</div>
                    ${team.players.map(p => `
                        <div style="display:flex;align-items:center;gap:.5rem;padding:.3rem 0;font-size:.85rem">
                            ${posBadge(p.position)}
                            <span style="flex:1">${p.name}</span>
                            <span class="money" style="font-size:.8rem">${formatMoney(p.market_value)}</span>
                            <span style="color:var(--accent-teal);font-weight:700">${p.total_points || ''}</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }
    }
});
