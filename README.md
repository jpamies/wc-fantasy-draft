# ⚽ WC Fantasy 2026

Fantasy football webapp para el **Mundial de Fútbol 2026** (USA, México, Canadá).

Draft con snake order, mercado de traspasos con clausulazos, cola de draft, puntuación por jornada, y todo en tiempo real con WebSocket.

**Live**: [https://fantasy.jpamies.com](https://fantasy.jpamies.com)

---

## 🎯 Concepto

A diferencia de los fantasy clásicos donde cada usuario elige su equipo de forma aislada, WC Fantasy introduce mecánicas competitivas de mercado:

- **Draft Mode**: Jugadores por turnos (snake order, estilo NBA/NFL)
- **Cola de Draft**: Pre-selecciona tus picks favoritos — el sistema los elige por ti
- **AutoDraft**: Selección automática inteligente con composición de plantilla balanceada
- **Clausulazos**: Paga 1.5× el valor de mercado para fichar instantáneamente
- **Mercado de traspasos**: Ofertas directas, pujas ciegas, liberaciones
- **Ligas privadas**: Crea una liga, comparte el código, y a jugar

## 🏗️ Estado del proyecto

**MVP funcional y desplegado** — 25/25 smoke tests passed.

| Feature | Estado |
|---|---|
| Catálogo de 9.106 jugadores (23 selecciones) | ✅ |
| Crear/unirse a ligas con código | ✅ |
| Draft con 4 modos (manual, auto-pick, cola, autodraft) | ✅ |
| WebSocket + polling para draft en tiempo real | ✅ |
| Gestión de equipo con campo táctico visual | ✅ |
| Mercado: clausulazos, ofertas, pujas, liberaciones | ✅ |
| Scoring con cálculo automático de puntos | ✅ |
| Clasificación de liga | ✅ |

## 🛠️ Tech Stack

| Capa | Tecnología |
|---|---|
| **Frontend** | HTML + CSS + Vanilla JS (SPA, tema oscuro) |
| **Backend** | Python 3.11 + FastAPI + WebSocket |
| **Base de datos** | SQLite (WAL mode) con PVC persistente |
| **Auth** | JWT (código de liga + nickname, sin passwords) |
| **CI/CD** | GitHub Actions → ghcr.io (multi-arch amd64+arm64) |
| **Infraestructura** | K3s en Raspberry Pi 4 + Flux (GitOps) |
| **Networking** | Cloudflare Tunnel (HTTPS, sin port forwarding) |
| **Datos** | Transfermarkt (23 países, ~9100 jugadores) |

## 📁 Estructura del proyecto

```
wc-fanasy/
├── README.md
├── Dockerfile
├── Makefile
├── requirements.txt
├── data/
│   └── transfermarkt/           # 23 JSONs de jugadores por país
├── src/
│   ├── frontend/                # SPA (HTML/CSS/JS)
│   │   ├── index.html
│   │   ├── css/styles.css
│   │   └── js/
│   │       ├── app.js
│   │       ├── api.js
│   │       ├── router.js
│   │       └── pages/           # home, league, draft, team, market, standings, scoring
│   ├── backend/                 # FastAPI
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── routes/              # leagues, players, teams, draft, market, scoring
│   │   └── services/            # draft_engine, market_engine, scoring_engine
│   └── scripts/
│       └── import_players.py    # Importa JSONs → SQLite
├── tests/
│   └── smoke_test.py            # 25 tests de integración
├── docs/                        # Documentación de diseño
│   ├── ARCHITECTURE.md
│   ├── DECISIONS.md             # 9 ADRs
│   ├── RULES.md
│   ├── DATA_MODEL.md
│   ├── SCORING.md
│   ├── API_DESIGN.md
│   └── ROADMAP.md
└── .github/
    └── workflows/
        └── build-image.yml      # Build multi-arch → ghcr.io
```

## 🚀 Quick Start (desarrollo local)

```bash
# Clonar
git clone https://github.com/jpamies/wc-fantasy-draft.git
cd wc-fantasy-draft

# Setup
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt     # Linux/Mac

# Arrancar (importa datos automáticamente al primer arranque)
python -m uvicorn src.backend.main:app --reload --port 8000

# Abrir http://localhost:8000
```

## 🐳 Docker

```bash
docker build -t wc-fantasy .
docker run -p 8000:8000 wc-fantasy
```

## ☸️ Despliegue (Kubernetes + Flux)

El proyecto se despliega en un **K3s en Raspberry Pi 4** con GitOps via Flux.

Los manifiestos K8s están en [k8s-homepi](https://github.com/jpamies/k8s-homepi):

```
apps/wc-fantasy/
├── deployment.yaml    # ghcr.io/jpamies/wc-fantasy-draft:latest (ARM64)
├── service.yaml       # ClusterIP:8000
├── pvc.yaml           # 1Gi local-path para SQLite
└── kustomization.yaml

apps/cloudflared/
├── deployment.yaml    # Cloudflare Tunnel
└── kustomization.yaml
```

**Flujo de despliegue**:
1. Push a `master` → GitHub Actions construye imagen multi-arch → `ghcr.io`
2. `kubectl rollout restart deployment wc-fantasy` (o Flux Image Automation)
3. Cloudflare Tunnel sirve **https://fantasy.jpamies.com**

## 📄 Licencia

MIT
