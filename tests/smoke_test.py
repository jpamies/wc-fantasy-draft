"""Quick integration smoke test for the API."""
import urllib.request
import json
import sys


def post(url, data, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, json.dumps(data).encode(), headers)
    return json.loads(urllib.request.urlopen(req).read())


def get(url, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    return json.loads(urllib.request.urlopen(req).read())


def patch(url, data, token):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    req = urllib.request.Request(url, json.dumps(data).encode(), headers, method="PATCH")
    return json.loads(urllib.request.urlopen(req).read())


BASE = "http://localhost:8000/api/v1"
passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}")
        failed += 1


print("=== WC Fantasy 2026 — Smoke Test ===\n")

# 1. Countries
print("1. Countries API")
countries = get(f"{BASE}/countries")
check("23 countries loaded", len(countries) == 23)

# 2. Players
print("2. Players API")
players = get(f"{BASE}/players?country=ESP&limit=5")
check("Spanish players returned", len(players) > 0)
check("Lamine Yamal exists", any(p["name"] == "Lamine Yamal" for p in players))
check("Clause value = 1.5x market value", players[0]["clause_value"] == int(players[0]["market_value"] * 1.5))

# 3. Create league
print("3. League creation")
league = post(f"{BASE}/leagues", {"name": "Test Liga MVP"})
check("League created with code", len(league["code"]) == 6)
league_id = league["id"]

# 4. Join as commissioner
print("4. Auth - join as commissioner")
auth1 = post(f"{BASE}/auth/join", {"league_code": league["code"], "nickname": "jordi", "team_name": "FC Jordi"})
check("Commissioner joined", auth1["is_commissioner"] is True)
token1 = auth1["token"]
team1 = auth1["team_id"]

# 5. Join as player 2
print("5. Auth - join as player 2")
auth2 = post(f"{BASE}/auth/join", {"league_code": league["code"], "nickname": "alex", "team_name": "FC Alex"})
check("Player 2 joined", auth2["is_commissioner"] is False)
token2 = auth2["token"]
team2 = auth2["team_id"]

# 6. Get league
print("6. League info")
lg = get(f"{BASE}/leagues/{league_id}")
check("League has 2 teams", len(lg["teams"]) == 2)

# 7. Start draft
print("7. Draft")
draft_result = post(f"{BASE}/leagues/{league_id}/draft/start", {}, token1)
check("Draft started", "draft_id" in draft_result)

state = get(f"{BASE}/leagues/{league_id}/draft")
check("Draft in progress", state["status"] == "in_progress")
check("Round 1, Pick 1", state["current_round"] == 1 and state["current_pick"] == 1)

# 8. Make picks
print("8. Draft picks")
current_token = token1 if state["current_team_id"] == team1 else token2
pick1 = post(f"{BASE}/leagues/{league_id}/draft/pick", {"player_id": "ESP-001"}, current_token)
check("Pick 1: Lamine Yamal", pick1["player_name"] == "Lamine Yamal")

state = get(f"{BASE}/leagues/{league_id}/draft")
next_token = token1 if state["current_team_id"] == team1 else token2
pick2 = post(f"{BASE}/leagues/{league_id}/draft/pick", {"player_id": "FRA-001"}, next_token)
check("Pick 2 made", pick2.get("ok") is True)

# 9. Get team
print("9. Team management")
team_data = get(f"{BASE}/teams/{team1}")
check("Team has players", len(team_data["players"]) > 0)

# 10. Standings
print("10. Standings")
standings = get(f"{BASE}/leagues/{league_id}/standings")
check("Standings for 2 teams", len(standings) == 2)

# 11. Matchday & scoring
print("11. Scoring")
md = post(f"{BASE}/scoring/matchdays", {"id": "MD1", "name": "Jornada 1", "date": "2026-06-11", "phase": "group_stage"}, token1)
check("Matchday created", md.get("ok") is True)

match = post(f"{BASE}/scoring/matchdays/MD1/matches", {"id": "ESP-CRC", "home_country": "ESP", "away_country": "CRO"}, token1)
check("Match added", match.get("ok") is True)

result = patch(f"{BASE}/scoring/matches/ESP-CRC/result", {"score_home": 3, "score_away": 0}, token1)
check("Result saved", result.get("ok") is True)

scores = post(f"{BASE}/scoring/matchdays/MD1/scores", {
    "match_id": "ESP-CRC",
    "scores": [
        {"player_id": "ESP-001", "minutes_played": 90, "goals": 1, "assists": 1, "is_mvp": True},
        {"player_id": "ESP-002", "minutes_played": 90, "goals": 0, "assists": 1},
    ]
}, token1)
check("Scores submitted", scores.get("ok") is True)
check("Yamal scored points", any(s["total_points"] > 0 for s in scores["scores"]))

md_detail = get(f"{BASE}/scoring/matchdays/MD1")
check("Matchday has scores", len(md_detail["scores"]) > 0)

# 12. Market
print("12. Market")
window = post(f"{BASE}/leagues/{league_id}/admin/open-window", {}, token1)
check("Transfer window opened", window.get("window_open") is True)

market = get(f"{BASE}/leagues/{league_id}/market")
check("Free agents available", len(market["free_agents"]) > 0)
check("Window is open", market["window_open"] is True)

# 13. Recover session
print("13. Session recovery")
recovered = post(f"{BASE}/auth/recover", {"league_code": league["code"], "nickname": "jordi"})
check("Session recovered", len(recovered["token"]) > 0)

print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed out of {passed+failed}")
if failed > 0:
    sys.exit(1)
print("=== ALL TESTS PASSED ===")
