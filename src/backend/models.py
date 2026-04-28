from pydantic import BaseModel, Field
from typing import Optional


# --- Auth ---
class AuthJoin(BaseModel):
    league_code: str
    nickname: str
    team_name: str
    display_name: str = ""

class AuthRecover(BaseModel):
    league_code: str
    nickname: str

class AuthResponse(BaseModel):
    token: str
    team_id: str
    league_id: str
    is_commissioner: bool = False


# --- Players ---
class PlayerOut(BaseModel):
    id: str
    name: str
    country_code: str
    position: str
    detailed_position: str = ""
    club: str = ""
    club_logo: str = ""
    age: int = 0
    market_value: int = 0
    photo: str = ""
    clause_value: int = 0

class CountryOut(BaseModel):
    code: str
    name: str
    name_local: str | None = ""
    flag: str | None = ""
    confederation: str | None = ""
    group_letter: str | None = None
    player_count: int = 0


# --- Leagues ---
class LeagueSettings(BaseModel):
    max_teams: Optional[int] = None
    initial_budget: Optional[int] = None
    draft_timer_seconds: Optional[int] = None
    max_clausulazos_per_window: Optional[int] = None
    auto_substitutions: Optional[bool] = None
    draft_order: Optional[str] = None
    captain_multiplier: Optional[float] = None

class LeagueCreate(BaseModel):
    name: str
    settings: Optional[LeagueSettings] = None

class LeagueOut(BaseModel):
    id: str
    name: str
    code: str
    commissioner_team_id: Optional[str] = None
    mode: str = "draft"
    status: str = "setup"
    max_teams: int = 10
    initial_budget: int = 100000000
    draft_timer_seconds: int = 60
    max_clausulazos_per_window: int = 2
    auto_substitutions: bool = True
    draft_order: str = "snake"
    captain_multiplier: float = 2.0
    transfer_window_open: bool = False
    teams: list = Field(default_factory=list)

class StandingEntry(BaseModel):
    team_id: str
    team_name: str
    owner_nick: str
    display_name: str = ""
    total_points: int = 0
    budget: int = 0


# --- Teams ---
class TeamOut(BaseModel):
    id: str
    league_id: str
    owner_nick: str
    team_name: str
    budget: int
    formation: str
    players: list = Field(default_factory=list)

class TeamPlayerOut(BaseModel):
    player_id: str
    name: str
    country_code: str
    country_flag: str = ""
    position: str
    detailed_position: str = ""
    club: str = ""
    photo: str = ""
    market_value: int = 0
    clause_value: int = 0
    is_starter: bool = False
    position_slot: str = ""
    is_captain: bool = False
    is_vice_captain: bool = False
    bench_order: int = 0
    acquired_via: str = "draft"
    total_points: int = 0
    is_alive: bool = True

class LineupUpdate(BaseModel):
    formation: Optional[str] = None
    starters: Optional[list[str]] = None
    captain: Optional[str] = None
    vice_captain: Optional[str] = None


# --- Draft ---
class DraftPickRequest(BaseModel):
    player_id: str

class AutoPickRequest(BaseModel):
    preferences: list[str] = Field(default_factory=lambda: ["FWD", "MID", "DEF", "GK"])

class DraftPickOut(BaseModel):
    round: int
    pick: int
    team_id: str
    team_name: str
    player_id: str
    player_name: str
    timestamp: str

class DraftState(BaseModel):
    id: str
    league_id: str
    status: str
    current_round: int = 0
    current_pick: int = 0
    pick_order: list[str] = Field(default_factory=list)
    picks: list[DraftPickOut] = Field(default_factory=list)
    current_team_id: Optional[str] = None
    current_team_name: Optional[str] = None
    available_count: int = 0


# --- Market ---
class ClauseRequest(BaseModel):
    player_id: str

class OfferCreate(BaseModel):
    to_team_id: str
    players_offered: list[str] = Field(default_factory=list)
    players_requested: list[str] = Field(default_factory=list)
    amount: int = 0

class OfferRespond(BaseModel):
    action: str  # accept, reject, counter
    counter_amount: Optional[int] = None

class BidRequest(BaseModel):
    player_id: str
    amount: int

class ReleaseRequest(BaseModel):
    player_id: str

class TransferOut(BaseModel):
    id: str
    type: str
    from_team_id: Optional[str] = None
    to_team_id: Optional[str] = None
    player_id: str
    player_name: str = ""
    amount: int = 0
    status: str
    created_at: str

class MarketStatus(BaseModel):
    window_open: bool = False
    free_agents: list = Field(default_factory=list)
    pending_offers: list = Field(default_factory=list)
    recent_transfers: list = Field(default_factory=list)


# --- Scoring ---
class MatchdayCreate(BaseModel):
    id: str
    name: str
    date: Optional[str] = None
    phase: str = "group_stage"

class MatchCreate(BaseModel):
    id: str
    home_country: str
    away_country: str
    kickoff: Optional[str] = None

