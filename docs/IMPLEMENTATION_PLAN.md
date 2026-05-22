# Plan de Implementación: Mercado y Draft de Reposición

## Fase 1: Base de Datos

### 1.1 Nuevas Tablas

```sql
-- Ventanas de mercado por fase del torneo
CREATE TABLE market_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    phase TEXT NOT NULL,  -- 'GRUPOS', 'Mercado_1', 'Reposicion_1', 'R32_1', 'Mercado_2', etc.
    market_type TEXT,  -- 'GRUPOS', 'Mercado_1_R32', 'Mercado_2_R32', 'Mercado_3_R32', 'Mercado_4_Semis', 'Mercado_5_Final'
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'clause_window', 'market_open', 'market_closed', 'reposition_draft', 'completed'
    
    -- Configuración de timing (editable por commissioner)
    clause_window_start DATETIME,  -- Cuándo abre protección de cláusulas
    clause_window_end DATETIME,    -- Cuándo cierra protección, abre mercado
    market_window_start DATETIME,  -- Igual a clause_window_end
    market_window_end DATETIME,    -- Cuándo cierra mercado, empieza reposición
    reposition_draft_start DATETIME,
    reposition_draft_end DATETIME,
    
    -- Límites del mercado
    max_buys INTEGER DEFAULT 3,  -- Máximo fichajes permitidos
    max_sells INTEGER DEFAULT 3,  -- Máximo robos permitidos
    initial_budget INTEGER DEFAULT 100000000,  -- 100M en centavos
    protect_budget INTEGER DEFAULT 300000000,  -- 300M para cláusulas
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(league_id) REFERENCES fantasy_leagues(id)
);

-- Cláusulas de protección por usuario y mercado
CREATE TABLE player_clauses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_window_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    clause_amount INTEGER NOT NULL DEFAULT 0,  -- En centavos (ej: 60000000 = 60M)
    is_blocked BOOLEAN DEFAULT 0,  -- Jugador bloqueado (max 2 por usuario)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(market_window_id, team_id, player_id),
    FOREIGN KEY(market_window_id) REFERENCES market_windows(id),
    FOREIGN KEY(team_id) REFERENCES fantasy_teams(id),
    FOREIGN KEY(player_id) REFERENCES players(id)
);

-- Presupuesto de cada usuario por mercado
CREATE TABLE market_budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_window_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    initial_budget INTEGER NOT NULL,  -- 100M en centavos
    earned_from_sales INTEGER DEFAULT 0,  -- Dinero ganado por robos
    spent_on_buys INTEGER DEFAULT 0,  -- Dinero gastado en fichajes
    remaining_budget INTEGER NOT NULL,  -- calculated: initial + earned - spent
    buys_count INTEGER DEFAULT 0,  -- Contador de fichajes
    sells_count INTEGER DEFAULT 0,  -- Contador de robos recibidos
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(market_window_id, team_id),
    FOREIGN KEY(market_window_id) REFERENCES market_windows(id),
    FOREIGN KEY(team_id) REFERENCES fantasy_teams(id)
);

-- Transacciones de compra/venta
CREATE TABLE market_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_window_id INTEGER NOT NULL,
    buyer_team_id INTEGER NOT NULL,  -- Equipo que compra
    seller_team_id INTEGER NOT NULL,  -- Equipo que vende/pierde jugador
    player_id INTEGER NOT NULL,
    clause_amount_paid INTEGER NOT NULL,  -- Lo que pagó buyer (precio de cláusula)
    transaction_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'completed',  -- 'completed', 'failed', 'reverted'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(market_window_id) REFERENCES market_windows(id),
    FOREIGN KEY(buyer_team_id) REFERENCES fantasy_teams(id),
    FOREIGN KEY(seller_team_id) REFERENCES fantasy_teams(id),
    FOREIGN KEY(player_id) REFERENCES players(id)
);

-- Reposición draft: orden y estado
CREATE TABLE reposition_draft_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_window_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    pick_number INTEGER NOT NULL,  -- Orden del turno
    player_id INTEGER,  -- NULL si el team pasó
    is_pass BOOLEAN DEFAULT 0,  -- 1 si el equipo pasó su turno
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(market_window_id) REFERENCES market_windows(id),
    FOREIGN KEY(team_id) REFERENCES fantasy_teams(id),
    FOREIGN KEY(player_id) REFERENCES players(id)
);
```

