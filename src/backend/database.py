import aiosqlite
import os
from src.backend.config import settings

DB_PATH = settings.DATABASE_PATH

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
    max_teams INTEGER DEFAULT 8,
    initial_budget INTEGER DEFAULT 500000000,
    draft_timer_seconds INTEGER DEFAULT 60,
    max_clausulazos_per_window INTEGER DEFAULT 2,
    auto_substitutions INTEGER DEFAULT 1,
    draft_order TEXT DEFAULT 'snake',
    captain_multiplier REAL DEFAULT 2.0,
    transfer_window_open INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fantasy_teams (
    id TEXT PRIMARY KEY,
    league_id TEXT NOT NULL REFERENCES leagues(id),
    owner_nick TEXT NOT NULL,
    team_name TEXT NOT NULL,
    budget INTEGER DEFAULT 500000000,
    formation TEXT DEFAULT '4-3-3',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id TEXT NOT NULL REFERENCES fantasy_teams(id),
    player_id TEXT NOT NULL REFERENCES players(id),
    is_starter INTEGER DEFAULT 0,
    position_slot TEXT,
    is_captain INTEGER DEFAULT 0,
    is_vice_captain INTEGER DEFAULT 0,
    bench_order INTEGER DEFAULT 0,
    acquired_via TEXT DEFAULT 'draft' CHECK(acquired_via IN ('draft','free_market','transfer','clause')),
    acquired_at TEXT NOT NULL,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    status TEXT DEFAULT 'scheduled' CHECK(status IN ('scheduled','live','finished'))
);

CREATE TABLE IF NOT EXISTS match_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
"""


async def get_db() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        await db.commit()
    finally:
        await db.close()
