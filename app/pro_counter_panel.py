"""Pro tournament evidence for existing counter rules and custom hero–item comparisons."""
from __future__ import annotations

from collections import Counter

import streamlit as st

from app.data import constants as C
from app.data.pro_matches import MIN_ITEM_GROUP, Record, compare_item, load_pro_matches, win_record
from app.engine.counter_analyzer import analyze_threats, counter_items
from app.models import GameState


def _record_text(record: Record) -> str:
    return f"{record.rate:.1%} ({record.wins}/{record.games} wins)" if record.rate is not None else "No games"


def _item_labels(items: set[str]) -> dict[str, str]:
    names = {item: C.item_display(item) for item in items}
    counts = Counter(names.values())
    catalog = C.items()
    return {item: f"{name} (item ID {catalog[item]['id']})" if counts[name] > 1 else name
            for item, name in names.items()}


def render_pro_counter_panel(state: GameState, hero_options: list[str]) -> None:
    st.subheader("Pro tournament counter items")
    try:
        sample = load_pro_matches()
    except (OSError, EOFError, ValueError):
        st.warning("The bundled pro tournament sample is unavailable. Live counter rules still work.")
        return

    st.caption(
        f"[OpenDota Explorer](https://docs.opendota.com/#tag/explorer) · "
        f"{sample.match_count:,} completed matches across {len(sample.league_counts)} selected pro tournaments · "
        f"{sample.start:%d %b %Y} to {sample.end:%d %b %Y} (UTC)."
    )
    live_hero = C.hero_short(state.hero.name)
    matchup, opponent, item_choice = st.columns(3)
    hero = matchup.selectbox(
        "Your hero", hero_options,
        index=hero_options.index(live_hero) if live_hero in hero_options else None,
        placeholder="Choose a hero", format_func=C.hero_display, key=f"pro-hero-{live_hero}",
    )
    if hero is None:
        st.info("Choose a hero to see tournament results, then pick an enemy for counter-item evidence.")
    else:
        heroes = C.heroes_by_name()
        hero_id = heroes[hero]["id"]
        visible = [h for h in state.enemy_heroes if h in heroes and h != hero]
        visible.sort(key=lambda h: len(sample.for_hero(hero_id, heroes[h]["id"])), reverse=True)
        enemies = [None, *dict.fromkeys((*visible, *(h for h in hero_options if h != hero)))]
        enemy = opponent.selectbox(
            "Enemy hero", enemies, index=1 if hero == live_hero and visible else 0,
            format_func=lambda h: C.hero_display(h) if h else "All opponents",
            key=f"pro-enemy-{hero}-{','.join(visible)}",
        )
        item_catalog = C.items()
        shop_items = {
            name for name, data in item_catalog.items()
            if (data.get("cost") or 0) > 0 and not (data.get("qual") or "").startswith("consumable")
        }
        rules = {entry.item: entry for entry in counter_items(analyze_threats([enemy]), my_hero=hero)
                 if entry.item in shop_items} if enemy else {}
        labels = _item_labels(shop_items)
        items = [*rules, *sorted(shop_items - rules.keys(), key=labels.__getitem__)]
        selected = item_choice.selectbox(
            "Inspect an item", items, index=0 if rules else None,
            placeholder="Choose an item (e.g. Radiance)", format_func=labels.__getitem__,
            key=f"pro-item-{hero}-{enemy}",
        )
        enemy_id = heroes[enemy]["id"] if enemy else None
        games = sample.for_hero(hero_id, enemy_id)
        scope = f"against {C.hero_display(enemy)}" if enemy else "across all opponents"
        st.markdown(f"**{C.hero_display(hero)} {scope}:** {_record_text(win_record(games))}")
        if not games:
            st.info("No matches for this selection. Try All opponents for the hero’s overall record.")
        elif selected:
            if selected in rules:
                st.caption(f"Why counter rules suggest {labels[selected]}: {rules[selected].explanation}")
            else:
                st.caption("Custom item comparison · not a rules-based counter recommendation.")
            rows = []
            for item in dict.fromkeys((selected, *rules)):
                comparison = compare_item(games, item_catalog[item]["id"])
                gap = comparison.gap_pp
                rows.append({
                    "Item": labels[item],
                    "With item": _record_text(comparison.with_item),
                    "Without item": _record_text(comparison.without_item),
                    "Difference": f"{gap:+.1f} pp" if gap is not None else "Small sample",
                })
            st.dataframe(rows, hide_index=True, width="stretch")
            st.caption(
                "Difference = win rate with item minus without it, in percentage points (pp). "
                f"Hidden unless both groups have at least {MIN_ITEM_GROUP} matches. "
                "Final inventory only (including backpack): this does not show purchases or timing. "
                "Patch, role, lineup and being ahead can affect who finishes an item. "
                "These are observed results, not expected gains; they don’t change the counter rules."
            )

            item_id = item_catalog[selected]["id"]
            with st.expander(f"Example matches for {labels[selected]}"):
                with_col, without_col = st.columns(2)
                for column, present in ((with_col, True), (without_col, False)):
                    column.markdown("**With item**" if present else "**Without item**")
                    examples = [game for game in reversed(games) if (item_id in game.item_ids) == present][:3]
                    for game in examples:
                        outcome = "Win" if game.won else "Loss"
                        column.caption(f"[{game.match_id}](https://www.opendota.com/matches/{game.match_id}) · "
                                       f"{sample.league_names[game.league_id]} · {outcome}")
                    if not examples:
                        column.caption("No matches in this group.")
        else:
            st.info("Pick an item to compare the hero’s results with and without it.")

    with st.expander("Tournaments in this sample"):
        st.caption("Selected main events only. Public matches and qualifiers are not included.")
        for identifier, name in sample.league_names.items():
            st.markdown(f"- [{name}](https://www.opendota.com/leagues/{identifier}) · "
                        f"{sample.league_counts[identifier]:,} matches")
