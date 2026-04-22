/* Market page */
Router.register('#/market', async (container) => {
    const leagueId = API.getLeagueId();
    const data = await API.get(`/leagues/${leagueId}/market`);

    container.innerHTML = `
        <div class="flex-between mb-2">
            <h2>🏪 Mercado de Traspasos</h2>
            <span class="badge ${data.window_open ? 'badge-teal' : 'badge-gold'}">
                <span class="status-dot ${data.window_open ? 'status-active' : 'status-closed'}"></span>
                ${data.window_open ? 'Ventana abierta' : 'Ventana cerrada'}
            </span>
        </div>

        ${!data.window_open ? '<div class="card text-center mb-2"><p style="color:var(--text-muted)">La ventana de traspasos está cerrada. El comisionado debe abrirla.</p></div>' : ''}

        <div class="grid grid-2">
            <div class="card">
                <div class="card-header">Agentes libres (${data.free_agents.length})</div>
                <div style="max-height:500px;overflow-y:auto">
                    ${data.free_agents.map(p => `
                        <div class="player-card">
                            <img src="${p.photo}" alt="" onerror="this.style.display='none'">
                            <div class="player-info">
                                <div class="player-name">${p.name}</div>
                                <div class="player-meta">${p.country_code} · ${p.club}</div>
                            </div>
                            ${posBadge(p.position)}
                            <div class="player-value">${formatMoney(p.market_value)}</div>
                            ${data.window_open ? `<button class="btn btn-sm btn-primary bid-btn" data-pid="${p.id}" data-name="${p.name}" data-value="${p.market_value}">Pujar</button>` : ''}
                        </div>
                    `).join('')}
                </div>
            </div>

            <div>
                <div class="card mb-2">
                    <div class="card-header">🔥 Clausulazo</div>
                    <p style="font-size:.85rem;color:var(--text-secondary);margin-bottom:.75rem">
                        Paga la cláusula de rescisión (1.5× valor de mercado) para fichar un jugador de otro equipo al instante.
                    </p>
                    ${data.window_open ? `
                    <div class="form-group">
                        <label>ID del jugador</label>
                        <input type="text" id="clause-player" placeholder="ej: ESP-001">
                    </div>
                    <button class="btn btn-danger" id="btn-clause">⚡ Ejecutar clausulazo</button>
                    ` : '<p style="color:var(--text-muted)">Ventana cerrada</p>'}
                </div>

                <div class="card mb-2">
                    <div class="card-header">Ofertas pendientes</div>
                    ${data.pending_offers.length === 0 ? '<p style="color:var(--text-muted)">Sin ofertas pendientes</p>' : ''}
                    ${data.pending_offers.map(o => `
                        <div style="padding:.5rem;border-bottom:1px solid var(--border)">
                            <div><strong>${o.player_name}</strong> — ${formatMoney(o.amount)}</div>
                            <div style="font-size:.8rem;color:var(--text-muted)">${o.type} · ${o.status}</div>
                            ${o.to_team_id === API.getTeamId() && o.status === 'pending' ? `
                                <div class="flex mt-1">
                                    <button class="btn btn-sm btn-primary accept-btn" data-oid="${o.id}">Aceptar</button>
                                    <button class="btn btn-sm btn-danger reject-btn" data-oid="${o.id}">Rechazar</button>
                                </div>
                            ` : ''}
                        </div>
                    `).join('')}
                </div>

                <div class="card">
                    <div class="card-header">Traspasos recientes</div>
                    ${data.recent_transfers.length === 0 ? '<p style="color:var(--text-muted)">Sin traspasos</p>' : ''}
                    ${data.recent_transfers.map(t => `
                        <div style="padding:.4rem;border-bottom:1px solid var(--border);font-size:.85rem">
                            <strong>${t.player_name}</strong> — ${t.type} — ${formatMoney(t.amount)}
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
    `;

    // Clausulazo
    document.getElementById('btn-clause')?.addEventListener('click', async () => {
        const pid = document.getElementById('clause-player')?.value?.trim();
        if (!pid) return showToast('Introduce el ID del jugador', 'error');
        try {
            const res = await API.post(`/leagues/${leagueId}/market/clause`, { player_id: pid });
            showToast(`¡Clausulazo! ${res.player_name} por ${formatMoney(res.amount)}`, 'success');
            Router.handleRoute();
        } catch (err) { showToast(err.message, 'error'); }
    });

    // Bid buttons
    container.querySelectorAll('.bid-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const pid = btn.dataset.pid;
            const name = btn.dataset.name;
            const val = parseInt(btn.dataset.value);
            showModal(`
                <div class="modal-title">Pujar por ${name}</div>
                <p style="margin-bottom:1rem;color:var(--text-secondary)">Valor de mercado: ${formatMoney(val)}</p>
                <div class="form-group">
                    <label>Tu puja (fantasillones)</label>
                    <input type="number" id="bid-amount" value="${val}" min="1">
                </div>
                <div class="flex">
                    <button class="btn btn-primary" id="btn-confirm-bid">Pujar</button>
                    <button class="btn btn-outline" onclick="closeModal()">Cancelar</button>
                </div>
            `);
            document.getElementById('btn-confirm-bid').addEventListener('click', async () => {
                const amount = parseInt(document.getElementById('bid-amount').value);
                try {
                    await API.post(`/leagues/${leagueId}/market/bid`, { player_id: pid, amount });
                    showToast('Puja registrada', 'success');
                    closeModal();
                    Router.handleRoute();
                } catch (err) { showToast(err.message, 'error'); }
            });
        });
    });

    // Accept/reject offers
    container.querySelectorAll('.accept-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            try {
                await API.post(`/leagues/${leagueId}/market/offer/${btn.dataset.oid}/respond`, { action: 'accept' });
                showToast('Oferta aceptada', 'success');
                Router.handleRoute();
            } catch (err) { showToast(err.message, 'error'); }
        });
    });
    container.querySelectorAll('.reject-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            try {
                await API.post(`/leagues/${leagueId}/market/offer/${btn.dataset.oid}/respond`, { action: 'reject' });
                showToast('Oferta rechazada', 'info');
                Router.handleRoute();
            } catch (err) { showToast(err.message, 'error'); }
        });
    });
});
