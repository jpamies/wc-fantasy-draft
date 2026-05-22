# WC Fantasy 2026 - Scoring System

Scoring rules implemented by `src/backend/services/scoring_engine.py`.

## 1. Participation

- Minutes >= 60: `+2`
- Minutes > 0 and < 60: `+1`
- Minutes = 0: `0`

## 2. Goals by Position

- `GK`: `+6` per goal
- `DEF`: `+6` per goal
- `MID`: `+5` per goal
- `FWD`: `+4` per goal

## 3. Assists

- Any position: `+3` per assist

## 4. Clean Sheet

Applied only if player has `minutes >= 60`:

- `GK`, `DEF`: `+4`
- `MID`: `+1`
- `FWD`: no clean sheet bonus

## 5. Goals Conceded Penalty

Applied only for `GK` and `DEF` with `minutes >= 60`:

- `-1` for every 2 goals conceded (`goals_conceded // 2`)

## 6. Penalties and Saves

- Penalty missed: `-2` each
- GK penalty saved: `+5` each
- GK saves: `+1` every 3 saves (`saves // 3`)

## 7. Discipline and Own Goals

- Yellow card: `-1` each
- Red card: `-3`
- Own goal: `-2` each

## 8. Bonuses

- MVP flag: `+3`
- Hat-trick (3+ goals): `+3`

## 9. Captain Multiplier

Team matchday scoring applies captain bonus:

- Active captain gets `x2` points.
- If captain did not play and vice-captain played, vice-captain gets `x2`.

Note: lineup-5 flow uses captain only; legacy vice-captain fallback still exists in scoring engine for compatibility with older roster data.

## 10. Team Matchday Total

- Starts from current starters for that matchday snapshot.
- Optional auto-subs (if enabled in league settings):
  - up to 3 substitutions,
  - prefer same-position bench player who played,
  - otherwise any bench player who played.
- Sum active players' points, then apply captain multiplier.

## 11. Data Pipeline

Scores are persisted in `match_scores` and used by standings and lineup views.