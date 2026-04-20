# Reglas del Juego — WC Fantasy 2026

> Reglamento completo del fantasy. Las reglas marcadas con 🆕 son mecánicas
> innovadoras que diferencian WC Fantasy de otros fantasy clásicos.

---

## 1. Conceptos básicos

### Liga
- Una **liga** es un grupo de 4 a 32 participantes compitiendo entre sí.
- Cada liga tiene un **comisionado** (creador) que configura las reglas.
- Tipos: **pública** (cualquiera se une con código) o **privada** (solo invitación).

### Equipo fantasy
- Cada participante gestiona **un equipo fantasy**.
- Plantilla de **23 jugadores** (de cualquier selección del Mundial).
- **11 titulares** que puntúan + **12 suplentes** (reservas).
- Un **capitán** que puntúa doble.

### Jornada
- Cada día de partidos del Mundial es una **jornada**.
- Los puntos se acumulan jornada a jornada.
- La clasificación se actualiza al finalizar cada jornada.

---

## 2. Formaciones permitidas

El participante elige una formación para sus 11 titulares:

| Formación | GK | DEF | MID | FWD |
|---|---|---|---|---|
| 4-3-3 | 1 | 4 | 3 | 3 |
| 4-4-2 | 1 | 4 | 4 | 2 |
| 3-5-2 | 1 | 3 | 5 | 2 |
| 3-4-3 | 1 | 3 | 4 | 3 |
| 5-3-2 | 1 | 5 | 3 | 2 |
| 5-4-1 | 1 | 5 | 4 | 1 |
| 4-5-1 | 1 | 4 | 5 | 1 |

- Siempre **1 portero** titular.
- La formación se puede cambiar entre jornadas.
- **Deadline de alineación**: 1 hora antes del primer partido de la jornada.

---

## 3. 🆕 Draft Mode

A diferencia de los fantasy donde todos pueden tener a Mbappé, en **Draft Mode**
cada jugador solo puede pertenecer a un equipo dentro de la liga.

### Cómo funciona

1. **Programación**: El comisionado fija fecha y hora del draft.
2. **Orden**: Aleatorio o por serpenteo (1→N, N→1, 1→N...).
3. **Turnos**: Cada participante tiene **60 segundos** para elegir un jugador.
4. **Rondas**: 23 rondas hasta completar la plantilla de cada equipo.
5. **Auto-pick**: Si el tiempo expira, se selecciona automáticamente según las preferencias del participante (posición prioritaria + mayor valor de mercado).

### Reglas del draft

- **Exclusividad**: Un jugador drafteado no puede ser seleccionado por otro participante de la misma liga.
- **Sin restricciones de selección**: Puedes mezclar jugadores de cualquier país.
- **Mínimos por posición**: Al menos 2 GK, 5 DEF, 5 MID, 3 FWD.
- **No hay máximo por selección**: Puedes tener 5 jugadores de España si quieres.

### Alternativa: Modo clásico

Para ligas que no quieran draft:
- Cada participante elige libremente (pueden repetirse jugadores entre equipos).
- Sin exclusividad.
- Presupuesto virtual como limitación.

> El comisionado elige el modo al crear la liga: **Draft** o **Clásico**.

---

## 4. 🆕 Mercado de traspasos

### Ventanas de traspasos

| Ventana | Cuándo | Duración |
|---|---|---|
| **Pre-torneo** | Después del draft, antes del primer partido | 48 horas |
| **Entre fases** | Entre fase de grupos y octavos | 24 horas |
| **Pre-semifinales** | Antes de semifinales | 12 horas |

### Tipos de operaciones

#### 4.1 Oferta directa
- Propón un intercambio a otro participante: jugador(es) + moneda por jugador(es).
- El otro participante puede **aceptar**, **rechazar**, o **contraofertar**.
- Timeout de oferta: 24 horas (auto-rechazo).

#### 4.2 🆕 Clausulazo
- Cada jugador tiene una **cláusula de rescisión** = **1.5× su valor de mercado** (Transfermarkt).
- Si pagas la cláusula, el jugador es tuyo **inmediatamente**, sin negociación.
- El equipo vendedor recibe el dinero de la cláusula.
- **Restricción anti-abuso**: Máximo 2 clausulazos por ventana de traspasos.
- Un jugador clausulado no puede ser clausulado de nuevo en la misma ventana.

