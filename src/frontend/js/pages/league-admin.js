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
        `;

        // Load markets list
        await loadMarketsList(leagueId);

        // Create market button
        document.getElementById('btn-create-market').addEventListener('click', async () => {
            const data = {
                phase: document.getElementById('phase').value,
                market_type: document.getElementById('market-type').value,
                clause_window_start: new Date(document.getElementById('clause-start').value).toISOString(),
                clause_window_end: new Date(document.getElementById('clause-end').value).toISOString(),
                market_window_start: new Date(document.getElementById('market-start').value).toISOString(),
                market_window_end: new Date(document.getElementById('market-end').value).toISOString(),
                reposition_draft_start: new Date(document.getElementById('reposition-start').value).toISOString(),
                reposition_draft_end: new Date(document.getElementById('reposition-end').value).toISOString(),
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

    } catch (err) {
        container.innerHTML = `<div class="card text-center"><p>Error: ${err.message}</p></div>`;
        console.error(err);
    }
});

async function loadMarketsList(leagueId) {
    try {
        // This would require an endpoint to list market windows
        // For now, show placeholder
        const container = document.getElementById('markets-list');
        if (!container) return;

        container.innerHTML = `
            <div class="card">
                <div class="card-header">📊 Mercados Activos</div>
                <p style="color:var(--text-muted)">
                    💡 Para gestionar mercados activos, accede desde la página de liga.
                </p>
                <div style="background:var(--bg-secondary);padding:1rem;border-radius:4px;font-size:.85rem">
                    <p><strong>Estados disponibles:</strong></p>
                    <ul style="margin-left:1rem;margin-top:.5rem">
                        <li>pending — Mercado creado, aún sin iniciar</li>
                        <li>clause_window — Fase de protección de cláusulas abierta</li>
                        <li>market_open — Mercado en transacciones</li>
                        <li>reposition_draft — Draft de reposición en curso</li>
                        <li>completed — Mercado finalizado</li>
                    </ul>
                </div>
            </div>
        `;
    } catch (err) {
        console.error(err);
    }
}
