"""Item recommendation engine (Phase 2): rule-based scoring with historical data as a
secondary signal. Popularity alone never produces a recommendation."""
from __future__ import annotations

from app.data import constants as C
from app.models import GamePhase, GameState, ItemRecommendation, Priority, Threat

PHASE_KEY = {GamePhase.PRE_GAME: "laning", GamePhase.LANING: "laning", GamePhase.MID: "mid", GamePhase.LATE: "late"}
NEXT_PHASE = {"laning": "mid", "mid": "late", "late": "late"}
POPULARITY_PHASE = {"laning": "early_game_items", "mid": "mid_game_items", "late": "late_game_items"}


# Items that suit only some hero types (DotaSense heuristics)
RIGHT_CLICK_ITEMS = {"monkey_king_bar", "bloodthorn", "silver_edge", "skadi", "satanic", "butterfly", "mjollnir",
                     "abyssal_blade", "manta", "assault"}
MELEE_ONLY_ITEMS = {"bfury"}
MELEE_PREFERRED_ITEMS = {"abyssal_blade"}
TANK_ITEMS = {"crimson_guard", "blade_mail", "eternal_shroud", "heavens_halberd", "pipe"}
CASTER_DEFENSE_ITEMS = {"cyclone", "aeon_disk"}
SUPPORT_ITEMS = {"glimmer_cape", "pipe", "solar_crest", "crimson_guard", "force_staff", "gem", "ward_sentry", "dust"}
DETECTION_ITEMS = {"dust", "ward_sentry", "gem"}
STANDARD_BOOTS = {"power_treads", "phase_boots", "arcane_boots", "tranquil_boots"}
UPGRADED_BOOTS = STANDARD_BOOTS | {"travel_boots"}
FARMING_ITEMS = {"bfury", "maelstrom"}
LANING_EXPENSIVE_THRESHOLD = 2000


def _fit_weight(item: str, hero: dict) -> float:
    roles = set(hero.get("roles") or [])
    attr = hero.get("primary_attr") or "all"
    is_carry = "Carry" in roles
    is_durable = "Durable" in roles or attr == "str"
    if item in MELEE_ONLY_ITEMS and hero.get("attack_type") != "Melee":
        return 0.0
    if item in MELEE_PREFERRED_ITEMS and hero.get("attack_type") != "Melee":
        return 0.15
    if item == "ghost" and is_carry and attr != "int":
        return 0.15
    if item in TANK_ITEMS and not is_durable:
        return 0.2
    if item in CASTER_DEFENSE_ITEMS and is_carry and attr == "agi":
        return 0.35
    if item in RIGHT_CLICK_ITEMS and not is_carry:
        return 0.3
    if item in SUPPORT_ITEMS and is_carry and "Support" not in roles and item not in DETECTION_ITEMS:
        return 0.35
    return 1.0


def _owned_or_upgraded(item: str, owned: set[str]) -> bool:
    if item in owned:
        return True
    if item in STANDARD_BOOTS and owned & UPGRADED_BOOTS:
        return True
    if item in FARMING_ITEMS and owned & FARMING_ITEMS:
        return True
    return any(up in owned for up in C.UPGRADES.get(item, []))


def _gold_needed_with_components(item: str, inventory: list[str]) -> tuple[int | None, list[str]]:
    """Gold still needed for an item (counting nested components in inventory), plus matched component names."""
    if C.item_cost(item) is None:
        return None, []
    spare = list(inventory)
    used_components: list[str] = []

    def needed(key: str, top: bool = False) -> int:
        if not top and key in spare:
            spare.remove(key)
            used_components.append(C.item_display(key))
            return 0
        cost = C.item_cost(key) or 0
        components = [c for c in C.items().get(key, {}).get("components") or [] if c]
        recipe = cost - sum(C.item_cost(c) or 0 for c in components)
        return max(recipe, 0) + sum(needed(c) for c in components) if components else cost

    return needed(item, top=True), used_components


def _gold_needed(item: str, inventory: list[str]) -> int | None:
    """Gold still needed for an item, counting (nested) components already in the inventory."""
    needed, _ = _gold_needed_with_components(item, inventory)
    return needed


def _popularity_share(popularity: dict | None, phase_key: str, item: str) -> float | None:
    if not popularity:
        return None
    bucket = popularity.get(POPULARITY_PHASE[phase_key]) or {}
    total = sum(bucket.values())
    item_id = C.items().get(item, {}).get("id")
    if not total or item_id is None:
        return None
    return bucket.get(str(item_id), 0) / total


