# Sistema de Mercado y Draft de Reposición - Flujo End-to-End

## 1. Ciclo de Vida de un Mercado

```
GRUPOS (Matchday 1-4)
    ↓
MERCADO 1 ABRE
    ↓
Fase 1: PROTECCIÓN DE CLÁUSULAS (24h típico)
  - UI: Sliders para distribuir 300M entre jugadores
  - Max 2 bloqueados (no pueden ser robados)
  - Cada usuario ajusta su protección
  - Auto-cierra al llegar deadline
    ↓
Fase 2: MERCADO ABIERTO (24h típico)
  - UI: Explorador de jugadores robables
  - Cada usuario ve otros jugadores + claúsulas
  - Compra = paga cláusula al otro team
  - Presupuesto: 100M + dinero recibido por robos
  - Max 3 compras por usuario
  - Max 3 robos recibidos por usuario
  - Auto-cierra al llegar deadline
    ↓
Fase 3: DRAFT DE REPOSICIÓN (variable)
  - UI: Draft board con orden descendente por presupuesto
  - Cada team (en orden) elige 1 jugador o pasa
  - Solo jugadores sin minutos
  - Mínimo 3 de cada posición (si hay disponibles)
  - Llena hasta 23 jugadores
  - Termina cuando todos pasan o alcanzan 23
    ↓
R32 / 1/16 COMIENZA con nuevas plantillas
    ↓
MERCADO 2 ABRE (proceso se repite)
```

## 2. Flujo de Usuario: Protección de Cláusulas

```
Usuario accede a: #/market/1

Backend retorna: window.status = "clause_window"

Frontend muestra:
  ┌─────────────────────────────────────┐
  │ 🏪 Mercado — R32 / 1/16            │
  │ Status: clause_window              │
  ├─────────────────────────────────────┤
  │ Presupuesto: 300M                   │
  ├─────────────────────────────────────┤
  │ 🔐 Protección de Cláusulas          │
  │                                      │
  │ [Mbappé (FWD)]  [✓] Bloqueado     │
  │ |━━━━━━━━━━━━━━━|  80M             │
  │                                      │
  │ [Kane (FWD)]    [ ] Bloqueado      │
  │ |━━━━━━━━━━━━━━━|  70M             │
  │                                      │
  │ [De Bruyne (MID)] [ ] Bloqueado    │
  │ |━━━━━━━━━━━━━━━|  60M             │
  │ ...más jugadores...                 │
  │                                      │
  │ [Guardar Cláusulas]                │
  └─────────────────────────────────────┘

Usuario guarda:
  - Mbappé: 80M, bloqueado
  - Kane: 70M, no bloqueado
  - De Bruyne: 60M, no bloqueado
  - ...resto en 0M...
  
Backend:
  1. Valida: sum=210M ≤ 300M ✓
  2. Valida: blocked_count=1 ≤ 2 ✓
  3. INSERT INTO player_clauses
  4. Retorna OK

Al llegar deadline (clause_window_end):
  - Auto-transición a "market_open"
  - Watchdog en main.py detecta timestamp
  - MarketService.start_market_phase()
  - Inicializa market_budgets (100M para todos)
```

## 3. Flujo de Usuario: Mercado Abierto

