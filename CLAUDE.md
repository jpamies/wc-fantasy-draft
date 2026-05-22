# CLAUDE.md — WC Fantasy 2026

> Contexto para agentes de IA (Claude, Copilot) que trabajan en este proyecto.

## Qué es esto

Webapp de fantasy football para el **Mundial 2026** (48 selecciones, formato FIFA).
Draft snake order, mercado de traspasos con clausulazos, puntuación en vivo,
alineaciones con bloqueo mid-matchday. Todo en tiempo real con WebSocket.

**Live**: https://fantasy.jpamies.com

## Tech stack

| Capa | Tecnología |
|------|------------|
| Frontend | HTML + CSS + Vanilla JS (SPA, hash router, tema oscuro) |
| Backend | Python 3.11 + FastAPI 0.115 + WebSocket |
| Base de datos | **PostgreSQL 16** via `asyncpg 0.30` (pool min=2, max=10) |
| Auth | JWT HS256 — código de liga + nickname, sin passwords |
| HTTP Client | httpx (async, comunicación con wc-simulator) |
| CI/CD | GitHub Actions → GHCR (multi-arch amd64+arm64) → auto-update k8s-homepi |
| Infra | **K3s** en Raspberry Pi + **Flux CD** (GitOps) |
| Red | **Cloudflare Tunnel** (HTTPS en `fantasy.jpamies.com`) |
| Datos | **wc-simulator API** (fuente primaria, jugadores + partidos EFEM) |

## Estructura del proyecto

```
wc-fanasy/
├── CLAUDE.md                  ← este fichero
├── Dockerfile                 ← python:3.11-slim + uvicorn
├── Makefile                   ← setup, dev, docker-build
├── requirements.txt           ← fastapi, asyncpg, httpx, pydantic, python-jose
├── docs/
│   ├── ARCHITECTURE.md        ← diagrama alto nivel
│   ├── API_DESIGN.md          ← endpoints REST + WebSocket
│   ├── DATA_MODEL.md          ← esquema de entidades
│   ├── DECISIONS.md           ← ADRs (arquitectura)
│   ├── ROADMAP.md             ← plan de fases (referencia histórica)
│   ├── RULES.md               ← reglas del juego fantasy
│   └── SCORING.md             ← sistema de puntuación
├── src/
│   ├── backend/
│   │   ├── main.py            ← FastAPI app + lifespan + 3 background tasks
│   │   ├── config.py          ← Settings (Pydantic, env prefix WCF_)
│   │   ├── database.py        ← asyncpg pool + PgConnection wrapper + schema DDL
│   │   ├── auth.py            ← JWT create/decode + get_current_team dependency
│   │   ├── models.py          ← Pydantic schemas (request/response)
│   │   ├── routes/
│   │   │   ├── draft.py       ← Draft REST + WebSocket + autodraft cascade
│   │   │   ├── leagues.py     ← CRUD ligas + bots + reset
│   │   │   ├── market.py      ← Clausulazos, ofertas, pujas, mercado
│   │   │   ├── players.py     ← Catálogo jugadores (proxy del simulador)
│   │   │   ├── scoring.py     ← Sync puntuaciones + matchdays
│   │   │   └── teams.py       ← Equipos + alineaciones + lineup por jornada
│   │   └── services/
│   │       ├── bot_service.py       ← Creación y gestión de bots
│   │       ├── draft_engine.py      ← Motor del draft (turnos, picks, autodraft)
│   │       ├── lineup_service.py    ← Lógica de alineaciones + auto-lineup
│   │       ├── market_engine.py     ← Lógica de mercado (clausulazos, waivers)
│   │       ├── market_service.py    ← Ventanas de mercado + transiciones
│   │       ├── scoring_engine.py    ← Cálculo de puntos fantasy
│   │       ├── simulator_client.py  ← httpx client para wc-simulator
│   │       └── sync_service.py      ← Sync de datos simulador → fantasy
│   ├── frontend/
│   │   ├── index.html         ← SPA entry point
│   │   ├── css/               ← Estilos (tema oscuro)
│   │   └── js/                ← Vanilla JS (router, componentes, API client)
│   └── scripts/
│       └── ...                ← Scripts de importación/migración
└── tests/
    └── smoke_test.py
```

## Base de datos (PostgreSQL)

### Conexión

```python
# config.py
WCF_DATABASE_URL = "postgresql://user:pass@host:5432/wc_fantasy"
```