def _pick_alternative(item: str, counters: dict[str, list[str]], owned: set[str], hero: dict, *,
                      targeted_lockdown: bool) -> str | None:
    def valid(a: str) -> bool:
        if item == "black_king_bar" and a == "sphere" and not targeted_lockdown:
            return False
        return a != item and a in C.items() and not _owned_or_upgraded(a, owned) and _fit_weight(a, hero) >= 0.5

    alts = C.alternatives(item, counters)
    if counters:
        same_threat = list(dict.fromkeys(
            ci for tag in counters for ci, _, _ in C.COUNTER_ITEMS.get(tag, []) if ci != item
        ))
        same_threat_set = set(same_threat)
        match = next((a for a in alts if a in same_threat_set and valid(a)), None)
        if match:
            return match
        match = next((a for a in same_threat if valid(a)), None)
        if match:
            return match
    return next((a for a in alts if valid(a)), None)


def recommend_items(state: GameState, threats: list[Threat], *, popularity: dict | None = None,
                    limit: int = 5) -> list[ItemRecommendation]:
    hero = C.heroes_by_name().get(C.hero_short(state.hero.name) or "")
    if hero is None:
        return []
    owned = set(state.items)
    phase_key = PHASE_KEY[state.phase]
    attr = hero.get("primary_attr") or "all"
    attr_label = C.ATTR_LABELS.get(attr, attr)
    build = C.CORE_BUILD.get(attr, C.CORE_BUILD["all"])
    targeted_lockdown = any("targeted_disable" in threat.tags for threat in threats)

    candidates: dict[str, dict] = {}

    def add(item: str, score: float, reason: str, benefit: str) -> None:
        if item not in C.items() or _owned_or_upgraded(item, owned):
            return
        weight = _fit_weight(item, hero)
        if weight == 0.0:
            return
        resolved_benefit = C.ITEM_BENEFITS.get(item) or benefit
        c = candidates.setdefault(item, {"score": 0.0, "reasons": [], "counters": {}, "benefit": resolved_benefit})
        c["score"] += score * weight
        c["reasons"].append(reason)

    core_score = 1.4 if phase_key == "laning" else 1.0
    for item in build[phase_key]:
        add(item, core_score, f"Core item for {hero['localized_name']} ({attr_label}) in the {phase_key} phase",
            "Completes your core build and power spike for this phase.")
    for item in build[NEXT_PHASE[phase_key]]:
        if phase_key != "late":
            add(item, 0.4, f"Plan ahead: core for the {NEXT_PHASE[phase_key]} phase",
                "Prepares the next power spike.")

    for threat in threats:
        scored_items = set()
        for tag in threat.tags:
            for item, why, _ in C.COUNTER_ITEMS.get(tag, []):
                if item not in scored_items:
                    scored_items.add(item)
                    item_cost = C.item_cost(item) or 0
                    phase_scale = 0.35 if (phase_key == "laning" and item_cost >= LANING_EXPENSIVE_THRESHOLD) else 1.0
                    if phase_key == "laning" and item == "gem":
                        phase_scale = 0.35
                    add(item, 0.35 * threat.severity * phase_scale, "", why)
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
            if share >= 0.01:
                reasons.append(f"{share:.0%} of recent {phase_key}-phase purchases on this hero (OpenDota)")
        cost = C.item_cost(item)
        alt = _pick_alternative(item, c["counters"], owned, hero, targeted_lockdown=targeted_lockdown)
        needed, owned_comps = _gold_needed_with_components(item, state.items)
        counter_hits = sum(len(h) for h in c["counters"].values())
        if phase_key == "laning":
            is_high = score >= 1.4
        else:
            is_high = score >= 1.6 or (counter_hits >= 2 and score >= 1.35)
        priority = Priority.HIGH if is_high else Priority.SITUATIONAL
        recs.append(ItemRecommendation(
            item=item, item_name=C.item_display(item), cost=cost,
            upgrade_cost=needed if owned_comps else None,
            owned_components=owned_comps,
            priority=priority,
            reason="; ".join(reasons), benefit=c["benefit"],
            alternative=alt, alternative_name=C.item_display(alt) if alt else None,
            remaining_gold=(state.gold - needed) if (state.gold is not None and needed is not None) else None,
            affordable=(state.gold >= needed) if (state.gold is not None and needed is not None) else None,
            score=round(score, 2),
        ))
    recs.sort(key=lambda r: (r.score, r.item == "dust", -(r.cost or 0)), reverse=True)
    # Keep at most one invisibility detection item (others are already shown as alternatives).
    filtered: list[ItemRecommendation] = []
    seen_detection = False
    for r in recs:
        if r.item in DETECTION_ITEMS:
            if seen_detection:
                continue
            seen_detection = True
        filtered.append(r)
        if len(filtered) >= limit:
            break
    return filtered
