import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.backend.database import init_db
from src.scripts.import_players import import_data
from src.backend.routes import leagues, players, teams, draft, market, scoring


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database and import player data on startup
    print("Initializing database...")
    await init_db()
    # Only import if players table is empty
    from src.backend.database import get_db
    db = await get_db()
    try:
        rows = await db.execute_fetchall("SELECT COUNT(*) as cnt FROM players")
        if rows[0]["cnt"] == 0:
            print("Importing player data from transfermarkt JSONs...")
            await import_data()
        else:
            print(f"Database has {rows[0]['cnt']} players, skipping import.")
    finally:
        await db.close()
    yield


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
