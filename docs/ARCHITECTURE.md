# Arquitectura del Sistema — WC Fantasy 2026

## Visión general

WC Fantasy es una webapp de fantasy football para el Mundial 2026 con dos componentes principales:
un **frontend estático** que consume una **API REST** respaldada por **PostgreSQL** via `asyncpg`.

## Diagrama de alto nivel

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENTES                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐              │
│  │ Browser  │  │ Browser  │  │  Mobile PWA  │              │
│  │ (Desktop)│  │ (Mobile) │  │  (futuro)    │              │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘              │
└───────┼──────────────┼───────────────┼──────────────────────┘
        │              │               │
        ▼              ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (SPA)                          │
│  HTML + CSS + Vanilla JS                                    │
│  Servido desde GitHub Pages / CDN                           │
│                                                             │
│  Páginas:                                                   │
│  ├── /              → Landing + login liga                  │
│  ├── /draft         → Sala de draft en vivo                 │
│  ├── /team          → Gestión de equipo + formación         │
│  ├── /market        → Mercado de traspasos                  │
│  ├── /league        → Clasificación + estadísticas          │
│  ├── /match         → Puntuación en vivo (día de partido)   │
│  └── /admin         → Gestión de liga (comisionado)         │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/JSON
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    BACKEND (API REST)                        │
│  Python — FastAPI                                           │
│                                                             │
│  Módulos:                                                   │
│  ├── auth/          → Autenticación (códigos + nicknames)   │
│  ├── leagues/       → CRUD de ligas                         │
│  ├── teams/         → Gestión de equipos fantasy            │
│  ├── draft/         → Motor de draft (turnos + WebSocket)   │
│  ├── market/        → Traspasos, clausulazos, pujas         │
│  ├── scoring/       → Cálculo de puntos                     │
│  └── players/       → Catálogo de jugadores                 │
└────────────────────────┬────────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
┌────────────────────┐  ┌────────────────────────┐
│    BASE DE DATOS   │  │   FUENTES EXTERNAS     │
│                    │  │                        │
│  PostgreSQL 16     │  │  └── wc-simulator API  │
│  (asyncpg pool)    │  │      (jugadores,       │
│                    │  │       partidos, stats)  │
└────────────────────┘  └────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  WORKERS / CRON JOBS                         │
│                                                             │
│  ├── fetch_scores.py    → Cada 5 min durante partidos       │
│  ├── fetch_players.py   → Diario (datos de plantillas)      │
│  ├── update_standings.py → Post-partido (clasificaciones)   │
│  └── GitHub Actions      → Scheduler para actualizaciones   │
└─────────────────────────────────────────────────────────────┘
```

## Componentes detallados

### Frontend

**Tecnología**: HTML5 + CSS3 + Vanilla JavaScript (sin framework)

**Justificación**: Coherencia con el proyecto `world-cup-list`, sin necesidad de build step,
despliegue trivial en GitHub Pages. Si la complejidad crece, se evaluará migración a un
framework ligero (Preact, Svelte).

**Responsabilidades**:
- Renderizado de UI (listas, formaciones, tablas)
- Estado local de la sesión (localStorage para caché)
- Comunicación con la API via `fetch()`
- WebSocket para el draft en tiempo real

**Páginas principales**:

| Ruta | Función | Datos principales |
|---|---|---|
| `/` | Landing, crear/unirse a liga | Código de liga, nickname |
| `/draft` | Sala de draft interactivo | Lista de jugadores, turnos, picks |
| `/team` | Gestión de equipo | Plantilla, formación, alineación |
| `/market` | Mercado de traspasos | Ofertas, clausulazos, jugadores libres |
| `/league` | Clasificación de la liga | Puntos, estadísticas, historial |
| `/match` | Día de partido — puntuación en vivo | Scores en tiempo real |
| `/admin` | Panel del comisionado de liga | Config de liga, expulsiones |

### Backend (API)

**Tecnología**: Python 3.11+ con FastAPI

**Justificación**: Experiencia existente con `transfermarkt-api` (mismo stack), async nativo,
autodocumentación con OpenAPI, servidor WebSocket integrado para el draft.

**Estructura de módulos**:

```
backend/
├── main.py                 # Entry point, CORS, lifespan
├── config.py               # Settings (env vars)
├── dependencies.py         # Dependency injection
├── models/
│   ├── player.py           # Jugador (del catálogo)
│   ├── fantasy_team.py     # Equipo fantasy
│   ├── league.py           # Liga
│   ├── draft.py            # Estado del draft
│   ├── transfer.py         # Transferencia / oferta
│   └── match_score.py      # Puntuación de partido
├── routes/
│   ├── auth.py             # Login/registro por liga
│   ├── leagues.py          # CRUD ligas
│   ├── teams.py            # CRUD equipos fantasy
│   ├── draft.py            # WebSocket + REST para draft
│   ├── market.py           # Traspasos y clausulazos
│   ├── scoring.py          # Consulta de puntuaciones
│   └── players.py          # Catálogo de jugadores
├── services/
│   ├── draft_engine.py     # Lógica de turnos del draft
│   ├── market_engine.py    # Motor de traspasos
│   ├── scoring_engine.py   # Calculador de puntos
│   └── data_loader.py      # Carga desde JSON / DB
└── db/
    ├── json_store.py       # v1: lectura/escritura JSON
    ├── sqlite_store.py     # v2: SQLite
    └── migrations/         # Migraciones de esquema
