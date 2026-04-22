/* Scoring page — matchday management and score entry */
Router.register('#/scoring', async (container) => {
    const matchdays = await API.get('/scoring/matchdays');
    const isComm = API.isCommissioner();

    container.innerHTML = `
        <div class="flex-between mb-2">
            <h2>⚽ Puntuación</h2>
            <div class="flex" style="gap:.5rem">
                ${isComm && matchdays.length === 0 ? '<button class="btn btn-primary" id="btn-populate-calendar">📅 Cargar Calendario WC2026</button>' : ''}
                ${isComm ? '<button class="btn btn-gold" id="btn-new-matchday">+ Crear Jornada</button>' : ''}
            </div>
        </div>

        ${matchdays.length === 0 ? `
            <div class="card text-center">
                <p style="color:var(--text-muted)">No hay jornadas creadas todavía.</p>
                ${isComm ? '<p style="font-size:.85rem;color:var(--text-secondary);margin-top:.5rem">Crea una jornada para empezar a registrar puntuaciones.</p>' : ''}
            </div>
        ` : `
            <div class="grid grid-2">
                ${matchdays.map(md => `
                    <div class="card" style="cursor:pointer" data-mdid="${md.id}">
                        <div class="flex-between">
                            <div class="card-header" style="margin:0">${md.name}</div>
                            <span class="badge ${md.status === 'completed' ? 'badge-teal' : 'badge-gold'}">${md.status}</span>
                        </div>
                        <div style="font-size:.85rem;color:var(--text-secondary)">${md.date || ''} · ${md.phase}</div>
                    </div>
                `).join('')}
            </div>
        `}
    `;

    // Click matchday to view detail
    container.querySelectorAll('[data-mdid]').forEach(card => {
        card.addEventListener('click', () => loadMatchday(container, card.dataset.mdid));
    });

    // Populate calendar
    document.getElementById('btn-populate-calendar')?.addEventListener('click', async () => {
        try {
            const res = await API.post('/scoring/populate-calendar');
            showToast(`Calendario cargado: ${res.matchdays_created} jornadas, ${res.matches_created} partidos`, 'success');
            Router.handleRoute();
        } catch (err) { showToast(err.message, 'error'); }
    });

    document.getElementById('btn-new-matchday')?.addEventListener('click', () => {
        showModal(`
            <div class="modal-title">Crear Jornada</div>
            <div class="form-group">
                <label>ID (ej: MD1)</label>
                <input type="text" id="md-id" required placeholder="MD1">
            </div>
            <div class="form-group">
                <label>Nombre</label>
                <input type="text" id="md-name" required placeholder="Jornada 1 — Fase de Grupos">
            </div>
            <div class="form-group">
                <label>Fecha</label>
                <input type="date" id="md-date">
            </div>
            <div class="flex">
                <button class="btn btn-gold" id="btn-create-md">Crear</button>
                <button class="btn btn-outline" onclick="closeModal()">Cancelar</button>
            </div>
        `);
        document.getElementById('btn-create-md').addEventListener('click', async () => {
            try {
                await API.post('/scoring/matchdays', {
                    id: document.getElementById('md-id').value,
                    name: document.getElementById('md-name').value,
                    date: document.getElementById('md-date').value || null,
                });
                showToast('Jornada creada', 'success');
                closeModal();
                Router.handleRoute();
            } catch (err) { showToast(err.message, 'error'); }
        });
    });
});

