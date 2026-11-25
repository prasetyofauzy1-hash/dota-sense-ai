"""Refresh the offline sample from OpenDota Explorer. Run from the repo root."""
from __future__ import annotations

import argparse
import gzip
import json
from datetime import UTC, date, datetime, time
from pathlib import Path

import requests

EXPLORER = "https://api.opendota.com/api/explorer"
OUTPUT = Path(__file__).resolve().parents[1] / "app" / "data" / "snapshot" / "pro_matches.json.gz"
# Selected pro tournament main events, not public matches or open qualifiers.
LEAGUES = (
    17420, 18988, 19099, 19101, 19102, 19239, 19255, 19269, 19290, 19422, 19435,
    19532, 19543, 19696, 19719, 19785, 20009, 20208, 20279, 20395, 20486, 20511,
)
SLOTS = [*range(5), *range(128, 133)]
ITEM_COLUMNS = ", ".join(
    [f"p.item_{i}" for i in range(6)] + [f"p.backpack_{i}" for i in range(3)]
)


def compact(row: dict) -> list | None:
    players = row["players"]
    if [p[0] for p in players] != SLOTS:
        return None
    if len({p[1] for p in players}) != 10 or any(not p[1] for p in players):
        return None
    if any(item is None or item < 0 for p in players for item in p[2:]):
        return None
    teams = [
        [[p[1], sorted({item for item in p[2:] if item})] for p in players[start:start + 5]]
        for start in (0, 5)
    ]
    return [row["match_id"], row["leagueid"], row["start_time"], row["radiant_win"], *teams]


def fetch(start: int, before: int) -> dict:
    matches = []
    leagues = {}
    with requests.Session() as session:
        for offset in range(0, len(LEAGUES), 4):
            ids = ", ".join(str(league) for league in LEAGUES[offset:offset + 4])
            sql = f"""
                SELECT m.match_id, m.leagueid, l.name, m.start_time, m.radiant_win,
                       json_agg(json_build_array(p.player_slot, p.hero_id, {ITEM_COLUMNS})
                                ORDER BY p.player_slot) AS players
                FROM matches m
                JOIN leagues l USING (leagueid)
                JOIN player_matches p USING (match_id)
                WHERE m.leagueid IN ({ids}) AND l.tier IN ('professional', 'premium')
                  AND m.start_time >= {start} AND m.start_time < {before}
                  AND m.radiant_win IS NOT NULL AND m.game_mode = 2 AND m.duration >= 600
                GROUP BY m.match_id, m.leagueid, l.name, m.start_time, m.radiant_win
            """
            response = session.get(EXPLORER, params={"sql": sql}, timeout=45)
            response.raise_for_status()
            result = response.json()
            if result.get("err") or not isinstance(result.get("rows"), list):
                raise RuntimeError(f"OpenDota Explorer returned an invalid result for league IDs {ids}")
            for row in result["rows"]:
                if match := compact(row):
                    matches.append(match)
                    leagues[row["leagueid"]] = row["name"].strip()
    if not matches:
        raise RuntimeError("No complete professional matches found")
    return {
        "leagues": dict(sorted(leagues.items())),
        "matches": sorted(matches, key=lambda row: (row[2], row[0])),
    }


def midnight(day: date) -> int:
    return int(datetime.combine(day, time.min, UTC).timestamp())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True, help="inclusive UTC date")
    parser.add_argument("--before", type=date.fromisoformat, required=True, help="exclusive UTC date")
    args = parser.parse_args()
    if args.before <= args.start:
        parser.error("--before must be later than --start")
    sample = fetch(midnight(args.start), midnight(args.before))
    packed = json.dumps(sample, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    OUTPUT.write_bytes(gzip.compress(packed, mtime=0))
    print(f"Wrote {len(sample['matches']):,} matches from {len(sample['leagues'])} tournaments to {OUTPUT}")