```

### Base de datos — Evolución progresiva

| Fase | Tecnología | Cuándo | Razón |
|---|---|---|---|
| **v1** | JSON files | MVP | Sin setup, reutiliza datos de world-cup-list |
| **v2** | SQLite | Beta | Consultas complejas, transacciones, un solo fichero |
| **v3** | PostgreSQL | Producción | Concurrencia, escalabilidad, backups |

La capa de acceso a datos usa un **patrón Repository** para abstraer el almacenamiento.
El cambio de v1 → v2 → v3 debe ser transparente para las rutas y servicios.

### Fuentes de datos externas

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  world-cup-list  │     │   Transfermarkt  │     │    SofaScore     │
│  (JSON estáticos)│     │  (HTML scraping) │     │   (REST API)     │
│                  │     │                  │     │                  │
│  23 países       │     │  Valor de        │     │  Puntuaciones    │
│  ~600 jugadores  │     │  mercado actual  │     │  en vivo         │
│  Posiciones      │     │  Nuevas          │     │  Ratings         │
│  Fotos           │     │  convocatorias   │     │  Estadísticas    │
└────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘
         │                        │                        │
         └────────────┬───────────┘                        │
                      ▼                                    ▼
              ┌───────────────┐                  ┌─────────────────┐
              │ fetch_players │                  │  fetch_scores   │
              │     .py       │                  │      .py        │
              └───────┬───────┘                  └────────┬────────┘
                      │                                   │
                      ▼                                   ▼
              ┌───────────────────────────────────────────────────┐
              │              BASE DE DATOS                        │
              │  players, match_scores, player_stats              │
              └───────────────────────────────────────────────────┘
```

### Comunicación en tiempo real

El **draft** y las **puntuaciones en vivo** requieren comunicación en tiempo real:

- **Draft**: WebSocket bidireccional
  - Server → Client: turno actual, picks de otros, timer
  - Client → Server: selección de jugador
  
- **Puntuaciones en vivo**: Server-Sent Events (SSE) o polling corto (15s)
  - Más simple que WebSocket para datos unidireccionales
  - Fallback a polling si SSE no disponible

## Seguridad

| Aspecto | Estrategia |
|---|---|
| Autenticación v1 | Código de liga + nickname (sin passwords) |
| Autenticación v2 | OAuth (GitHub/Google) |
| Autorización | Solo el propietario puede modificar su equipo |
| CORS | Whitelist de dominios permitidos |
| Rate limiting | Límite por IP en endpoints públicos |
| Datos sensibles | Sin PII más allá del nickname. Sin pagos reales |
| Secrets | Variables de entorno, nunca en código |

## Despliegue

```
                    ┌─────────────┐
                    │   GitHub    │
                    │   Repo      │
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │   GitHub    │
                    │   Actions   │
                    └──┬──────┬───┘
                       │      │
              ┌────────┘      └────────┐
              ▼                        ▼
    ┌──────────────────┐    ┌──────────────────┐
    │  GitHub Pages    │    │    Fly.io        │
    │  (Frontend)      │    │    (Backend)     │
    │                  │    │                  │
    │  HTML/CSS/JS     │    │  FastAPI +       │
    │  estáticos       │    │  SQLite/Postgres │
    └──────────────────┘    └──────────────────┘
```

**CI/CD**: GitHub Actions
- Push a `main` → deploy frontend a GitHub Pages
- Push a `main` con cambios en `src/backend/` → deploy a Fly.io
- Cron job nocturno → actualizar datos de jugadores
- Cron job cada 5 min (días de partido) → actualizar puntuaciones
