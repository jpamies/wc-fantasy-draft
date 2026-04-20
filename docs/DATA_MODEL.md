# Modelo de Datos — WC Fantasy 2026

> Diseño del modelo de datos. Representado como esquema conceptual que se
> implementará primero en JSON (v1), luego SQLite (v2), y PostgreSQL (v3).

---

## Diagrama de entidades

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│    League     │1    N │ FantasyTeam  │1    N │  TeamPlayer  │
│──────────────│───────│──────────────│───────│──────────────│
│ id           │       │ id           │       │ team_id (FK) │
│ name         │       │ league_id(FK)│       │ player_id(FK)│
│ code (6 chr) │       │ owner_nick   │       │ is_starter   │
│ mode         │       │ team_name    │       │ position_slot│
│ settings     │       │ budget       │       │ is_captain   │
│ commissioner │       │ formation    │       │ acquired_via │
│ status       │       │ created_at   │       │ acquired_at  │
│ created_at   │       └──────────────┘       └──────────────┘
└──────────────┘              │                      │
                              │                      │
                              │N                     │
                        ┌─────┴────────┐       ┌─────┴────────┐
                        │   Transfer   │       │    Player    │
                        │──────────────│       │──────────────│
                        │ id           │       │ id           │
                        │ league_id    │       │ name         │
                        │ from_team_id │       │ country_code │
                        │ to_team_id   │       │ position     │
                        │ player_id    │       │ detailed_pos │
                        │ type         │       │ club         │
                        │ amount       │       │ age          │
                        │ status       │       │ market_value │
                        │ created_at   │       │ photo_url    │
                        └──────────────┘       │ clause_value │
                                               └──────────────┘
                                                     │
                        ┌──────────────┐             │1
                        │   Country    │       ┌─────┴────────┐
                        │──────────────│       │  MatchScore  │
                        │ code (PK)    │       │──────────────│
                        │ name         │       │ id           │
                        │ name_local   │       │ player_id    │
                        │ flag         │       │ matchday     │
                        │ confederation│       │ minutes      │
                        │ group        │       │ goals        │
                        └──────────────┘       │ assists      │
                                               │ clean_sheet  │
┌──────────────┐                               │ yellow_cards │
│    Draft     │                               │ red_card     │
│──────────────│                               │ own_goals    │
│ id           │                               │ pen_missed   │
│ league_id    │                               │ pen_saved    │
│ status       │                               │ rating       │
│ current_round│                               │ bonus        │
│ current_pick │                               │ total_points │
│ pick_order   │                               │ source       │
│ picks[]      │                               └──────────────┘
└──────────────┘

┌──────────────┐       ┌──────────────┐
│   Matchday   │1    N │    Match     │
│──────────────│───────│──────────────│
│ id           │       │ id           │
│ name         │       │ matchday_id  │
│ date         │       │ home_country │
│ phase        │       │ away_country │
│ deadline     │       │ kickoff      │
│ status       │       │ score_home   │
└──────────────┘       │ score_away   │
                       │ status       │
                       └──────────────┘