class MatchResultUpdate(BaseModel):
    score_home: int
    score_away: int

class PlayerScoreEntry(BaseModel):
    player_id: str
    minutes_played: int = 0
    goals: int = 0
    assists: int = 0
    yellow_cards: int = 0
    red_card: bool = False
    own_goals: int = 0
    penalties_missed: int = 0
    penalties_saved: int = 0
    saves: int = 0
    rating: float = 0.0
    is_mvp: bool = False

class ScoreBatchEntry(BaseModel):
    match_id: str
    scores: list[PlayerScoreEntry]

class MatchdayOut(BaseModel):
    id: str
    name: str
    date: Optional[str] = None
    phase: str
    status: str
    matches: list = Field(default_factory=list)

class PlayerScoreOut(BaseModel):
    player_id: str
    player_name: str = ""
    position: str = ""
    country_code: str = ""
    minutes_played: int = 0
    goals: int = 0
    assists: int = 0
    clean_sheet: bool = False
    yellow_cards: int = 0
    red_card: bool = False
    own_goals: int = 0
    penalties_missed: int = 0
    penalties_saved: int = 0
    saves: int = 0
    rating: float = 0.0
    bonus_points: int = 0
    total_points: int = 0


# --- Market & Reposition Draft ---

class MarketWindowCreate(BaseModel):
    phase: str  # 'GRUPOS', 'Mercado_1_R32', etc.
    market_type: str
    clause_window_start: str
    clause_window_end: str
    market_window_start: str
    market_window_end: str
    reposition_draft_start: str
    reposition_draft_end: str
    max_buys: int = 3
    max_sells: int = 3
    initial_budget: int = 100000000
    protect_budget: int = 300000000

class MarketWindowUpdate(BaseModel):
    clause_window_start: Optional[str] = None
    clause_window_end: Optional[str] = None
    market_window_start: Optional[str] = None
    market_window_end: Optional[str] = None
    reposition_draft_start: Optional[str] = None
    reposition_draft_end: Optional[str] = None
    max_buys: Optional[int] = None
    max_sells: Optional[int] = None
    initial_budget: Optional[int] = None
    protect_budget: Optional[int] = None

class MarketWindowOut(BaseModel):
    id: int
    league_id: str
    phase: str
    market_type: str
    status: str
    clause_window_start: Optional[str] = None
    clause_window_end: Optional[str] = None
    market_window_start: Optional[str] = None
    market_window_end: Optional[str] = None
    reposition_draft_start: Optional[str] = None
    reposition_draft_end: Optional[str] = None
    max_buys: int = 3
    max_sells: int = 3
    initial_budget: int = 100000000
    protect_budget: int = 300000000
    created_at: str

class PlayerClauseIn(BaseModel):
    player_id: str
    clause_amount: int
    is_blocked: bool = False

class PlayerClausesSetRequest(BaseModel):
    clauses: list[PlayerClauseIn]

class PlayerClauseOut(BaseModel):
    player_id: str
    player_name: str = ""
    clause_amount: int
    is_blocked: bool = False

class MarketBudgetOut(BaseModel):
    initial_budget: int
    earned_from_sales: int
    spent_on_buys: int
    remaining_budget: int
    buys_count: int
    sells_count: int
    max_buys: int
    max_sells: int

class AvailablePlayerOut(BaseModel):
    player_id: str
    name: str
    position: str
    country_code: str
    photo: str = ""
    market_value: int = 0
    current_team_id: str
    current_team_name: str
    clause_amount: int
    is_blocked: bool = False

class MarketTransactionOut(BaseModel):
    id: int
    buyer_team_id: str
    buyer_team_name: str
    seller_team_id: str
    seller_team_name: str
    player_id: str
    player_name: str
    clause_amount_paid: int
    transaction_date: str
    status: str

class BuyPlayerRequest(BaseModel):
    player_id: str

class RepositionDraftOrderEntry(BaseModel):
    team_id: str
    team_name: str
    owner_nick: str
    remaining_budget: int
    players_count: int
    gk_count: int = 0
    def_count: int = 0
    mid_count: int = 0
    fwd_count: int = 0
    pick_number: int = 0

class RepositionDraftState(BaseModel):
    status: str  # 'waiting_turn', 'your_turn', 'completed'
    current_turn_team_id: Optional[str] = None
    current_turn_number: int = 0
    draft_order: list[RepositionDraftOrderEntry] = Field(default_factory=list)
    remaining_available_players: int = 0
    my_picks: list = Field(default_factory=list)
    leaderboard: list[RepositionDraftOrderEntry] = Field(default_factory=list)

class RepositionAvailablePlayerOut(BaseModel):
    player_id: str
    name: str
    position: str
    country_code: str
    photo: str = ""
    market_value: int = 0

class RepositionDraftPickRequest(BaseModel):
    player_id: Optional[str] = None  # None = pasar turno

