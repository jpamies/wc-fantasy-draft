# WC Fantasy 2026 - Game Rules

This document describes the current gameplay rules implemented in the app.

## 1. Squad and Lineup Model

- Squad size per team: 12 players.
- Position cap per squad: max 4 players for each position (`GK`, `DEF`, `MID`, `FWD`).
- Matchday lineup uses 5 slots:
  - `GK`
  - `DEF`
  - `MID`
  - `FWD`
  - `WILDCARD` (any position)

## 2. Matchday Lineups

- Each matchday has its own lineup snapshot.
- You can save a partial lineup (not all 5 slots are required).
- Completed matchdays are locked.
- During active matchdays:
  - You can still edit, but
  - You cannot promote to starter a player whose country has already played.

## 3. Captaincy

- Captain is optional in the 5-slot lineup flow.
- Captain points are doubled (`x2`) for matchday scoring.
- No vice-captain is used in the main 5-slot lineup flow.
- Auto-lineup assigns a captain automatically.

## 4. Draft

- Snake order draft.
- 12 rounds per team.
- Queue and autodraft are available.
- Position caps are enforced in picks.

## 5. Market and Clause Attempts

- Market runs in windows/phases.
- Teams can submit clause attempts during the allowed phases.
- Clause attempts are resolved later, in random order.
- At resolution time, each attempt is validated against:
  - current remaining budget,
  - team-level limits (max squad size and max per-position cap),
  - per-window attempt/sell limits.

This means a submitted attempt can still fail if earlier resolutions consumed budget or slots.

## 6. Reposition Draft

- Reposition draft can run after market phases.
- Picks follow turn order from reposition state.
- Picks enforce:
  - max squad size (12),
  - max per-position cap (4).
- Teams can pass their turn.

## 7. Standings

- Total standings are based on accumulated team points.
- Matchday standings can be viewed per matchday.
- Budget is not displayed in standings view.

## 8. Source of Truth

- Current runtime behavior in backend/frontend code is authoritative.
- This file is maintained to match the implemented behavior.