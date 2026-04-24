import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.backend.database import init_db
from src.backend.config import settings
from src.backend.routes import leagues, players, teams, draft, market, scoring


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database
    print("Initializing database...")
    await init_db()

    if settings.SIMULATOR_API_URL:
        print(f"Simulator API configured: {settings.SIMULATOR_API_URL}")
        print("Player data will be fetched live from wc-simulator.")
    else:
        print("⚠️  No SIMULATOR_API_URL configured.")
        print("   Set SIMULATOR_API_URL to point to wc-simulator for player data.")

    yield

    # Cleanup httpx client on shutdown
    if settings.SIMULATOR_API_URL:
        from src.backend.services.simulator_client import close_client
        await close_client()


app = FastAPI(
    title="WC Fantasy 2026",
    description="Fantasy football API for the 2026 FIFA World Cup",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if not path.startswith("/api/"):
            if path.endswith(".html") or path == "/" or "." not in path.split("/")[-1]:
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            else:
                response.headers["Cache-Control"] = "public, max-age=300"
        return response


app.add_middleware(NoCacheStaticMiddleware)

# Include API routers
app.include_router(leagues.router)
app.include_router(players.router)
app.include_router(teams.router)
app.include_router(draft.router)
app.include_router(market.router)
app.include_router(scoring.router)

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "app": "wc-fantasy-2026"}
