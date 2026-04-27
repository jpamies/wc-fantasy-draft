/* League admin page — market window management */
Router.register('#/admin/market', async (container) => {
    const leagueId = API.getLeagueId();
    const currentTeam = API.getCurrentTeam();

    // Check if commissioner
    if (!currentTeam?.is_commissioner) {
        container.innerHTML = '<div class="card text-center"><p>❌ Solo el comisionado puede acceder a esta página</p></div>';
        return;
    }

    try {
        container.innerHTML = `
            <div class="flex-between mb-2">
                <h2>⚙️ Control de Mercados</h2>
            </div>

            <div class="grid grid-2 mb-2">
                <div class="card">
                    <div class="card-header">➕ Crear Nuevo Mercado</div>
                    <p style="color:var(--text-muted);font-size:.85rem;margin-bottom:.75rem">
                        🕐 Todas las horas se interpretan como <strong>hora de Madrid</strong> (Europe/Madrid).
                    </p>
                    <div class="form-group">
                        <label>Fase</label>
                        <input type="text" id="phase" placeholder="ej: Mercado_1_R32" required>
                    </div>
                    <div class="form-group">
                        <label>Tipo de Mercado</label>
                        <input type="text" id="market-type" placeholder="ej: R32 / 1/16" required>
                    </div>
                    <div class="form-group">
                        <label>Inicio Protección (ISO DateTime)</label>
                        <input type="datetime-local" id="clause-start" required>
                    </div>
                    <div class="form-group">
                        <label>Fin Protección</label>
                        <input type="datetime-local" id="clause-end" required>
                    </div>
                    <div class="form-group">
                        <label>Inicio Mercado</label>
                        <input type="datetime-local" id="market-start" required>
                    </div>
                    <div class="form-group">
                        <label>Fin Mercado</label>
                        <input type="datetime-local" id="market-end" required>
                    </div>
                    <div class="form-group">
                        <label>Inicio Reposición</label>
                        <input type="datetime-local" id="reposition-start" required>
                    </div>
                    <div class="form-group">
                        <label>Fin Reposición</label>
                        <input type="datetime-local" id="reposition-end" required>
                    </div>
                    <div class="grid grid-2">
                        <div class="form-group">
                            <label>Max Compras</label>
                            <input type="number" id="max-buys" value="3" min="1">
                        </div>
                        <div class="form-group">
                            <label>Max Robos</label>
                            <input type="number" id="max-sells" value="3" min="1">
                        </div>
                    </div>
                    <button class="btn btn-primary" id="btn-create-market" style="width:100%">Crear Mercado</button>
                </div>

                <div id="markets-list"></div>
            </div>

            <div class="card mb-2">
                <div class="card-header">🔧 Acciones rápidas</div>
                <div class="grid grid-2">
                    <button class="btn btn-secondary" id="btn-fix-bot-lineups">
                        🤖 Arreglar alineaciones de bots
                    </button>
                    <button class="btn btn-secondary" id="btn-force-market-tick">
                        ⏱️ Forzar avance de fase de mercado
                    </button>
                </div>
                <p style="color:var(--text-muted);font-size:.85rem;margin-top:.5rem">
                    Las alineaciones se aplican a los bots con 23 jugadores pero sin titulares (problema histórico).
                    El forzado de fase ejecuta la transición ahora si el deadline ya pasó.
                </p>
            </div>
        `;

        // Load markets list
        await loadMarketsList(leagueId);

        // Create market button
        document.getElementById('btn-create-market').addEventListener('click', async () => {
            const data = {
                phase: document.getElementById('phase').value,
                market_type: document.getElementById('market-type').value,
                // Send naive local datetime strings — backend interprets them as Europe/Madrid
                clause_window_start: document.getElementById('clause-start').value,
                clause_window_end: document.getElementById('clause-end').value,
                market_window_start: document.getElementById('market-start').value,
                market_window_end: document.getElementById('market-end').value,
                reposition_draft_start: document.getElementById('reposition-start').value,
                reposition_draft_end: document.getElementById('reposition-end').value,
                max_buys: parseInt(document.getElementById('max-buys').value),
                max_sells: parseInt(document.getElementById('max-sells').value),
            };

            try {
                const result = await API.post(`/leagues/${leagueId}/admin/market-windows`, data);
                showToast('Mercado creado', 'success');
                await loadMarketsList(leagueId);
            } catch (err) {
                showToast(err.message, 'error');
            }
        });

        document.getElementById('btn-fix-bot-lineups').addEventListener('click', async () => {
            try {
                const r = await API.post(`/leagues/${leagueId}/admin/auto-lineup-bots`, {});
                showToast(`Alineaciones aplicadas a ${r.bots_lineup_set} bots`, 'success');
            } catch (err) {
                showToast(err.message, 'error');
            }
        });

        document.getElementById('btn-force-market-tick').addEventListener('click', async () => {
            try {
                const r = await API.post(`/leagues/${leagueId}/admin/market-tick`, {});
                showToast(r.transitions > 0 ? `Avance: ${r.transitions} ventana(s)` : 'No hay transiciones pendientes', 'success');
            } catch (err) {
                showToast(err.message, 'error');
            }
        });
    } catch (err) {
        container.innerHTML = `<div class="card text-center"><p>Error: ${err.message}</p></div>`;
        console.error(err);
    }
});

