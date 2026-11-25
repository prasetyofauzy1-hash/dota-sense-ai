"""Counter intelligence: threat analysis of the visible enemy lineup (Phase 3)."""
from __future__ import annotations

from app.data import constants as C
from app.engine.item_recommender import _fit_weight, _owned_or_upgraded
from app.models import CounterItem, Threat


def hero_tags(hero: str) -> tuple[list[str], str]:
    """Threat tags for a hero (short name), from curated table or OpenDota roles."""
    short = C.hero_short(hero) or ""
    if short in C.CURATED_HERO_THREATS:
        return C.CURATED_HERO_THREATS[short], "curated"
    info = C.heroes_by_name().get(short)
    roles = info.get("roles", []) if info else []
    tags = [C.ROLE_THREATS[r] for r in roles if r in C.ROLE_THREATS]
    return list(dict.fromkeys(tags)), "roles"


def hero_abilities(hero: str) -> list[str]:
    """Display names of a hero's abilities (from the OpenDota constants snapshot)."""
    from app.data.opendota import _load_snapshot

    full = f"{C.HERO_PREFIX}{C.hero_short(hero)}"
    raw = _load_snapshot("hero_abilities").get(full, {}).get("abilities", [])
    prefix = f"{C.hero_short(hero)}_"
    names = [a for a in raw if a and a != "generic_hidden"]
    return [a.removeprefix(prefix).replace("_", " ").title() for a in names]


def analyze_threats(enemy_heroes: list[str], *, my_hero_id: int | None = None,
                    matchups: list[dict] | None = None) -> list[Threat]:
    """Rank enemy heroes by threat. `matchups` is OpenDota /heroes/{id}/matchups for
    the player's hero; when given, a low historical win rate raises severity."""
    winrates: dict[int, tuple[float, int]] = {}
    for m in matchups or []:
        if m.get("games_played"):
            winrates[m["hero_id"]] = (m["wins"] / m["games_played"], m["games_played"])

    threats: list[Threat] = []
    seen = set()
    for enemy in enemy_heroes:
        short = C.hero_short(enemy)
        if short not in C.heroes_by_name() or short in seen:
            continue
        seen.add(short)
        info = C.heroes_by_name()[short]
        tags, source = hero_tags(short)
        severity = 1.0 + (0.5 if source == "curated" else 0.25) * len(tags)
        parts = [", ".join(C.THREAT_LABELS[t] for t in tags) or "No mechanic identified from roles"]
        if info["id"] in winrates:
            wr, games = winrates[info["id"]]
            if games >= 20:
                severity += max(0.0, (0.5 - wr) * 10)
                parts.append(f"your hero won {wr:.0%} of {games} recent public games against it (OpenDota)")
        threats.append(Threat(
            hero=short, hero_name=info["localized_name"], tags=tags,
            severity=round(severity, 2), explanation="; ".join(parts), tags_source=source,
        ))
    return sorted(threats, key=lambda t: t.severity, reverse=True)


def counter_items(threats: list[Threat], owned: list[str] | None = None,
                  my_hero: str | None = None) -> list[CounterItem]:
    owned_set = set(owned or [])
    hero = C.heroes_by_name().get(C.hero_short(my_hero) or "")
    merged: dict[str, CounterItem] = {}
    options: dict[str, list[str]] = {}
    reasons: dict[str, dict[str, str]] = {}
    coverage: dict[str, dict[str, float]] = {}
    for threat in threats:
        for tag in threat.tags:
            for item, why, defensive in C.COUNTER_ITEMS.get(tag, []):
                if item not in C.items() or _owned_or_upgraded(item, owned_set):
                    continue
                if hero and _fit_weight(item, hero) == 0.0:
                    continue
                entry = merged.get(item)
                if entry is None:
                    entry = merged[item] = CounterItem(
                        item=item, item_name=C.item_display(item), counters=[], against_heroes=[],
                        explanation="", defensive=defensive,
                    )
                if C.THREAT_LABELS[tag] not in entry.counters:
                    entry.counters.append(C.THREAT_LABELS[tag])
                    options.setdefault(tag, []).append(item)
                    reasons.setdefault(item, {})[tag] = why
                if threat.hero_name not in entry.against_heroes:
                    entry.against_heroes.append(threat.hero_name)
                    coverage.setdefault(item, {})[threat.hero] = threat.severity

    for item, entry in merged.items():
        entry.explanation = " ".join(dict.fromkeys(reasons[item].values()))

    focus = dict.fromkeys((*C.COUNTER_FOCUS, *options))
    first = dict.fromkeys(options[tag][0] for tag in focus if tag in options)
    rest = sorted(merged.keys() - first.keys(),
                  key=lambda item: (-sum(coverage[item].values()), -len(reasons[item]), item))
    return [merged[item] for item in (*first, *rest)]
