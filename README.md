# WC Fantasy 2026

Fantasy football web app for the FIFA World Cup 2026.

Live: https://fantasy.jpamies.com

## What This Repository Contains

This repository contains the full WC Fantasy application code:
- FastAPI backend (Python 3.11)
- Vanilla JS SPA frontend
- Game logic for draft, lineups, market, and scoring sync

## Current Gameplay Rules (Authoritative Summary)

### Squad and Lineups
- Squad size: 12 players.
- Position cap: max 4 for each position (`GK`, `DEF`, `MID`, `FWD`).
- Matchday lineup: 5 slots (`GK`, `DEF`, `MID`, `FWD`, `WILDCARD`).
- Partial lineup save is allowed.

### Captaincy
- Captain is optional in the 5-slot lineup flow.
- Captain receives `x2` points.
- No vice-captain in the main 5-slot lineup flow.

### Draft
- Snake order draft.
- 12 picks per team.
- Queue and autodraft supported.
- Position caps enforced at pick time.

### Market and Reposition
- Market works in windows/phases.
- Clause attempts can be submitted and resolved later.
- Resolution enforces budget, squad size, and position caps at resolution time.
- Reposition draft follows the same roster limits.

## Stack

- Backend: FastAPI, asyncpg, httpx, python-jose
- Frontend: HTML/CSS/Vanilla JS
- Database: PostgreSQL 16
- External provider: wc-simulator API

## Project Structure

```text
wc-fanasy/
├── src/
│   ├── backend/
│   │   ├── routes/
│   │   └── services/
│   └── frontend/
├── docs/
├── scripts/
└── tests/
```

## Local Development

```powershell
make setup
make dev
```

App runs on: http://localhost:8000

## Environment Variables

Variables use the `WCF_` prefix:
- `WCF_SECRET_KEY`
- `WCF_DATABASE_URL`
- `WCF_SIMULATOR_API_URL`
- `WCF_CORS_ORIGINS`
- `WCF_JWT_ALGORITHM`

## API Surface (High-Level)

Base path: `/api/v1`

- Auth/leagues
- Draft (state, picks, queue, autodraft)
- Teams (roster + 5-slot lineup)
- Market (windows, attempts, transactions, reposition)
- Scoring (sync + standings)

## Documentation

See [docs/README.md](docs/README.md) for document status and reading order.

## Security (Public Repository)

This is a public repository. Follow these rules:
- Never commit real secrets, credentials, tokens, or internal hostnames.
- Treat default values in code as local-development placeholders only.
- Keep production values only in runtime secrets (Kubernetes secrets, CI secrets, etc.).
- Prefer restrictive CORS in production; avoid `*` outside local/dev scenarios.
- Rotate credentials immediately if exposure is suspected.

### Current Security Posture

- Runtime reads secrets from environment variables (`WCF_*`).
- The source code currently includes development fallback defaults in `src/backend/config.py`.
- Production values are injected from the infrastructure repo (`k8s-homepi`), not from this codebase.

Recommended hardening for public code:
- Keep safe non-sensitive defaults only (or empty defaults that fail fast in production).
- Add startup validation to reject weak/default secret values when `ENV=production`.
- Keep CORS explicit in production (`WCF_CORS_ORIGINS` with trusted domains only).

## Deployment

Production deployment is managed from a separate infrastructure repository (`k8s-homepi`) using Flux GitOps.

## Related Repositories

- `wc-simulator`: data source for players, calendar, and match stats.
- `k8s-homepi`: Kubernetes manifests and GitOps deployment automation.
