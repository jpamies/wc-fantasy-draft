"""Database layer using asyncpg (PostgreSQL).

Provides a thin wrapper around asyncpg that mimics the aiosqlite API used
by routes and services: get_db(), db.execute(), db.execute_fetchall(),
db.commit(), db.close().

All SQL uses PostgreSQL placeholder syntax ($1, $2, ...) and dialect.
"""

import logging
import time
import asyncpg
from src.backend.config import DATABASE_URL

_pool: asyncpg.Pool | None = None
logger = logging.getLogger("wc-fantasy.db")
SLOW_QUERY_MS = 100

SCHEMA = """
CREATE TABLE IF NOT EXISTS countries (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_local TEXT,
    flag TEXT,
    confederation TEXT
);

CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    country_code TEXT NOT NULL REFERENCES countries(code),
    position TEXT NOT NULL CHECK(position IN ('GK','DEF','MID','FWD')),
    detailed_position TEXT,
    club TEXT,
    club_logo TEXT,
    age INTEGER,
    market_value INTEGER DEFAULT 0,
    photo TEXT,
    clause_value INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS leagues (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    commissioner_team_id TEXT,
    mode TEXT NOT NULL DEFAULT 'draft' CHECK(mode IN ('draft','classic')),
    status TEXT NOT NULL DEFAULT 'setup' CHECK(status IN ('setup','draft_pending','draft_in_progress','active','completed')),
    max_teams INTEGER DEFAULT 10,
    initial_budget INTEGER DEFAULT 500000000,
    draft_timer_seconds INTEGER DEFAULT 60,
    max_clausulazos_per_window INTEGER DEFAULT 2,
    auto_substitutions INTEGER DEFAULT 0,
    draft_order TEXT DEFAULT 'snake',
    captain_multiplier REAL DEFAULT 2.0,
    transfer_window_open INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fantasy_teams (
    id TEXT PRIMARY KEY,
    league_id TEXT NOT NULL REFERENCES leagues(id),
    owner_nick TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    team_name TEXT NOT NULL,
    budget INTEGER DEFAULT 500000000,
    formation TEXT DEFAULT '4-3-3',
    protect_budget_allocated INTEGER DEFAULT 0,
    last_market_window_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_players (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES fantasy_teams(id),
    player_id TEXT NOT NULL REFERENCES players(id),
    is_starter INTEGER DEFAULT 0,
    position_slot TEXT,
    is_captain INTEGER DEFAULT 0,
    is_vice_captain INTEGER DEFAULT 0,
    bench_order INTEGER DEFAULT 0,
    acquired_via TEXT DEFAULT 'draft' CHECK(acquired_via IN ('draft','free_market','transfer','clause')),
    acquired_at TEXT NOT NULL,
    market_window_acquired INTEGER,
    UNIQUE(team_id, player_id)
);

CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    league_id TEXT NOT NULL UNIQUE REFERENCES leagues(id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','in_progress','completed')),
    current_round INTEGER DEFAULT 0,
    current_pick INTEGER DEFAULT 0,
    pick_order TEXT,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS draft_picks (
    id SERIAL PRIMARY KEY,
    draft_id TEXT NOT NULL REFERENCES drafts(id),
    round INTEGER NOT NULL,
    pick INTEGER NOT NULL,
    team_id TEXT NOT NULL REFERENCES fantasy_teams(id),
    player_id TEXT NOT NULL REFERENCES players(id),
    timestamp TEXT NOT NULL,
    UNIQUE(draft_id, round, pick)
);

CREATE TABLE IF NOT EXISTS transfers (
    id TEXT PRIMARY KEY,
    league_id TEXT NOT NULL REFERENCES leagues(id),
    type TEXT NOT NULL CHECK(type IN ('offer','clause','free_market','release')),
    from_team_id TEXT REFERENCES fantasy_teams(id),
    to_team_id TEXT REFERENCES fantasy_teams(id),
    player_id TEXT NOT NULL REFERENCES players(id),
    players_offered TEXT,
    amount INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','rejected','expired','completed','vetoed')),
    counter_offer TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS matchdays (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    date TEXT,
    phase TEXT DEFAULT 'group_stage',
    deadline TEXT,
    status TEXT DEFAULT 'upcoming' CHECK(status IN ('upcoming','active','completed'))
);

CREATE TABLE IF NOT EXISTS matches (
    id TEXT PRIMARY KEY,
    matchday_id TEXT NOT NULL REFERENCES matchdays(id),
    home_country TEXT NOT NULL REFERENCES countries(code),
    away_country TEXT NOT NULL REFERENCES countries(code),
    kickoff TEXT,
    score_home INTEGER,
    score_away INTEGER,
    status TEXT DEFAULT 'scheduled' CHECK(status IN ('scheduled','live','finished')),
    tournament_phase TEXT
);

CREATE TABLE IF NOT EXISTS match_scores (
    id SERIAL PRIMARY KEY,
    player_id TEXT NOT NULL REFERENCES players(id),
    matchday_id TEXT NOT NULL REFERENCES matchdays(id),
    match_id TEXT REFERENCES matches(id),
    minutes_played INTEGER DEFAULT 0,
    goals INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    clean_sheet INTEGER DEFAULT 0,
    yellow_cards INTEGER DEFAULT 0,
    red_card INTEGER DEFAULT 0,
    own_goals INTEGER DEFAULT 0,
    penalties_missed INTEGER DEFAULT 0,
    penalties_saved INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    goals_conceded INTEGER DEFAULT 0,
    rating REAL DEFAULT 0,
    bonus_points INTEGER DEFAULT 0,
    total_points INTEGER DEFAULT 0,
    UNIQUE(player_id, matchday_id)
);

CREATE INDEX IF NOT EXISTS idx_players_country ON players(country_code);
CREATE INDEX IF NOT EXISTS idx_players_position ON players(position);
CREATE INDEX IF NOT EXISTS idx_team_players_team ON team_players(team_id);
CREATE INDEX IF NOT EXISTS idx_team_players_player ON team_players(player_id);
CREATE INDEX IF NOT EXISTS idx_match_scores_player ON match_scores(player_id);
CREATE INDEX IF NOT EXISTS idx_match_scores_matchday ON match_scores(matchday_id);
CREATE INDEX IF NOT EXISTS idx_transfers_league ON transfers(league_id);
CREATE INDEX IF NOT EXISTS idx_fantasy_teams_league ON fantasy_teams(league_id);

CREATE TABLE IF NOT EXISTS matchday_lineups (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES fantasy_teams(id),
    matchday_id TEXT NOT NULL REFERENCES matchdays(id),
    player_id TEXT NOT NULL REFERENCES players(id),
    is_starter INTEGER DEFAULT 0,
    is_captain INTEGER DEFAULT 0,
    is_vice_captain INTEGER DEFAULT 0,
    UNIQUE(team_id, matchday_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_matchday_lineups_team ON matchday_lineups(team_id, matchday_id);

CREATE TABLE IF NOT EXISTS draft_settings (
    id SERIAL PRIMARY KEY,
    draft_id TEXT NOT NULL REFERENCES drafts(id),
    team_id TEXT NOT NULL REFERENCES fantasy_teams(id),
    autodraft INTEGER DEFAULT 0,
    queue TEXT DEFAULT '[]',
    UNIQUE(draft_id, team_id)
);

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- MARKET & DRAFT TABLES

CREATE TABLE IF NOT EXISTS market_windows (
    id SERIAL PRIMARY KEY,
    league_id TEXT NOT NULL REFERENCES leagues(id),
    phase TEXT NOT NULL,
    market_type TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','clause_window','market_open','market_closed','reposition_draft','completed')),
    clause_window_start TEXT,
    clause_window_end TEXT,
    market_window_start TEXT,
    market_window_end TEXT,
    reposition_draft_start TEXT,
    reposition_draft_end TEXT,
    max_buys INTEGER DEFAULT 3,
    max_sells INTEGER DEFAULT 3,
    initial_budget INTEGER DEFAULT 100000000,
    protect_budget INTEGER DEFAULT 300000000,
    auto_generated INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS'),
    updated_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS'),
    UNIQUE(league_id, phase)
);

CREATE TABLE IF NOT EXISTS player_clauses (
    id SERIAL PRIMARY KEY,
    market_window_id INTEGER NOT NULL REFERENCES market_windows(id),
    team_id TEXT NOT NULL REFERENCES fantasy_teams(id),
    player_id TEXT NOT NULL REFERENCES players(id),
    clause_amount INTEGER NOT NULL DEFAULT 0,
    is_blocked INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS'),
    updated_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS'),
    UNIQUE(market_window_id, team_id, player_id)
);

CREATE TABLE IF NOT EXISTS market_budgets (
    id SERIAL PRIMARY KEY,
    market_window_id INTEGER NOT NULL REFERENCES market_windows(id),
    team_id TEXT NOT NULL REFERENCES fantasy_teams(id),
    initial_budget INTEGER NOT NULL,
    earned_from_sales INTEGER DEFAULT 0,
    spent_on_buys INTEGER DEFAULT 0,
    remaining_budget INTEGER NOT NULL,
    buys_count INTEGER DEFAULT 0,
    sells_count INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS'),
    UNIQUE(market_window_id, team_id)
);

CREATE TABLE IF NOT EXISTS market_transactions (
    id SERIAL PRIMARY KEY,
    market_window_id INTEGER NOT NULL REFERENCES market_windows(id),
    buyer_team_id TEXT NOT NULL REFERENCES fantasy_teams(id),
    seller_team_id TEXT NOT NULL REFERENCES fantasy_teams(id),
    player_id TEXT NOT NULL REFERENCES players(id),
    clause_amount_paid INTEGER NOT NULL,
    transaction_date TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS'),
    status TEXT DEFAULT 'completed' CHECK(status IN ('completed','failed','reverted')),
    created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS reposition_draft_picks (
    id SERIAL PRIMARY KEY,
    market_window_id INTEGER NOT NULL REFERENCES market_windows(id),
    team_id TEXT NOT NULL REFERENCES fantasy_teams(id),
    pick_number INTEGER NOT NULL,
    player_id TEXT REFERENCES players(id),
    is_pass INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS')
);

CREATE INDEX IF NOT EXISTS idx_market_windows_league ON market_windows(league_id);
CREATE INDEX IF NOT EXISTS idx_player_clauses_market ON player_clauses(market_window_id);
CREATE INDEX IF NOT EXISTS idx_player_clauses_team ON player_clauses(team_id);
CREATE INDEX IF NOT EXISTS idx_market_budgets_market ON market_budgets(market_window_id);
CREATE INDEX IF NOT EXISTS idx_market_transactions_market ON market_transactions(market_window_id);
CREATE INDEX IF NOT EXISTS idx_market_transactions_buyer ON market_transactions(buyer_team_id);
CREATE INDEX IF NOT EXISTS idx_market_transactions_seller ON market_transactions(seller_team_id);
CREATE INDEX IF NOT EXISTS idx_reposition_picks_market ON reposition_draft_picks(market_window_id);
CREATE INDEX IF NOT EXISTS idx_reposition_picks_team ON reposition_draft_picks(team_id);
"""


