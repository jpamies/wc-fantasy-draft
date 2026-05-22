/* Player detail page — stats from simulator + fantasy points */
Router.register('#/player/:id', async (container, params) => {
    const playerId = params.id;

    let data;
    try {
        data = await API.get(`/players/${playerId}/stats`);
    } catch {
        container.innerHTML = '<div class="card text-center"><p style="color:var(--text-muted)">Jugador no encontrado</p></div>';
        return;
    }

    const p = data.player || {};
    const sim = data.sim_stats || {};
    const cs = sim.summary || {};
    const matchHistory = sim.matches || [];
    const fantasyScores = data.fantasy_scores || [];
    const hasStats = (cs.matches || 0) > 0;
    const totalFantasyPts = fantasyScores.reduce((s, fs) => s + (fs.total_points || 0), 0);
    const avgFantasyPts = fantasyScores.length > 0 ? (totalFantasyPts / fantasyScores.length).toFixed(1) : '—';

    const TAB_LABELS = {GS1:'J1',GS2:'J2',GS3:'J3',R32:'1/32',R16:'1/16',QF:'1/4',SF:'1/2',FINAL:'Final'};

    function flagImg(flag) {
        if (!flag) return '';
        if (typeof flag === 'string' && flag.startsWith('http')) return `<img src="${flag}" alt="" style="height:20px;vertical-align:middle">`;
        return flag;
    }

    const attrs = [
        { label: 'Ritmo', key: 'pace', color: '#2dd4bf' },
        { label: 'Disparo', key: 'shooting', color: '#f59e0b' },
        { label: 'Pase', key: 'passing', color: '#818cf8' },
        { label: 'Regate', key: 'dribbling', color: '#34d399' },
        { label: 'Defensa', key: 'defending', color: '#60a5fa' },
        { label: 'Físico', key: 'physic', color: '#f472b6' },
    ];

    container.innerHTML = `
        <div style="margin-bottom:1rem">
            <a href="javascript:history.back()" style="font-size:.85rem;color:var(--text-secondary)">← Volver</a>
        </div>

        <div class="card mb-2" style="display:flex;gap:1.5rem;align-items:center;flex-wrap:wrap">
            <div style="position:relative;flex-shrink:0">
                <img src="${p.photo || ''}" alt="" style="width:100px;height:100px;border-radius:50%;object-fit:cover;border:3px solid var(--accent-gold)"
                     referrerpolicy="no-referrer" onerror="this.style.display='none'">
                ${p.strength ? `<div style="position:absolute;bottom:0;right:0;background:var(--accent-gold);color:#000;font-weight:800;font-size:.9rem;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center">${p.strength}</div>` : ''}
            </div>
            <div style="flex:1;min-width:200px">
                <h2 style="margin:0 0 .3rem">${p.name || 'Jugador'}</h2>
                <div style="display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;font-size:.9rem;color:var(--text-secondary)">
                    ${flagImg(p.flag)} <span>${p.country_name || p.country_code || ''}</span>
                    <span>·</span> ${posBadge(p.position || 'MID')} <span>${p.detailed_position || p.position || ''}</span>
                </div>
                <div style="font-size:.85rem;color:var(--text-muted);margin-top:.3rem">${p.club || ''} ${p.league ? `· ${p.league}` : ''}</div>
                <div style="display:flex;gap:1rem;margin-top:.5rem;flex-wrap:wrap">
                    <div><span style="font-size:.75rem;color:var(--text-muted)">Edad</span><br><strong>${p.age || '—'}</strong></div>
                    <div><span style="font-size:.75rem;color:var(--text-muted)">Valor</span><br><strong class="money">${formatMoney(p.market_value || 0)}</strong></div>
                    <div><span style="font-size:.75rem;color:var(--text-muted)">Fantasy Pts</span><br><strong style="color:var(--accent-teal)">${totalFantasyPts}</strong></div>
                    <div><span style="font-size:.75rem;color:var(--text-muted)">Media</span><br><strong style="color:var(--accent-teal)">${avgFantasyPts}</strong></div>
                </div>
            </div>
        </div>

        ${attrs.some(a => p[a.key] != null) ? `
        <div class="card mb-2">
            <div class="card-header">Atributos</div>
            <div style="display:grid;gap:.5rem">
                ${attrs.map(a => {
                    const val = p[a.key];
                    if (val == null) return '';
                    return `
                    <div style="display:flex;align-items:center;gap:.5rem">
                        <span style="width:70px;font-size:.8rem;color:var(--text-secondary)">${a.label}</span>
                        <div style="flex:1;height:8px;background:var(--bg-tertiary);border-radius:4px;overflow:hidden">
                            <div style="width:${val}%;height:100%;background:${a.color};border-radius:4px"></div>
                        </div>
                        <span style="width:28px;font-size:.85rem;font-weight:700;color:${a.color};text-align:right">${val}</span>
                    </div>`;
                }).join('')}
            </div>
        </div>
        ` : ''}

        ${hasStats ? `
        <div class="card mb-2">
            <div class="card-header">Estadísticas del Torneo</div>
            <div style="display:flex;flex-wrap:wrap;gap:.8rem;justify-content:center">
                ${[
                    ['Partidos', cs.matches],
                    ['Titular', cs.starts],
                    ['Minutos', cs.minutes],
                    ['Goles', cs.goals],
                    ['Asist.', cs.assists],
                    ['Media', cs.avg_rating],
                    ['🟨', cs.yellows],
                    ['🟥', cs.reds],
                    ...(p.position === 'GK' ? [['Paradas', cs.saves], ['GC', cs.goals_conceded], ['Imbatido', cs.clean_sheets]] : []),
                ].map(([label, val]) => `
                    <div style="text-align:center;min-width:55px">
                        <div style="font-size:1.2rem;font-weight:700">${val ?? '—'}</div>
                        <div style="font-size:.7rem;color:var(--text-muted)">${label}</div>
                    </div>
                `).join('')}
            </div>
        </div>
        ` : ''}

        ${fantasyScores.length > 0 ? `
        <div class="card mb-2">
            <div class="card-header">Puntos Fantasy por Jornada</div>
            <div style="display:flex;gap:.3rem;flex-wrap:wrap;justify-content:center">
                ${fantasyScores.map(fs => {
                    const label = TAB_LABELS[fs.matchday_id] || fs.matchday_id;
                    const pts = fs.total_points || 0;
                    const bg = pts >= 8 ? 'var(--accent-green)' : pts >= 4 ? 'var(--accent-teal)' : pts >= 0 ? 'var(--accent-gold)' : 'var(--accent-red)';
                    return `
                    <div style="text-align:center;padding:.4rem .6rem;border-radius:8px;background:var(--bg-secondary);min-width:50px">
                        <div style="font-size:1.1rem;font-weight:700;color:${bg}">${pts}</div>
                        <div style="font-size:.65rem;color:var(--text-muted)">${label}</div>
                        <div style="font-size:.6rem;color:var(--text-muted)">
                            ${fs.goals > 0 ? `⚽${fs.goals}` : ''} ${fs.assists > 0 ? `🅰️${fs.assists}` : ''} ${fs.yellow_cards > 0 ? '🟨' : ''} ${fs.red_card > 0 ? '🟥' : ''}
                        </div>
                    </div>`;
                }).join('')}
            </div>
        </div>
        ` : ''}

        ${matchHistory.length > 0 ? `
        <div class="card">
            <div class="card-header">Historial de Partidos</div>
            ${matchHistory.map(m => {
                const ratingColor = m.rating >= 7.5 ? 'var(--accent-green)' : m.rating >= 6.5 ? 'var(--accent-gold)' : 'var(--text-muted)';
                return `
                <div style="display:flex;align-items:center;gap:.5rem;padding:.4rem 0;border-bottom:1px solid var(--border);font-size:.85rem">
                    <span style="font-weight:700;min-width:35px">${m.score_home}-${m.score_away}</span>
                    <span style="flex:1;font-size:.8rem;color:var(--text-secondary)">${m.home_team} vs ${m.away_team}</span>
                    ${m.goals ? `<span>⚽×${m.goals}</span>` : ''}
                    ${m.assists ? `<span>🅰️×${m.assists}</span>` : ''}
                    ${m.yellow_cards ? '<span>🟨</span>' : ''}${m.red_card ? '<span>🟥</span>' : ''}
                    ${m.saves ? `<span style="font-size:.75rem">${m.saves}sv</span>` : ''}
                    <span style="font-size:.75rem;color:var(--text-muted)">${m.minutes_played}'</span>
                    <span style="font-weight:700;color:${ratingColor};min-width:28px;text-align:right">${m.rating || '—'}</span>
                </div>`;
            }).join('')}
        </div>
        ` : ''}
    `;
});
