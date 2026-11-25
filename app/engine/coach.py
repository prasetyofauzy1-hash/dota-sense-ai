"""Post-match coach (Phase 5, first version): builds a report from OpenDota match data."""
from __future__ import annotations

from app.data import constants as C
from app.data.opendota import OpenDotaClient

KEY_ITEM_COST = 2000


def _find_player(match: dict, account_id: int | None, hero_id: int | None) -> dict | None:
    for p in match.get("players", []):
        if account_id is not None and p.get("account_id") == account_id:
            return p
        if account_id is None and hero_id is not None and p.get("hero_id") == hero_id:
            return p
    return None


def build_report(match: dict, *, account_id: int | None = None, hero_id: int | None = None,
                 popularity: dict | None = None) -> dict:
    player = _find_player(match, account_id, hero_id)
    if player is None:
        raise ValueError("Player not found in this match (check account ID or hero).")
    hero = C.heroes().get(player["hero_id"], {})
    radiant = player.get("player_slot", 0) < 128
    won = bool(match.get("radiant_win")) == radiant
    minutes = (match.get("duration") or 0) / 60

    timings = []
    for entry in player.get("purchase_log") or []:
        key = entry.get("key")
        cost = C.item_cost(key) or 0
        if cost >= KEY_ITEM_COST:
            timings.append({"item": key, "item_name": C.item_display(key), "minute": round(entry["time"] / 60, 1), "cost": cost})

    benchmarks = {k: round(v.get("pct", 0) * 100) for k, v in (player.get("benchmarks") or {}).items()
                  if isinstance(v, dict) and "pct" in v}
    final_items = [C.items_by_id().get(player.get(f"item_{i}")) for i in range(6)]
    final_items = [i for i in final_items if i]

    suggestions: list[str] = []
    if benchmarks.get("last_hits_per_min", 100) < 40:
        suggestions.append("Last hits per minute were below 40% of players on this hero: practise last-hitting and farm patterns.")
    if benchmarks.get("gold_per_min", 100) < 40:
        suggestions.append("GPM was low for this hero: spend less time between camps and avoid idle walking.")
    if (player.get("deaths") or 0) > max(6, minutes / 5):
        suggestions.append(f"{player.get('deaths')} deaths: review positioning and consider earlier defensive items.")
    if timings and timings[0]["minute"] > 20:
        suggestions.append(f"First major item ({timings[0]['item_name']}) came at {timings[0]['minute']} min; aim to finish it earlier.")
    if not player.get("purchase_log"):
        suggestions.append("Item timings unavailable: this match is not parsed on OpenDota (request a parse at opendota.com).")
    if popularity and final_items:
        late = popularity.get("late_game_items") or {}
        popular = {C.items_by_id().get(int(k)) for k, _ in sorted(late.items(), key=lambda kv: -kv[1])[:8]}
        unusual = [C.item_display(i) for i in final_items if i not in popular and (C.item_cost(i) or 0) >= KEY_ITEM_COST]
        if unusual:
            suggestions.append("Less common late items for this hero: " + ", ".join(unusual) +
                               ". Fine if situational — check they answered the enemy lineup.")
    if not suggestions:
        suggestions.append("Solid game by these metrics. Compare item timings with your previous matches.")

    return {
        "match_id": str(match.get("match_id")),
        "hero": hero.get("localized_name", str(player["hero_id"])),
        "result": "Win" if won else "Loss",
        "duration_min": round(minutes, 1),
        "kda": f"{player.get('kills')}/{player.get('deaths')}/{player.get('assists')}",
        "gpm": player.get("gold_per_min"),
        "xpm": player.get("xp_per_min"),
        "last_hits": player.get("last_hits"),
        "final_items": [C.item_display(i) for i in final_items],
        "item_timings": timings,
        "benchmarks_pct": benchmarks,
        "parsed": bool(player.get("purchase_log")),
        "suggestions": suggestions,
        "source": "OpenDota",
    }


def coach_match(client: OpenDotaClient, match_id: int | str, *, account_id: int | None = None,
                hero_id: int | None = None) -> dict:
    match = client.match(match_id)
    player = _find_player(match, account_id, hero_id)
    popularity = None
    if player is not None:
        try:
            popularity = client.hero_item_popularity(player["hero_id"])
        except Exception:  # popularity is optional context
            popularity = None
    return build_report(match, account_id=account_id, hero_id=hero_id, popularity=popularity)
