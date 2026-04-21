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
    const leagueId = API.getLeagueId();

    container.innerHTML = `
        <div class="flex-between mb-2">
            <div>
                <a href="#/scoring" style="font-size:.85rem">← Volver</a>
                <h2>${md.name}</h2>
            </div>
            <span class="badge ${md.status === 'completed' ? 'badge-teal' : 'badge-gold'}">${md.status}</span>
        </div>

        <div class="card mb-2">
            <div class="flex-between mb-1">
                <div class="card-header" style="margin:0">Partidos</div>
                <div class="flex" style="gap:.5rem">
                    ${isComm && md.status !== 'completed' ? `<button class="btn btn-sm btn-outline" id="btn-simulate" title="Simular puntuaciones aleatorias para testing">🎲 Simular</button>` : ''}
                    ${isComm ? `<button class="btn btn-sm btn-primary" id="btn-add-match">+ Añadir partido</button>` : ''}
                </div>
            </div>
            ${md.matches.length === 0 ? '<p style="color:var(--text-muted)">Sin partidos</p>' : ''}
            ${md.matches.map(m => `
                <div style="padding:.6rem;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:1rem">
                    <span>${m.home_flag} <strong>${m.home_name}</strong></span>
                    <span style="font-size:1.2rem;font-weight:700;color:var(--accent-gold)">
                        ${m.score_home != null ? `${m.score_home} - ${m.score_away}` : 'vs'}
                    </span>
                    <span><strong>${m.away_name}</strong> ${m.away_flag}</span>
                    <span class="badge ${m.status === 'finished' ? 'badge-teal' : 'badge-gold'}" style="margin-left:auto">${m.status}</span>
                    ${isComm && m.status !== 'finished' ? `
                        <button class="btn btn-sm btn-outline result-btn" data-mid="${m.id}" data-home="${m.home_country}" data-away="${m.away_country}">Resultado</button>
                    ` : ''}
                    ${isComm ? `<button class="btn btn-sm btn-primary scores-btn" data-mid="${m.id}" data-home="${m.home_country}" data-away="${m.away_country}">Scores</button>` : ''}
                </div>
            `).join('')}
        </div>

        ${md.scores.length > 0 ? `
        <div class="card">
            <div class="card-header">Puntuaciones</div>
            <table>
                <thead><tr><th>Jugador</th><th>Pos</th><th>Min</th><th>Goles</th><th>Asist</th><th>TA</th><th>Puntos</th></tr></thead>
                <tbody>
                    ${md.scores.map(s => `
                        <tr>
                            <td>${s.player_name} <small style="color:var(--text-muted)">${s.country_code}</small></td>
                            <td>${posBadge(s.position)}</td>
                            <td>${s.minutes_played}'</td>
                            <td>${s.goals || ''}</td>
                            <td>${s.assists || ''}</td>
                            <td>${s.yellow_cards ? '🟨' : ''}${s.red_card ? '🟥' : ''}</td>
                            <td style="font-weight:700;color:var(--accent-teal)">${s.total_points}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
        ` : ''}
    `;

    // Simulate scores
    document.getElementById('btn-simulate')?.addEventListener('click', async () => {
        if (!confirm('¿Simular puntuaciones aleatorias para esta jornada? Los resultados existentes se sobrescribirán.')) return;
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
        btn.addEventListener('click', () => {
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
        btn.addEventListener('click', async () => {
            const home = btn.dataset.home;
            const away = btn.dataset.away;
            const matchId = btn.dataset.mid;
            // Get players from both countries
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