```
Usuario recarga página o espera auto-refresh

Backend retorna: window.status = "market_open"
                 budget.remaining_budget = 100000000 (100M)

Frontend muestra:
  ┌──────────────────────────────────────────────┐
  │ 🏪 Mercado — R32 / 1/16                     │
  │ Status: market_open                          │
  ├──────────────────────────────────────────────┤
  │ Presupuesto: 100M                            │
  │ Compras: 0/3     Robos Recibidos: 0/3       │
  ├──────────────────────────────────────────────┤
  │ 🎯 Explorador de Mercado                    │
  │                                               │
  │ Filtro: [GK ▼] [DEF ▼] [MID ▼] [FWD ▼]    │
  │                                               │
  │ ┌─────────────────────────────────────────┐ │
  │ │ [foto] Mbappé (FWD)                     │ │
  │ │         Real Madrid · FRA               │ │
  │ │ Cláusula: 80M 🔒 BLOQUEADO            │ │
  │ │ [Comprar] (disabled - está bloqueado) │ │
  │ └─────────────────────────────────────────┘ │
  │                                               │
  │ ┌─────────────────────────────────────────┐ │
  │ │ [foto] De Bruyne (MID)                  │ │
  │ │         Man City · BEL                  │ │
  │ │ Cláusula: 60M                          │ │
  │ │ [Comprar]                              │ │
  │ └─────────────────────────────────────────┘ │
  │ ...más jugadores...                         │
  └──────────────────────────────────────────────┘

Usuario hace click en [Comprar] por De Bruyne (60M):
  
Frontend:
  1. confirm("¿Comprar por 60M?")
  2. POST /teams/{id}/market/{window_id}/buy-player
  3. { player_id: "BEL-001" }

Backend MarketService.buy_player():
  1. Valida: buyer budget ≥ 60M ✓
  2. Valida: buys_count < 3 ✓
  3. Valida: seller sells_count < 3 ✓
  4. Transacción ACID:
     a. UPDATE team_players: De Bruyne → usuario
     b. UPDATE market_budgets buyer: spent+60, buys+1
     c. UPDATE market_budgets seller: earned+60, sells+1
     d. INSERT market_transactions
  5. Retorna success

Frontend:
  - Toast: "¡Jugador comprado!"
  - Recarga página
  - Presupuesto ahora: 40M (100 - 60)
  - Compras: 1/3

Otro usuario ve a De Bruyne:
  - Ya NO aparece en explorador (está en equipo de usuario 1)
  - Su presupuesto creció en 60M (de 100M → 160M)
```

## 4. Flujo de Usuario: Reposición Draft

```
Al llegar reposition_draft_end:
  - Auto-transición a "reposition_draft"
  - Watchdog calcula orden descendente: [250M, 180M, 120M, ...]
  - Crea reposition_draft_picks con pick_number 1,2,3...

Usuario 1 (250M) accede #/market/1:

Frontend retorna:
  ┌─────────────────────────────────────┐
  │ 📋 Draft de Reposición              │
  │                                      │
  │ Tu Turno: ✅ TÚ                    │
  │ Tu Plantilla: 22/23                │
  │ Disponibles: 185                    │
  │                                      │
  │ Orden del Draft:                    │
  │ ┌──────────────────┬──────┬────────┐│
  │ │ Equipo 1         │ 250M │ 22/23  ││
  │ │ Equipo 2         │ 180M │ 22/23  ││
  │ │ Equipo 3         │ 120M │ 20/23  ││
  │ │ Equipo 4         │ 95M  │ 21/23  ││
  │ └──────────────────┴──────┴────────┘│
  │                                      │
  │ Jugadores Disponibles (sin minutos):│
  │                                      │
  │ [foto] Neymar     [Elegir]         │
  │ [foto] Vinícius   [Elegir]         │
  │ [foto] Bellingham [Elegir]         │
  │ ...                                 │
  │ [Pasar Turno]                      │
  └─────────────────────────────────────┘

Usuario 1 elige Neymar:
  
Backend:
  1. Valida: current_team_id == usuario_1 ✓
  2. UPDATE reposition_draft_picks: player_id=Neymar
  3. INSERT team_players: Neymar → usuario_1
  4. Calcula next_turn (Usuario_2)
  5. Retorna OK

Usuario 2 recibe notificación en tiempo real y ve su turno
Usuario 2 elige jugador (o pasa)
...continue hasta que todos tengan ≥23 o todos pasen...

Cuando draft termina:
  - Window transiciona a "completed"
  - Usuarios ven sus nuevas plantillas de 23 jugadores
  - Listo para próxima fase del torneo
```

## 5. Estados y Transiciones Automáticas

