/* Scoring page — calendar from simulator, scores from sync */
Router.register('#/scoring', async (container) => {
    const matchdays = await API.get('/scoring/matchdays');

    container.innerHTML = `
        <div class="flex-between mb-2">
            <h2>⚽ Calendario y Puntuación</h2>
        </div>

        ${matchdays.length === 0 ? `
            <div class="card text-center">
                <p style="color:var(--text-muted)">No hay jornadas disponibles.</p>
                <p style="font-size:.85rem;color:var(--text-secondary);margin-top:.5rem">El calendario se carga automáticamente del simulador.</p>
            </div>
        ` : `
            <div class="grid grid-2">
                ${matchdays.map(md => {
                    const statusIcon = md.status === 'active' ? '🔴' : md.status === 'completed' ? '✅' : '📋';
                    const badgeClass = md.status === 'completed' ? 'badge-teal' : md.status === 'active' ? 'badge-gold' : '';
                    return `
                    <div class="card" style="cursor:pointer" data-mdid="${md.id}">
                        <div class="flex-between">
                            <div class="card-header" style="margin:0">${md.name}</div>
                            <span class="badge ${badgeClass}">${statusIcon} ${md.status}</span>
                        </div>
                        <div style="font-size:.85rem;color:var(--text-secondary)">${md.date || ''} · ${md.phase}</div>
                    </div>`;
                }).join('')}
            </div>
        `}
    `;

    // Click matchday to view detail
    container.querySelectorAll('[data-mdid]').forEach(card => {
        card.addEventListener('click', () => loadMatchday(container, card.dataset.mdid));
    });
});

