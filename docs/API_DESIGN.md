# Diseño de la API — WC Fantasy 2026

> API REST servida por FastAPI. Todas las respuestas en JSON.
> Base URL: `/api/v1`

---

## Autenticación

### v1 (MVP)
- **Sin passwords**. Identificación por código de liga + nickname.
- Al unirse a una liga, se genera un **JWT** (`HS256`) con `team_id` y `league_id`.
- El JWT se envía como `Authorization: Bearer <token>` en cada request.
- Sin expiración corta (aceptable para MVP sin datos sensibles).

### Endpoints de auth

```
POST /api/v1/auth/join
  Body: { "league_code": "XK9F2A", "nickname": "jordi", "team_name": "FC Fantasía" }
  Response: { "token": "eyJ...", "team_id": "team-xyz789", "league_id": "league-abc123" }

POST /api/v1/auth/recover
  Body: { "league_code": "XK9F2A", "nickname": "jordi" }
  Response: { "token": "eyJ..." }
```

---

## Ligas

```
POST   /api/v1/leagues
  Body: { "name": "La Liga de los Cracks", "settings": { ... } }
  Response: { "id": "league-abc123", "code": "XK9F2A", ... }

GET    /api/v1/leagues/{league_id}
  Response: { liga completa con equipos y estado }

GET    /api/v1/leagues/{league_id}/standings
  Response: { clasificación con puntos por equipo }

PATCH  /api/v1/leagues/{league_id}/settings
  Auth: solo comisionado
  Body: { "max_clausulazos_per_window": 3 }
```

---

## Equipos fantasy

```
GET    /api/v1/leagues/{league_id}/teams
  Response: [ lista de equipos en la liga ]

GET    /api/v1/teams/{team_id}
  Response: { equipo con plantilla completa }

PATCH  /api/v1/teams/{team_id}/lineup
  Auth: solo propietario
  Body: {
    "formation": "4-3-3",
    "starters": ["esp-001", "fra-003", ...],
    "captain": "esp-001",
    "vice_captain": "fra-003"
  }
  Response: { alineación actualizada }

GET    /api/v1/teams/{team_id}/points
  Query: ?matchday=MD1
  Response: { desglose de puntos por jugador y jornada }
```

---

## Jugadores (catálogo)

```
GET    /api/v1/players
  Query: ?country=ESP&position=FWD&search=yamal&sort=market_value&limit=50
  Response: { "players": [...], "total": 600 }

GET    /api/v1/players/{player_id}
  Response: { jugador con stats y puntuaciones }

GET    /api/v1/players/{player_id}/scores
  Response: [ puntuaciones por jornada ]
```

---

## Draft

```
POST   /api/v1/leagues/{league_id}/draft/start
  Auth: solo comisionado
  Response: { "draft_id": "draft-001", "status": "in_progress" }

GET    /api/v1/leagues/{league_id}/draft
  Response: { estado del draft: ronda, turno, picks, disponibles }

POST   /api/v1/leagues/{league_id}/draft/pick
  Auth: solo el equipo en turno
  Body: { "player_id": "esp-001" }
  Response: { pick confirmado, siguiente turno }

POST   /api/v1/leagues/{league_id}/draft/autopick
  Auth: solo el equipo en turno
  Body: { "preferences": ["FWD", "MID", "DEF", "GK"] }
  Response: { jugador auto-seleccionado }

WS     /api/v1/leagues/{league_id}/draft/ws
  → Conexión WebSocket para actualizaciones en tiempo real
  
  Server → Client:
    { "type": "turn",      "team_id": "team-b", "time_left": 60, "round": 3, "pick": 2 }
    { "type": "pick",      "team_id": "team-a", "player": { ... }, "round": 3, "pick": 1 }
    { "type": "draft_end", "summary": { ... } }
  
  Client → Server:
    { "type": "pick",      "player_id": "esp-001" }
    { "type": "autopick",  "preferences": ["FWD", "MID"] }
```

---

