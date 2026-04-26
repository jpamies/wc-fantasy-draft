/* Team management page — per-matchday lineups */
Router.register('#/team', async (container) => {
    const teamId = API.getTeamId();
    const team = await API.get(`/teams/${teamId}`);

    // Get all matchdays from simulator
    let matchdays = [];
    let defaultMdIndex = 0;
    try {
        matchdays = await API.get('/scoring/matchdays');
        // Default tab: first active, or first upcoming, or last completed
        const activeIdx = matchdays.findIndex(md => md.status === 'active');
        const upcomingIdx = matchdays.findIndex(md => md.status === 'upcoming');
        if (activeIdx >= 0) defaultMdIndex = activeIdx;
        else if (upcomingIdx >= 0) defaultMdIndex = upcomingIdx;
        else if (matchdays.length > 0) defaultMdIndex = matchdays.length - 1;
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
        <div class="flex mb-2" id="md-tabs" style="gap:.4rem;border-bottom:2px solid var(--border);padding-bottom:.5rem;overflow-x:auto;flex-wrap:nowrap">
            ${matchdays.map((md, i) => {
                const icon = md.status === 'completed' ? '✅' : md.status === 'active' ? '🔴' : '📋';
                const badgeClass = md.status === 'completed' ? 'badge-teal' : md.status === 'active' ? 'badge-gold' : '';
                const TAB_LABELS = {GS1:'J1',GS2:'J2',GS3:'J3',R32:'1/32',R16:'1/16',QF:'1/4',SF:'1/2',FINAL:'Final'};
                const shortName = TAB_LABELS[md.id] || md.id;
                return `
                <button class="btn ${i === defaultMdIndex ? 'btn-gold' : 'btn-outline'} md-tab" data-mdid="${md.id}" style="font-size:.8rem;white-space:nowrap;padding:.4rem .7rem">
                    ${shortName}
                    <span class="badge ${badgeClass}" style="font-size:.65rem;margin-left:.2rem">${icon}</span>
                </button>`;
            }).join('')}
        </div>
        <div id="matchday-lineup-area"></div>
        ` : `
        <div class="card text-center" style="color:var(--text-muted)">
            <p>No hay jornadas disponibles. El calendario aparecerá cuando el simulador lo tenga listo.</p>
        </div>
        <div id="matchday-lineup-area"></div>
        `}
    `;

    async function loadMatchdayLineup(mdId) {
        const area = document.getElementById('matchday-lineup-area');
        if (!area) return;

        // Find matchday metadata
        const mdMeta = matchdays.find(md => md.id === mdId) || {};
        const isCompleted = mdMeta.status === 'completed';

        // Highlight active tab and scroll into view
        container.querySelectorAll('.md-tab').forEach(btn => {
            btn.className = btn.dataset.mdid === mdId ? 'btn btn-gold md-tab' : 'btn btn-outline md-tab';
            if (btn.dataset.mdid === mdId) btn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
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

        function autoLineup() {
            // Pick best 11: 1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD
            // Sort by avg_points DESC, then market_value DESC as tiebreaker
            const sortFn = (a, b) => (b.avg_points || 0) - (a.avg_points || 0) || (b.market_value || 0) - (a.market_value || 0);
            const available = lineup.players.filter(p => !p.locked);
            const locked_starters = lineup.players.filter(p => p.locked && starterIds.has(p.player_id));

            const byPos = {GK:[], DEF:[], MID:[], FWD:[]};
            available.forEach(p => byPos[p.position]?.push(p));
            Object.values(byPos).forEach(arr => arr.sort(sortFn));

            // Start with locked starters (can't remove them)
            const picks = new Set(locked_starters.map(p => p.player_id));
            const posCounts = {GK:0, DEF:0, MID:0, FWD:0};
            locked_starters.forEach(p => posCounts[p.position]++);

            // Fill minimums first: 1 GK, 3 DEF, 2 MID, 1 FWD
            const mins = {GK:1, DEF:3, MID:2, FWD:1};
            for (const pos of ['GK','DEF','MID','FWD']) {
                const need = mins[pos] - posCounts[pos];
                for (let i = 0; i < need && byPos[pos].length; i++) {
                    const p = byPos[pos].shift();
                    picks.add(p.player_id);
                    posCounts[pos]++;
                }
            }

            // Fill remaining slots (11 - current) with best available respecting max limits
            const remaining = [];
            for (const pos of ['DEF','MID','FWD']) {
                byPos[pos].forEach(p => remaining.push(p));
            }
            remaining.sort(sortFn);
            for (const p of remaining) {
                if (picks.size >= 11) break;
                if (posCounts[p.position] < POS_LIMITS[p.position].max) {
                    picks.add(p.player_id);
                    posCounts[p.position]++;
                }
            }

            starterIds = picks;
            // Auto-captain: best avg_points starter
            const starterList = lineup.players.filter(p => picks.has(p.player_id)).sort(sortFn);
            if (starterList.length > 0) captainId = starterList[0].player_id;
            if (starterList.length > 1) viceCaptainId = starterList[1].player_id;
            render();
        }

        function renderChip(p, actions) {
            const mdPts = p.matchday_points || 0;
            const avgPts = p.avg_points || 0;
            const totalPts = p.total_points || 0;
            const locked = p.locked;
            const mdIcons = [
                p.matchday_goals > 0 ? `⚽×${p.matchday_goals}` : '',
                p.matchday_assists > 0 ? `🅰️×${p.matchday_assists}` : '',
                p.matchday_yellow_cards > 0 ? '🟨' : '',
                p.matchday_red_card > 0 ? '🟥' : '',
            ].filter(Boolean).join(' ');
            return `
                <div class="player-chip" style="${locked ? 'opacity:.7;' : ''}">
                    <img src="${p.photo}" alt="" referrerpolicy="no-referrer" onerror="this.style.display='none'">
                    <div class="player-chip-info">
                        <div class="player-name">
                            ${p.player_id === captainId ? '<span class="chip-badge cap">C</span>' : ''}
                            ${p.player_id === viceCaptainId ? '<span class="chip-badge vc">VC</span>' : ''}
                            <a href="#/player/${p.player_id}" style="color:inherit;text-decoration:none" onclick="event.stopPropagation()">${p.name}</a> ${locked ? '🔒' : ''}
                        </div>
                        <div class="player-meta">${p.country_code} · ${p.club} ${mdIcons ? `· ${mdIcons}` : ''}</div>
                    </div>
                    ${posBadge(p.position)}
                    <div style="text-align:right;min-width:40px;line-height:1.2">
                        ${mdPts ? `<div style="font-weight:700;color:var(--accent-teal);font-size:.9rem">${mdPts}</div>` : ''}
                        <div style="font-size:.7rem;color:var(--text-muted)">${avgPts > 0 ? `⌀${avgPts}` : ''}</div>
                    </div>
                    <div class="chip-actions">${actions}</div>
                </div>`;
        }

        function renderPitch() {
            const starters = getStarters();
            const byPos = {GK:[], DEF:[], MID:[], FWD:[]};
            starters.forEach(p => byPos[p.position]?.push(p));

            function pitchPlayer(p) {
                if (!p) return '<div class="pitch-player empty"><img src=""><div class="pitch-name">—</div></div>';
                return `
                    <div class="pitch-player">
                        ${p.player_id === captainId ? '<span class="pitch-badge cap">C</span>' : ''}
                        ${p.player_id === viceCaptainId ? '<span class="pitch-badge vc">VC</span>' : ''}
                        <img src="${p.photo || ''}" alt="" referrerpolicy="no-referrer" onerror="this.style.display='none'">
                        <div class="pitch-name">${p.name?.split(' ').pop() || ''}</div>
                    </div>`;
            }

            // Rows: FWD at top, GK at bottom
            return `
                <div class="pitch">
                    <div class="pitch-row">${byPos.FWD.map(p => pitchPlayer(p)).join('') || '<div class="pitch-player empty"><div class="pitch-name">FWD</div></div>'}</div>
                    <div class="pitch-row">${byPos.MID.map(p => pitchPlayer(p)).join('') || '<div class="pitch-player empty"><div class="pitch-name">MID</div></div>'}</div>
                    <div class="pitch-row">${byPos.DEF.map(p => pitchPlayer(p)).join('') || '<div class="pitch-player empty"><div class="pitch-name">DEF</div></div>'}</div>
                    <div class="pitch-row">${byPos.GK.map(p => pitchPlayer(p)).join('') || '<div class="pitch-player empty"><div class="pitch-name">GK</div></div>'}</div>
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
                    ${starterIds.size > 0 ? renderPitch() : ''}
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
                                ${posPlayers.map(p => {
                                    const frozen = p.locked || isCompleted;
                                    return renderChip(p, `
                                    <button class="btn btn-sm btn-outline bench-btn" data-pid="${p.player_id}" title="${frozen ? 'Bloqueado' : 'Al banquillo'}"${frozen ? ' disabled' : ''}>
                                        ${frozen ? '🔒' : '↓'}
                                    </button>
                                    <button class="btn btn-sm ${p.player_id === captainId ? 'btn-gold' : 'btn-outline'} cap-btn" data-pid="${p.player_id}" title="Capitán"${frozen ? ' disabled' : ''}>C</button>
                                    <button class="btn btn-sm ${p.player_id === viceCaptainId ? 'btn-primary' : 'btn-outline'} vc-btn" data-pid="${p.player_id}" title="Vice" style="font-size:.7rem"${frozen ? ' disabled' : ''}>VC</button>
                                    `);
                                }).join('')}
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
                                    const frozen = p.locked || isCompleted;
                                    const canPromote = canAddPosition(pos) && !frozen;
                                    return renderChip(p, `
                                        <button class="btn btn-sm ${canPromote ? 'btn-primary' : 'btn-outline'} start-btn" data-pid="${p.player_id}"
                                            ${canPromote ? '' : 'disabled'}
                                            title="${frozen ? 'Bloqueado' : !canAddPosition(pos) ? 'Posición llena' : 'Titular'}">
                                            ${frozen ? '🔒' : '↑'}
                                        </button>
                                    `);
                                }).join('')}
                            `;
                        }).join('')}
                    </div>
                </div>

                ${isCompleted ? `
                <div class="mt-1 text-center"><span style="color:var(--text-muted);font-size:.85rem">✅ Jornada completada — alineación bloqueada</span></div>
                ` : `
                <div class="mt-2 text-center" style="display:flex;gap:.5rem;justify-content:center">
                    <button class="btn btn-outline" id="btn-auto-lineup">🤖 Auto-alineación</button>
                    <button class="btn btn-gold" id="btn-save-md-lineup">💾 Guardar alineación</button>
                </div>
                `}
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
            document.getElementById('btn-auto-lineup')?.addEventListener('click', () => {
                autoLineup();
                showToast('🤖 Alineación automática aplicada — guarda para confirmar', 'success');
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

    // Load default tab (first active > first upcoming > last completed)
    if (matchdays.length > 0) {
        loadMatchdayLineup(matchdays[defaultMdIndex].id);
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
