# TODO — Fantasy ↔ Simulator Integration

## Arquitectura: Polling via API HTTP (desacoplado)

Fantasy hace polling periódico al simulador para detectar cambios.
No DB compartida, no webhooks. Simplicidad y desacoplamiento.

## Endpoints que faltan en el Simulador

### Stats de partidos (CRÍTICO para puntuar en Fantasy)
- [ ] `GET /api/v1/matches/{match_id}/stats` — stats de todos los jugadores de un partido (YA EXISTE)
- [ ] `GET /api/v1/matchdays/{id}/results` — resultados + stats de toda una jornada
- [ ] `GET /api/v1/matches?status=finished&since={timestamp}` — partidos terminados desde una fecha (para polling)
- [ ] `GET /api/v1/stats/player/{id}` — historial de stats de un jugador (YA EXISTE)

### Calendario y Jornadas
- [ ] `GET /api/v1/tournament/calendar` — calendario completo (YA EXISTE)
- [ ] `GET /api/v1/tournament/progress` — estado de progreso del torneo (YA EXISTE)

## Mecanismo de Polling en Fantasy

### Flujo propuesto
```
1. Fantasy tiene un background task que cada 60s llama:
   GET /api/v1/matches?status=finished&since={last_check}
   
2. Si hay partidos nuevos terminados:
   a. Para cada partido: GET /api/v1/matches/{id}/stats
   b. Aplica fórmula de puntos fantasy a cada jugador
   c. Guarda fantasy_points por equipo/jornada
   d. Actualiza last_check timestamp

3. Frontend del fantasy muestra puntos actualizados
```

### Implementación
- [ ] Crear `PollingService` en fantasy que se ejecute como background task (asyncio)
- [ ] Tabla `sync_state` en fantasy para guardar `last_check_timestamp`
- [ ] Tabla `fantasy_points` para puntos calculados por jugador/jornada
- [ ] Endpoint en fantasy: `POST /scoring/sync` (trigger manual de sincronización)
- [ ] Config: `POLLING_INTERVAL_SECONDS` (default 60)

## Simplificación del Fantasy

### Tablas a revisar
- [ ] `players` — solo cachear jugadores que estén en equipos de usuarios (FK refs)
- [ ] `countries` — fetch del simulador, no almacenar local
- [ ] `match_scores` — reemplazar con datos sincronizados del simulador

### Lo que Fantasy SÍ debe mantener localmente
- `leagues` — ligas de fantasy
- `fantasy_teams` — equipos de usuarios
- `team_players` — jugadores drafteados por cada usuario
- `matchday_lineups` — alineación por jornada (titular, capitán, banquillo)
- `fantasy_points` — puntos calculados (derivados de stats del simulador)
- `draft_picks` — historial del draft
- `transfers` — historial de mercado
- `sync_state` — estado de sincronización con simulador

## Fórmula de Puntos Fantasy (propuesta)

| Evento | Puntos |
|---|---|
| Minutos jugados (>0) | +1 |
| Minutos jugados (>60) | +1 |
| Gol (FWD) | +4 |
| Gol (MID) | +5 |
| Gol (DEF/GK) | +6 |
| Asistencia | +3 |
| Portería a cero (GK/DEF, >60 min) | +4 |
| Cada 3 paradas (GK) | +1 |
| Penalti fallado | -2 |
| Tarjeta amarilla | -1 |
| Tarjeta roja | -3 |
| Gol en propia | -2 |
| Cada 2 goles encajados (GK/DEF) | -1 |
| Bonus MVP (rating >= 8) | +3 |
| Capitán | x2 puntos |

## Observabilidad

- [x] Slow query logging en PgConnection (>100ms)
- [x] TimingMiddleware con X-Response-Time header (>200ms log WARNING)
- [ ] Endpoint `/health` con métricas básicas (uptime, DB pool, query counts)
- [ ] Evaluar SigNoz Cloud free tier si se necesita más