class PgConnection:
    """Thin wrapper around asyncpg.Connection mimicking aiosqlite API.

    Usage:
        db = await get_db()
        try:
            rows = await db.execute_fetchall("SELECT * FROM t WHERE id = $1", (val,))
            await db.execute("INSERT INTO t VALUES ($1, $2)", (a, b))
            await db.commit()
        finally:
            await db.close()
    """

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn
        self._tx = None

    async def execute(self, sql: str, params=None):
        if self._tx is None:
            self._tx = self._conn.transaction()
            await self._tx.start()
        start = time.perf_counter()
        if params:
            await self._conn.execute(sql, *params)
        else:
            await self._conn.execute(sql)
        ms = (time.perf_counter() - start) * 1000
        if ms > SLOW_QUERY_MS:
            logger.warning(f"SLOW EXEC ({ms:.0f}ms): {sql[:120]}")

    async def execute_fetchall(self, sql: str, params=None) -> list[dict]:
        start = time.perf_counter()
        if params:
            rows = await self._conn.fetch(sql, *params)
        else:
            rows = await self._conn.fetch(sql)
        ms = (time.perf_counter() - start) * 1000
        if ms > SLOW_QUERY_MS:
            logger.warning(f"SLOW QUERY ({ms:.0f}ms, {len(rows)} rows): {sql[:120]}")
        return [dict(r) for r in rows]

    async def fetchval(self, sql: str, params=None):
        if params:
            return await self._conn.fetchval(sql, *params)
        return await self._conn.fetchval(sql)

    async def commit(self):
        if self._tx is not None:
            await self._tx.commit()
            self._tx = None

    async def rollback(self):
        if self._tx is not None:
            try:
                await self._tx.rollback()
            except Exception:
                pass
            self._tx = None

    async def close(self):
        if self._tx is not None:
            try:
                await self._tx.rollback()
            except Exception:
                pass
            self._tx = None
        await _pool.release(self._conn)


async def get_db() -> PgConnection:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    conn = await _pool.acquire()
    return PgConnection(conn)


async def init_db():
    """Create tables if they don't exist."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)

    async with _pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'countries')"
        )
        if not exists:
            await conn.execute(SCHEMA)
            print("[DB] PostgreSQL schema created")
        else:
            print("[DB] PostgreSQL schema already exists, skipping")


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None



async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

