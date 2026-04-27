"""Smoke test for market system."""
import asyncio
import httpx
from datetime import datetime, timedelta

BASE = "http://localhost:8765/api/v1"


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=10.0) as client:
        # Create league
        print("[1] Creating league...")
        r = await client.post("/leagues", json={"name": "Market Smoke Test"})
        assert r.status_code == 200, f"Create league: {r.status_code} {r.text}"
        league = r.json()
        league_id = league["id"]
        league_code = league["code"]
        print(f"    league_id={league_id} code={league_code}")

        # Join as 3 teams
        teams = []
        for i, nick in enumerate(["alice", "bob", "charlie"]):
            r = await client.post("/auth/join", json={
                "league_code": league_code,
                "nickname": nick,
                "team_name": f"Team {nick}",
                "display_name": nick.title(),
            })
            assert r.status_code == 200, f"Join {nick}: {r.text}"
            d = r.json()
            teams.append({
                "team_id": d["team_id"],
                "token": d["token"],
                "is_commissioner": d["is_commissioner"],
                "headers": {"Authorization": f"Bearer {d['token']}"},
            })
            print(f"    joined {nick}: team_id={d['team_id']} commissioner={d['is_commissioner']}")

        comm = teams[0]
        assert comm["is_commissioner"]

        # Create market window
        print("[2] Creating market window...")
        now = datetime.now()
        body = {
            "phase": "TEST_R32",
            "market_type": "R32 Test",
            "clause_window_start": now.isoformat(),
            "clause_window_end": (now + timedelta(hours=1)).isoformat(),
            "market_window_start": (now + timedelta(hours=1)).isoformat(),
            "market_window_end": (now + timedelta(hours=2)).isoformat(),
            "reposition_draft_start": (now + timedelta(hours=2)).isoformat(),
            "reposition_draft_end": (now + timedelta(hours=3)).isoformat(),
        }
        r = await client.post(f"/leagues/{league_id}/admin/market-windows",
                              json=body, headers=comm["headers"])
        assert r.status_code == 200, f"Create window: {r.text}"
        window_id = r.json()["id"]
        print(f"    window_id={window_id}")

        # Test 403 for non-commissioner
        print("[3] Testing 403 for non-commissioner...")
        r = await client.post(f"/leagues/{league_id}/admin/market-windows",
                              json=body, headers=teams[1]["headers"])
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
        print(f"    OK")

        # List windows
        print("[4] Listing market windows...")
        r = await client.get(f"/leagues/{league_id}/market-windows", headers=comm["headers"])
        assert r.status_code == 200
        assert len(r.json()) == 1

        # Get window detail
        print("[5] Getting window detail...")
        r = await client.get(f"/leagues/{league_id}/market/{window_id}", headers=comm["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "pending"

        # Update window
        print("[6] Updating window timing...")
        r = await client.patch(f"/leagues/{league_id}/admin/market-windows/{window_id}",
                               json={"max_buys": 5}, headers=comm["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["max_buys"] == 5

        # Start clause phase
        print("[7] Starting clause phase...")
        r = await client.post(
            f"/leagues/{league_id}/admin/market-windows/{window_id}/start-clause-phase",
            headers=comm["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "clause_window"

        # Get budget (should auto-init in clause phase)
        r = await client.get(f"/teams/{comm['team_id']}/market/{window_id}/budget",
                             headers=comm["headers"])
        assert r.status_code == 200, r.text
        budget = r.json()
        assert budget["initial_budget"] == 100000000
        print(f"    budget remaining: {budget['remaining_budget']}")

        # Get empty clauses
        r = await client.get(f"/teams/{comm['team_id']}/market/{window_id}/clauses",
                             headers=comm["headers"])
        assert r.status_code == 200
        assert r.json() == []

        # Test 403 viewing other team's clauses
        r = await client.get(f"/teams/{teams[1]['team_id']}/market/{window_id}/clauses",
                             headers=comm["headers"])
        assert r.status_code == 403
        print(f"    403 viewing other team's clauses: OK")

        # Start market phase
        print("[8] Starting market phase...")
        r = await client.post(
            f"/leagues/{league_id}/admin/market-windows/{window_id}/start-market-phase",
            headers=comm["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "market_open"

        # All teams have budget now
        for t in teams:
            r = await client.get(f"/teams/{t['team_id']}/market/{window_id}/budget",
                                 headers=t["headers"])
            assert r.status_code == 200, r.text
            assert r.json()["remaining_budget"] == 100000000

        # Available players
        r = await client.get(f"/leagues/{league_id}/market/{window_id}/available-players",
                             headers=comm["headers"])
        assert r.status_code == 200, r.text
        print(f"    available players: {len(r.json())}")

        # Close market
        print("[9] Closing market...")
        r = await client.post(
            f"/leagues/{league_id}/admin/market-windows/{window_id}/close-market",
            headers=comm["headers"])
        assert r.status_code == 200
        assert r.json()["status"] == "market_closed"

        # Start reposition draft
        print("[10] Starting reposition draft...")
        r = await client.post(
            f"/leagues/{league_id}/admin/market-windows/{window_id}/start-reposition-draft",
            headers=comm["headers"])
        assert r.status_code == 200, r.text

        # Get reposition state
        r = await client.get(
            f"/leagues/{league_id}/market/{window_id}/reposition-draft-state",
            headers=comm["headers"])
        assert r.status_code == 200, r.text
        st = r.json()
        print(f"    status={st['status']} current_turn={st['current_turn_team_id']}")
        print(f"    draft order: {[e['team_name'] for e in st['draft_order']]}")
        assert len(st["draft_order"]) == 3

        # Pass turn for current team
        current_team_id = st["current_turn_team_id"]
        current_team = next(t for t in teams if t["team_id"] == current_team_id)
        r = await client.post(
            f"/teams/{current_team['team_id']}/market/{window_id}/reposition-draft-pick",
            json={"player_id": None}, headers=current_team["headers"])
        assert r.status_code == 200, r.text

        # Verify turn moved
        r = await client.get(
            f"/leagues/{league_id}/market/{window_id}/reposition-draft-state",
            headers=comm["headers"])
        st2 = r.json()
        assert st2["current_turn_team_id"] != current_team_id
        print(f"    after pass: new current_turn={st2['current_turn_team_id']}")

        print("\n✅ ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
