"""Item recommendation engine (Phase 2): rule-based scoring with historical data as a
secondary signal. Popularity alone never produces a recommendation."""
from __future__ import annotations

from app.data import constants as C
from app.models import GamePhase, GameState, ItemRecommendation, Priority, Threat

PHASE_KEY = {GamePhase.PRE_GAME: "laning", GamePhase.LANING: "laning", GamePhase.MID: "mid", GamePhase.LATE: "late"}
NEXT_PHASE = {"laning": "mid", "mid": "late", "late": "late"}
POPULARITY_PHASE = {"laning": "early_game_items", "mid": "mid_game_items", "late": "late_game_items"}


# Items that suit only some hero types (DotaSense heuristics): item -> (check, weight if unfit)
RIGHT_CLICK_ITEMS = {"monkey_king_bar", "bloodthorn", "silver_edge", "skadi", "satanic", "butterfly", "mjollnir",
                     "abyssal_blade", "manta"}
MELEE_ONLY_ITEMS = {"bfury"}
SUPPORT_ITEMS = {"glimmer_cape", "pipe", "solar_crest", "crimson_guard", "force_staff", "gem", "ward_sentry", "dust"}


def _fit_weight(item: str, hero: dict) -> float:
    roles = set(hero.get("roles") or [])
    is_carry = "Carry" in roles
    if item in MELEE_ONLY_ITEMS and hero.get("attack_type") != "Melee":
        return 0.0
    if item in RIGHT_CLICK_ITEMS and not is_carry:
        return 0.3
    if item in SUPPORT_ITEMS and is_carry and "Support" not in roles and item not in {"dust", "ward_sentry", "gem"}:
        return 0.4
    return 1.0


def _owned_or_upgraded(item: str, owned: set[str]) -> bool:
    if item in owned:
        return True
    return any(up in owned for up in C.UPGRADES.get(item, []))


def _gold_needed(item: str, inventory: list[str]) -> int | None:
    """Gold still needed for an item, counting (nested) components already in the inventory."""
    if C.item_cost(item) is None:
        return None
    spare = list(inventory)

    def needed(key: str, top: bool = False) -> int:
        if not top and key in spare:
            spare.remove(key)
            return 0
        cost = C.item_cost(key) or 0
        components = [c for c in C.items().get(key, {}).get("components") or [] if c]
        recipe = cost - sum(C.item_cost(c) or 0 for c in components)
        return max(recipe, 0) + sum(needed(c) for c in components) if components else cost

    return needed(item, top=True)


def _popularity_share(popularity: dict | None, phase_key: str, item: str) -> float | None:
    if not popularity:
        return None
    bucket = popularity.get(POPULARITY_PHASE[phase_key]) or {}
    total = sum(bucket.values())
    item_id = C.items().get(item, {}).get("id")
    if not total or item_id is None:
        return None
    return bucket.get(str(item_id), 0) / total


def recommend_items(state: GameState, threats: list[Threat], *, popularity: dict | None = None,
                    limit: int = 5) -> list[ItemRecommendation]:
    hero = C.heroes_by_name().get(C.hero_short(state.hero.name) or "")
    if hero is None:
        return []
    owned = set(state.items)
    phase_key = PHASE_KEY[state.phase]
    build = C.CORE_BUILD.get(hero.get("primary_attr") or "all", C.CORE_BUILD["all"])

    candidates: dict[str, dict] = {}

    def add(item: str, score: float, reason: str, benefit: str) -> None:
        if item not in C.items() or _owned_or_upgraded(item, owned):
            return
        weight = _fit_weight(item, hero)
        if weight == 0.0:
            return
        c = candidates.setdefault(item, {"score": 0.0, "reasons": [], "counters": {}, "benefit": benefit})
        c["score"] += score * weight
        c["reasons"].append(reason)

    for item in build[phase_key]:
        add(item, 1.0, f"Core item for {hero['localized_name']} ({hero['primary_attr']}) in the {phase_key} phase",
            "Completes your core build and power spike for this phase.")
    for item in build[NEXT_PHASE[phase_key]]:
        if phase_key != "late":
            add(item, 0.4, f"Plan ahead: core for the {NEXT_PHASE[phase_key]} phase",
                "Prepares the next power spike.")

    for threat in threats:
        for tag in threat.tags:
            for item, why, _ in C.COUNTER_ITEMS.get(tag, []):
                add(item, 0.35 * threat.severity, "", why)
                if item in candidates:
                    candidates[item]["counters"].setdefault(tag, []).append(threat.hero_name)

    recs: list[ItemRecommendation] = []
    for item, c in candidates.items():
        share = _popularity_share(popularity, phase_key, item)
        score = c["score"]
        reasons = [r for r in dict.fromkeys(c["reasons"]) if r]
        reasons += [f"Counters {C.THREAT_LABELS[tag].lower()} ({', '.join(heroes)})"
                    for tag, heroes in c["counters"].items()]
        if share is not None and share > 0:
            score += min(0.3, share * 3)
            reasons.append(f"{share:.0%} of recent {phase_key}-phase purchases on this hero (OpenDota)")
        cost = C.item_cost(item)
        alt = next((a for a in C.alternatives(item)
                    if a in C.items() and not _owned_or_upgraded(a, owned) and _fit_weight(a, hero) > 0), None)
        needed = _gold_needed(item, state.items)
        counter_hits = sum(len(h) for h in c["counters"].values())
        priority = Priority.HIGH if (score >= 1.6 or (counter_hits >= 2 and score >= 1.2)) else Priority.SITUATIONAL
        recs.append(ItemRecommendation(
            item=item, item_name=C.item_display(item), cost=cost, priority=priority,
            reason="; ".join(reasons), benefit=c["benefit"],
            alternative=alt, alternative_name=C.item_display(alt) if alt else None,
            remaining_gold=(state.gold - needed) if (state.gold is not None and needed is not None) else None,
            affordable=(state.gold >= needed) if (state.gold is not None and needed is not None) else None,
            score=round(score, 2),
        ))
    recs.sort(key=lambda r: r.score, reverse=True)
    return recs[:limit]
