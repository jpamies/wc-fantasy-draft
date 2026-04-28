# Decisiones Técnicas (ADRs) — WC Fantasy 2026

> Registro de decisiones de arquitectura. Cada decisión incluye contexto,
> opciones evaluadas, y justificación.

---

## ADR-001: Frontend sin framework (Vanilla JS)

**Estado**: Aceptada  
**Fecha**: 2026-04-20

### Contexto
Necesitamos una webapp interactiva con varias vistas (draft, equipo, mercado, liga).
Tenemos experiencia previa con `world-cup-list` que usa vanilla HTML/CSS/JS.

### Opciones evaluadas

| Opción | Pros | Contras |
|---|---|---|
| **Vanilla JS** | Sin build step, despliegue trivial, DOM API nativa | Sin routing SPA built-in, gestión de estado manual |
| React/Next.js | Ecosistema maduro, componentes reutilizables | Build tooling pesado, overkill para el MVP |
| Svelte | Ligero, compilado, reactivo | Ecosistema menor, dependencia de bundler |
| Preact | React-compatible, 3KB | Necesita build step |

### Decisión
**Vanilla JS** con routing basado en hash (`#/draft`, `#/team`, etc.) y un mini-framework
de componentes casero (render functions que devuelven strings HTML).

### Consecuencias
- (+) Zero dependencies, deploy como estáticos
- (+) Coherencia con world-cup-list
- (-) Si la UI crece mucho, evaluar migración a Preact/Svelte
- (-) No hay hot-reload nativo (usar Live Server de VS Code)

### Revisión
Si al terminar la Fase 2 (draft) la complejidad del frontend resulta inmanejable,
migrar a Preact manteniendo la misma estructura de archivos.

---

## ADR-002: Backend con Python (FastAPI)

**Estado**: Aceptada  
**Fecha**: 2026-04-20

### Contexto
Necesitamos una API REST con soporte para WebSocket (draft en vivo),
integración con fuentes de datos externas (scraping), y evolución de base de datos.

### Opciones evaluadas

| Opción | Pros | Contras |
|---|---|---|
| **FastAPI (Python)** | Async, auto-docs, WebSocket, experiencia con transfermarkt-api | GIL para CPU-bound (no aplica aquí) |
| Express (Node.js) | JS en todo el stack | Menos tipado, más boilerplate para validación |
| Go (net/http) | Rendimiento, binario único | Más verboso, sin auto-docs, no necesitamos ese rendimiento |
| Flask (Python) | Simple, muy conocido | Sin async nativo, sin WebSocket built-in |

### Decisión
**FastAPI** con Pydantic para modelos, `uvicorn` como servidor ASGI.

### Consecuencias
- (+) WebSocket nativo para el draft
- (+) OpenAPI auto-generado (útil para frontend)
- (+) Scripts de scraping en el mismo lenguaje
- (-) Dependencia de Python en el servidor

---

## ADR-003: Base de datos con evolución progresiva (JSON → SQLite → PostgreSQL)

**Estado**: Completada (PostgreSQL en producción desde abril 2026)  
**Fecha**: 2026-04-20

### Contexto
Queremos empezar rápido reutilizando los JSON de `world-cup-list`, pero el fantasy
necesita relaciones complejas (ligas, equipos, traspasos, historial de puntos).

### Opciones evaluadas

| Opción | Pros | Contras |
|---|---|---|
| **JSON → SQLite → Postgres** | Evolución gradual, sin setup inicial | Requiere capa de abstracción |
| PostgreSQL desde el inicio | Potente, escalable | Overhead de setup para MVP |
| MongoDB | Flexible, JSON nativo | Consultas relacionales pobres |
| Solo JSON files | Sin dependencias | No escala, sin transacciones |

### Decisión
Patrón **Repository** que abstrae el almacenamiento. Tres implementaciones:
1. `JsonStore` — lee/escribe JSON files (MVP)
2. `SqliteStore` — SQLite con schema migrations (beta)
3. `PostgresStore` — PostgreSQL vía `asyncpg` (producción)

### Consecuencias
- (+) MVP funcional en horas, sin setup de BD
- (+) Migración transparente para el resto del código
- (-) Mantener 2-3 implementaciones del store
- (-) JsonStore no soporta concurrencia real (aceptable para MVP)

> **Nota (abril 2026)**: La evolución se completó. En producción se usa
> PostgreSQL 16 via `asyncpg` con un `PgConnection` wrapper que emula la
> interfaz de aiosqlite. SQLite y JSON stores ya no se usan. El patrón
> Repository no se implementó; en su lugar, un wrapper fino sobre asyncpg.

---

## ADR-004: Autenticación simplificada (v1) vs OAuth (v2)

