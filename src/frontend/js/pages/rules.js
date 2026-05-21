/* Rules page — game rules and scoring system */
Router.register('#/rules', async (container) => {
    container.innerHTML = `
        <div class="flex-between mb-2">
            <h2>📖 Reglas del Juego</h2>
        </div>

        <div class="flex mb-2" style="gap:.5rem;border-bottom:2px solid var(--border);padding-bottom:.5rem">
            <button class="btn btn-gold rules-tab" data-tab="rules">📋 Reglas</button>
            <button class="btn btn-outline rules-tab" data-tab="scoring">⚽ Puntuación</button>
        </div>

        <div id="rules-content"></div>
    `;

    const rulesHTML = `
        <div class="card mb-2">
            <div class="card-header">1. Formato actual (resumen)</div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem">
                <div>
                    <h4 style="color:var(--accent-gold)">Equipo fantasy</h4>
                    <ul style="font-size:.85rem;color:var(--text-secondary);padding-left:1.2rem">
                        <li>Plantilla de <strong>12 jugadores</strong></li>
                        <li><strong>5 titulares</strong> por jornada</li>
                        <li>7 suplentes en banquillo</li>
                    </ul>
                </div>
                <div>
                    <h4 style="color:var(--accent-gold)">Jornada</h4>
                    <ul style="font-size:.85rem;color:var(--text-secondary);padding-left:1.2rem">
                        <li>Cada jornada tiene alineación independiente</li>
                        <li>Los puntos se acumulan jornada a jornada</li>
                        <li>La jornada <strong>completada</strong> queda bloqueada</li>
                    </ul>
                </div>
                <div>
                    <h4 style="color:var(--accent-gold)">Draft</h4>
                    <ul style="font-size:.85rem;color:var(--text-secondary);padding-left:1.2rem">
                        <li>Modo draft exclusivo por liga</li>
                        <li><strong>12 rondas</strong> por equipo</li>
                        <li>Auto-pick si se agota el tiempo</li>
                    </ul>
                </div>
            </div>
        </div>

        <div class="card mb-2">
            <div class="card-header">2. Alineación de jornada (5)</div>
            <table style="font-size:.85rem">
                <thead><tr><th>Slot</th><th>Posición</th><th>Cantidad</th></tr></thead>
                <tbody>
                    <tr><td><strong>GK</strong></td><td>Portero</td><td>1</td></tr>
                    <tr><td><strong>DEF</strong></td><td>Defensa</td><td>1</td></tr>
                    <tr><td><strong>MID</strong></td><td>Mediocampo</td><td>1</td></tr>
                    <tr><td><strong>FWD</strong></td><td>Delantero</td><td>1</td></tr>
                    <tr><td><strong>WILDCARD</strong></td><td>Cualquier posición</td><td>1</td></tr>
                </tbody>
            </table>
            <p style="font-size:.82rem;color:var(--text-muted);margin-top:.75rem">
                Nota: en la pantalla de alineación actual no se usa selector manual de capitán/vicecapitán.
            </p>
        </div>

        <div class="card mb-2">
            <div class="card-header">3. Cambios durante la jornada</div>
            <ul style="font-size:.85rem;color:var(--text-secondary);padding-left:1.2rem">
                <li>Se puede editar la alineación mientras la jornada está <strong>activa</strong>.</li>
                <li>Si una selección ya jugó, sus jugadores se marcan como <strong>Ya jugó</strong>.</li>
                <li>No puedes subir desde banquillo a titular a un jugador cuyo país ya jugó.</li>
                <li>Sí puedes bajar a un titular que ya jugó, pero perderás sus puntos de esa jornada.</li>
                <li>Cuando una jornada está <strong>completed</strong>, ya no admite cambios.</li>
            </ul>
        </div>

        <div class="card mb-2">
            <div class="card-header">4. Mercado de traspasos</div>
            <div class="grid grid-2" style="gap:1rem">
                <div>
                    <h4 style="color:var(--accent-gold)">🔥 Clausulazo</h4>
                    <p style="font-size:.85rem;color:var(--text-secondary)">
                        Pago de <strong>1.5× valor de mercado</strong>. Límite por ventana configurado por liga.
                    </p>
                </div>
                <div>
                    <h4 style="color:var(--accent-gold)">🤝 Oferta directa</h4>
                    <p style="font-size:.85rem;color:var(--text-secondary)">
                        Intercambio negociado entre equipos (jugadores + dinero).
                    </p>
                </div>
                <div>
                    <h4 style="color:var(--accent-gold)">📋 Mercado libre</h4>
                    <p style="font-size:.85rem;color:var(--text-secondary)">
                        Pujas ciegas por jugadores libres. Gana la oferta más alta.
                    </p>
                </div>
                <div>
                    <h4 style="color:var(--accent-gold)">🚪 Liberar jugador</h4>
                    <p style="font-size:.85rem;color:var(--text-secondary)">
                        Al liberar recuperas el <strong>50%</strong> del valor de mercado.
                    </p>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">5. Economía rápida</div>
            <table style="font-size:.85rem">
                <thead><tr><th>Acción</th><th>Efecto</th></tr></thead>
                <tbody>
                    <tr><td>Presupuesto inicial por liga</td><td style="color:var(--accent-teal)">Configurable</td></tr>
                    <tr><td>Clausulazo (comprador)</td><td style="color:var(--accent-red)">−cláusula</td></tr>
                    <tr><td>Clausulazo (vendedor)</td><td style="color:var(--accent-teal)">+cláusula</td></tr>
                    <tr><td>Liberar jugador</td><td style="color:var(--accent-teal)">+50% valor</td></tr>
                    <tr><td>Puja ganada</td><td style="color:var(--accent-red)">−importe de puja</td></tr>
                </tbody>
            </table>
        </div>
    `;

    const scoringHTML = `
        <div class="card mb-2">
            <div class="card-header">Participación</div>
            <table style="font-size:.85rem">
                <thead><tr><th>Evento</th><th>Puntos</th><th>Notas</th></tr></thead>
                <tbody>
                    <tr><td>Titular (≥60 min)</td><td style="color:var(--accent-teal)">+2</td><td></td></tr>
                    <tr><td>Suplente (1–59 min)</td><td style="color:var(--accent-teal)">+1</td><td></td></tr>
                    <tr><td>No juega (0 min)</td><td>0</td><td>Auto-sustitución</td></tr>
                </tbody>
            </table>
        </div>

        <div class="card mb-2">
            <div class="card-header">⚽ Ataque</div>
            <table style="font-size:.85rem">
                <thead><tr><th>Evento</th><th>GK</th><th>DEF</th><th>MID</th><th>FWD</th></tr></thead>
                <tbody>
                    <tr><td>Gol</td><td style="color:var(--accent-teal)">+6</td><td style="color:var(--accent-teal)">+6</td><td style="color:var(--accent-teal)">+5</td><td style="color:var(--accent-teal)">+4</td></tr>
                    <tr><td>Asistencia</td><td style="color:var(--accent-teal)">+3</td><td style="color:var(--accent-teal)">+3</td><td style="color:var(--accent-teal)">+3</td><td style="color:var(--accent-teal)">+3</td></tr>
                    <tr><td>Penalti fallado</td><td style="color:var(--accent-red)">-2</td><td style="color:var(--accent-red)">-2</td><td style="color:var(--accent-red)">-2</td><td style="color:var(--accent-red)">-2</td></tr>
                </tbody>
            </table>
        </div>

        <div class="card mb-2">
            <div class="card-header">🛡️ Defensa</div>
            <table style="font-size:.85rem">
                <thead><tr><th>Evento</th><th>GK</th><th>DEF</th><th>MID</th><th>FWD</th></tr></thead>
                <tbody>
                    <tr><td>Clean sheet (≥60 min)</td><td style="color:var(--accent-teal)">+4</td><td style="color:var(--accent-teal)">+4</td><td style="color:var(--accent-teal)">+1</td><td>—</td></tr>
                    <tr><td>Cada 2 goles encajados</td><td style="color:var(--accent-red)">-1</td><td style="color:var(--accent-red)">-1</td><td>—</td><td>—</td></tr>
                    <tr><td>Penalti parado</td><td style="color:var(--accent-teal)">+5</td><td>—</td><td>—</td><td>—</td></tr>
                    <tr><td>Parada (cada 3)</td><td style="color:var(--accent-teal)">+1</td><td>—</td><td>—</td><td>—</td></tr>
                </tbody>
            </table>
        </div>

        <div class="card mb-2">
            <div class="card-header">🟨 Disciplina</div>
            <table style="font-size:.85rem">
                <thead><tr><th>Evento</th><th>Puntos</th></tr></thead>
                <tbody>
                    <tr><td>Tarjeta amarilla</td><td style="color:var(--accent-red)">-1</td></tr>
                    <tr><td>Tarjeta roja (directa)</td><td style="color:var(--accent-red)">-3</td></tr>
                    <tr><td>Gol en propia puerta</td><td style="color:var(--accent-red)">-2</td></tr>
                </tbody>
            </table>
        </div>

        <div class="card mb-2">
            <div class="card-header">⭐ Bonus</div>
            <table style="font-size:.85rem">
                <thead><tr><th>Evento</th><th>Puntos</th><th>Condición</th></tr></thead>
                <tbody>
                    <tr><td>MVP del partido</td><td style="color:var(--accent-teal)">+3</td><td>Rating más alto (≥7.5)</td></tr>
                    <tr><td>Hat-trick</td><td style="color:var(--accent-teal)">+3</td><td>3+ goles en un partido</td></tr>
                </tbody>
            </table>
        </div>

        <div class="card mb-2">
            <div class="card-header">👑 Capitán</div>
            <ul style="font-size:.85rem;color:var(--text-secondary);padding-left:1.2rem">
                <li>El capitán multiplica <strong>todos sus puntos ×2</strong></li>
                <li>Si el capitán no juega, el <strong>vice-capitán hereda</strong> el ×2</li>
                <li>Si ninguno juega, no hay multiplicador</li>
            </ul>
        </div>

        <div class="card">
            <div class="card-header">📊 Ejemplo</div>
            <div style="background:var(--bg-card);border-radius:.5rem;padding:1rem;font-size:.85rem">
                <p><strong>Lamine Yamal</strong> (FWD, capitán) — España 3–0 Costa Rica</p>
                <table style="margin-top:.5rem">
                    <tbody>
                        <tr><td>Titular (90 min)</td><td style="color:var(--accent-teal)">+2</td></tr>
                        <tr><td>1 gol (FWD)</td><td style="color:var(--accent-teal)">+4</td></tr>
                        <tr><td>1 asistencia</td><td style="color:var(--accent-teal)">+3</td></tr>
                        <tr><td>MVP (rating 9.1)</td><td style="color:var(--accent-teal)">+3</td></tr>
                        <tr style="border-top:1px solid var(--border)"><td><strong>Subtotal</strong></td><td style="color:var(--accent-teal)"><strong>+12</strong></td></tr>
                        <tr><td><strong>Capitán ×2</strong></td><td style="color:var(--accent-gold);font-size:1.1rem"><strong>= 24 pts</strong></td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    `;

    const contentEl = document.getElementById('rules-content');
    contentEl.innerHTML = rulesHTML;

    container.querySelectorAll('.rules-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            container.querySelectorAll('.rules-tab').forEach(b => b.className = 'btn btn-outline rules-tab');
            btn.className = 'btn btn-gold rules-tab';
            contentEl.innerHTML = btn.dataset.tab === 'scoring' ? scoringHTML : rulesHTML;
        });
    });
});
