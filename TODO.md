# TODO — Fantasy ↔ Simulator Integration

## NEXT: Cambios durante jornada (mid-matchday swaps)

### Reglas
1. **Jornada empieza** cuando el primer partido de esa jornada se ha jugado (status=finished en simulador)
2. Al empezar la jornada, se congela un **snapshot** de `matchday_lineups` (titulares + suplentes)
3. Las altas/bajas del mercado NO afectan a la jornada en curso
4. **"Ha jugado"** = su selección nacional ha disputado un partido en esa jornada (independiente de minutos)

### Swaps permitidos durante jornada
| Acción | País del jugador YA jugó | País NO ha jugado |
|---|---|---|
| Quitar de titular → banquillo | ✅ (pierde sus puntos) | ✅ |
| Poner de banquillo → titular | ❌ No permitido | ✅ |

### Implementación necesaria
- [ ] Endpoint `POST /lineup/{matchday_id}/swap` con validaciones:
  - Verificar que la jornada ha empezado
  - Verificar que el jugador a poner como titular: su país NO ha jugado
  - No importa si el que sale ya jugó o no
- [ ] El sync recalcula puntos basándose en el estado ACTUAL de titulares
  - Si quitas un titular que tenía puntos → se pierden
  - Si pones un titular cuyo país aún no jugó → cuando juegue, sumará
- [ ] Endpoint `GET /lineup/{matchday_id}/available-swaps` para el frontend:
  - Lista de suplentes disponibles (cuyo país no ha jugado)
  - Lista de titulares que se pueden quitar (todos)
- [ ] Necesita saber qué países han jugado: del simulador `GET /matches?status=finished&matchday_id=X`

### Idempotencia del sync
- [x] match_scores usa INSERT OR REPLACE (idempotente por player_id+matchday_id)
- [x] Si se ejecuta 2 veces, no duplica datos
- [x] Detecta reset del simulador y limpia datos stale
- [ ] Puntos de equipo se recalculan en cada sync basándose en titulares actuales

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