```

---

## Entidades detalladas

### Player (Jugador)

Fuente primaria: `world-cup-list/data/*.json`

```json
{
  "id": "esp-001",
  "name": "Lamine Yamal",
  "country_code": "ESP",
  "position": "FWD",
  "detailed_position": "Right Winger",
  "club": "FC Barcelona",
  "club_logo": "https://...",
  "age": 18,
  "market_value": 200000000,
  "photo_url": "https://...",
  "clause_value": 300000000
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | string | ID único: `{country_code}-{seq}` |
| `name` | string | Nombre completo |
| `country_code` | string | ISO 3166-1 alpha-3 (ESP, FRA, etc.) |
| `position` | enum | GK, DEF, MID, FWD |
| `detailed_position` | string | Posición detallada (Right Winger, etc.) |
| `club` | string | Club actual |
| `club_logo` | string | URL del escudo |
| `age` | int | Edad |
| `market_value` | int | Valor de mercado en euros |
| `photo_url` | string | URL de la foto |
| `clause_value` | int | Cláusula = market_value × 1.5 (calculado) |

### Country (Selección)

```json
{
  "code": "ESP",
  "name": "Spain",
  "name_local": "España",
  "flag": "🇪🇸",
  "confederation": "UEFA",
  "group": "A"
}
```

### League (Liga fantasy)

```json
{
  "id": "league-abc123",
  "name": "La Liga de los Cracks",
  "code": "XK9F2A",
  "mode": "draft",
  "commissioner": "jordi",
  "settings": {
    "max_teams": 8,
    "initial_budget": 500000000,
    "draft_timer_seconds": 60,
    "max_clausulazos_per_window": 2,
    "auto_substitutions": true,
    "draft_order": "snake",
    "captain_multiplier": 2,
    "visibility": "private"
  },
  "status": "draft_pending",
  "created_at": "2026-06-01T10:00:00Z"
}
```

**Posibles estados** de una liga:
```
setup → draft_pending → draft_in_progress → active → completed
                                              ↕
                                        transfer_window
```

### FantasyTeam (Equipo fantasy)

```json
{
  "id": "team-xyz789",
  "league_id": "league-abc123",
  "owner_nick": "jordi",
  "team_name": "FC Fantasía",
  "budget": 350000000,
  "formation": "4-3-3",
  "token": "jwt-session-token...",
  "created_at": "2026-06-01T10:05:00Z"
}
```

### TeamPlayer (relación equipo-jugador)

```json
{
  "team_id": "team-xyz789",
  "player_id": "esp-001",
  "is_starter": true,
  "position_slot": "FWD-1",
  "is_captain": false,
  "acquired_via": "draft",
  "acquired_at": "2026-06-01T11:00:00Z"
}
```

| `acquired_via` | Descripción |
|---|---|
| `draft` | Seleccionado en el draft |
| `free_market` | Fichado del mercado libre |
| `transfer` | Traspaso negociado |
| `clause` | Clausulazo |

### Transfer (Traspaso)

```json
{
  "id": "transfer-001",
  "league_id": "league-abc123",
  "type": "clause",
  "from_team_id": "team-abc",
  "to_team_id": "team-xyz789",
  "players_offered": [],
  "players_requested": ["esp-001"],
  "amount": 300000000,
  "status": "completed",
  "created_at": "2026-06-20T15:00:00Z",
  "resolved_at": "2026-06-20T15:00:01Z"
}
```

**Tipos de transfer**: `offer`, `clause`, `free_market`, `release`

**Estados**: `pending` → `accepted` / `rejected` / `expired` / `completed` / `vetoed`

### Draft

```json
{
  "id": "draft-001",
  "league_id": "league-abc123",
  "status": "in_progress",
  "current_round": 5,
  "current_pick": 3,
  "pick_order": ["team-a", "team-b", "team-c", "team-d"],
  "picks": [
    {
      "round": 1,
      "pick": 1,
      "team_id": "team-a",
      "player_id": "fra-001",
      "timestamp": "2026-06-01T11:00:30Z"
    }
  ],
  "available_players": ["esp-001", "arg-002", "..."],
  "started_at": "2026-06-01T11:00:00Z"
}
```

### MatchScore (Puntuación por partido)

```json
{
  "id": "score-001",
  "player_id": "esp-001",
  "matchday": "MD1",
  "match_id": "match-esp-crc",
  "minutes_played": 90,
  "goals": 1,
  "assists": 1,
  "clean_sheet": true,
  "yellow_cards": 0,
  "red_card": false,
  "own_goals": 0,
  "penalties_missed": 0,
  "penalties_saved": 0,
  "rating": 8.5,
  "bonus_points": 2,
  "total_points": 14,
  "source": "sofascore",
  "updated_at": "2026-06-15T22:00:00Z"
}
```

### Matchday (Jornada)

```json
{
  "id": "MD1",
  "name": "Jornada 1 — Fase de Grupos",
  "date": "2026-06-11",
  "phase": "group_stage",
  "deadline": "2026-06-11T15:00:00Z",
  "status": "completed"
}
```

### Match (Partido)

```json
{
  "id": "match-esp-crc",
  "matchday_id": "MD1",
  "home_country": "ESP",
  "away_country": "CRC",
  "kickoff": "2026-06-11T18:00:00Z",
  "score_home": 3,
  "score_away": 0,
  "status": "finished"
}
```

---

## Relaciones clave

```
League 1──N FantasyTeam     Una liga tiene muchos equipos
League 1──1 Draft           Una liga tiene un draft (modo draft)
FantasyTeam 1──N TeamPlayer Un equipo tiene 23 jugadores
Player 1──N TeamPlayer      Un jugador puede estar en equipos de distintas ligas
Player 1──N MatchScore      Un jugador tiene puntuaciones por jornada
League 1──N Transfer        Una liga tiene muchos traspasos
Matchday 1──N Match         Una jornada tiene muchos partidos
Country 1──N Player         Una selección tiene muchos jugadores
```

---

## Índices recomendados (para SQLite/PostgreSQL)

```sql
-- Búsquedas frecuentes
CREATE INDEX idx_player_country ON player(country_code);
CREATE INDEX idx_player_position ON player(position);
CREATE INDEX idx_team_player_team ON team_player(team_id);
CREATE INDEX idx_team_player_player ON team_player(player_id);
CREATE INDEX idx_match_score_player ON match_score(player_id);
CREATE INDEX idx_match_score_matchday ON match_score(matchday);
CREATE INDEX idx_transfer_league ON transfer(league_id);
CREATE INDEX idx_league_code ON league(code);
```

---

## Almacenamiento v1 (JSON files)

Estructura de ficheros para el MVP:

```
data/
├── players/
│   ├── ESP.json          # Reutilizado de world-cup-list (spain.json → ESP.json)
│   ├── FRA.json
│   ├── ARG.json
│   └── ... (23 archivos)
├── tournaments/
│   ├── groups.json       # Composición de grupos
│   ├── calendar.json     # Calendario de partidos
│   └── matchdays.json    # Definición de jornadas
├── scoring/
│   ├── MD1.json          # Puntuaciones jornada 1
│   ├── MD2.json
│   └── ...
└── leagues/
    └── {league_id}/
        ├── league.json       # Config de la liga
        ├── draft.json        # Estado del draft
        ├── teams/
        │   ├── {team_id}.json
        │   └── ...
        └── transfers/
            └── transfers.json
```