async function loadMatchday(container, mdId) {
    const md = await API.get(`/scoring/matchdays/${mdId}`);
    const isComm = API.isCommissioner();

    // Group scores by match_id and country
    const scoresByMatch = {};
    md.scores.forEach(s => {
        if (!scoresByMatch[s.match_id]) scoresByMatch[s.match_id] = {};
        if (!scoresByMatch[s.match_id][s.country_code]) scoresByMatch[s.match_id][s.country_code] = [];
        scoresByMatch[s.match_id][s.country_code].push(s);
    });

    function renderMatchPlayers(matchId, countryCode) {
        const players = (scoresByMatch[matchId]?.[countryCode] || [])
            .sort((a, b) => b.minutes_played - a.minutes_played || b.total_points - a.total_points);
        const starters = players.filter(p => p.minutes_played >= 60 || (p.minutes_played > 0 && p.minutes_played < 60 && players.filter(x => x.minutes_played >= 60).length < 11));
        // Simple: top 11 by minutes = starters, rest = subs
        const sorted = [...players].sort((a, b) => b.minutes_played - a.minutes_played);
        const starting = sorted.slice(0, 11);
        const subs = sorted.slice(11);

        function playerRow(p) {
            return `<div style="display:flex;align-items:center;gap:.5rem;padding:.3rem 0;font-size:.85rem">
                ${posBadge(p.position)}
                <span style="flex:1">${p.player_name}</span>
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

    container.innerHTML = `
        <div class="flex-between mb-2">
            <div>
                <a href="#/scoring" style="font-size:.85rem">← Volver</a>
                <h2>${md.name}</h2>
            </div>
            <div class="flex" style="gap:.5rem;align-items:center">
                <span class="badge ${md.status === 'completed' ? 'badge-teal' : 'badge-gold'}">${md.status}</span>
                ${isComm && md.status !== 'completed' ? `<button class="btn btn-sm btn-outline" id="btn-simulate">🎲 Simular</button>` : ''}
                ${isComm ? `<button class="btn btn-sm btn-primary" id="btn-add-match">+ Partido</button>` : ''}
            </div>
        </div>

        <div class="card mb-2">
            <div class="card-header">Partidos</div>
            ${md.matches.length === 0 ? '<p style="color:var(--text-muted)">Sin partidos</p>' : ''}
            ${md.matches.map(m => {
                const hasScores = scoresByMatch[m.id] && Object.keys(scoresByMatch[m.id]).length > 0;
                return `
                <div class="match-accordion" style="border-bottom:1px solid var(--border)">
                    <div class="match-header" data-mid="${m.id}" style="padding:.75rem;display:flex;align-items:center;gap:1rem;cursor:${hasScores ? 'pointer' : 'default'}">
                        <span>${m.home_flag} <strong>${m.home_name}</strong></span>
                        <span style="font-size:1.3rem;font-weight:700;color:var(--accent-gold);min-width:50px;text-align:center">
                            ${m.score_home != null ? `${m.score_home} - ${m.score_away}` : 'vs'}
                        </span>
                        <span><strong>${m.away_name}</strong> ${m.away_flag}</span>
                        <span class="badge ${m.status === 'finished' ? 'badge-teal' : 'badge-gold'}" style="margin-left:auto;font-size:.75rem">${m.status}</span>
                        ${hasScores ? '<span style="color:var(--text-muted);font-size:.8rem">▼</span>' : ''}
                        ${isComm && m.status !== 'finished' ? `<button class="btn btn-sm btn-outline result-btn" data-mid="${m.id}" style="font-size:.75rem">Resultado</button>` : ''}
                        ${isComm ? `<button class="btn btn-sm btn-primary scores-btn" data-mid="${m.id}" data-home="${m.home_country}" data-away="${m.away_country}" style="font-size:.75rem">Scores</button>` : ''}
                    </div>
                    <div class="match-detail" id="detail-${m.id}" style="display:none;padding:0 .75rem .75rem">
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
                            <div>
                                <div style="font-weight:600;margin-bottom:.5rem">${m.home_flag} ${m.home_name}</div>
                                ${renderMatchPlayers(m.id, m.home_country)}
                            </div>
                            <div>
                                <div style="font-weight:600;margin-bottom:.5rem">${m.away_name} ${m.away_flag}</div>
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
            if (e.target.closest('.btn')) return; // Don't toggle when clicking buttons
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

    // Simulate scores
    document.getElementById('btn-simulate')?.addEventListener('click', async () => {
        if (!confirm('¿Simular puntuaciones aleatorias para esta jornada?')) return;
        try {
            await API.post(`/scoring/matchdays/${mdId}/simulate`);
            showToast('Puntuaciones simuladas', 'success');
            loadMatchday(container, mdId);
        } catch (err) { showToast(err.message, 'error'); }
    });

    // Add match
    document.getElementById('btn-add-match')?.addEventListener('click', async () => {
        const countries = await API.get('/countries');
        showModal(`
            <div class="modal-title">Añadir Partido</div>
            <div class="form-group">
                <label>ID partido</label>
                <input type="text" id="match-id" placeholder="ESP-CRC">
            </div>
            <div class="form-group">
                <label>Local</label>
                <select id="match-home">${countries.map(c => `<option value="${c.code}">${c.flag} ${c.name}</option>`).join('')}</select>
            </div>
            <div class="form-group">
                <label>Visitante</label>
                <select id="match-away">${countries.map(c => `<option value="${c.code}">${c.flag} ${c.name}</option>`).join('')}</select>
            </div>
            <button class="btn btn-gold" id="btn-confirm-match">Añadir</button>
        `);
        document.getElementById('btn-confirm-match').addEventListener('click', async () => {
            try {
                await API.post(`/scoring/matchdays/${mdId}/matches`, {
                    id: document.getElementById('match-id').value,
                    home_country: document.getElementById('match-home').value,
                    away_country: document.getElementById('match-away').value,
                });
                closeModal();
                showToast('Partido añadido', 'success');
                loadMatchday(container, mdId);
            } catch (err) { showToast(err.message, 'error'); }
        });
    });

    // Match result
    container.querySelectorAll('.result-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            showModal(`
                <div class="modal-title">Resultado</div>
                <div class="flex" style="justify-content:center;gap:1rem;margin:1rem 0">
                    <input type="number" id="res-home" min="0" value="0" style="width:60px;text-align:center;font-size:1.5rem">
                    <span style="font-size:1.5rem">-</span>
                    <input type="number" id="res-away" min="0" value="0" style="width:60px;text-align:center;font-size:1.5rem">
                </div>
                <button class="btn btn-gold" id="btn-save-result" style="width:100%">Guardar</button>
            `);
            document.getElementById('btn-save-result').addEventListener('click', async () => {
                try {
                    await API.patch(`/scoring/matches/${btn.dataset.mid}/result`, {
                        score_home: parseInt(document.getElementById('res-home').value),
                        score_away: parseInt(document.getElementById('res-away').value),
                    });
                    closeModal();
                    showToast('Resultado guardado', 'success');
                    loadMatchday(container, mdId);
                } catch (err) { showToast(err.message, 'error'); }
            });
        });
    });

    // Enter scores
    container.querySelectorAll('.scores-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const home = btn.dataset.home;
            const away = btn.dataset.away;
            const matchId = btn.dataset.mid;
            const homePlayers = await API.get(`/players?country=${home}&limit=50`);
            const awayPlayers = await API.get(`/players?country=${away}&limit=50`);
            const allPlayers = [...homePlayers, ...awayPlayers];

            showModal(`
                <div class="modal-title">Puntuaciones — ${home} vs ${away}</div>
                <div style="max-height:60vh;overflow-y:auto">
                    <table style="font-size:.8rem">
                        <thead><tr><th>Jugador</th><th>Min</th><th>Gol</th><th>Asist</th><th>TA</th><th>TR</th><th>MVP</th></tr></thead>
                        <tbody>
                            ${allPlayers.slice(0, 50).map(p => `
                                <tr data-pid="${p.id}">
                                    <td>${p.name} <small>${p.country_code}</small></td>
                                    <td><input type="number" class="sc-min" min="0" max="120" value="0" style="width:45px"></td>
                                    <td><input type="number" class="sc-goals" min="0" value="0" style="width:35px"></td>
                                    <td><input type="number" class="sc-assists" min="0" value="0" style="width:35px"></td>
                                    <td><input type="number" class="sc-yc" min="0" max="2" value="0" style="width:35px"></td>
                                    <td><input type="checkbox" class="sc-rc"></td>
                                    <td><input type="checkbox" class="sc-mvp"></td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
                <button class="btn btn-gold mt-1" id="btn-submit-scores" style="width:100%">Guardar puntuaciones</button>
            `);

            document.getElementById('btn-submit-scores').addEventListener('click', async () => {
                const rows = document.querySelectorAll('#modal-content tr[data-pid]');
                const scores = [];
                rows.forEach(row => {
                    const min = parseInt(row.querySelector('.sc-min').value) || 0;
                    if (min > 0) {
                        scores.push({
                            player_id: row.dataset.pid,
                            minutes_played: min,
                            goals: parseInt(row.querySelector('.sc-goals').value) || 0,
                            assists: parseInt(row.querySelector('.sc-assists').value) || 0,
                            yellow_cards: parseInt(row.querySelector('.sc-yc').value) || 0,
                            red_card: row.querySelector('.sc-rc').checked,
                            is_mvp: row.querySelector('.sc-mvp').checked,
                        });
                    }
                });
                try {
                    await API.post(`/scoring/matchdays/${mdId}/scores`, { match_id: matchId, scores });
                    closeModal();
                    showToast(`${scores.length} puntuaciones guardadas`, 'success');
                    loadMatchday(container, mdId);
                } catch (err) { showToast(err.message, 'error'); }
            });
        });
    });
}