async function loadMarketsList(leagueId) {
    try {
        const container = document.getElementById('markets-list');
        if (!container) return;

        const windows = await API.get(`/leagues/${leagueId}/market-windows`);

        const statusBadge = (s) => {
            const map = {
                pending: { cls: 'badge-gold', txt: 'Pendiente' },
                clause_window: { cls: 'badge-teal', txt: 'Cláusulas' },
                market_open: { cls: 'badge-teal', txt: 'Abierto' },
                market_closed: { cls: 'badge-gold', txt: 'Cerrado' },
                reposition_draft: { cls: 'badge-teal', txt: 'Reposición' },
                completed: { cls: 'badge-muted', txt: 'Finalizado' },
            };
            const m = map[s] || { cls: 'badge-muted', txt: s };
            return `<span class="badge ${m.cls}">${m.txt}</span>`;
        };

        container.innerHTML = `
            <div class="card">
                <div class="card-header">📊 Mercados</div>
                ${windows.length === 0 ? '<p style="color:var(--text-muted)">No hay mercados creados.</p>' : `
                <table style="width:100%;font-size:.85rem">
                    <thead><tr><th>Fase</th><th>Tipo</th><th>Estado</th><th>Inicio</th><th>Acciones</th></tr></thead>
                    <tbody>
                    ${windows.map(w => `
                        <tr>
                            <td>${w.phase}</td>
                            <td>${w.market_type || '—'}</td>
                            <td>${statusBadge(w.status)}</td>
                            <td>${formatMadrid(w.clause_window_start)}</td>
                            <td>
                                ${['market_open','market_closed','reposition_draft'].includes(w.status) ? `
                                    <button class="btn btn-sm btn-secondary btn-rewind-clause" data-wid="${w.id}">
                                        ⏪ Rebobinar a Cláusulas
                                    </button>
                                ` : ''}
                                <a href="#/market/${w.id}" class="btn btn-sm btn-outline">Ver</a>
                            </td>
                        </tr>
                    `).join('')}
                    </tbody>
                </table>
                `}
            </div>
        `;

        container.querySelectorAll('.btn-rewind-clause').forEach(btn => {
            btn.addEventListener('click', async () => {
                if (!confirm('¿Rebobinar este mercado a la fase de Cláusulas? Se borrarán los picks del draft de reposición y los deadlines avanzarán 24h.')) return;
                try {
                    await API.post(`/leagues/${leagueId}/admin/market-windows/${btn.dataset.wid}/rewind-to-clause`, {});
                    showToast('Mercado rebobinado a fase de Cláusulas', 'success');
                    await loadMarketsList(leagueId);
                } catch (err) {
                    showToast(err.message, 'error');
                }
            });
        });
    } catch (err) {
        console.error(err);
    }
}
