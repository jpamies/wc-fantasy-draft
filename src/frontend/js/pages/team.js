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

    const LINEUP_SLOTS = ['GK', 'DEF', 'MID', 'FWD', 'WILDCARD'];
    const POS_ORDER = {GK:0, DEF:1, MID:2, FWD:3, WILDCARD:4};
    const SQUAD_SIZE_MAX = 12;
    const LINEUP_SIZE = 5;

    // Show team header
    container.innerHTML = `
        <div class="flex-between mb-2">
            <h2>🏟️ ${team.team_name}</h2>
            <div class="money">${formatMoney(team.budget)}</div>
        </div>
        <div class="grid grid-3 mb-2">
            <div class="card text-center">
                <div style="font-size:.85rem;color:var(--text-secondary)">Jugadores</div>
                <div style="font-size:1.5rem;font-weight:700">${team.players.length}/${SQUAD_SIZE_MAX}</div>
            </div>
            <div class="card text-center">
                <div style="font-size:.85rem;color:var(--text-secondary)">Puntos totales</div>
                <div style="font-size:1.5rem;font-weight:700;color:var(--accent-teal)">${team.total_points || 0}</div>
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
        const isActive = mdMeta.status === 'active';

        // Highlight active tab
        container.querySelectorAll('.md-tab').forEach(btn => {
            btn.className = btn.dataset.mdid === mdId ? 'btn btn-gold md-tab' : 'btn btn-outline md-tab';
            if (btn.dataset.mdid === mdId) btn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
        });

        let lineupData;
        try {
            lineupData = await API.get(`/teams/${teamId}/lineup-5/${mdId}`);
        } catch {
            area.innerHTML = '<div class="card text-center"><p style="color:var(--text-muted)">Error cargando alineación</p></div>';
            return;
        }

        let currentLineup = { ...lineupData.starters };  // {GK: {...}, DEF: {...}, ...}
        const bench = lineupData.bench || [];
        
        function renderLineupEditor() {
            const slotOptions = {};
            LINEUP_SLOTS.forEach(slot => {
                slotOptions[slot] = [];
                bench.forEach(p => {
                    if (slot === 'WILDCARD' || p.position === slot) {
                        slotOptions[slot].push(p);
                    }
                });
            });
            
            return `
                <div class="card mb-2">
                    <div class="card-header">⚽ Alineación (5 jugadores)</div>
                    <div class="lineup-grid" style="display:grid;grid-template-columns:repeat(5,1fr);gap:1rem;padding:1rem">
                        ${LINEUP_SLOTS.map(slot => {
                            const currentPlayer = currentLineup[slot];
                            const label = slot === 'WILDCARD' ? '🃏 Wildcard' : slot;
                            return `
                                <div class="slot-selector">
                                    <label style="font-weight:600;font-size:.9rem">${label}</label>
                                    <select class="slot-player" data-slot="${slot}" ${isActive ? 'disabled' : ''}>
                                        <option value="">— Seleccionar —</option>
                                        ${(slotOptions[slot] || [])
                                            .map(p => `<option value="${p.player_id}" ${currentPlayer?.player_id === p.player_id ? 'selected' : ''}>
                                                ${p.name} (${p.country_code}) ${p.country_played ? '🚫' : ''}
                                            </option>`)
                                            .join('')}
                                    </select>
                                    ${currentPlayer ? `<div style="font-size:.75rem;margin-top:.3rem;color:var(--text-muted)">${currentPlayer.name}</div>` : ''}
                                </div>
                            `;
                        }).join('')}
                    </div>
                    <div style="padding:0 1rem;margin-top:1rem">
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
                            <div>
                                <label style="font-weight:600;font-size:.9rem">⚡ Capitán</label>
                                <select id="select-captain" ${isActive ? 'disabled' : ''}>
                                    <option value="">— Ninguno —</option>
                                    ${Object.values(currentLineup)
                                        .filter(p => p)
                                        .map(p => `<option value="${p.player_id}" ${p.player_id === lineupData.captain_id ? 'selected' : ''}>
                                            ${p.name}
                                        </option>`)
                                        .join('')}
                                </select>
                            </div>
                            <div>
                                <label style="font-weight:600;font-size:.9rem">⚙️ Vice-Capitán</label>
                                <select id="select-vice-captain" ${isActive ? 'disabled' : ''}>
                                    <option value="">— Ninguno —</option>
                                    ${Object.values(currentLineup)
                                        .filter(p => p)
                                        .map(p => `<option value="${p.player_id}" ${p.player_id === lineupData.vice_captain_id ? 'selected' : ''}>
                                            ${p.name}
                                        </option>`)
                                        .join('')}
                                </select>
                            </div>
                        </div>
                    </div>
                    ${!isActive ? `<button class="btn btn-primary" id="btn-save-lineup-5" style="margin:1rem">💾 Guardar alineación</button>` : ''}
                </div>
            `;
        }
        
        function renderInGameSubs() {
            if (!isActive) return '';
            
            const playedBench = bench.filter(p => p.matchday_minutes > 0);
            const unplayedBench = bench.filter(p => p.matchday_minutes === 0);
            
            return `
                <div class="card mb-2">
                    <div class="card-header">🔄 Cambios en vivo</div>
                    <div style="font-size:.85rem;color:var(--text-muted);margin-bottom:1rem">
                        ✅ Saca: Jugador que YA HA JUGADO<br>
                        ✅ Mete: Jugador que NO HA JUGADO
                    </div>
                    <div style="display:grid;grid-template-columns:1fr auto 1fr;gap:1rem;align-items:end">
                        <div>
                            <label style="font-size:.85rem">Sacar (ya ha jugado)</label>
                            <select id="sub-out-player">
                                <option value="">— Seleccionar —</option>
                                ${Object.values(currentLineup).map(p => `
                                    <option value="${p.player_id}" ${p.matchday_minutes > 0 ? '' : 'disabled'}>
                                        ${p.name} (${p.matchday_minutes}min)
                                    </option>
                                `).join('')}
                            </select>
                        </div>
                        <button class="btn btn-gold" style="padding:0.5rem 1rem">⇄</button>
                        <div>
                            <label style="font-size:.85rem">Meter (no ha jugado)</label>
                            <select id="sub-in-player">
                                <option value="">— Seleccionar —</option>
                                ${unplayedBench.map(p => `
                                    <option value="${p.player_id}">
                                        ${p.name} (${p.country_code})
                                    </option>
                                `).join('')}
                            </select>
                        </div>
                    </div>
                    ${unplayedBench.length === 0 ? '<div style="margin-top:1rem;color:var(--accent-red);font-size:.85rem">⚠️ No hay jugadores sin jugar disponibles</div>' : ''}
                    <button class="btn btn-gold mt-1" id="btn-perform-sub" ${unplayedBench.length === 0 ? 'disabled' : ''}>✅ Hacer cambio</button>
                </div>
            `;
        }

        area.innerHTML = renderLineupEditor() + renderInGameSubs();

        // Event listeners for lineup editor
        document.getElementById('btn-save-lineup-5')?.addEventListener('click', async () => {
            const spec = {};
            let valid = true;
            LINEUP_SLOTS.forEach(slot => {
                const select = document.querySelector(`.slot-player[data-slot="${slot}"]`);
                const playerId = select?.value;
                if (!playerId) {
                    valid = false;
                    showToast(`${slot} slot vacío`, 'error');
                }
                spec[slot] = playerId;
            });
            
            if (!valid) return;
            
            const captainId = document.getElementById('select-captain').value || null;
            const viceCaptainId = document.getElementById('select-vice-captain').value || null;
            if (captainId) spec.captain_id = captainId;
            if (viceCaptainId) spec.vice_captain_id = viceCaptainId;
            
            try {
                const result = await API.patch(`/teams/${teamId}/lineup-5/${mdId}`, spec);
                showToast('✅ Alineación guardada', 'success');
                loadMatchdayLineup(mdId);
            } catch (err) {
                showToast(`❌ ${err.message}`, 'error');
            }
        });

        // Event listeners for in-game subs
        document.getElementById('btn-perform-sub')?.addEventListener('click', async () => {
            const outId = document.getElementById('sub-out-player').value;
            const inId = document.getElementById('sub-in-player').value;
            
            if (!outId || !inId) {
                showToast('Selecciona ambos jugadores', 'error');
                return;
            }
            
            try {
                const result = await API.post(`/teams/${teamId}/matchday/${mdId}/in-game-sub`, {
                    player_out_id: outId,
                    player_in_id: inId
                });
                showToast(`✅ ${result.message}`, 'success');
                loadMatchdayLineup(mdId);
            } catch (err) {
                showToast(`❌ ${err.message}`, 'error');
            }
        });
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
