"""Game decision assistant (Phase 3): transparent rules over visible information.
Suggestions are skipped when inputs are missing; uncertain ones are labeled."""
from __future__ import annotations

from app.models import GamePhase, GameState, ItemRecommendation, Priority, Suggestion, Threat

UNCERTAIN = "low (uncertain)"


def suggest(state: GameState, threats: list[Threat], recs: list[ItemRecommendation]) -> list[Suggestion]:
    if state.game_time is None or state.game_time < 0 or state.hero.level is None or state.hero.level < 1:
        return [Suggestion(category="info", confidence=UNCERTAIN,
                           text="Not enough match data for strategic suggestions.",
                           reasons=["in-game time or hero level unavailable"])]
    if state.hero.alive is False:
        return [Suggestion(category="info", confidence="high",
                           text="You are dead. Reassess the map and objectives when you respawn.",
                           reasons=["hero is dead"])]
    out: list[Suggestion] = []
    minutes = state.game_time / 60
    low_hp = state.hero.health_percent is not None and state.hero.health_percent < 35

    # Farm vs fight
    out.append(Suggestion(category="farm_vs_fight", confidence=UNCERTAIN,
                          text="Join only if nearby allies can follow up and key spells are ready. Otherwise use safe farm or reset.",
                          reasons=["team readiness, enemy positions and safe farm are not known"]))

    # Power spike
    affordable = next((r for r in recs if r.priority == Priority.HIGH and r.affordable), None)
    if affordable and state.gold is not None and affordable.remaining_gold is not None:
        follow = "Recover HP first." if low_hp else "Check the fight and your team's readiness before committing."
        needed = state.gold - affordable.remaining_gold
        out.append(Suggestion(category="power_spike", confidence=UNCERTAIN,
                              text=f"You have enough gold for {affordable.item_name}. It may help once delivered. {follow}",
                              reasons=[f"{state.gold} gold covers the {needed} still needed; delivery and fight readiness are unknown"]))
    elif recs and recs[0].remaining_gold is not None:
        gap = -recs[0].remaining_gold
        if 0 < gap <= 800:
            out.append(Suggestion(category="power_spike", confidence=UNCERTAIN,
                                  text=f"{gap} gold away from {recs[0].item_name}. Finish it first if you can farm safely without giving up an objective.",
                                  reasons=["gold gap is known; farm safety and objective urgency are not"]))

    # Aggressive vs defensive
    if low_hp:
        out.append(Suggestion(category="stance", confidence="high", text="Low HP: play defensively and regenerate.",
                              reasons=[f"HP {state.hero.health_percent}%"]))
    elif state.deaths is not None and state.kills is not None and state.assists is not None:
        if state.deaths > state.kills + state.assists / 2 + 2:
            out.append(Suggestion(category="stance", confidence=UNCERTAIN,
                                  text="If you are being picked off, play within reach of teammates or vision.",
                                  reasons=[f"K/D/A {state.kills}/{state.deaths}/{state.assists}; causes of deaths are unknown"]))
        elif state.kills >= state.deaths + 3:
            out.append(Suggestion(category="stance", confidence=UNCERTAIN,
                                  text="Take more space only if your team can back you up and enemy threats are accounted for.",
                                  reasons=[f"K/D/A {state.kills}/{state.deaths}/{state.assists} does not establish a team lead"]))

    # Push / defend
    piercing = [t.hero_name for t in threats if "piercing_disable" in t.tags]
    if piercing:
        out.append(Suggestion(category="team_fight", confidence=UNCERTAIN,
                              text="Don't count on BKB for piercing lockdown. Spread out against area control and check whether the key spell was used before committing.",
                              reasons=[f"lineup threats: {', '.join(piercing)}; enemy cooldowns are unknown"]))

    pushers = [t.hero_name for t in threats if "push" in t.tags or "role_push" in t.tags]
    if pushers:
        out.append(Suggestion(category="push_defend", confidence=UNCERTAIN,
                              text="Watch waves against this lineup. Clear a threatened wave if safe; don't defend an exposed tower alone.",
                              reasons=[f"potential pushers: {', '.join(pushers)}; wave and tower status are unknown"]))
    elif state.phase in (GamePhase.MID, GamePhase.LATE) and affordable:
        out.append(Suggestion(category="push_defend", confidence=UNCERTAIN,
                              text="After your item arrives, consider a tower only if allies and a wave are in position.",
                              reasons=["tower and enemy positions are not available to DotaSense"]))

    # Roshan
    if minutes >= 15 and state.hero.level >= 12:
        out.append(Suggestion(category="roshan", confidence=UNCERTAIN,
                              text="Roshan may be an option after a won fight or with enemy heroes dead.",
                              reasons=["Roshan status and enemy positions are not visible to DotaSense"]))
    return out
