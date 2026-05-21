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
                <div style="font-size:.85rem;color:var(--text-secondary)">Puntos jornada</div>
                <div id="team-matchday-points" style="font-size:2rem;font-weight:800;color:var(--accent-gold)">0</div>
            </div>
            <div class="card text-center">
                <div style="font-size:.85rem;color:var(--text-secondary)">Puntos totales equipo</div>
                <div id="team-total-points" style="font-size:1.5rem;font-weight:700;color:var(--accent-teal)">${team.total_points || 0}</div>
            </div>
        </div>
        ${matchdays.length > 0 ? `
        <div class="flex mb-2" id="md-tabs" style="gap:.4rem;border-bottom:2px solid var(--border);padding-bottom:.5rem;overflow-x:visible;flex-wrap:wrap">
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

        const mdMeta = matchdays.find(md => md.id === mdId) || {};
        const isLocked = mdMeta.status === 'completed';

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

        const startersFromApi = lineupData.starters || {};
        const squadMap = new Map();
        (team.players || []).forEach(p => {
            const playerId = p.player_id || p.id;
            if (!playerId) return;
            squadMap.set(playerId, {
                player_id: playerId,
                name: p.name,
                position: p.position,
                country_code: p.country_code,
                photo: p.photo,
                club: p.club,
                market_value: p.market_value || 0,
                total_points: p.total_points || 0,
                matchday_points: p.matchday_points || 0,
                matchday_minutes: p.matchday_minutes || 0,
                country_played: p.country_played || false,
            });
        });
        Object.values(startersFromApi).forEach(p => {
            if (p && p.player_id) squadMap.set(p.player_id, p);
        });
        (lineupData.bench || []).forEach(p => {
            if (p && p.player_id) squadMap.set(p.player_id, p);
        });
        const squadPlayers = Array.from(squadMap.values()).sort((a, b) => {
            const p1 = POS_ORDER[a.position] ?? 99;
            const p2 = POS_ORDER[b.position] ?? 99;
            if (p1 !== p2) return p1 - p2;
            return (a.name || '').localeCompare(b.name || '');
        });
        const currentLineup = {};
        LINEUP_SLOTS.forEach(slot => {
            currentLineup[slot] = startersFromApi[slot] || null;
        });

        const updateHeaderPoints = () => {
            const mdPts = LINEUP_SLOTS.reduce((sum, slot) => {
                const p = currentLineup[slot];
                return sum + Number(p?.matchday_points || 0);
            }, 0);
            const mdEl = document.getElementById('team-matchday-points');
            if (mdEl) mdEl.textContent = String(mdPts);

            const totalEl = document.getElementById('team-total-points');
            if (totalEl) totalEl.textContent = String(team.total_points || 0);
        };

        const slotLabel = (slot) => (slot === 'WILDCARD' ? 'WILDCARD' : slot);
        const slotAccepts = (slot, pos) => slot === 'WILDCARD' || slot === pos;

        const assignPlayerToSlot = async (slot, player) => {
            const existing = currentLineup[slot];
            
            // Warn if replacing a starter whose country's match has already started
            if (existing && existing.country_played) {
                const confirmed = await new Promise(resolve => {
                    const msg = `⚠️ ${existing.name} ya ha jugado y lleva ${existing.matchday_points || 0} puntos.\n\n¿Seguro que quieres reemplazarlo y perder esos puntos?`;
                    resolve(confirm(msg));
                });
                if (!confirmed) return;
            }
            
            // Remove from other slots
            LINEUP_SLOTS.forEach(s => {
                if (currentLineup[s]?.player_id === player.player_id) currentLineup[s] = null;
            });
            currentLineup[slot] = player;
            
            // Auto-save
            const spec = buildSpec();
            if (spec) {
                try {
                    await API.patch(`/teams/${teamId}/lineup-5/${mdId}`, spec);
                } catch (err) {
                    showToast(`Error guardando: ${err.message}`, 'error');
                }
            }
            render();
        };

        const playerScore = (player) => {
            return Number(player.total_points || 0) * 1000000 + Number(player.market_value || 0);
        };

        const autoBuildLineup = () => {
            const nextLineup = {};
            const used = new Set();

            const takeBest = (slot) => {
                const candidates = squadPlayers
                    .filter(player => !used.has(player.player_id) && slotAccepts(slot, player.position))
                    .sort((left, right) => playerScore(right) - playerScore(left));
                return candidates[0] || null;
            };

            ['GK', 'DEF', 'MID', 'FWD'].forEach(slot => {
                const best = takeBest(slot);
                if (best) {
                    nextLineup[slot] = best;
                    used.add(best.player_id);
                }
            });

            const wildcard = squadPlayers
                .filter(player => !used.has(player.player_id))
                .sort((left, right) => playerScore(right) - playerScore(left))[0] || null;

            if (wildcard) {
                nextLineup.WILDCARD = wildcard;
                used.add(wildcard.player_id);
            }

            LINEUP_SLOTS.forEach(slot => {
                currentLineup[slot] = nextLineup[slot] || null;
            });
        };

        const buildSpec = () => {
            const spec = {};
            for (const slot of LINEUP_SLOTS) {
                const p = currentLineup[slot];
                if (!p?.player_id) return null;
                if (!slotAccepts(slot, p.position)) return null;
                spec[slot] = p.player_id;
            }
            const unique = new Set(Object.values(spec));
            if (unique.size !== LINEUP_SIZE) return null;
            return spec;
        };

        const render = () => {
            area.innerHTML = `
                <div class="card mb-2">
                    <div class="card-header">Alineacion de jornada (5)</div>
                    <div style="font-size:.85rem;color:var(--text-muted);padding:0 1rem .8rem 1rem">
                        Obligatorio: 1 GK, 1 DEF, 1 MID, 1 FWD y 1 WILDCARD (cualquier posicion).
                        ${isLocked ? ' La jornada finalizo y esta bloqueada para editar.' : ' Mete o quita titulares directamente desde tu plantilla (si un pais ya jugo, no puedes meter desde banquillo a ese jugador).'}
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.75rem;padding:0 1rem 1rem 1rem">
                        ${LINEUP_SLOTS.map(slot => {
                            const p = currentLineup[slot];
                            return `
                                <div class="slot-card" data-slot="${slot}" style="border:2px solid ${p ? 'var(--accent-gold)' : 'var(--border)'};border-radius:10px;padding:.6rem;background:var(--bg-secondary);min-width:0">
                                    <div style="font-weight:700;font-size:.85rem;margin-bottom:.4rem">${slotLabel(slot)}</div>
                                    ${p ? `
                                        ${p.photo ? `<img src="${p.photo}" alt="${p.name}" style="width:100%;height:auto;border-radius:6px;margin-bottom:.4rem;aspect-ratio:1/1;object-fit:cover">` : ''}
                                        <div style="display:flex;justify-content:space-between;align-items:flex-end;gap:.5rem">
                                            <div style="min-width:0">
                                                <div style="font-size:.85rem;line-height:1.2;overflow-wrap:anywhere;font-weight:600">${p.name}</div>
                                                <div style="font-size:.75rem;color:var(--text-muted);margin-bottom:.3rem">${p.position} · ${p.country_code}</div>
                                            </div>
                                            <div style="text-align:right;line-height:1">
                                                <div style="font-size:.68rem;color:var(--text-muted);margin-bottom:.15rem">Jornada</div>
                                                <div style="font-size:1.6rem;font-weight:800;color:${p.country_played ? '#2dd4bf' : 'var(--text-muted)'}">${p.country_played ? (p.matchday_points || 0) : '-'}</div>
                                            </div>
                                        </div>
                                        <div style="display:flex;gap:.4rem;font-size:.75rem;margin-bottom:.4rem">
                                            <div><span style="color:var(--text-muted)">Total:</span> <span style="color:var(--accent-gold);font-weight:700">${p.total_points || 0}</span></div>
                                        </div>
                                    ` : `<div style="font-size:.8rem;color:var(--text-muted)">Vacio</div>`}
                                </div>
                            `;
                        }).join('')}
                    </div>
                    ${!isLocked ? `<div style="padding:0 1rem 1rem 1rem;display:flex;gap:.6rem;flex-wrap:wrap"><button class="btn btn-outline" id="btn-auto-lineup-5">Auto alineacion</button></div>` : ''}
                </div>

                <div class="card mb-2">
                    <div class="card-header">Tu plantilla (${squadPlayers.length}/${SQUAD_SIZE_MAX})</div>
                    <div style="padding:.75rem;display:grid;gap:.5rem">
                        ${squadPlayers.map(p => {
                            const inSlot = LINEUP_SLOTS.find(s => currentLineup[s]?.player_id === p.player_id);
                            const validSlots = LINEUP_SLOTS.filter(slot => slotAccepts(slot, p.position));
                            const hasPlayed = !!p.country_played;
                            const canAssignToLineup = !hasPlayed || !!inSlot;
                            return `
                                <div style="display:grid;grid-template-columns:60px 1fr auto;gap:.75rem;align-items:center;padding:.5rem;border:1px solid var(--border);border-radius:8px;background:var(--bg-secondary)">
                                    <div style="display:flex;flex-direction:column;align-items:center;gap:.3rem">
                                        ${p.photo ? `<img src="${p.photo}" alt="${p.name}" style="width:55px;height:55px;border-radius:6px;object-fit:cover">` : `<div style="width:55px;height:55px;border-radius:6px;background:var(--border);display:flex;align-items:center;justify-content:center">${posBadge(p.position)}</div>`}
                                        ${posBadge(p.position)}
                                    </div>
                                    <div style="min-width:0">
                                        <div style="font-size:.88rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${p.name}</div>
                                        <div style="font-size:.74rem;color:var(--text-muted)">${p.country_code} · ${p.market_value ? formatMoney(p.market_value) : 'N/A'}</div>
                                    </div>
                                    <div style="display:flex;flex-direction:column;gap:.35rem;align-items:flex-end">
                                        <div style="display:flex;flex-direction:column;align-items:flex-end;line-height:1.1;margin-bottom:.15rem">
                                            <div style="font-size:.72rem;color:var(--text-muted)">Jornada</div>
                                            <div style="font-size:1.15rem;color:var(--accent-teal);font-weight:800">${p.matchday_points || 0}</div>
                                            <div style="font-size:.72rem;color:var(--text-muted);margin-top:.15rem">Total</div>
                                            <div style="font-size:1.05rem;color:var(--accent-gold);font-weight:800">${p.total_points || 0}</div>
                                        </div>
                                        ${inSlot ? `<span class="badge badge-gold" style="font-size:.7rem">En ${inSlot}</span>` : ''}
                                        ${hasPlayed ? `<span class="badge" style="font-size:.7rem;background:var(--border);color:var(--text-muted)">Ya jugo</span>` : ''}
                                        ${!isLocked ? `
                                            <div style="display:flex;gap:.25rem;flex-wrap:wrap;justify-content:flex-end">
                                                ${canAssignToLineup ? validSlots.map(slot => `<button class="btn btn-xs ${inSlot === slot ? 'btn-gold' : 'btn-outline'} btn-place-player" data-pid="${p.player_id}" data-slot="${slot}" style="font-size:.7rem;padding:.3rem .4rem">${slot === 'WILDCARD' ? 'WC' : slot}</button>`).join('') : ''}
                                            </div>
                                        ` : ''}
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            `;

            updateHeaderPoints();

            if (!isLocked) {
                area.querySelectorAll('.btn-place-player').forEach(el => {
                    el.addEventListener('click', async () => {
                        const pid = el.dataset.pid;
                        const slot = el.dataset.slot;
                        const player = squadPlayers.find(p => p.player_id === pid);
                        if (!player || !slotAccepts(slot, player.position)) return;
                        await assignPlayerToSlot(slot, player);
                    });
                });

                area.querySelector('#btn-auto-lineup-5')?.addEventListener('click', async () => {
                    autoBuildLineup();
                    const spec = buildSpec();
                    if (!spec) {
                        showToast('No se pudo generar una alineacion valida automaticamente', 'error');
                        return;
                    }
                    try {
                        await API.patch(`/teams/${teamId}/lineup-5/${mdId}`, spec);
                        showToast('Auto alineacion guardada', 'success');
                        await loadMatchdayLineup(mdId);
                    } catch (err) {
                        showToast(`Error: ${err.message}`, 'error');
                    }
                });
            }

        };

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