**Ejemplo**:
> Mbappé tiene un valor de mercado de 180M. Su cláusula es 270M fantasillones.
> Si tienes 270M disponibles, lo activas y te llevas a Mbappé del equipo rival.

#### 4.3 Mercado libre (waivers)
- Jugadores no drafteados o liberados están en el **mercado libre**.
- Sistema de **pujas ciegas**: cada interesado pone una cantidad, gana la más alta.
- Las pujas se resuelven al cierre de la ventana de traspasos.
- Empate: gana el equipo con peor clasificación (equidad).

#### 4.4 Liberación de jugadores
- Puedes **liberar** a un jugador (vuelve al mercado libre).
- Recuperas el 50% de su valor de mercado en moneda.
- Un jugador liberado no puede ser re-fichado por el mismo equipo en la misma ventana.

---

## 5. Economía (moneda virtual)

### Presupuesto inicial
- Cada equipo empieza con **500M fantasillones** (ajustable por el comisionado).
- En **modo draft**, el presupuesto solo se usa para traspasos y clausulazos.
- En **modo clásico**, el presupuesto se usa también para fichar la plantilla inicial.

### Flujo de dinero

| Acción | Efecto en presupuesto |
|---|---|
| Clausulazo (comprador) | -cláusula del jugador |
| Clausulazo (vendedor) | +cláusula del jugador |
| Traspaso negociado | Según acuerdo |
| Liberar jugador | +50% valor de mercado |
| Puja (mercado libre) | -precio de puja ganada |
| Bonus por clasificación | +10M por cada jornada como líder |

---

## 6. Puntuación

> Ver [SCORING.md](SCORING.md) para el detalle completo.

### Resumen rápido

| Evento | Puntos |
|---|---|
| Jugar el partido (titular) | +2 |
| Jugar el partido (suplente, >0 min) | +1 |
| Gol (FWD) | +4 |
| Gol (MID) | +5 |
| Gol (DEF/GK) | +6 |
| Asistencia | +3 |
| Clean sheet (GK/DEF) | +4 |
| Clean sheet (MID) | +1 |
| Penalti fallado | -2 |
| Tarjeta amarilla | -1 |
| Tarjeta roja | -3 |
| Gol en propia | -2 |
| Capitán | ×2 todos los puntos |

---

## 7. Clasificación

### Puntuación total
- Suma de puntos de los **11 titulares** en cada jornada.
- Los suplentes no puntúan (salvo sustitución automática — ver §8).

### Desempates
1. Mayor número de goles de sus jugadores
2. Mayor número de clean sheets
3. Menor número de tarjetas rojas
4. Orden alfabético del nombre del equipo

---

## 8. 🆕 Sustituciones automáticas

Si un titular **no juega** (0 minutos en el partido real):
- Se sustituye automáticamente por el primer suplente **de la misma posición**.
- Si no hay suplente de la misma posición, se busca el siguiente suplente válido
  que mantenga una formación legal.
- Máximo **3 sustituciones automáticas** por jornada.

---

## 9. Reglas del comisionado

El comisionado tiene poderes especiales:
- Configurar reglas de la liga (modo, presupuesto, tamaño).
- Abrir/cerrar ventanas de traspasos manualmente.
- **Vetar** un traspaso (con justificación visible para todos).
- Expulsar a un participante (su equipo se disuelve y los jugadores van al mercado libre).
- Pausar/reanudar el draft.

**Límites del comisionado**:
- No puede modificar resultados de partidos ni puntuaciones.
- No puede darse ventajas a sí mismo.
- Todas sus acciones quedan registradas en el log de la liga.

---

## 10. Configuración de liga (opciones del comisionado)

| Opción | Valores | Default |
|---|---|---|
| Modo de selección | Draft / Clásico | Draft |
| Nº de participantes | 4–32 | 8 |
| Presupuesto inicial | 200M–1000M | 500M |
| Timer del draft (seg) | 30–120 | 60 |
| Clausulazos por ventana | 0–5 | 2 |
| Sustituciones auto | Sí/No | Sí |
| Orden del draft | Aleatorio / Serpenteo | Serpenteo |
| Liga pública/privada | Pública / Privada | Privada |
| Multiplicador capitán | ×1.5 / ×2 / ×3 | ×2 |
