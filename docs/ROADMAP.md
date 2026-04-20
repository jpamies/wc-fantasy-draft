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

**Estado**: En curso  
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

## Fase 1 — Datos y backend base

**Objetivo**: API funcional con datos de jugadores y CRUD de ligas  
**Duración estimada**: ~2 semanas

### 1.1 Preparación de datos
- [ ] Script para convertir JSONs de world-cup-list al formato WC Fantasy
- [ ] Añadir campo `clause_value` (market_value × 1.5)
- [ ] Validar datos: todos los jugadores con foto, posición, club
- [ ] Crear `tournaments/groups.json` con los grupos del Mundial
- [ ] Crear `tournaments/calendar.json` con el calendario de partidos

### 1.2 Backend — FastAPI scaffold
- [ ] Setup FastAPI con uvicorn
- [ ] Estructura de carpetas (models, routes, services)
- [ ] Config desde variables de entorno
- [ ] CORS configurado
- [ ] Health check endpoint

### 1.3 Catálogo de jugadores API
- [ ] `GET /api/v1/players` con filtros (país, posición, búsqueda)
- [ ] `GET /api/v1/players/{id}` detalle
- [ ] JsonStore: leer datos desde ficheros JSON

### 1.4 Ligas API
- [ ] `POST /api/v1/leagues` crear liga
- [ ] `GET /api/v1/leagues/{id}` consultar liga
- [ ] `POST /api/v1/auth/join` unirse a liga
- [ ] Generación de JWT para sesión
- [ ] JsonStore: persistir ligas en ficheros

### 1.5 Tests
- [ ] Tests unitarios para modelos
- [ ] Tests de integración para endpoints
- [ ] Makefile con `make test`

---

## Fase 2 — Draft

**Objetivo**: Draft funcional con WebSocket  
**Duración estimada**: ~2 semanas

### 2.1 Motor de draft
- [ ] Lógica de turnos (aleatorio + serpenteo)
- [ ] Timer por pick (configurable)
- [ ] Auto-pick por preferencias
- [ ] Validación de mínimos por posición

### 2.2 API de draft
- [ ] `POST /draft/start` — iniciar draft
- [ ] `POST /draft/pick` — seleccionar jugador
- [ ] `GET /draft` — estado actual
- [ ] WebSocket `/draft/ws` — tiempo real

### 2.3 Frontend — Draft UI
- [ ] Sala de draft: lista de jugadores disponibles
- [ ] Timer visual con countdown
- [ ] Log de picks en tiempo real
- [ ] Indicador de turno
- [ ] Auto-pick config (preferencias de posición)

### 2.4 Tests
- [ ] Test del motor de draft (turnos, serpenteo, timer)
- [ ] Test de WebSocket (conexión, mensajes, reconexión)

---

## Fase 3 — Gestión de equipo y alineación

**Objetivo**: Usuarios pueden gestionar su equipo  
**Duración estimada**: ~1 semana

### 3.1 API de equipos
- [ ] `GET /teams/{id}` — plantilla completa
- [ ] `PATCH /teams/{id}/lineup` — cambiar alineación, formación, capitán

### 3.2 Frontend — Mi equipo
- [ ] Vista de plantilla con formación visual (campo de fútbol)
- [ ] Drag & drop para cambiar titulares/suplentes
- [ ] Selector de formación
- [ ] Selector de capitán y vice-capitán
- [ ] Contador de deadline

---

## Fase 4 — Puntuación

**Objetivo**: Puntuación automática basada en datos reales  
**Duración estimada**: ~2 semanas

### 4.1 Scripts de datos
- [ ] `fetch_scores.py` — obtener datos de SofaScore/Football-Data
- [ ] Mapeo de player IDs (WC Fantasy ↔ fuentes externas)
- [ ] Cálculo de puntos según tabla de SCORING.md
- [ ] `update_standings.py` — calcular clasificación

### 4.2 API de puntuación
- [ ] `GET /scoring/matchdays` — jornadas
- [ ] `GET /scoring/matchdays/{id}` — puntuaciones
- [ ] `GET /scoring/live` — puntuaciones en vivo
- [ ] SSE `/scoring/live/stream` — stream en tiempo real

### 4.3 Frontend — Puntuaciones
- [ ] Vista de jornada: partidos + puntuaciones
- [ ] Puntuación en vivo durante partidos
- [ ] Desglose de puntos por jugador
- [ ] Clasificación de la liga con gráfico de evolución

### 4.4 GitHub Actions
- [ ] Cron job: actualizar datos de jugadores (diario)
- [ ] Cron job: fetch scores durante días de partido (cada 5 min)

---

## Fase 5 — Mercado de traspasos 🆕

**Objetivo**: Clausulazos, ofertas, mercado libre  
**Duración estimada**: ~2 semanas

### 5.1 Motor de traspasos
- [ ] Ofertas directas (proponer intercambio)
- [ ] Clausulazos (compra inmediata por cláusula)
- [ ] Mercado libre (pujas ciegas)
- [ ] Liberación de jugadores
- [ ] Validaciones: presupuesto, límites, ventana abierta

### 5.2 API de mercado
- [ ] `POST /market/offer` — crear oferta
- [ ] `POST /market/offer/{id}/respond` — aceptar/rechazar
- [ ] `POST /market/clause` — ejecutar clausulazo
- [ ] `POST /market/bid` — pujar por agente libre
- [ ] `POST /market/release` — liberar jugador
- [ ] `POST /admin/veto/{id}` — vetar traspaso

### 5.3 Frontend — Mercado
- [ ] Panel de mercado: jugadores libres, ofertas pendientes
- [ ] Interfaz de clausulazo (confirmar compra)
- [ ] Sistema de ofertas y contraofertas
- [ ] Historial de traspasos
- [ ] Notificaciones de ofertas recibidas

---

## Fase 6 — Polish y lanzamiento

**Objetivo**: Listo para usar con amigos  
**Deadline**: 28 mayo 2026 (2 semanas antes del Mundial)

### 6.1 UX/UI
- [ ] Diseño responsive (mobile-first)
- [ ] Modo oscuro
- [ ] Animaciones y transiciones
- [ ] Loading states y error handling

### 6.2 Despliegue
- [ ] Frontend → GitHub Pages
- [ ] Backend → Fly.io
- [ ] CI/CD con GitHub Actions
- [ ] Dominio propio (opcional)

### 6.3 Testing con amigos
- [ ] Liga de prueba con 4-8 participantes
- [ ] Draft de prueba
- [ ] Feedback y ajustes

---

## Fase 7 — Post-MVP (durante el Mundial)

Mejoras incrementales mientras se juega:

- [ ] Migración de JSON → SQLite
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
MUST HAVE (MVP - Fases 1-3)
├── Catálogo de jugadores
├── Crear/unirse a ligas
├── Draft funcional
├── Gestión de equipo y alineación
└── Clasificación básica (puntos manuales si hace falta)

SHOULD HAVE (Fases 4-5)
├── Puntuación automática
├── Mercado de traspasos
├── Clausulazos
└── Puntuación en vivo

NICE TO HAVE (Fase 6-7)
├── OAuth
├── Mobile PWA
├── Estadísticas avanzadas
└── Ligas públicas
```
