# TODO — Fantasy ↔ Simulator Integration

## Endpoints que faltan en el Simulador

### Stats de partidos (CRÍTICO para puntuar en Fantasy)
- [ ] `GET /api/v1/matches/{match_id}/stats` — stats de todos los jugadores de un partido
- [ ] `GET /api/v1/matchdays/{id}/stats` — stats de toda una jornada (para puntuar masivamente)
- [ ] `GET /api/v1/players/{id}/stats` — historial de stats de un jugador
- [ ] `GET /api/v1/matches?status=finished` — partidos terminados con resultados

### Convocatorias
- [ ] Verificar que `GET /api/v1/squads/{country_code}` devuelve todos los datos que Fantasy necesita

## Simplificación del Fantasy

### Tablas a revisar
- [ ] `players` — actualmente es mirror del simulador. Solo debería cachear jugadores que estén en equipos de usuarios (FK refs)
- [ ] `countries` — no necesaria si se fetch del simulador
- [ ] `match_scores` — debería sincronizarse automáticamente del simulador en vez de entrada manual

### Lo que Fantasy SÍ debe mantener localmente
- `leagues` — ligas de fantasy
- `fantasy_teams` — equipos de usuarios
- `team_players` — jugadores drafteados por cada usuario
- `matchday_lineups` — alineación por jornada (titular, capitán, banquillo)
- `fantasy_points` — puntos calculados (derivados de stats del simulador)
- `draft_picks` — historial del draft
- `transfers` — historial de mercado

## Flujo de scoring propuesto

```
1. Simulador simula partido → genera player_match_stats
2. Fantasy llama GET /matches/{id}/stats al simulador
3. Fantasy aplica su fórmula de puntos (goles, asistencias, tarjetas, etc.)
4. Fantasy guarda puntos por equipo/jornada en fantasy_points
```

## Observabilidad

- [x] Slow query logging en PgConnection (>100ms)
- [x] TimingMiddleware con X-Response-Time header (>200ms log WARNING)
- [ ] Endpoint `/health` con métricas básicas (uptime, DB pool, query counts)
- [ ] Evaluar SigNoz Cloud free tier si se necesita más
