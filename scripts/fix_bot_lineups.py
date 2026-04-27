"""One-off repair: set a default 11 + captain/VC for every bot whose
team_players have no is_starter flagged. Standalone (sqlite3 only)."""
import sqlite3
import sys

FORMATIONS = [
    {"GK": 1, "DEF": 4, "MID": 3, "FWD": 3},
    {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2},
    {"GK": 1, "DEF": 3, "MID": 4, "FWD": 3},
    {"GK": 1, "DEF": 3, "MID": 5, "FWD": 2},
    {"GK": 1, "DEF": 5, "MID": 3, "FWD": 2},
    {"GK": 1, "DEF": 5, "MID": 4, "FWD": 1},
    {"GK": 1, "DEF": 4, "MID": 5, "FWD": 1},
]

DB = sys.argv[1] if len(sys.argv) > 1 else "/data/wc_fantasy.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

bots = cur.execute(
    "SELECT id, owner_nick, team_name FROM fantasy_teams WHERE owner_nick LIKE 'bot_%'"
).fetchall()
print(f"Found {len(bots)} bot teams")

for bot in bots:
    team_id = bot["id"]
    rows = cur.execute(
        """SELECT tp.player_id, p.position,
                  COALESCE(p.market_value, 0) AS market_value
           FROM team_players tp JOIN players p ON tp.player_id = p.id
           WHERE tp.team_id=?""",
        (team_id,),
    ).fetchall()
    if not rows:
        print(f"  {bot['team_name']}: no players, skip")
        continue

    by_pos = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for r in rows:
        by_pos.setdefault(r["position"], []).append(dict(r))
    for arr in by_pos.values():
        arr.sort(key=lambda x: x["market_value"], reverse=True)

    chosen = None
    used = None
    for f in FORMATIONS:
        if all(len(by_pos.get(pos, [])) >= n for pos, n in f.items()):
            picks = []
            for pos, n in f.items():
                picks.extend(by_pos[pos][:n])
            chosen = picks
            used = f
            break
    if chosen is None:
        all_sorted = sorted([dict(r) for r in rows], key=lambda x: x["market_value"], reverse=True)
        chosen = all_sorted[:11]
        used = "fallback-best11"

    sorted_starters = sorted(chosen, key=lambda x: x["market_value"], reverse=True)
    captain_id = sorted_starters[0]["player_id"]
    vc_id = sorted_starters[1]["player_id"] if len(sorted_starters) > 1 else None

    cur.execute(
        "UPDATE team_players SET is_starter=0, is_captain=0, is_vice_captain=0 WHERE team_id=?",
        (team_id,),
    )
    for p in chosen:
        cur.execute(
            "UPDATE team_players SET is_starter=1 WHERE team_id=? AND player_id=?",
            (team_id, p["player_id"]),
        )
    cur.execute(
        "UPDATE team_players SET is_captain=1 WHERE team_id=? AND player_id=?",
        (team_id, captain_id),
    )
    if vc_id:
        cur.execute(
            "UPDATE team_players SET is_vice_captain=1 WHERE team_id=? AND player_id=?",
            (team_id, vc_id),
        )
    print(f"  {bot['team_name']}: 11 starters set ({used}), cap={captain_id[:12]}")

con.commit()
con.close()
print("Done.")