async function loadMatchday(container, mdId) {
    const md = await API.get(`/scoring/matchdays/${mdId}`);

    function flagImg(flag) {
        if (!flag) return '';
        if (flag.startsWith('http')) return `<img src="${flag}" alt="" style="height:16px;vertical-align:middle">`;
        return flag;
    }

    // Group scores by match_id and country
    const scoresByMatch = {};
    md.scores.forEach(s => {
        if (!scoresByMatch[s.match_id]) scoresByMatch[s.match_id] = {};
        if (!scoresByMatch[s.match_id][s.country_code]) scoresByMatch[s.match_id][s.country_code] = [];
        scoresByMatch[s.match_id][s.country_code].push(s);
    });

    function renderMatchPlayers(matchId, countryCode) {
        const posOrder = {GK:0, DEF:1, MID:2, FWD:3};
        const players = (scoresByMatch[matchId]?.[countryCode] || []);
        const sorted = [...players].sort((a, b) => b.minutes_played - a.minutes_played);
        const starting = sorted.slice(0, 11).sort((a, b) => (posOrder[a.position]||9) - (posOrder[b.position]||9));
        const subs = sorted.slice(11).sort((a, b) => (posOrder[a.position]||9) - (posOrder[b.position]||9));

        function playerRow(p) {
            return `<div style="display:flex;align-items:center;gap:.5rem;padding:.3rem 0;font-size:.85rem">
                ${posBadge(p.position)}
                <a href="#/player/${p.player_id}" style="flex:1;color:inherit;text-decoration:none">${p.player_name}</a>
                <span style="color:var(--text-muted)">${p.minutes_played}'</span>
                ${p.goals ? `<span>⚽×${p.goals}</span>` : ''}
                ${p.assists ? `<span>🅰️×${p.assists}</span>` : ''}
                ${p.yellow_cards ? '🟨' : ''}${p.red_card ? '🟥' : ''}
                <span style="font-weight:700;color:var(--accent-teal);min-width:28px;text-align:right">${p.total_points}</span>
            </div>`;
        }

        if (!players.length) return '<p style="color:var(--text-muted);font-size:.8rem;margin:.5rem 0">Sin datos</p>';
        return `
            ${starting.length ? `<div style="margin-bottom:.5rem"><small style="color:var(--text-secondary)">Titulares</small>${starting.map(playerRow).join('')}</div>` : ''}
            ${subs.length ? `<div><small style="color:var(--text-secondary)">Suplentes</small>${subs.map(playerRow).join('')}</div>` : ''}
        `;
    }

    const statusIcon = md.status === 'active' ? '🔴' : md.status === 'completed' ? '✅' : '📋';

    container.innerHTML = `
        <div class="flex-between mb-2">
            <div>
                <a href="#/scoring" style="font-size:.85rem">← Volver</a>
                <h2>${md.name}</h2>
            </div>
            <span class="badge ${md.status === 'completed' ? 'badge-teal' : md.status === 'active' ? 'badge-gold' : ''}">${statusIcon} ${md.status}</span>
        </div>

        <div class="card mb-2">
            <div class="card-header">Partidos</div>
            ${md.matches.length === 0 ? '<p style="color:var(--text-muted)">Sin partidos</p>' : ''}
            ${md.matches.map(m => {
                const hasScores = scoresByMatch[m.id] && Object.keys(scoresByMatch[m.id]).length > 0;
                // Build goal scorers summary
                let eventsSummary = '';
                if (hasScores) {
                    const allPlayers = Object.values(scoresByMatch[m.id]).flat();
                    const goalScorers = allPlayers.filter(p => p.goals > 0)
                        .map(p => `⚽ ${p.player_name}${p.goals > 1 ? ` ×${p.goals}` : ''}`)
                        .slice(0, 6);
                    const reds = allPlayers.filter(p => p.red_card).map(p => `🟥 ${p.player_name}`);
                    const events = [...goalScorers, ...reds];
                    if (events.length) eventsSummary = `<div style="font-size:.75rem;color:var(--text-secondary);padding:0 .75rem .3rem">${events.join(' · ')}</div>`;
                }
                return `
                <div class="match-accordion" style="border-bottom:1px solid var(--border)">
                    <div class="match-header" data-mid="${m.id}" style="padding:.75rem;display:flex;align-items:center;gap:1rem;cursor:${hasScores ? 'pointer' : 'default'}">
                        <span>${flagImg(m.home_flag)} <strong>${m.home_name}</strong></span>
                        <span style="font-size:1.3rem;font-weight:700;color:var(--accent-gold);min-width:50px;text-align:center">
                            ${m.score_home != null ? `${m.score_home} - ${m.score_away}` : 'vs'}
                        </span>
                        <span><strong>${m.away_name}</strong> ${flagImg(m.away_flag)}</span>
                        <span class="badge ${m.status === 'finished' ? 'badge-teal' : ''}" style="margin-left:auto;font-size:.75rem">${m.status}</span>
                        ${hasScores ? '<span style="color:var(--text-muted);font-size:.8rem">▼</span>' : ''}
                    </div>
                    ${eventsSummary}
                    <div class="match-detail" id="detail-${m.id}" style="display:none;padding:0 .75rem .75rem">
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
                            <div>
                                <div style="font-weight:600;margin-bottom:.5rem">${flagImg(m.home_flag)} ${m.home_name}</div>
                                ${renderMatchPlayers(m.id, m.home_country)}
                            </div>
                            <div>
                                <div style="font-weight:600;margin-bottom:.5rem">${flagImg(m.away_flag)} ${m.away_name}</div>
                                ${renderMatchPlayers(m.id, m.away_country)}
                            </div>
                        </div>
                    </div>
                </div>`;
            }).join('')}
        </div>

        <div class="card" id="fantasy-points-card">
            <div class="card-header">Puntos de equipos — ${md.name}</div>
            <div id="fantasy-points-body" style="color:var(--text-muted);padding:.5rem">Cargando...</div>
        </div>
    `;

    // Accordion toggle
    container.querySelectorAll('.match-header').forEach(header => {
        header.addEventListener('click', (e) => {
            const detail = document.getElementById('detail-' + header.dataset.mid);
            if (detail && detail.innerHTML.trim()) {
                detail.style.display = detail.style.display === 'none' ? 'block' : 'none';
            }
        });
    });

    // Load fantasy team points
    try {
        const fp = await API.get(`/scoring/matchdays/${mdId}/fantasy-points`);
        const fpBody = document.getElementById('fantasy-points-body');
        if (fp.length === 0 || fp.every(t => t.points === 0)) {
            fpBody.innerHTML = '<p style="color:var(--text-muted)">Sin puntuaciones todavía para esta jornada</p>';
        } else {
            fpBody.innerHTML = `
                <table>
                    <thead><tr><th>#</th><th>Equipo</th><th>Manager</th><th>Puntos</th></tr></thead>
                    <tbody>
                        ${fp.map((t, i) => `
                            <tr class="${t.team_id === API.getTeamId() ? 'rank-1' : ''}">
                                <td class="${i < 3 ? `rank-${i+1}` : ''}">${i + 1}</td>
                                <td><strong>${t.team_name}</strong></td>
                                <td>${t.display_name}</td>
                                <td style="font-weight:700;color:var(--accent-teal)">${t.points}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }
    } catch {}
}
