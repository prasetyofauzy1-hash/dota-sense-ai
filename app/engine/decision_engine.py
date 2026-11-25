"""Game decision assistant (Phase 3): transparent rules over visible information.
Suggestions are skipped when inputs are missing; uncertain ones are labeled."""
from __future__ import annotations

from app.data import constants as C
from app.models import GamePhase, GameState, ItemRecommendation, Suggestion, Threat

MAJOR_ITEM_COST = 2000
UNCERTAIN = "low (uncertain)"


def suggest(state: GameState, threats: list[Threat], recs: list[ItemRecommendation]) -> list[Suggestion]:
    if state.game_time is None or state.hero.level is None:
        return [Suggestion(category="info", confidence=UNCERTAIN,
                           text="Not enough match data for strategic suggestions.",
                           reasons=["game time or hero level unavailable"])]
    out: list[Suggestion] = []
    minutes = state.game_time / 60
    major_items = [i for i in state.items if (C.item_cost(i) or 0) >= MAJOR_ITEM_COST]
    expected = max(0, int((minutes - 8) // 8))

    # Farm vs fight
    if len(major_items) < expected:
        out.append(Suggestion(category="farm_vs_fight", confidence="medium",
                              text="Prioritise farming safe lanes/jungle before taking fights.",
                              reasons=[f"{len(major_items)} major item(s) at {minutes:.0f} min, ~{expected} expected"]))
    else:
        out.append(Suggestion(category="farm_vs_fight", confidence="medium",
                              text="Your items are on time: join fights and objectives with your team.",
                              reasons=[f"{len(major_items)} major item(s) at {minutes:.0f} min"]))

    # Power spike
    affordable = [r for r in recs if r.affordable and r.priority.value == "high"]
    if affordable:
        r = affordable[0]
        low_hp = state.hero.health_percent is not None and state.hero.health_percent < 35
        follow = "Heal up first, then look for a fight." if low_hp else "Consider fighting right after."
        out.append(Suggestion(category="power_spike", confidence="high",
                              text=f"You can buy {r.item_name} now — a power spike. {follow}",
                              reasons=[f"gold {state.gold} covers what is left to buy ({r.cost} total)"]))
    elif recs and recs[0].remaining_gold is not None:
        gap = -recs[0].remaining_gold
        if 0 < gap <= 800:
            out.append(Suggestion(category="power_spike", confidence="medium",
                                  text=f"{gap} gold away from {recs[0].item_name}: farm a little before committing.",
                                  reasons=["next high-value item is close"]))

    # Aggressive vs defensive
    if state.hero.health_percent is not None and state.hero.health_percent < 35:
        out.append(Suggestion(category="stance", confidence="high", text="Low HP: play defensively and regenerate.",
                              reasons=[f"HP {state.hero.health_percent}%"]))
    elif state.deaths is not None and state.kills is not None:
        if state.deaths > state.kills + (state.assists or 0) / 2 + 2:
            out.append(Suggestion(category="stance", confidence="medium",
                                  text="You are dying often: play closer to your team and buy defensive items.",
                                  reasons=[f"K/D/A {state.kills}/{state.deaths}/{state.assists}"]))
        elif state.kills >= state.deaths + 3:
            out.append(Suggestion(category="stance", confidence="medium",
                                  text="You are ahead: play aggressively and take map control.",
                                  reasons=[f"K/D/A {state.kills}/{state.deaths}/{state.assists}"]))

    # Push / defend
    pushers = [t.hero_name for t in threats if "push" in t.tags]
    if pushers:
        out.append(Suggestion(category="push_defend", confidence="medium",
                              text="Enemy has strong pushers: keep waves pushed out and defend towers early.",
                              reasons=[f"pushers: {', '.join(pushers)}"]))
    elif state.phase in (GamePhase.MID, GamePhase.LATE) and affordable:
        out.append(Suggestion(category="push_defend", confidence=UNCERTAIN,
                              text="After your power spike, pushing a tower with your team may be good.",
                              reasons=["tower and enemy positions are not available to DotaSense"]))

    # Roshan
    if minutes >= 15 and state.hero.level >= 12:
        out.append(Suggestion(category="roshan", confidence=UNCERTAIN,
                              text="Roshan may be an option after a won fight or with enemy heroes dead.",
                              reasons=["Roshan status and enemy positions are not visible to DotaSense"]))
    return out