`database.py` crea un pool `asyncpg` al arrancar. `PgConnection` wrappea
`asyncpg.Connection` con la interfaz que esperan los routes/services:
`execute()`, `execute_fetchall()`, `fetchval()`, `commit()`, `rollback()`.

### Tablas (18 tablas)

**Core**: `countries`, `players`, `leagues`, `fantasy_teams`, `team_players`
**Draft**: `drafts`, `draft_picks`, `draft_settings`
**Transfers**: `transfers`
**Scoring**: `matchdays`, `matches`, `match_scores`, `matchday_lineups`
**Market**: `market_windows`, `player_clauses`, `market_budgets`, `market_transactions`, `reposition_draft_picks`
**System**: `sync_state`

### Placeholders

PostgreSQL usa `$1, $2, ...` (NO `?` de SQLite). Para IN-clauses dinámicas:

```python
placeholders = ",".join(f"${i+OFFSET}" for i in range(len(items)))
query = f"SELECT ... WHERE id IN ({placeholders})"
await db.execute_fetchall(query, [*other_params, *items])
```

Donde `OFFSET` = 1 si no hay params previos, o `N+1` si ya hay `$1..$N`.

## Background tasks (main.py lifespan)

1. **`_autodraft_watchdog`** — cada 120s. Reanuda drafts en progreso con bots/autodraft.
2. **`_market_auto_transition_watchdog`** — cada 60s. Transiciona ventanas de mercado por fases.
3. **`_auto_market_window_creator`** — cada 60s. Crea ventanas de mercado automáticamente al detectar transición de fase del torneo.

## Autodraft

- `toggle_autodraft` devuelve 200 inmediatamente y lanza la cascada en background (`asyncio.create_task`).
- `_process_and_broadcast_autodraft` serializada por liga con `asyncio.Lock` (evita cascadas concurrentes).
- Cada pick se broadcastea por WebSocket con `sleep(1.0)` entre picks para UX realista.
- `DraftEngine.process_autodraft(max_iterations=1)` hace 1 pick por llamada; el outer loop itera.

## Configuración (env vars)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `WCF_SECRET_KEY` | `wc-fantasy-2026-dev-secret...` | JWT signing |
| `WCF_DATABASE_URL` | `postgresql://wcadmin:...@localhost:5432/wc_fantasy` | Postgres URL |
| `WCF_SIMULATOR_API_URL` | `""` | URL del wc-simulator (vacío = modo local) |
| `WCF_CORS_ORIGINS` | `*` | CORS origins |
| `WCF_JWT_ALGORITHM` | `HS256` | Algoritmo JWT |

## Comandos de desarrollo

```bash
make setup          # Crear venv + instalar deps
make dev            # uvicorn --reload en :8000
make docker-build   # Build Docker image
make docker-run     # Docker container local
```

## Infraestructura (k8s-homepi)

```
wc-fantasy (Deployment)  →  postgres-fantasy (StatefulSet)
      ↓ httpx                    PostgreSQL 16-alpine
wc-simulator (Deployment) →  postgres (StatefulSet)
```

- PVCs para datos persistentes
- PodDisruptionBudgets con `minAvailable: 1`
- RollingUpdate strategy con `maxUnavailable: 0`
- Flux CD reconcilia cambios en el repo k8s-homepi

## Convenciones

- **Idioma código**: inglés (variables, funciones, comentarios)
- **Idioma docs**: español
- **SQL**: PostgreSQL `$N` placeholders, `ON CONFLICT` en vez de `INSERT OR IGNORE`
- **Async**: todo el backend es async (FastAPI + asyncpg + httpx)
- **Cascadas largas**: siempre fire-and-forget con `asyncio.create_task`, nunca bloquear HTTP response
- **Tests**: `python -m py_compile` para verificar syntax antes de commit
- **Commits**: conventional commits (`fix(scope):`, `feat(scope):`, `chore:`)

## Relación con otros repos

| Repo | Relación |
|------|----------|
| `wc-simulator` | Fuente de datos (jugadores, partidos, resultados). wc-fantasy consume su API via httpx |
| `k8s-homepi` | Manifiestos K8s (deployments, services, PVCs). Flux CD sincroniza |
| `world-cup-list` | Repo original de datos de jugadores (Transfermarkt scraping). Inspiración para el frontend |
