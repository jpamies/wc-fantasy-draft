# Roadmap — WC Fantasy 2026

> Plan de desarrollo por fases. El Mundial empieza el **11 de junio de 2026**.
> Objetivo: tener el MVP funcional al menos 2 semanas antes para testing.

---

## Timeline del Mundial 2026

```
Mayo 2026         Junio 2026                    Julio 2026
───────────────── ─────────────────────────────  ──────────────────
                  11 Jun: Inicio fase de grupos
                  26 Jun: Fin fase de grupos
                  28 Jun: Octavos de final
                  4-5 Jul: Cuartos de final
                  8-9 Jul: Semifinales
                  19 Jul: FINAL
```

---

## Fase 0 — Diseño y planificación ✅

**Estado**: Completada  
**Duración**: Abril 2026

| Tarea | Estado |
|---|---|
| README.md | ✅ |
| ARCHITECTURE.md | ✅ |
| DECISIONS.md (ADRs) | ✅ |
| RULES.md (reglas del juego) | ✅ |
| DATA_MODEL.md | ✅ |
| SCORING.md | ✅ |
| API_DESIGN.md | ✅ |
| ROADMAP.md | ✅ |
| Estructura de carpetas | ✅ |
| .gitignore + Makefile | ✅ |

---

## Fase 1 — Datos y backend base ✅

**Estado**: Completada  
**Objetivo**: API funcional con datos de jugadores y CRUD de ligas

### 1.1 Preparación de datos
- [x] Script para convertir JSONs de world-cup-list al formato WC Fantasy
- [x] Añadir campo `clause_value` (market_value × 1.5)
- [x] Validar datos: todos los jugadores con foto, posición, club
- [x] Crear `tournaments/groups.json` con los grupos del Mundial
- [x] Crear `tournaments/calendar.json` con el calendario de partidos

### 1.2 Backend — FastAPI scaffold
- [x] Setup FastAPI con uvicorn
- [x] Estructura de carpetas (models, routes, services)
- [x] Config desde variables de entorno
- [x] CORS configurado
- [x] Health check endpoint

### 1.3 Catálogo de jugadores API
- [x] `GET /api/v1/players` con filtros (país, posición, búsqueda)
- [x] `GET /api/v1/players/{id}` detalle
- [x] Datos via wc-simulator API (proxy en tiempo real)

### 1.4 Ligas API
- [x] `POST /api/v1/leagues` crear liga
- [x] `GET /api/v1/leagues/{id}` consultar liga
- [x] `POST /api/v1/auth/join` unirse a liga
- [x] Generación de JWT para sesión
- [x] PostgreSQL: persistir ligas en BD

### 1.5 Tests
- [x] Smoke test básico
- [ ] Tests unitarios para modelos
- [ ] Tests de integración para endpoints

---

## Fase 2 — Draft ✅

**Estado**: Completada  
**Objetivo**: Draft funcional con WebSocket

### 2.1 Motor de draft
- [x] Lógica de turnos (aleatorio + serpenteo)
- [x] Timer por pick (configurable)
- [x] Auto-pick por preferencias
- [x] Validación de mínimos por posición
- [x] Cola de draft (pre-selección)
- [x] AutoDraft inteligente (composición balanceada)
- [x] Bots (autodraft automático para ligas con menos humanos)

### 2.2 API de draft
- [x] `POST /draft/start` — iniciar draft
- [x] `POST /draft/pick` — seleccionar jugador
- [x] `GET /draft` — estado actual
- [x] WebSocket `/draft/ws` — tiempo real
- [x] `POST /draft/autodraft` — toggle autodraft (fire-and-forget)
- [x] `POST /draft/queue/add` — añadir a cola

### 2.3 Frontend — Draft UI
- [x] Sala de draft: lista de jugadores disponibles
- [x] Timer visual con countdown
- [x] Log de picks en tiempo real
- [x] Indicador de turno
- [x] Auto-pick config (preferencias de posición)
- [x] Cola de draft interactiva

### 2.4 Tests
- [ ] Test del motor de draft (turnos, serpenteo, timer)
- [ ] Test de WebSocket (conexión, mensajes, reconexión)

---

## Fase 3 — Gestión de equipo y alineación ✅

**Estado**: Completada  
**Objetivo**: Usuarios pueden gestionar su equipo

### 3.1 API de equipos
- [x] `GET /teams/{id}` — plantilla completa
- [x] `PATCH /teams/{id}/lineup` — cambiar alineación, formación, capitán
- [x] `GET /teams/{id}/matchday-lineup/{md}` — alineación por jornada
- [x] `PATCH /teams/{id}/matchday-lineup/{md}` — actualizar (con bloqueo mid-matchday)
- [x] Auto-alineación (mejores 11 por media de puntos)

