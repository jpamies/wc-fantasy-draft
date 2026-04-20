# ⚽ WC Fantasy 2026

Fantasy football webapp para el **Mundial de Fútbol 2026** (USA, México, Canadá).

Un juego de fantasy con reglas innovadoras: **draft inicial**, **traspasos entre equipos fantasy**, **clausulazos**, y puntuación en tiempo real con fuentes externas.

---

## 🎯 Concepto

A diferencia de los fantasy clásicos donde cada usuario elige su equipo de forma aislada, WC Fantasy introduce mecánicas competitivas de mercado:

- **Draft Mode**: Los participantes de cada liga eligen jugadores por turnos (estilo NBA/NFL Draft)
- **Mercado de traspasos**: Ventana de fichajes entre jornadas para negociar jugadores entre equipos fantasy
- **Clausulazos**: Cada jugador tiene una cláusula de rescisión — si pagas el precio (en moneda virtual), te lo llevas sin negociar
- **Ligas múltiples**: Crea o únete a ligas privadas/públicas con amigos o desconocidos

## 🏗️ Estado del proyecto

> **Fase actual: Diseño y planificación** — No hay código de producción todavía.

| Documento | Descripción |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Arquitectura del sistema |
| [DECISIONS.md](docs/DECISIONS.md) | Decisiones técnicas (ADRs) |
| [RULES.md](docs/RULES.md) | Reglas del juego fantasy |
| [DATA_MODEL.md](docs/DATA_MODEL.md) | Modelo de datos |
| [SCORING.md](docs/SCORING.md) | Sistema de puntuación |
| [API_DESIGN.md](docs/API_DESIGN.md) | Diseño de la API |
| [ROADMAP.md](docs/ROADMAP.md) | Fases de desarrollo |

## 🧩 Características principales

### Gestión de equipos
- Cada participante gestiona un equipo fantasy de **23 jugadores** (de cualquier selección)
- Formación táctica configurable (4-3-3, 4-4-2, 3-5-2, etc.)
- 11 titulares + 12 suplentes — solo los titulares puntúan

### Draft Mode
- Al crear una liga, se programa un **evento de draft**
- Los participantes eligen jugadores por turnos (orden aleatorio o serpenteo)
- Rondas hasta completar plantillas — sin repeticiones dentro de la liga
- Opción de autodraft con preferencias preconfiguradas

### Mercado de traspasos
- Ventana de traspasos activa entre fases de grupos y eliminatorias
- **Ofertas directas**: propón un intercambio a otro participante
- **Clausulazo**: paga la cláusula de un jugador — transferencia inmediata sin negociación
- **Mercado libre**: jugadores no drafteados disponibles con sistema de pujas

### Ligas
- **Públicas**: cualquiera puede unirse (con código o búsqueda)
- **Privadas**: solo por invitación
- Clasificación por puntos totales y head-to-head
- Soporte para ligas de 4 a 32 participantes

### Puntuación
- Puntos basados en rendimiento real de los jugadores en el Mundial
- Fuentes de datos externas: **SofaScore**, **Transfermarkt**
- Bonus por goles, asistencias, clean sheets, MVP del partido
- Penalizaciones por tarjetas, goles en contra, penaltis fallados

## 📦 Fuentes de datos

| Fuente | Uso | Estado |
|---|---|---|
| [world-cup-list](../world-cup-list/) | Plantillas nacionales (23 países, ~600 jugadores) | ✅ Disponible |
| Transfermarkt | Valor de mercado, datos de jugadores | ✅ Vía scraping (download-data.py) |
| SofaScore API | Puntuaciones en vivo, estadísticas de partido | 🔬 Investigado |
| SOFIFA API | Datos complementarios de jugadores | 🔬 Investigado |

> La base de datos inicial será **ficheros JSON estáticos** reutilizando los datos de `world-cup-list/data/`. El objetivo es migrar a una API propia cuando el proyecto madure.

## 🛠️ Tech Stack (propuesto)

| Capa | Tecnología | Justificación |
|---|---|---|
| **Frontend** | HTML + CSS + Vanilla JS | Simplicidad, sin build step, coherencia con world-cup-list |
| **Backend** | Python (FastAPI) | Experiencia existente (transfermarkt-api), async, rápido |
| **Base de datos** | JSON → SQLite → PostgreSQL | Evolución progresiva según necesidad |
| **Autenticación** | Códigos de liga + nicknames (v1), OAuth (v2) | MVP sin fricción |
| **Hosting** | GitHub Pages (frontend) + Fly.io (backend) | Gratuito / bajo coste |
| **Puntuación** | Scripts Python + cron/GitHub Actions | Actualización periódica de datos |

## 📁 Estructura del proyecto

```
wc-fanasy/
├── README.md
├── Makefile
├── .gitignore
├── docs/                        # Documentación de diseño
│   ├── ARCHITECTURE.md
│   ├── DECISIONS.md
│   ├── RULES.md
│   ├── DATA_MODEL.md
│   ├── SCORING.md
│   ├── API_DESIGN.md
│   └── ROADMAP.md
├── data/                        # Base de datos de ficheros
│   ├── players/                 # JSONs de jugadores por país
│   ├── tournaments/             # Estructura del torneo (grupos, calendario)
│   └── scoring/                 # Puntuaciones por jornada
├── src/
│   ├── frontend/                # Web app (HTML/CSS/JS)
│   │   ├── index.html
│   │   ├── css/
│   │   ├── js/
│   │   └── assets/
│   ├── backend/                 # API server (FastAPI)
│   │   ├── main.py
│   │   ├── models/
│   │   ├── routes/
│   │   └── services/
│   └── scripts/                 # Data fetching & scoring
│       ├── fetch_players.py
│       ├── fetch_scores.py
│       └── update_standings.py
└── tests/
    ├── backend/
    └── scripts/
```

## 🚀 Quick Start

> Todavía no hay código ejecutable. Este README se actualizará cuando comience la implementación.

```bash
# Clonar el repo
git clone https://github.com/jordipamies/wc-fanasy.git
cd wc-fanasy

# Ver la documentación de diseño
cat docs/ROADMAP.md
```

## 📄 Licencia

MIT