### 1.2 Cambios en Tablas Existentes

```sql
-- Agregar columnas a fantasy_teams
ALTER TABLE fantasy_teams ADD COLUMN protect_budget_allocated INTEGER DEFAULT 0;  -- Dinero asignado en protección
ALTER TABLE fantasy_teams ADD COLUMN last_market_window_id INTEGER;  -- Referencia al último mercado participado

-- Agregar columna a team_players para rastrear cuándo fue adquirido
ALTER TABLE team_players ADD COLUMN acquired_via TEXT;  -- 'initial_draft', 'market_buy', 'reposition_draft'
ALTER TABLE team_players ADD COLUMN market_window_acquired INTEGER;  -- Referencia al mercado donde fue adquirido

-- Agregar columnas a matches (necesario para detectar fin de fase)
ALTER TABLE matches ADD COLUMN tournament_phase TEXT;  -- 'GRUPOS', 'R32', 'R32', 'R32', 'R32', 'Semis', 'Final'
```

---

## Fase 2: API Endpoints

### 2.1 Gestión de Ventanas de Mercado (Commissioner)

**POST /leagues/{league_id}/admin/market-windows**
- Input: phase, market_type, timing config (clause_start, clause_end, market_start, market_end), budgets/limits
- Output: market_window_id, status
- Permisos: commissioner only
- Lógica: Crea nueva ventana de mercado, pasa a status='pending'

**PATCH /leagues/{league_id}/admin/market-windows/{window_id}**
- Input: clause_start, clause_end, market_start, market_end, max_buys, max_sells, initial_budget, protect_budget
- Output: updated market_window
- Permisos: commissioner only
- Lógica: Edita ventana si aún no ha iniciado fase de cláusulas

**POST /leagues/{league_id}/admin/market-windows/{window_id}/start-clause-phase**
- Output: market_window con status='clause_window'
- Permisos: commissioner only
- Lógica: Inicia fase de protección de cláusulas

**POST /leagues/{league_id}/admin/market-windows/{window_id}/start-market-phase**
- Output: market_window con status='market_open'
- Permisos: commissioner only
- Lógica: Cierra fase de cláusulas, abre mercado

**POST /leagues/{league_id}/admin/market-windows/{window_id}/close-market**
- Output: market_window con status='market_closed', inicializa market_budgets para todos los teams
- Permisos: commissioner only
- Lógica: Cierra mercado, prepara reposición draft

**POST /leagues/{league_id}/admin/market-windows/{window_id}/start-reposition-draft**
- Output: market_window con status='reposition_draft', calcula orden (descendente por presupuesto)
- Permisos: commissioner only
- Lógica: Inicia draft de reposición

### 2.2 Protección de Cláusulas

**GET /teams/{team_id}/market/{window_id}/clauses**
- Output: [{ player_id, clause_amount, is_blocked }, ...]
- Lógica: Lista cláusulas del equipo en ese mercado

**POST /teams/{team_id}/market/{window_id}/clauses/set**
- Input: { clauses: [{ player_id, amount, is_blocked }, ...] }
- Output: updated clauses list, remaining protect_budget
- Validaciones:
  - Total no excede 300M
  - Max 2 bloqueados
  - Solo jugadores en plantilla actual
  - Status window = 'clause_window'
- Lógica: Actualiza todas las cláusulas del equipo en esa ventana

**POST /teams/{team_id}/market/{window_id}/clauses/lock**
- Output: status='locked'
- Lógica: Bloquea cambios de cláusulas (antes de que cierre fase)

### 2.3 Explorador de Mercado