### 3.2 Frontend — Mi equipo
- [x] Vista de plantilla con formación visual (campo de fútbol)
- [x] Drag & drop para cambiar titulares/suplentes
- [x] Selector de formación
- [x] Selector de capitán y vice-capitán
- [x] Bloqueo mid-matchday (🔒 jugadores cuyo país ya jugó)
- [x] Puntos por jornada en la vista de equipo

---

## Fase 4 — Puntuación ✅

**Estado**: Completada  
**Objetivo**: Puntuación automática sincronizada con wc-simulator

### 4.1 Sync de datos
- [x] `POST /scoring/sync` — obtener datos de wc-simulator
- [x] Mapeo automático de jugadores (lazy creation en BD)
- [x] Cálculo de puntos según tabla de SCORING.md
- [x] Clasificación con desglose por jornada

### 4.2 API de puntuación
- [x] `GET /scoring/matchdays` — calendario del simulador
- [x] `GET /scoring/matchdays/{id}` — partidos + scores
- [x] `GET /scoring/leaderboard` — leaderboard completo
- [x] `GET /leagues/{id}/standings` — clasificación interactiva

### 4.3 Frontend — Puntuaciones
- [x] Vista de jornada: partidos + puntuaciones
- [x] Desglose de puntos por jugador
- [x] Clasificación interactiva (General / Por Jornada)
- [x] Click en equipo → ver alineación con puntos
- [x] Ficha de jugador: atributos, stats, historial de puntos

### 4.4 Background tasks
- [x] `_autodraft_watchdog` (cada 120s, reanuda drafts)
- [x] `_market_auto_transition_watchdog` (cada 60s, transiciona ventanas)
- [x] `_auto_market_window_creator` (cada 60s, crea ventanas al cambiar de fase)

---

## Fase 5 — Mercado de traspasos ✅ 🆕

**Estado**: Completada  
**Objetivo**: Clausulazos, ofertas, mercado libre, ventanas automáticas

### 5.1 Motor de traspasos
- [x] Ofertas directas (proponer intercambio)
- [x] Clausulazos (compra inmediata por cláusula)
- [x] Mercado libre (pujas ciegas)
- [x] Liberación de jugadores
- [x] Validaciones: presupuesto, límites, ventana abierta
- [x] Ventanas de mercado automáticas entre fases del torneo
- [x] Transición automática de fases: clause_window → market_open → reposition_draft

### 5.2 API de mercado
- [x] `POST /market/clause` — ejecutar clausulazo
- [x] `POST /market/offer` — crear oferta
- [x] `POST /market/bid` — pujar por agente libre
- [x] `GET /leagues/{id}/market` — estado del mercado

### 5.3 Frontend — Mercado
- [x] Panel de mercado: jugadores libres, ofertas pendientes
- [x] Interfaz de clausulazo (confirmar compra)
- [x] Sistema de ofertas y contraofertas
- [x] Historial de traspasos

---

## Fase 6 — Polish y lanzamiento 🚧

**Estado**: En curso  
**Deadline**: 28 mayo 2026 (2 semanas antes del Mundial)

### 6.1 UX/UI
- [x] Diseño responsive (mobile-first)
- [x] Modo oscuro
- [ ] Animaciones y transiciones
- [x] Loading states y error handling

### 6.2 Despliegue
- [x] Frontend servido por FastAPI (estáticos)
- [x] Backend → K3s en Raspberry Pi (GHCR + Flux CD)
- [x] PostgreSQL → StatefulSet dedicado (`postgres-fantasy`)
- [x] Cloudflare Tunnel (HTTPS)
- [x] PodDisruptionBudgets + RollingUpdate zero-downtime
- [x] GitHub Actions CI/CD (multi-arch)

### 6.3 Testing con amigos
- [ ] Liga de prueba con 4-8 participantes
- [ ] Draft de prueba
- [ ] Feedback y ajustes

---

## Fase 7 — Post-MVP (durante el Mundial)

Mejoras incrementales mientras se juega:

- [x] Migración a PostgreSQL (completada ADR-010)
- [ ] OAuth (GitHub/Google) para persistencia
- [ ] Notificaciones push (via PWA)
- [ ] Estadísticas avanzadas (xG, pases completados, etc.)
- [ ] Head-to-head entre equipos fantasy
- [ ] Ligas públicas globales
- [ ] Modo "mini-liga" para fases eliminatorias
- [ ] App móvil (PWA wrapper)

---

## Prioridades

```
MUST HAVE (MVP - Fases 1-3) ✅ COMPLETADO
├── Catálogo de jugadores
├── Crear/unirse a ligas
├── Draft funcional
├── Gestión de equipo y alineación
└── Clasificación con puntuación automática

SHOULD HAVE (Fases 4-5) ✅ COMPLETADO
├── Puntuación automática (sync con wc-simulator)
├── Mercado de traspasos
├── Clausulazos
└── Ventanas de mercado automáticas

NICE TO HAVE (Fase 6-7) 🚧 EN CURSO
├── OAuth
├── Mobile PWA
├── Estadísticas avanzadas
└── Ligas públicas
```