**Estado**: Aceptada  
**Fecha**: 2026-04-20

### Contexto
El MVP necesita identificar participantes dentro de una liga sin fricción.
No hay pagos reales — la seguridad requerida es baja.

### Decisión

**v1 (MVP)**: Código de liga + nickname
- El comisionado crea una liga → recibe un código de 6 caracteres
- Los participantes se unen con el código + eligen un nickname
- Se genera un token de sesión (JWT sin expiración corta) almacenado en localStorage
- Sin passwords, sin emails, sin PII

**v2 (post-MVP)**: OAuth con GitHub y Google
- Login social para persistencia entre dispositivos
- Vinculación de cuenta con ligas existentes

### Consecuencias
- (+) Cero fricción para el usuario en v1
- (+) Sin gestión de passwords ni emails
- (-) Si pierdes el localStorage, pierdes el acceso al equipo
- Mitigación: endpoint de "recuperar equipo" por código de liga + nickname exacto

---

## ADR-005: Puntuación basada en fuentes externas

**Estado**: Aceptada  
**Fecha**: 2026-04-20

### Contexto
La puntuación del fantasy se basa en el rendimiento real de los jugadores.
Necesitamos una fuente fiable de datos de partidos.

### Opciones evaluadas

| Fuente | Pros | Contras |
|---|---|---|
| **SofaScore API** | Ratings detallados, stats por jugador | API no oficial, puede cambiar |
| Transfermarkt | Ya integrado en world-cup-list | No tiene stats de partido en vivo |
| Football-Data.org | API oficial, gratuita | Stats limitadas (goles, tarjetas) |
| Combinación | Lo mejor de cada fuente | Más complejidad |

### Decisión
**Enfoque por capas**:
1. **Base**: Football-Data.org o API-Football para eventos del partido (goles, tarjetas, sustituciones)
2. **Enriquecimiento**: SofaScore para ratings detallados y stats avanzadas
3. **Fallback**: Entrada manual por el comisionado si las APIs fallan

### Consecuencias
- (+) No dependemos de una sola fuente
- (+) Entrada manual como red de seguridad
- (-) Más lógica de reconciliación de datos

---

## ADR-006: Draft con WebSocket

**Estado**: Aceptada  
**Fecha**: 2026-04-20

### Contexto
El draft requiere turnos en tiempo real: todos los participantes ven quién elige,
el timer corre, y cuando alguien pickea, todos se actualizan instantáneamente.

### Decisión
**WebSocket** para la sala de draft con fallback a polling.

Protocolo:
```
Server → Client:
  { "type": "turn",       "player": "user123", "timeLeft": 60 }
  { "type": "pick",       "player": "user456", "picked": { "id": 42, "name": "..." } }
  { "type": "draft_end",  "results": [...] }

Client → Server:
  { "type": "pick",       "playerId": 42 }
  { "type": "auto_pick",  "preferences": ["FWD", "MID"] }
```

### Consecuencias
- (+) Experiencia en tiempo real, fluida
- (+) FastAPI soporta WebSocket nativamente
- (-) Más complejidad que REST puro
- (-) Necesita gestión de reconexión

---

## ADR-007: Monorepo con frontend y backend juntos

**Estado**: Aceptada  
**Fecha**: 2026-04-20

### Contexto
¿Separar frontend y backend en repos distintos o mantenerlos juntos?

### Decisión
**Monorepo** — todo en `wc-fanasy/` con carpetas separadas (`src/frontend/`, `src/backend/`).

### Consecuencias
- (+) Un solo repo, un solo PR, una sola verdad
- (+) Scripts compartidos, Makefile unificado
- (+) Más fácil para un equipo pequeño (1-3 personas)
- (-) Deploys acoplados (mitigable con CI condicional)

---

## ADR-008: Moneda virtual para el mercado de traspasos

**Estado**: Aceptada  
**Fecha**: 2026-04-20

### Contexto
El mercado de traspasos necesita una economía interna. ¿Cómo manejar el "dinero"
para clausulazos y pujas?

### Decisión
**Moneda virtual** (WC Coins / Fantasillones) con estas reglas:
- Cada equipo empieza con un **presupuesto fijo** (ej: 500M fantasillones)
- El valor de la cláusula de cada jugador se basa en su **valor de mercado real** (Transfermarkt)
- Los traspasos negociados pueden incluir jugadores + moneda
- El presupuesto se recalcula al vender/comprar

### Consecuencias
- (+) Añade estrategia al juego
- (+) Basado en datos reales (valor de mercado)
- (-) Necesita balanceo para que no sea P2W (pay-to-win con mejor conocimiento)
- Mitigación: todos empiezan con el mismo presupuesto, cláusulas transparentes

---

