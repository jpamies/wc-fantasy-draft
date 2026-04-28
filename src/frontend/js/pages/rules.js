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
            <div class="card-header">1. Conceptos básicos</div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem">
                <div>
                    <h4 style="color:var(--accent-gold)">Liga</h4>
                    <ul style="font-size:.85rem;color:var(--text-secondary);padding-left:1.2rem">
                        <li>Grupo de 2 a 10 participantes</li>
                        <li>Código de 6 letras para unirse</li>
                        <li>Comisionado configura las reglas</li>
                    </ul>
                </div>
                <div>
                    <h4 style="color:var(--accent-gold)">Equipo Fantasy</h4>
                    <ul style="font-size:.85rem;color:var(--text-secondary);padding-left:1.2rem">
                        <li>Plantilla de <strong>23 jugadores</strong></li>
                        <li><strong>11 titulares</strong> que puntúan</li>
                        <li>12 suplentes de reserva</li>
                        <li>Un <strong>capitán</strong> que puntúa ×2</li>
                    </ul>
                </div>
                <div>
                    <h4 style="color:var(--accent-gold)">Jornada</h4>
                    <ul style="font-size:.85rem;color:var(--text-secondary);padding-left:1.2rem">
                        <li>Cada día de partidos = 1 jornada</li>
                        <li>Puntos acumulativos</li>
                        <li>Alineación independiente por jornada</li>
                    </ul>
                </div>
            </div>
        </div>

        <div class="card mb-2">
            <div class="card-header">2. Formaciones permitidas</div>
            <table style="font-size:.85rem">
                <thead><tr><th>Formación</th><th>GK</th><th>DEF</th><th>MID</th><th>FWD</th></tr></thead>
                <tbody>
                    <tr><td><strong>4-3-3</strong></td><td>1</td><td>4</td><td>3</td><td>3</td></tr>
                    <tr><td><strong>4-4-2</strong></td><td>1</td><td>4</td><td>4</td><td>2</td></tr>
                    <tr><td><strong>3-5-2</strong></td><td>1</td><td>3</td><td>5</td><td>2</td></tr>
                    <tr><td><strong>3-4-3</strong></td><td>1</td><td>3</td><td>4</td><td>3</td></tr>
                    <tr><td><strong>5-3-2</strong></td><td>1</td><td>5</td><td>3</td><td>2</td></tr>
                    <tr><td><strong>5-4-1</strong></td><td>1</td><td>5</td><td>4</td><td>1</td></tr>
                    <tr><td><strong>4-5-1</strong></td><td>1</td><td>4</td><td>5</td><td>1</td></tr>
                </tbody>
            </table>
        </div>

        <div class="card mb-2">
            <div class="card-header">3. 🆕 Draft Mode</div>
            <p style="color:var(--text-secondary);font-size:.9rem;margin-bottom:1rem">
                A diferencia de los fantasy clásicos, en <strong>Draft Mode</strong> cada jugador solo puede pertenecer a un equipo dentro de la liga.
            </p>
            <div class="grid grid-2" style="gap:1rem">
                <div>
                    <h4 style="color:var(--accent-teal)">Cómo funciona</h4>
                    <ol style="font-size:.85rem;color:var(--text-secondary);padding-left:1.2rem">
                        <li>El comisionado inicia el draft</li>
                        <li>Orden aleatorio + serpenteo (1→N, N→1)</li>
                        <li><strong>60 segundos</strong> por pick</li>
                        <li>23 rondas hasta completar plantilla</li>
                        <li>Auto-pick si se agota el tiempo</li>
                    </ol>
                </div>
                <div>
                    <h4 style="color:var(--accent-teal)">Mínimos por posición</h4>
                    <ul style="font-size:.85rem;color:var(--text-secondary);padding-left:1.2rem">
                        <li>🧤 Mínimo 2 porteros (GK)</li>
                        <li>🛡️ Mínimo 5 defensas (DEF)</li>
                        <li>🎯 Mínimo 5 centrocampistas (MID)</li>
                        <li>⚡ Mínimo 3 delanteros (FWD)</li>
                        <li>Sin máximo por selección</li>
                    </ul>
                </div>
            </div>
        </div>

        <div class="card mb-2">
            <div class="card-header">4. 🆕 Mercado de traspasos</div>
            <div class="grid grid-2" style="gap:1rem">
                <div>
                    <h4 style="color:var(--accent-gold)">🔥 Clausulazo</h4>
                    <p style="font-size:.85rem;color:var(--text-secondary)">
                        Paga <strong>1.5× el valor de mercado</strong> y el jugador es tuyo <strong>inmediatamente</strong>. Máximo 2 por ventana.
                    </p>
                </div>
                <div>
                    <h4 style="color:var(--accent-gold)">🤝 Oferta directa</h4>
                    <p style="font-size:.85rem;color:var(--text-secondary)">
                        Propón un intercambio. El otro puede aceptar, rechazar o contraofertar. Timeout: 24h.
                    </p>
                </div>
                <div>
                    <h4 style="color:var(--accent-gold)">📋 Mercado libre</h4>
                    <p style="font-size:.85rem;color:var(--text-secondary)">
                        Pujas ciegas por jugadores no drafteados. Gana la más alta. Empate: peor clasificado gana.
                    </p>
                </div>
                <div>
                    <h4 style="color:var(--accent-gold)">🚪 Liberar jugador</h4>
                    <p style="font-size:.85rem;color:var(--text-secondary)">
                        Devuelve al mercado libre. Recuperas el <strong>50% de su valor</strong>.
                    </p>
                </div>
            </div>
        </div>

        <div class="card mb-2">
            <div class="card-header">5. Economía (💰 Fantasillones)</div>
            <table style="font-size:.85rem">
                <thead><tr><th>Acción</th><th>Efecto</th></tr></thead>
                <tbody>
                    <tr><td>Presupuesto inicial</td><td style="color:var(--accent-teal)">+100M</td></tr>
                    <tr><td>Clausulazo (comprador)</td><td style="color:var(--accent-red)">−cláusula del jugador</td></tr>
                    <tr><td>Clausulazo (vendedor)</td><td style="color:var(--accent-teal)">+cláusula del jugador</td></tr>
                    <tr><td>Liberar jugador</td><td style="color:var(--accent-teal)">+50% valor de mercado</td></tr>
                    <tr><td>Puja ganada</td><td style="color:var(--accent-red)">−precio de puja</td></tr>
                </tbody>
            </table>
        </div>

        <div class="card mb-2">
            <div class="card-header">6. 🆕 Alineaciones por jornada</div>
            <ul style="font-size:.85rem;color:var(--text-secondary);padding-left:1.2rem">
                <li>Cada jornada tiene su <strong>alineación independiente</strong></li>
                <li>Puedes preparar la siguiente jornada mientras la actual está en juego</li>
                <li>🔒 <strong>Bloqueo</strong>: cuando un partido empieza, los jugadores de esos equipos quedan bloqueados</li>
                <li>✅ Puedes <strong>bajar un titular</strong> que ya jugó y subir otro cuyo partido no ha empezado</li>
                <li>❌ <strong>No puedes subir</strong> un suplente cuyo partido ya ha comenzado</li>
                <li>Máximo <strong>3 auto-sustituciones</strong> si un titular tiene 0 minutos</li>
            </ul>
        </div>

        <div class="card">
            <div class="card-header">7. Poderes del comisionado</div>
            <div class="grid grid-2" style="gap:1rem;font-size:.85rem;color:var(--text-secondary)">
                <div>
                    <strong style="color:var(--accent-teal)">Puede:</strong>
                    <ul style="padding-left:1.2rem">
                        <li>Configurar reglas de la liga</li>
                        <li>Iniciar el draft</li>
                        <li>Abrir/cerrar mercado</li>
                        <li>Cargar puntuaciones</li>
                        <li>Eliminar la liga</li>
                    </ul>
                </div>
                <div>
                    <strong style="color:var(--accent-red)">No puede:</strong>
                    <ul style="padding-left:1.2rem">
                        <li>Modificar puntuaciones a su favor</li>
                        <li>Darse ventaja en el draft</li>
                        <li>Cambiar resultados de partidos</li>
                    </ul>
                </div>
            </div>
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