```
Watchdog en main.py (_market_auto_transition_watchdog):

Cada 60 segundos:
  SELECT * FROM market_windows WHERE status != 'completed'
  
  FOR CADA window:
    IF status="clause_window" AND now >= clause_window_end:
      → MarketService.start_market_phase()
      → status = "market_open"
    
    ELSE IF status="market_open" AND now >= market_window_end:
      → MarketService.close_market()
      → status = "market_closed"
    
    ELSE IF status="market_closed" AND now >= reposition_draft_start:
      → MarketService.start_reposition_draft()
      → status = "reposition_draft"
    
    ELSE IF status="reposition_draft" AND now >= reposition_draft_end:
      → UPDATE status = "completed"

No require commissioner intervention!
```

## 6. API Call Sequence (Ejemplo Completo)

```
┌─────────────────┐
│   COMMISSIONER  │
└────────┬────────┘
         │
         │ POST /leagues/{id}/admin/market-windows
         │ { phase: "Mercado_1", ... }
         │
         ├──→ Backend: CREATE market_window (id=1, status="pending")
         │
         │ POST /leagues/{id}/admin/market-windows/1/start-clause-phase
         │
         ├──→ Backend: UPDATE market_windows SET status="clause_window"
         │
         └──→ Frontend: Muestra UI de protección
         
┌──────────────┐
│     USER 1   │
└────────┬─────┘
         │
         │ GET /teams/{id}/market/1/clauses
         │ (ver claúsulas actuales)
         │
         │ POST /teams/{id}/market/1/clauses/set
         │ { clauses: [{player_id, amount, is_blocked}, ...] }
         │
         ├──→ Backend: DELETE old clauses, INSERT new ones
         │
         └──→ Frontend: Toast "Guardado"

         [Auto-transition después de deadline]
         
         │ GET /leagues/{id}/market/1/available-players?position=FWD
         │ (ver jugadores para comprar)
         │
         │ GET /teams/{id}/market/1/budget
         │ (ver presupuesto)
         │
         │ POST /teams/{id}/market/1/buy-player
         │ { player_id: "..." }
         │
         ├──→ Backend: ACID transaction
         │    - Move player
         │    - Update budgets
         │    - Record transaction
         │
         │ GET /teams/{id}/market/1/transaction-history
         │ (ver compras/ventas)
         │
         └──→ Frontend: Actualizar UI

         [Auto-transition a reposition_draft]
         
         │ GET /leagues/{id}/market/1/reposition-draft-state
         │
         │ GET /leagues/{id}/market/1/reposition-available-players
         │
         │ POST /teams/{id}/market/1/reposition-draft-pick
         │ { player_id: "..." }
         │
         └──→ Backend: Registrar pick, calcular next turn
```

## 7. Validaciones y Constraints

```
Protección de Cláusulas:
  ✓ sum(clause_amount) ≤ 300M per team
  ✓ count(is_blocked) ≤ 2 per team
  ✓ Solo jugadores en plantilla actual

Mercado Abierto:
  ✓ remaining_budget ≥ clause_amount
  ✓ buys_count < max_buys
  ✓ seller.sells_count < max_sells
  ✓ !is_blocked (no puede comprar bloqueados)
  ✓ Concurrencia: Database ACID garantiza "first wins"

Reposición Draft:
  ✓ Es turno del usuario
  ✓ Jugador sin minutos
  ✓ Min 3 de cada posición (si hay pool)
  ✓ Llena hasta 23 o todos pasan
```

## 8. Notificaciones (Future)

```
WebSocket feed podría mostrar:

📢 Equipo 2 robó a Mbappé por 80M
   → Afecta a Equipo 1 (pierde jugador, gana 80M)

📢 Equipo 3 compró a De Bruyne por 60M
   → Afecta a Equipo 2 (pierde jugador, gana 60M)

📢 Equipo 1 pasó en draft de reposición (Turno 3)
   → Avanza a Equipo 2 (Turno 4)

Notificaciones en tiempo real = mejor UX
```

---

**Status:** ✅ Sistema completo, probado, listo para deployment a K8s
