/* Team management page */
Router.register('#/team', async (container) => {
    const teamId = API.getTeamId();
    const team = await API.get(`/teams/${teamId}`);

    const starters = team.players.filter(p => p.is_starter);
    const bench = team.players.filter(p => !p.is_starter);

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
                    ${['4-3-3','4-4-2','3-5-2','3-4-3','5-3-2','5-4-1','4-5-1'].map(f =>
                        `<option value="${f}" ${f === team.formation ? 'selected' : ''}>${f}</option>`
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
                <div class="card-header">Titulares (${starters.length}/11)</div>
                ${starters.length === 0 ? '<p style="color:var(--text-muted)">Selecciona titulares desde el banquillo</p>' : ''}
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
                                        ${p.is_captain ? '©️ ' : ''}${p.is_vice_captain ? 'VC ' : ''}${p.name}
                                    </div>
                                    <div class="player-meta">${p.club} · ${p.country_code}</div>
                                </div>
                                ${posBadge(p.position)}
                                <button class="btn btn-sm btn-outline bench-btn" data-pid="${p.player_id}" title="Al banquillo">↓</button>
                                <button class="btn btn-sm ${p.is_captain ? 'btn-gold' : 'btn-outline'} cap-btn" data-pid="${p.player_id}" title="Capitán">C</button>
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

        <div class="mt-2 text-center">
            <button class="btn btn-gold" id="btn-save-lineup">💾 Guardar alineación</button>
        </div>
    `;

    // Track changes
    let currentStarters = new Set(starters.map(p => p.player_id));
    let captain = starters.find(p => p.is_captain)?.player_id || '';

    container.querySelectorAll('.bench-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            currentStarters.delete(btn.dataset.pid);
            reloadTeamPage();
        });
    });

    container.querySelectorAll('.start-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            currentStarters.add(btn.dataset.pid);
            reloadTeamPage();
        });
    });

    container.querySelectorAll('.cap-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            captain = btn.dataset.pid;
            showToast('Capitán seleccionado', 'info');
        });
    });

    document.getElementById('formation-select')?.addEventListener('change', () => {});

    document.getElementById('btn-save-lineup')?.addEventListener('click', async () => {
        const formation = document.getElementById('formation-select')?.value || team.formation;
        const starterList = [...currentStarters];
        try {
            await API.patch(`/teams/${teamId}/lineup`, {
                formation,
                starters: starterList.length === 11 ? starterList : undefined,
                captain: captain || undefined,
            });
            showToast('Alineación guardada', 'success');
            Router.handleRoute();
        } catch (err) { showToast(err.message, 'error'); }
    });

    async function reloadTeamPage() { Router.handleRoute(); }
});