**GET /leagues/{league_id}/market/{window_id}/available-players**
- Query params: position, country, min_market_value, max_market_value, page, limit
- Output: [{ player_id, name, position, country, market_value, current_team_id, current_team_name, clause_amount, is_blocked }, ...]
- Validaciones: status = 'market_open'
- Lógica: Lista jugadores robables (de otros equipos)

**GET /leagues/{league_id}/market/{window_id}/my-budget**
- Output: { initial_budget, earned_from_sales, spent_on_buys, remaining_budget, buys_count, sells_count, max_buys, max_sells }
- Lógica: Presupuesto actual del usuario en mercado

**GET /teams/{team_id}/market/{window_id}/transaction-history**
- Output: [{ id, buyer_team, seller_team, player, clause_amount, date, direction }, ...]
- Lógica: Historial de compras y ventas (robos) del equipo

### 2.4 Transacciones de Mercado

**POST /teams/{team_id}/market/{window_id}/buy-player**
- Input: player_id
- Output: { success: true, transaction_id, new_budget, ... } o { success: false, reason: "Jugador ya vendido" }
- Validaciones:
  - Status = 'market_open'
  - Presupuesto suficiente (remaining >= clause_amount)
  - Buys_count < max_buys
  - Jugador existe en otro equipo
  - Jugador no está bloqueado en equipo seller
- Lógica:
  1. Lock player row (optimistic lock / transaction)
  2. Si jugador ya no existe en seller, return error
  3. Restar dinero del buyer
  4. Sumar dinero al seller
  5. Mover jugador de seller a buyer
  6. Incrementar buys_count de buyer, sells_count de seller
  7. Registrar transacción en market_transactions
  8. Notificar a ambos usuarios

### 2.5 Draft de Reposición

**GET /leagues/{league_id}/market/{window_id}/reposition-draft-state**
- Output: {
    status: 'waiting_turn' | 'your_turn' | 'completed',
    current_turn_team_id,
    current_turn_number,
    draft_order: [{ team_id, team_name, remaining_budget, players_count }, ...],
    remaining_available_players: N,
    my_picks: [{ turn, player_id }, ...],
    leaderboard: [{ team_id, players_count, gk_count, def_count, mid_count, fwd_count }, ...]
  }
- Lógica: Estado actual del draft de reposición

**GET /leagues/{league_id}/market/{window_id}/reposition-available-players**
- Query params: position, without_minutes_only (true)
- Output: [{ player_id, name, position, country, photo, market_value }, ...]
- Lógica: Jugadores disponibles (sin minutos jugados)

**POST /teams/{team_id}/market/{window_id}/reposition-draft-pick**
- Input: player_id (o NULL para pasar turno)
- Output: { success, new_state }
- Validaciones:
  - Es tu turno
  - Status = 'reposition_draft'
  - Jugador no ha jugado aún (sin minutos)
  - Si tienes <23 jugadores y eliges pasar, OK
  - Si es último turno válido, respeta mínimo 3 por posición
- Lógica:
  1. Registra pick en reposition_draft_picks
  2. Agrega jugador a equipo
  3. Calcula next turn (descendente por presupuesto)
  4. Si todos han pasado o todos tienen ≥23, marca draft como 'completed'
  5. Notifica a todos

### 2.6 Auto-Transiciones (Sistema)

**Sistema automático: detecta fin de fase → transición**

Cada X minutos (ej: cada 5 min):
- Si market_window.market_window_end < NOW y status='market_open' → cierra mercado (POST .../close-market)
- Si market_window.reposition_draft_end < NOW y status='reposition_draft' → completa draft

---

## Fase 3: Frontend

### 3.1 Páginas Nuevas

**[League]/Market**
- Tab 1: Protección de cláusulas (durante clause_window)
  - Sliders/inputs para distribuir 300M
  - Checkbox para 2 bloqueados
  - Preview: "Tienes X jugadores sin protección"
  - Botón: Guardar, Revisar antes de abrir mercado

