# ⚽ WC Fantasy 2026

Fantasy football webapp para el **Mundial de Fútbol 2026** (48 selecciones, formato FIFA).

Draft con snake order, mercado de traspasos con clausulazos, puntuación en vivo por jornada, alineaciones con bloqueo mid-matchday, y todo en tiempo real con WebSocket.

**Live**: [https://fantasy.jpamies.com](https://fantasy.jpamies.com)

## Concepto

- **Draft Mode**: Jugadores por turnos (snake order, estilo NBA/NFL)
- **Cola de Draft**: Pre-selecciona tus picks favoritos — el sistema los elige por ti
- **AutoDraft**: Selección automática inteligente con composición de plantilla balanceada
- **Clausulazos**: Paga 1.5× el valor de mercado para fichar instantáneamente
- **Mercado de traspasos**: Ofertas directas, pujas ciegas, liberaciones
- **Ligas privadas**: Crea una liga, comparte el código, y a jugar
- **Scoring en vivo**: Sync automático con el simulador cada 60 segundos
- **Alineaciones por jornada**: Cambios mid-matchday (solo jugadores no bloqueados)
- **Auto-alineación**: Selecciona automáticamente los mejores 11 por media de puntos

## Tech Stack

| Capa | Tecnología |
|---|---|
| Frontend | HTML + CSS + Vanilla JS (SPA, hash router con params dinámicos, tema oscuro) |
| Backend | Python 3.11 + FastAPI + WebSocket (asyncpg) |
| Base de datos | **PostgreSQL 16** via asyncpg (pool min=2, max=10) |
| Auth | JWT (HS256) — código de liga + nickname, sin passwords |
| HTTP Client | httpx (async, para comunicación con wc-simulator) |
| CI/CD | GitHub Actions → GHCR (multi-arch amd64+arm64) → auto-update k8s-homepi |
| Infraestructura | **K3s** en Raspberry Pi + **Flux CD** (GitOps) |
| Networking | **Cloudflare Tunnel** (HTTPS en `fantasy.jpamies.com`) |
| Datos | **wc-simulator API** (fuente primaria, 244k jugadores EFEM) |

## Configuración (env vars)

Todas con prefijo `WCF_`:

| Variable | Default | Descripción |
|----------|---------|-------------|
| `WCF_SECRET_KEY` | `wc-fantasy-2026-dev-secret...` | JWT signing secret |
| `WCF_DATABASE_URL` | `postgresql://wcadmin:...@localhost:5432/wc_fantasy` | PostgreSQL connection URL |
| `WCF_SIMULATOR_API_URL` | `""` | URL del wc-simulator (vacío = modo local) |
| `WCF_CORS_ORIGINS` | `*` | CORS origins |
| `WCF_JWT_ALGORITHM` | `HS256` | Algoritmo JWT |

## Arquitectura

```
                    Internet
                       │
                  Cloudflare Tunnel
                       │
               fantasy.jpamies.com
                       │
               ┌───────┴───────┐
               │  wc-fantasy   │
               │  FastAPI:8000 │
               └───────┬───────┘
                       │ asyncpg
               ┌───────┴───────┐
               │postgres-fantasy│
               │  PG 16 (PVC)  │
               └───────┬───────┘
                       │ httpx (async)
               ┌───────┴───────┐
               │ wc-simulator  │
               │ FastAPI:8001  │
               │  PostgreSQL   │
               └───────────────┘
                       │
                  CronJob (60s)
              POST /scoring/sync
```

### Flujo de datos

1. **Jugadores/Calendario**: el fantasy lee del simulador en tiempo real (no replica)
2. **Resultados**: CronJob cada 60s llama `POST /scoring/sync` que:
   - Obtiene partidos terminados del simulador (`GET /matches/finished-with-stats`)
   - Calcula puntos fantasy por jugador
   - Crea snapshots de alineaciones
   - Recalcula puntos de equipos (incluye swaps mid-matchday)
3. **Datos locales**: PostgreSQL guarda ligas, equipos, lineups, scores, drafts, transfers, market windows

## Base de datos (PostgreSQL)

18 tablas:

| Tabla | Propósito |
|-------|-----------|
| `countries` | Selecciones (code, name, flag) — creadas lazily por sync |
| `players` | Jugadores (name, position, club, market_value, photo) — creados lazily |
| `leagues` | Ligas fantasy (code, settings, status) |
| `fantasy_teams` | Equipos (owner, budget, formation) |
| `team_players` | Plantilla por defecto (player_id, is_starter, captain) |
| `drafts` | Estado del draft (round, pick, order) |
| `draft_picks` | Historial de picks |
| `draft_settings` | Autodraft + cola por equipo |
| `transfers` | Ofertas, clausulazos, pujas, liberaciones |
| `matchdays` | Jornadas (status: upcoming/active/completed) |
| `matches` | Partidos con resultados (sincronizados del simulador) |
| `match_scores` | Puntuaciones individuales por partido (goles, asist, tarjetas, pts fantasy) |
| `matchday_lineups` | Alineación por equipo por jornada (snapshot, bloqueos por país jugado) |
| `sync_state` | Estado del último sync |
| `market_windows` | Ventanas de mercado (fases, deadlines) |
| `player_clauses` | Cláusulas de rescisión |
| `market_budgets` | Presupuestos de mercado |
| `market_transactions` | Historial de transacciones |
| `reposition_draft_picks` | Picks de reposición post-mercado |

## API Endpoints

Base: `/api/v1`

### Auth & Ligas
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/leagues` | Crear liga |
| POST | `/auth/join` | Unirse por código+nick → JWT |
| POST | `/auth/recover` | Recuperar sesión |
| GET | `/leagues/{id}` | Detalle de liga + equipos |
| GET | `/leagues/{id}/standings` | **Clasificación** con desglose por jornada |
| GET | `/leagues/{id}/team-lineup/{team}/{md}` | Alineación de cualquier equipo (read-only) |
| PATCH | `/leagues/{id}/settings` | Configurar liga (commissioner) |

### Jugadores
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/players` | Búsqueda con filtros |
| GET | `/players/{id}` | Detalle de jugador |
| GET | `/players/{id}/stats` | **Ficha completa**: bio + stats simulador + puntos fantasy |
| GET | `/countries` | Lista de selecciones |

### Equipos
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/teams/{id}` | Equipo con plantilla y puntos |
| GET | `/teams/{id}/matchday-lineup/{md}` | Alineación de jornada (con puntos, goles, locked) |
| PATCH | `/teams/{id}/matchday-lineup/{md}` | Actualizar alineación (validación de bloqueos) |

### Draft (WebSocket)
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/leagues/{id}/draft/start` | Iniciar draft |
| GET | `/leagues/{id}/draft` | Estado del draft |
| POST | `/leagues/{id}/draft/pick` | Hacer pick |
| WS | `/leagues/{id}/draft/ws` | Tiempo real |

### Mercado
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/leagues/{id}/market` | Estado del mercado |
| POST | `/leagues/{id}/market/clause` | Clausulazo (1.5× instant buy) |
| POST | `/leagues/{id}/market/offer` | Oferta de traspaso |
| POST | `/leagues/{id}/market/bid` | Puja por agente libre |

### Puntuación
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/scoring/matchdays` | Calendario del simulador (live) |
| GET | `/scoring/matchdays/{id}` | Partidos + scores de una jornada |
| POST | `/scoring/sync` | Sincronizar resultados del simulador |
| GET | `/scoring/leaderboard` | Leaderboard completo |

## Frontend (SPA)

10 páginas con router hash + soporte para params dinámicos (`:id`):

| Ruta | Página | Descripción |
|------|--------|-------------|
| `#/` | home | Login/crear liga |
| `#/league` | league | Detalle de liga |
| `#/draft` | draft | Sala de draft (WebSocket real-time) |
| `#/team` | team | Gestión de equipo + alineaciones por jornada |
| `#/market` | market | Mercado de traspasos |
| `#/standings` | standings | **Clasificación** (General / Por Jornada + click → ver alineación) |
| `#/scoring` | scoring | Calendario + resultados + goleadores + stats detallados |
| `#/rules` | rules | Reglas del juego |
| `#/player/:id` | player-detail | **Ficha de jugador** (foto, OVR, atributos, stats, puntos fantasy) |

### Features del frontend
- **Auto-alineación**: botón que selecciona los mejores 11 por media de puntos + valor de mercado
- **Bloqueo mid-matchday**: jugadores cuyo país ya jugó aparecen con 🔒
- **Puntos por jornada**: cada jugador muestra sus puntos, goles, asistencias, tarjetas de esa jornada
- **Clasificación interactiva**: General/Jornada, click en equipo → ver su alineación con puntos
- **Ficha de jugador**: atributos (barras), stats del torneo, puntos fantasy por jornada, historial
- **Player names clickables** en todas las vistas (equipo, standings, draft, mercado, calendario)

## Sistema de puntuación

| Evento | GK | DEF | MID | FWD |
|--------|:--:|:---:|:---:|:---:|
| Minutos jugados | +1 | +1 | +1 | +1 |
| 60+ minutos | +1 | +1 | +1 | +1 |
| Gol | +6 | +6 | +5 | +4 |
| Asistencia | +3 | +3 | +3 | +3 |
| Clean sheet (60+min) | +4 | +4 | +1 | — |
| Cada 3 paradas (GK) | +1 | — | — | — |
| Penalti parado | +5 | — | — | — |
| Cada 2 goles encajados | -1 | -1 | — | — |
| Penalti fallado | -2 | -2 | -2 | -2 |
| Amarilla | -1 | -1 | -1 | -1 |
| Roja | -3 | -3 | -3 | -3 |
| Gol en propia puerta | -2 | -2 | -2 | -2 |
| MVP (rating ≥ 8.0) | +3 | +3 | +3 | +3 |

**Capitán**: puntos × 2.0 (configurable). Vice-capitán hereda si el capitán no juega.

## Reglas de alineación

- **23 jugadores** por equipo (draft)
- **11 titulares** con formación flexible (1GK, 3-5DEF, 2-5MID, 1-3FWD)
- **Alineación por jornada**: snapshot creado automáticamente desde la default
- **Mid-matchday**: si un país ya jugó → sus jugadores quedan 🔒 (no se pueden mover)
- **Auto-sustitución** (configurable por liga): si un titular no juega → suplente lo reemplaza

## Deploy

### Docker

```bash
docker build -t wc-fantasy .
docker run -p 8000:8000 -v data:/data wc-fantasy
```

### CI/CD (GitHub Actions)

1. Push a `master` → build multi-arch (amd64+arm64)
2. Push a `ghcr.io/jpamies/wc-fantasy-draft:latest` + `:sha`
3. **Auto-deploy**: actualiza `k8s-homepi/apps/wc-fantasy/deployment.yaml` → push → Flux reconcilia

### Kubernetes (k8s-homepi)

- **Deployment**: 1 réplica, 128Mi-512Mi RAM
- **Service**: ClusterIP puerto 8000
- **PVC**: 1Gi para SQLite (`/data/wc_fantasy.db`)
- **CronJob**: `fantasy-sync` cada 60s → `POST /scoring/sync`
- **Env**: `WCF_SIMULATOR_API_URL=http://wc-simulator.default.svc.cluster.local:8001`

## Integración con wc-simulator

El simulador es la **fuente de verdad** para:
- Catálogo de jugadores (bio, atributos, fotos, market value)
- Calendario del torneo (matchdays + partidos)
- Resultados y stats individuales

El fantasy **nunca modifica** datos del simulador. Solo lee y almacena localmente los scores calculados.

### Endpoints consumidos del simulador
- `GET /api/v1/tournament/calendar` — Calendario completo
- `GET /api/v1/matches/finished-with-stats` — Resultados + stats (para sync)
- `GET /api/v1/matches?matchday_id=X&status=finished` — Partidos por jornada
- `GET /api/v1/squads/all-players` — Jugadores convocados (1248)
- `GET /api/v1/players/{id}` — Detalle de jugador
- `GET /api/v1/stats/player/{id}` — Stats del torneo
- `GET /api/v1/countries` — Selecciones

## Estructura

```
wc-fanasy/
├── .github/workflows/build-image.yml
├── src/
│   ├── frontend/
│   │   ├── index.html
│   │   ├── css/styles.css
│   │   └── js/
│   │       ├── api.js           # HTTP client + JWT + helpers
│   │       ├── router.js        # Hash router con :param support
│   │       ├── app.js           # Init + nav
│   │       └── pages/
│   │           ├── home.js, league.js, draft.js, team.js
│   │           ├── market.js, standings.js, scoring.js
│   │           ├── rules.js, player-detail.js
│   ├── backend/
│   │   ├── main.py              # FastAPI app + middleware
│   │   ├── auth.py              # JWT creation/validation
│   │   ├── config.py            # Env vars (WCF_ prefix)
│   │   ├── database.py          # SQLite schema (14 tablas) + aiosqlite
│   │   ├── models.py            # Pydantic schemas
│   │   ├── routes/
│   │   │   ├── leagues.py       # Auth, ligas, standings, team lineup público
│   │   │   ├── players.py       # Jugadores, países, stats proxy
│   │   │   ├── teams.py         # Equipos, alineaciones por jornada
│   │   │   ├── draft.py         # Draft WebSocket + REST
│   │   │   ├── market.py        # Traspasos, clausulazos, pujas
│   │   │   └── scoring.py       # Calendario, sync, leaderboard
│   │   └── services/
│   │       ├── draft_engine.py      # Snake order, auto-pick, queue
│   │       ├── market_engine.py     # Clausulazos, ofertas, pujas
│   │       ├── scoring_engine.py    # Cálculo de puntos + captain bonus
│   │       ├── simulator_client.py  # httpx client al simulador
│   │       ├── sync_service.py      # Polling → scores → team points
│   │       └── lineup_service.py    # Snapshots, swaps, lock validation
│   └── scripts/
├── data/transfermarkt/              # JSONs legacy (fallback si no hay simulador)
├── docs/
│   ├── API_DESIGN.md, ARCHITECTURE.md, DATA_MODEL.md
│   ├── DECISIONS.md, RULES.md, SCORING.md, ROADMAP.md
├── tests/smoke_test.py
├── Dockerfile
├── Makefile
└── requirements.txt
```

## Quick Start (desarrollo local)

```bash
git clone https://github.com/jpamies/wc-fantasy-draft.git
cd wc-fantasy-draft
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
python -m uvicorn src.backend.main:app --reload --port 8000
# → http://localhost:8000
```

Para conectar con el simulador local:
```bash
WCF_SIMULATOR_API_URL=http://localhost:8001 python -m uvicorn src.backend.main:app --reload --port 8000
```