## ADR-009: SQLite por liga como estrategia de escalado

**Estado**: Superada (PostgreSQL reemplaza SQLite)  
**Fecha**: 2026-04-21

### Contexto
Actualmente toda la app usa un único fichero SQLite (`data/wc_fantasy.db`).
SQLite con WAL mode soporta lecturas concurrentes ilimitadas y una escritura
a la vez. Para el MVP (10 ligas, ~80 usuarios) es más que suficiente.

Si el proyecto crece a 50+ ligas activas simultáneas, la contención de
escritura en un solo fichero podría ser un cuello de botella.

### Propuesta

Separar en un SQLite compartido (catálogo read-only) + un SQLite por liga:

```
data/
├── players.db              ← catálogo de jugadores (read-only)
├── leagues/
│   ├── league-abc123.db    ← equipos, draft, traspasos, scores
│   ├── league-def456.db
│   └── ...
```

### Ventajas
- (+) Zero contención entre ligas
- (+) Borrar una liga = borrar un fichero
- (+) Backup/restore granular por liga
- (+) Cada liga podría estar en un File Share diferente

### Inconvenientes
- (-) Más complejidad en routing de conexiones
- (-) Queries cross-liga imposibles (ej: ranking global)

### Trigger para implementar
Cuando se detecte lentitud en escrituras concurrentes entre ligas distintas,
o cuando haya 50+ ligas activas simultáneas.

### Cambio necesario
Solo afecta a `database.py` (cambiar path del DB según `league_id`).
El schema SQL no cambia.

> **Nota (abril 2026)**: Esta propuesta queda superada por la migración
> a PostgreSQL (ADR-010). Postgres maneja la concurrencia entre ligas sin
> necesidad de separar ficheros.

---

## ADR-010: Migración de SQLite a PostgreSQL

**Estado**: Implementada  
**Fecha**: 2026-04-28

### Contexto
SQLite con WAL mode funcionaba para el MVP, pero la concurrencia de escritura
(múltiples ligas activas, autodraft de bots, sync de scoring, mercado)
empezaba a generar `database is locked` bajo carga. Además, el deploy en K8s
con PVC y single-writer era frágil ante pod restarts.

### Decisión
Migrar a **PostgreSQL 16-alpine** via `asyncpg 0.30.0`:
- StatefulSet `postgres-fantasy` en K8s con PVC dedicado
- Connection pool (min=2, max=10) gestionado por asyncpg
- `PgConnection` wrapper en `database.py` que emula la interfaz de aiosqlite
  (`execute`, `execute_fetchall`, `fetchval`, `commit`, `rollback`)
- Env var `WCF_DATABASE_URL` para la connection string

### Cambios clave
- `?` placeholders → `$1, $2, ...` (asyncpg/libpq)
- `INSERT OR IGNORE` → `ON CONFLICT DO NOTHING`
- `INSERT OR REPLACE` → `ON CONFLICT DO UPDATE`
- `cursor.lastrowid` → `RETURNING id`
- `aiosqlite` eliminado de requirements; `asyncpg` añadido
- Dynamic IN-clauses: `",".join(f"${i+OFFSET}" for i in range(len(items)))`

### Consecuencias
- (+) Concurrencia de escritura real (MVCC)
- (+) Preparado para múltiples réplicas del pod fantasy
- (+) Mejor integridad referencial y tipos
- (-) Requiere un pod adicional (postgres-fantasy StatefulSet)
- (-) El wrapper PgConnection añade indirección, pero mantiene compatibilidad

---

## ADR-011: Autodraft fire-and-forget con lock por liga

**Estado**: Implementada  
**Fecha**: 2026-04-28

### Contexto
El endpoint `toggle_autodraft` esperaba (`await`) a que toda la cascada de
picks de bots terminara antes de devolver 200. En ligas con 6 bots, esto
podía tardar >10 segundos (1s delay × picks restantes), bloqueando la UI
y haciendo que el botón de autodraft nunca pareciera activarse.

### Decisión
- Todos los call-sites que disparan `_process_and_broadcast_autodraft` usan
  `asyncio.create_task` (fire-and-forget).
- Un `asyncio.Lock` por liga previene cascadas concurrentes.
- `DraftEngine.process_autodraft(max_iterations=1)` — 1 pick por llamada,
  el outer loop pone `sleep(1.0)` entre broadcasts para UX realista.

### Consecuencias
- (+) El HTTP response vuelve instantáneamente
- (+) La UI actualiza el botón de autodraft sin delay
- (+) Los picks llegan por WebSocket con ritmo realista (1 pick/segundo)
- (-) Si el pod se reinicia mid-cascada, el `_autodraft_watchdog` (cada 120s)
  retoma la cascada automáticamente