- Tab 2: Explorador de mercado (durante market_open)
  - Filtros: posición, país, valor
  - Cards: nombre, equipo, cláusula, bloqueado sí/no
  - Botón: Comprar (si tienes presupuesto)
  - Presupuesto real-time: X + (robos recibidos) = total disponible

- Tab 3: Mi equipo en mercado
  - Tabla: mis jugadores, cláusula, bloqueado sí/no, intentos de robo
  - Notificaciones: "User X robó a Jugador Y por 60M"

- Tab 4: Draft de reposición (durante reposition_draft)
  - Turno actual, orden del draft
  - Disponibles: jugadores sin minutos
  - Mi plantilla: GK 1, DEF 2, MID 2, FWD 1 (contador en vivo)
  - Botón: Elegir jugador o Pasar

### 3.2 Componentes de Admin (Commissioner)

**[League]/Admin/Market**
- Crear mercado: dropdown de fase + calendario de timing
- Editar mercado: cambiar fechas/límites si no ha iniciado
- Botones: "Iniciar protección", "Abrir mercado", "Cerrar mercado", "Iniciar reposición"
- Estado visual: barra de progreso temporal

### 3.3 Notificaciones

- Toast: "¡User X te robó a Jugador Y! Recibiste 60M"
- Toast: "¡Compraste a Jugador Z por 40M!"
- Feed en liga: historial de transacciones últimas 24h

---

## Fase 4: Lógica de Negocio

### 4.1 Estado Machine (Mercado)

```
pending
  ↓
clause_window (fase de protección) ← [SET clauses, PUT clauses, GET balance]
  ↓
market_open (fase de compra) ← [GET available players, POST buy, GET transactions]
  ↓
market_closed (cálculo de orden de draft)
  ↓
reposition_draft ← [GET available players sin minutos, POST pick/pass]
  ↓
completed
```

### 4.2 Cálculo de Orden (Draft Reposición)

```python
# Después de cerrar mercado, calcular orden para reposición
def calculate_reposition_draft_order(market_window_id):
    # Obtener todos los teams en liga
    # Calcular remaining_budget de cada team
    # Ordenar descendente por remaining_budget
    # Crear reposition_draft_picks con pick_number = 1..N
    # Retornar lista ordenada
```

### 4.3 Validación de Pool (Reposición)

```python
# Verificar que hay suficientes jugadores sin minutos
def get_available_reposition_players(league_id, exclude_team_ids):
    # Obtener todos los jugadores del universo
    # Excluir: ya en plantillas, ya draftados antes, con minutos jugados
    # Retornar lista disponible
    
# Validar mínimo 3 por posición
def can_complete_reposition(team_id, picks_so_far, available_players):
    # Contar GK, DEF, MID, FWD en picks_so_far
    # Verificar si available_players tiene suficientes del resto
    # Retornar bool
```

---

## Fase 5: Testing

### 5.1 Unit Tests

- `test_clause_validation.py`: máximo 2 bloqueados, total ≤ 300M
- `test_budget_calculation.py`: remaining = initial + earned - spent
- `test_transaction_concurrency.py`: 2 users compran mismo player → 1 wins, 1 fails
- `test_reposition_order.py`: orden descendente por presupuesto
- `test_reposition_minimum_positions.py`: mínimo 3 de cada posición

### 5.2 Integration Tests

- `test_full_market_flow.py`: desde protección → compras → reposición → plantilla final
- `test_auto_transitions.py`: detecta fin de fase, cambia estados
- `test_notifications.py`: usuarios reciben alertas de compras/ventas

---

## Fase 6: Deployment

1. Commit: DB migrations (Alembic)
2. Commit: Backend endpoints + lógica
3. Test en environment local
4. Commit: Frontend components
5. Deploy: push a repos, Flux reconcilia
6. Test en K8s pod

---

## Estimación

- DB Schema: 1-2h
- Endpoints base: 4-6h
- Lógica (state machine, validaciones): 3-4h
- Frontend: 6-8h
- Testing: 2-3h
- Deployment + debugging: 1-2h

**Total estimado: 17-25h de trabajo**
