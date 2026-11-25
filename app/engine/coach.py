"""Post-match coach (Phase 5): builds a report from OpenDota match data."""
from __future__ import annotations

from collections import Counter

from app.data import constants as C
from app.data.opendota import OpenDotaClient

CORE_ITEM_COST = 2000
SUPPORT_ITEM_COST = 1400
STEAM64_OFFSET = 76561197960265728

GAME_MODES: dict[int, str] = {
    0: "Unknown",
    1: "All Pick",
    2: "Captains Mode",
    3: "Random Draft",
    4: "Single Draft",
    5: "All Random",
    12: "Least Played",
    16: "Captains Draft",
    18: "Ability Draft",
    22: "All Pick",
    23: "Turbo",
}

LOBBY_TYPES: dict[int, str] = {
    0: "Normal",
    1: "Practice",
    2: "Tournament",
    4: "Co-op Bots",
    5: "Ranked Team",
    6: "Ranked Solo",
    7: "Ranked",
    9: "Battle Cup",
}


def parse_account_id(raw: int | str | None) -> int | None:
    """Validate Steam32 account ID (auto-converts Steam64 IDs)."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError("Enter a valid numeric Steam32 (or Steam64) account ID.")
    text = str(raw).strip()
    if not text:
        return None
    if not text.isdigit():
        raise ValueError("Account ID must be numeric (Steam32 or Steam64 ID).")
    val = int(text)
    if val >= STEAM64_OFFSET:
        val -= STEAM64_OFFSET
    if val <= 0:
        raise ValueError("Account ID must be a positive number.")
    return val


def _is_completed_item(key: str | None) -> bool:
    """True for purchasable completed/standalone items (excludes raw secret-shop components & recipes)."""
    if not key or key.startswith("recipe_"):
        return False
    item = C.items().get(key)
    if not item:
        return False
    if (item.get("cost") or 0) <= 0:
        return False
    if item.get("qual") == "secret_shop" and not item.get("components"):
        return False
    return True


def _game_mode_label(match: dict) -> tuple[str, bool]:
    gm = match.get("game_mode")
    lt = match.get("lobby_type")
    is_turbo = gm == 23
    mode = GAME_MODES.get(gm, f"Mode {gm}") if gm is not None else "Standard"
    if lt == 7 and not is_turbo:
        return f"Ranked {mode}", False
    if lt == 4:
        return f"Co-op Bots ({mode})", False
    return mode, is_turbo


def _find_player(match: dict, account_id: int | None, hero_id: int | None) -> dict | None:
    players = match.get("players") or []
    if account_id is not None:
        for p in players:
            if p.get("account_id") == account_id:
                return p
    if hero_id is not None:
        for p in players:
            if p.get("hero_id") == hero_id:
                return p
    return None


def _player_not_found_message(match: dict, account_id: int | None, hero_id: int | None) -> str:
    heroes_in_match = [
        C.heroes().get(p.get("hero_id"), {}).get("localized_name")
        for p in (match.get("players") or [])
        if p.get("hero_id")
    ]
    heroes_in_match = [h for h in heroes_in_match if h]
    hint = ""
    if account_id is not None:
        hint = " Private Dota 2 profiles hide account IDs on OpenDota — try selecting your hero instead."
    if heroes_in_match:
        return f"Player not found in this match.{hint} Heroes in this match: {', '.join(heroes_in_match)}."
    return f"Player not found in this match (check account ID or hero).{hint}"


def _infer_role(match: dict, player: dict, hero: dict, minutes: float, is_turbo: bool) -> str:
    radiant = player.get("player_slot", 0) < 128
    teammates = [p for p in (match.get("players") or []) if (p.get("player_slot", 0) < 128) == radiant]
    wards_total = (player.get("obs_placed") or 0) + (player.get("sen_placed") or 0)
    is_support_hero = "Support" in (hero.get("roles") or [])

    if len(teammates) < 3:
        return "Support" if (is_support_hero and wards_total >= 3) else "Core"

    def _farm_score(p: dict) -> float:
        return float(p.get("net_worth") or p.get("gold_per_min") or 0)

    ranked = sorted(teammates, key=_farm_score, reverse=True)
    rank = next((idx + 1 for idx, p in enumerate(ranked) if p is player), len(ranked))
    bottom_two = rank >= len(ranked) - 1
    lh_per_min = (player.get("last_hits") or 0) / max(minutes, 1.0)
    if bottom_two and (wards_total >= 3 or is_support_hero or (not is_turbo and lh_per_min < 2.5)):
        return "Support"
    return "Core"


def _popular_completed_items(popularity: dict) -> set[str]:
    counts: Counter[str] = Counter()
    for phase in ("early_game_items", "mid_game_items", "late_game_items"):
        for item_id_str, cnt in (popularity.get(phase) or {}).items():
            try:
                key = C.items_by_id().get(int(item_id_str))
            except (TypeError, ValueError):
                continue
            if _is_completed_item(key) and (C.item_cost(key) or 0) >= SUPPORT_ITEM_COST:
                counts[key] += int(cnt or 0)
    if not counts:
        return set()
    top_count = counts.most_common(1)[0][1]
    popular = {k for k, _ in counts.most_common(15)}
    popular |= {k for k, v in counts.items() if top_count > 0 and v >= top_count * 0.15}
    return popular


def build_report(match: dict, *, account_id: int | None = None, hero_id: int | None = None,
                 popularity: dict | None = None) -> dict:
    account_id = parse_account_id(account_id)
    player = _find_player(match, account_id, hero_id)
    if player is None:
        raise ValueError(_player_not_found_message(match, account_id, hero_id))

    pid_hero = player.get("hero_id") or 0
    hero = C.heroes().get(pid_hero, {})
    radiant = player.get("player_slot", 0) < 128
    won = bool(match.get("radiant_win")) == radiant
    minutes = (match.get("duration") or 0) / 60
    mode_label, is_turbo = _game_mode_label(match)
    short_match = minutes < 5 or pid_hero == 0
    role = _infer_role(match, player, hero, minutes, is_turbo)
    parsed = bool(player.get("purchase_log"))

    item_cost_threshold = SUPPORT_ITEM_COST if role == "Support" else CORE_ITEM_COST
    timings: list[dict] = []
    seen_timings: set[str] = set()
    for entry in player.get("purchase_log") or []:
        key = entry.get("key")
        if key in seen_timings or not _is_completed_item(key):
            continue
        cost = C.item_cost(key) or 0
        if cost >= item_cost_threshold:
            seen_timings.add(key)
            timings.append({
                "item": key,
                "item_name": C.item_display(key),
                "minute": round((entry.get("time") or 0) / 60, 1),
                "cost": cost,
            })

    benchmarks = {
        k: round(v["pct"] * 100)
        for k, v in (player.get("benchmarks") or {}).items()
        if isinstance(v, dict) and isinstance(v.get("pct"), (int, float))
    }

    final_item_keys = [C.items_by_id().get(player.get(f"item_{i}")) for i in range(6)]
    final_item_keys = [i for i in final_item_keys if i]
    neutral_key = C.items_by_id().get(player.get("item_neutral"))
    consumed_buffs: list[str] = []
    if player.get("aghanims_scepter") == 1 and "ultimate_scepter" not in final_item_keys:
        consumed_buffs.append("Aghanim's Scepter (consumed)")
    if player.get("aghanims_shard") == 1:
        consumed_buffs.append("Aghanim's Shard")

    teammates = [p for p in (match.get("players") or []) if (p.get("player_slot", 0) < 128) == radiant]
    team_kills = sum((p.get("kills") or 0) for p in teammates)
    kills = player.get("kills") or 0
    deaths = player.get("deaths") or 0
    assists = player.get("assists") or 0
    kp_pct = round(100 * (kills + assists) / team_kills) if team_kills > 0 else None

    obs_placed = player.get("obs_placed")
    sen_placed = player.get("sen_placed")
    wards = (
        {"obs": int(obs_placed or 0), "sen": int(sen_placed or 0)}
        if (obs_placed is not None or sen_placed is not None)
        else None
    )

    suggestions: list[str] = []
    if short_match:
        suggestions.append(
            "Match ended very early (under 5 min) or had an unpicked hero — performance coaching is skipped."
        )
    else:
        if is_turbo:
            suggestions.append("Turbo match (2x gold/XP): standard GPM and item-timing benchmarks are not applied.")

        if role == "Core":
            if not is_turbo and benchmarks.get("last_hits_per_min", 100) < 40:
                suggestions.append(
                    "Last hits per minute were below 40% of players on this hero: practise lane last-hitting and farm patterns."
                )
            if not is_turbo and benchmarks.get("gold_per_min", 100) < 40:
                suggestions.append(
                    "GPM was low for this hero: reduce idle time between waves and jungle camps."
                )
            if not is_turbo and timings and timings[0]["minute"] > 20:
                suggestions.append(
                    f"First major item ({timings[0]['item_name']}) came at {timings[0]['minute']} min; aim to finish it earlier."
                )
            if not is_turbo and benchmarks.get("hero_damage_per_min", 100) < 25 and not won:
                suggestions.append(
                    "Hero damage was low for this hero: look for earlier fights once your core item is online."
                )
        else:
            if kp_pct is not None and team_kills >= 10 and kp_pct < 45:
                suggestions.append(
                    f"Kill participation was {kp_pct}% ({kills + assists}/{team_kills} team kills): rotate more to join fights."
                )
            if wards is not None and not is_turbo and wards["obs"] < max(3, int(minutes / 6)):
                suggestions.append(
                    f"Only {wards['obs']} Observer Wards placed in {round(minutes)} min: keep vision up around objectives."
                )

        death_limit = max(7, minutes / 4.5) if role == "Support" else max(6, minutes / 5)
        if deaths > death_limit:
            suggestions.append(f"{deaths} deaths: review positioning and consider earlier defensive items.")

        if not parsed:
            suggestions.append(
                f"Item timings and ward stats unavailable: match is not parsed on OpenDota (request a parse at https://www.opendota.com/request#{match.get('match_id')})."
            )

        if popularity and final_item_keys:
            popular = _popular_completed_items(popularity)
            if popular:
                unusual = [
                    C.item_display(i)
                    for i in final_item_keys
                    if i not in popular and _is_completed_item(i) and (C.item_cost(i) or 0) >= CORE_ITEM_COST
                ]
                if unusual:
                    suggestions.append(
                        "Less common items for this hero: " + ", ".join(dict.fromkeys(unusual))
                        + ". Fine if situational — check they answered the enemy lineup."
                    )

        if not suggestions or (len(suggestions) == 1 and is_turbo):
            suggestions.append("Solid game by these metrics. Compare timings and impact with your previous matches.")

    match_id_str = str(match.get("match_id"))
    return {
        "match_id": match_id_str,
        "hero_id": pid_hero,
        "hero": hero.get("localized_name", f"Hero #{pid_hero}" if pid_hero else "Unknown"),
        "role": role,
        "game_mode": mode_label,
        "is_turbo": is_turbo,
        "short_match": short_match,
        "result": "Win" if won else "Loss",
        "duration_min": round(minutes, 1),
        "kda": f"{kills}/{deaths}/{assists}",
        "gpm": player.get("gold_per_min"),
        "xpm": player.get("xp_per_min"),
        "last_hits": player.get("last_hits"),
        "net_worth": player.get("net_worth"),
        "hero_damage": player.get("hero_damage"),
        "tower_damage": player.get("tower_damage"),
        "kill_participation_pct": kp_pct,
        "wards": wards,
        "final_items": [C.item_display(i) for i in final_item_keys],
        "neutral_item": C.item_display(neutral_key) if neutral_key else None,
        "consumed_buffs": consumed_buffs,
        "item_timings": timings,
        "benchmarks_pct": benchmarks,
        "parsed": parsed,
        "suggestions": suggestions,
        "opendota_url": f"https://www.opendota.com/matches/{match_id_str}",
        "parse_request_url": f"https://www.opendota.com/request#{match_id_str}",
        "source": "OpenDota",
    }


def coach_match(client: OpenDotaClient, match_id: int | str, *, account_id: int | None = None,
                hero_id: int | None = None, force_refresh: bool = False) -> dict:
    account_id = parse_account_id(account_id)
    match = client.match(match_id, force_refresh=force_refresh)
    player = _find_player(match, account_id, hero_id)
    popularity = None
    if player is not None and player.get("hero_id"):
        try:
            popularity = client.hero_item_popularity(player["hero_id"])
        except Exception:  # popularity is optional context
            popularity = None
    return build_report(match, account_id=account_id, hero_id=hero_id, popularity=popularity)
