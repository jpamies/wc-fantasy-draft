# Sistema de Puntuación — WC Fantasy 2026

> Detalle completo de cómo se calculan los puntos.
> Fuentes de datos: SofaScore (ratings), Football-Data.org (eventos), entrada manual (fallback).

---

## 1. Puntos por evento

### Participación

| Evento | Puntos | Notas |
|---|---|---|
| Titular (juega ≥60 min) | +2 | |
| Suplente (juega 1–59 min) | +1 | |
| No juega (0 min) | 0 | Se activa sustitución automática |

### Ataque

| Evento | GK | DEF | MID | FWD |
|---|---|---|---|---|
| Gol | +6 | +6 | +5 | +4 |
| Asistencia | +3 | +3 | +3 | +3 |
| Penalti anotado | +4 | +4 | +4 | +4 |
| Penalti fallado | -2 | -2 | -2 | -2 |

### Defensa

| Evento | GK | DEF | MID | FWD |
|---|---|---|---|---|
| Clean sheet (0 goles encajados, ≥60 min) | +4 | +4 | +1 | — |
| Cada 2 goles encajados (≥60 min) | -1 | -1 | — | — |
| Penalti parado | +5 | — | — | — |
| Parada (cada 3) | +1 | — | — | — |

### Disciplina

| Evento | Puntos |
|---|---|
| Tarjeta amarilla | -1 |
| Tarjeta roja (directa) | -3 |
| Doble amarilla → roja | -2 (amarilla -1 + expulsión -1) |
| Gol en propia puerta | -2 |

### Bonus

| Evento | Puntos | Condición |
|---|---|---|
| MVP del partido | +3 | Rating más alto del partido (SofaScore ≥8.0) |
| Hat-trick | +3 | 3+ goles en un partido (adicional a puntos por gol) |
| Sin recibir disparo a puerta (GK) | +2 | Solo GK, ≥60 min jugados |

---

## 2. Capitán

- El capitán multiplica **todos sus puntos** por el multiplicador configurado (default: ×2).
- Se elige antes del deadline de alineación.
- Si el capitán no juega, el **vice-capitán** hereda la multiplicación.
- Si ninguno juega, no hay multiplicador.

---

## 3. Sustituciones automáticas

Cuando un titular tiene 0 minutos jugados:

1. Se busca el primer suplente **de la misma posición** en el banco.
2. Si no hay, se busca un suplente que mantenga una **formación válida**.
3. Máximo **3 sustituciones automáticas** por jornada.
4. Orden de prioridad: posición del banco (1→12).

---

## 4. Ejemplo de puntuación

**Jugador**: Lamine Yamal (FWD, capitán)  
**Partido**: España 3–0 Costa Rica

| Evento | Puntos |
|---|---|
| Titular (90 min) | +2 |
| 1 gol (FWD) | +4 |
| 1 asistencia | +3 |
| MVP (rating 9.1) | +3 |
| **Subtotal** | **+12** |
| **Capitán ×2** | **+24** |

---

## 5. Fuentes de datos para puntuación

### Prioridad de fuentes

```
1. SofaScore API        →  Ratings, stats detalladas
2. Football-Data.org    →  Eventos (goles, tarjetas, sustituciones)
3. Entrada manual       →  Fallback por el comisionado
```

### Mapeo de datos SofaScore → Puntos

| Campo SofaScore | Uso en WC Fantasy |
|---|---|
| `rating` | MVP (≥8.0 = más alto del partido) |
| `goals` | Puntos por gol según posición |
| `assists` | Puntos por asistencia |
| `minutesPlayed` | Titular vs suplente, clean sheet elegibilidad |
| `yellowCards` | Penalización |
| `redCards` | Penalización |
| `ownGoals` | Penalización |
| `savedPenalties` | Bonus GK |
| `saves` | Bonus GK (cada 3) |
| `goalsConceded` | Penalización GK/DEF |

### Timing de actualización

| Momento | Acción |
|---|---|
| Pre-partido (1h antes) | Bloquear alineaciones |
| Durante el partido | Actualizar minutos y eventos cada 5 min |
| Post-partido (final) | Calcular puntos definitivos |
| Post-partido (+2h) | Aplicar correcciones (goles reasignados, etc.) |
| Post-jornada | Actualizar clasificación de la liga |

---

## 6. Clasificación de la liga

### Puntuación acumulada
- Suma de puntos del **11 titular** (+ sustituciones auto) en cada jornada.
- **Ranking global**: de mayor a menor puntuación total.

### Historial
- Se guarda el desglose por jornada para cada equipo.
- Gráfico de evolución de puntos a lo largo del torneo.

### Premios virtuales (badges)

| Badge | Condición |
|---|---|
| 🏆 Campeón | 1º al final del torneo |
| 🥈 Subcampeón | 2º al final |
| 🥉 Tercero | 3º al final |
| ⚡ Mejor jornada | Mayor puntuación en una sola jornada |
| 🎯 Ojo de águila | Más clausulazos exitosos |
| 🧤 Muro | Mayor puntuación acumulada de GK+DEF |
| 📈 Remontada | Mayor mejora de posición entre jornada 1 y final |
