/* Standings page — General + per-matchday classification */
Router.register('#/standings', async (container) => {
    const leagueId = API.getLeagueId();
    const myTeamId = API.getTeamId();
    const data = await API.get(`/leagues/${leagueId}/standings`);
    const standings = data.standings || [];
    const mdIds = data.matchday_ids || [];

    // All matchdays from simulator for tab labels
    let allMatchdays = [];
    try { allMatchdays = await API.get('/scoring/matchdays'); } catch {}

    const TAB_LABELS = {GS1:'J1',GS2:'J2',GS3:'J3',R32:'1/32',R16:'1/16',QF:'1/4',SF:'1/2',FINAL:'Final'};

    let mode = 'general'; // 'general' or matchday id
    let selectedMd = mdIds.length > 0 ? mdIds[mdIds.length - 1] : '';

    function getLabel(mdId) { return TAB_LABELS[mdId] || mdId; }

    function getSorted() {
        if (mode === 'general') {
            return [...standings].sort((a, b) => b.total_points - a.total_points);
        }
        return [...standings].sort((a, b) => (b.matchday_points[mode] || 0) - (a.matchday_points[mode] || 0));
    }

    function render() {
        const sorted = getSorted();
        const isGeneral = mode === 'general';
        const pointsLabel = isGeneral ? 'Total' : getLabel(mode);

        container.innerHTML = `
            <h2 class="mb-2">📊 Clasificación</h2>

            <div class="flex mb-1" style="gap:.5rem">
                <button class="btn ${isGeneral ? 'btn-gold' : 'btn-outline'} mode-btn" data-mode="general" style="font-size:.85rem">General</button>
                <button class="btn ${!isGeneral ? 'btn-gold' : 'btn-outline'} mode-btn" data-mode="matchday" style="font-size:.85rem">Por Jornada</button>
            </div>

            ${!isGeneral ? `
            <div class="flex mb-2" style="gap:.3rem;overflow-x:auto;padding-bottom:.3rem">
                ${allMatchdays.map(md => {
                    const active = mode === md.id;
                    const hasData = mdIds.includes(md.id);
                    const icon = md.status === 'active' ? '🔴' : md.status === 'completed' ? '✅' : '📋';
                    return `<button class="btn ${active ? 'btn-gold' : 'btn-outline'} md-btn"
                        data-md="${md.id}" style="font-size:.8rem;white-space:nowrap;padding:.3rem .6rem;${!hasData ? 'opacity:.4;' : ''}"
                        ${!hasData ? 'disabled' : ''}>
                        ${getLabel(md.id)} ${icon}
                    </button>`;
                }).join('')}
            </div>` : ''}

            <div class="card">
                <table>
                    <thead>
                        <tr>
                            <th>#</th><th>Equipo</th><th>Manager</th>
                            <th style="text-align:right">${pointsLabel}</th>
                            ${isGeneral ? '<th style="text-align:right">Presupuesto</th>' : ''}
                        </tr>
                    </thead>
                    <tbody>
                        ${sorted.map((s, i) => {
                            const pts = isGeneral ? s.total_points : (s.matchday_points[mode] || 0);
                            const isMe = s.team_id === myTeamId;
                            const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : '';
                            return `
                            <tr class="${isMe ? 'rank-1' : ''} team-row" data-tid="${s.team_id}" style="cursor:pointer">
                                <td>${medal || (i + 1)}</td>
                                <td><strong>${s.team_name}</strong></td>
                                <td>${s.display_name}</td>
                                <td style="font-weight:700;color:var(--accent-teal);text-align:right">${pts}</td>
                                ${isGeneral ? `<td class="money" style="text-align:right">${formatMoney(s.budget)}</td>` : ''}
                            </tr>`;
                        }).join('')}
                        ${sorted.length === 0 ? '<tr><td colspan="5" class="text-center" style="color:var(--text-muted)">Sin datos todavía</td></tr>' : ''}
                    </tbody>
                </table>
            </div>

            <div id="team-detail-area"></div>
        `;

        // Mode buttons
        container.querySelectorAll('.mode-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                if (btn.dataset.mode === 'general') {
                    mode = 'general';
                } else {
                    mode = selectedMd || (mdIds.length > 0 ? mdIds[mdIds.length - 1] : '');
                }
                render();
            });
        });

        // Matchday tabs
        container.querySelectorAll('.md-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                mode = btn.dataset.md;
                selectedMd = btn.dataset.md;
                render();
            });
        });

        // Team click → show lineup
        container.querySelectorAll('.team-row').forEach(row => {
            row.addEventListener('click', () => showTeamLineup(row.dataset.tid));
        });
    }

    async function showTeamLineup(teamId) {
        const area = document.getElementById('team-detail-area');
        if (!area) return;
        const mdId = mode === 'general' ? (mdIds[mdIds.length - 1] || '') : mode;
        if (!mdId) { area.innerHTML = ''; return; }

        const team = standings.find(s => s.team_id === teamId);
        if (!team) return;

        area.innerHTML = '<div class="card text-center" style="color:var(--text-muted)">Cargando...</div>';

        try {
            const lineup = await API.get(`/leagues/${leagueId}/team-lineup/${teamId}/${mdId}`);
            const players = lineup.players || [];
            const starters = players.filter(p => p.is_starter);
            const bench = players.filter(p => !p.is_starter);
            const totalPts = starters.reduce((s, p) => s + (p.matchday_points || 0), 0);

            const posOrder = {GK:0, DEF:1, MID:2, FWD:3};
            starters.sort((a, b) => (posOrder[a.position]||9) - (posOrder[b.position]||9));
            bench.sort((a, b) => (posOrder[a.position]||9) - (posOrder[b.position]||9));

            function playerRow(p, isBench) {
                const icons = [
                    p.goals > 0 ? `⚽×${p.goals}` : '',
                    p.assists > 0 ? `🅰️×${p.assists}` : '',
                    p.yellow_cards > 0 ? '🟨' : '',
                    p.red_card > 0 ? '🟥' : '',
                ].filter(Boolean).join(' ');
                const pts = isBench ? '' : (p.matchday_points || '—');
                return `<div style="display:flex;align-items:center;gap:.5rem;padding:.35rem 0;font-size:.85rem;border-bottom:1px solid var(--border);${isBench ? 'opacity:.6;' : ''}">
                    ${p.photo ? `<img src="${p.photo}" alt="" style="width:28px;height:28px;border-radius:50%;object-fit:cover" referrerpolicy="no-referrer" onerror="this.style.display='none'">` : '<span style="width:28px"></span>'}
                    ${posBadge(p.position)}
                    ${p.is_captain ? '<span class="chip-badge cap" style="font-size:.65rem">C</span>' : ''}
                    ${p.is_vice_captain ? '<span class="chip-badge vc" style="font-size:.65rem">VC</span>' : ''}
                    <a href="#/player/${p.player_id}" style="flex:1;color:inherit;text-decoration:none">${p.name}</a>
                    <span style="font-size:.75rem;color:var(--text-muted)">${p.country_code}</span>
                    ${icons ? `<span style="font-size:.75rem">${icons}</span>` : ''}
                    ${p.minutes_played > 0 ? `<span style="font-size:.7rem;color:var(--text-muted)">${p.minutes_played}'</span>` : ''}
                    <span style="font-weight:700;color:var(--accent-teal);min-width:28px;text-align:right">${pts}</span>
                </div>`;
            }

            area.innerHTML = `
                <div class="card mt-2">
                    <div class="flex-between mb-1">
                        <div class="card-header" style="margin:0">${team.team_name} — ${getLabel(mdId)}</div>
                        <span style="font-weight:700;color:var(--accent-teal);font-size:1.2rem">${totalPts} pts</span>
                    </div>
                    <div style="margin-bottom:.3rem"><small style="color:var(--text-secondary)">Titulares (${starters.length})</small></div>
                    ${starters.map(p => playerRow(p, false)).join('')}
                    ${bench.length > 0 ? `
                    <div style="margin:.5rem 0 .3rem"><small style="color:var(--text-secondary)">Banquillo (${bench.length})</small></div>
                    ${bench.map(p => playerRow(p, true)).join('')}
                    ` : ''}
                </div>
            `;
        } catch {
            area.innerHTML = `<div class="card mt-2 text-center" style="color:var(--text-muted)">No hay alineación para esta jornada</div>`;
        }
    }

    render();
});
