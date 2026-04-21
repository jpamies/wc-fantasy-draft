/* Standings page */
Router.register('#/standings', async (container) => {
    const leagueId = API.getLeagueId();
    const standings = await API.get(`/leagues/${leagueId}/standings`);

    container.innerHTML = `
        <h2 class="mb-2">📊 Clasificación</h2>
        <div class="card">
            <table>
                <thead>
                    <tr><th>#</th><th>Equipo</th><th>Manager</th><th>Puntos</th><th>Presupuesto</th></tr>
                </thead>
                <tbody>
                    ${standings.map((s, i) => `
                        <tr class="${s.team_id === API.getTeamId() ? 'rank-1' : ''}">
                            <td class="${i < 3 ? `rank-${i+1}` : ''}">${i + 1}</td>
                            <td><strong>${s.team_name}</strong></td>
                            <td>${s.owner_nick}</td>
                            <td style="font-weight:700;color:var(--accent-teal)">${s.total_points}</td>
                            <td class="money">${formatMoney(s.budget)}</td>
                        </tr>
                    `).join('')}
                    ${standings.length === 0 ? '<tr><td colspan="5" class="text-center" style="color:var(--text-muted)">Sin datos todavía</td></tr>' : ''}
                </tbody>
            </table>
        </div>
    `;
});