## Mercado de traspasos

```
GET    /api/v1/leagues/{league_id}/market
  Response: { 
    "window_status": "open",
    "free_agents": [...],
    "pending_offers": [...],
    "recent_transfers": [...]
  }

POST   /api/v1/leagues/{league_id}/market/offer
  Auth: equipo que oferta
  Body: {
    "to_team_id": "team-abc",
    "players_offered": ["ger-005"],
    "players_requested": ["esp-001"],
    "amount": 50000000
  }
  Response: { oferta creada, status: pending }

POST   /api/v1/leagues/{league_id}/market/offer/{offer_id}/respond
  Auth: equipo receptor
  Body: { "action": "accept" | "reject" | "counter", "counter_offer": { ... } }

POST   /api/v1/leagues/{league_id}/market/clause
  Auth: equipo comprador
  Body: { "player_id": "esp-001" }
  Response: { clausulazo ejecutado, jugador transferido }
  Errors: 
    403 "Máximo de clausulazos alcanzado"
    402 "Presupuesto insuficiente"
    409 "Jugador ya fue clausulado en esta ventana"

POST   /api/v1/leagues/{league_id}/market/bid
  Auth: equipo que puja
  Body: { "player_id": "fra-010", "amount": 25000000 }
  Response: { puja registrada }

POST   /api/v1/leagues/{league_id}/market/release
  Auth: equipo propietario
  Body: { "player_id": "ger-005" }
  Response: { jugador liberado, presupuesto recuperado }

POST   /api/v1/leagues/{league_id}/market/veto/{transfer_id}
  Auth: solo comisionado
  Body: { "reason": "Traspaso sospechoso" }
```

---

## Puntuaciones

```
GET    /api/v1/scoring/matchdays
  Response: [ lista de jornadas con estado ]

GET    /api/v1/scoring/matchdays/{matchday_id}
  Response: { partidos, puntuaciones de todos los jugadores }

GET    /api/v1/scoring/live
  Response: { puntuaciones en tiempo real de partidos en curso }

SSE    /api/v1/scoring/live/stream
  → Server-Sent Events para puntuaciones en vivo
  
  data: { "type": "goal",    "player_id": "esp-001", "match": "ESP-CRC", "minute": 42 }
  data: { "type": "card",    "player_id": "crc-007", "card": "yellow", "minute": 55 }
  data: { "type": "update",  "player_id": "esp-001", "total_points": 12 }
```

---

## Admin / Comisionado

```
POST   /api/v1/leagues/{league_id}/admin/open-window
  Auth: solo comisionado
  Body: { "duration_hours": 24 }

POST   /api/v1/leagues/{league_id}/admin/close-window
  Auth: solo comisionado

POST   /api/v1/leagues/{league_id}/admin/kick/{team_id}
  Auth: solo comisionado
  Body: { "reason": "Inactividad" }

GET    /api/v1/leagues/{league_id}/admin/log
  Auth: solo comisionado
  Response: [ log de todas las acciones admin ]
```

---

## Códigos de error

| HTTP | Código | Descripción |
|---|---|---|
| 400 | `INVALID_REQUEST` | Body mal formado o parámetros inválidos |
| 401 | `UNAUTHORIZED` | Token ausente o inválido |
| 402 | `INSUFFICIENT_BUDGET` | No hay presupuesto para la operación |
| 403 | `FORBIDDEN` | No tienes permisos (no es tu equipo, no eres comisionado) |
| 404 | `NOT_FOUND` | Recurso no encontrado |
| 409 | `CONFLICT` | Jugador ya en otro equipo, clausulazo ya usado, etc. |
| 429 | `RATE_LIMITED` | Demasiadas peticiones |

---

## Rate limiting

| Endpoint | Límite |
|---|---|
| General | 60 req/min por IP |
| Draft (WebSocket) | Sin límite (autenticado) |
| Scoring (SSE) | 1 conexión por equipo |
| Market operations | 10 req/min por equipo |
