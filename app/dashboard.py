"""Streamlit dashboard: `streamlit run app/dashboard.py`."""
from __future__ import annotations

import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.config import settings  # noqa: E402
from app.data import constants as C  # noqa: E402
from app.data.opendota import OpenDotaClient, OpenDotaError, snapshot_meta  # noqa: E402
from app.database import models as db  # noqa: E402
from app.database.connection import connect  # noqa: E402
from app.engine.coach import coach_match  # noqa: E402
from app.gsi.provider import LiveGSIProvider, MockProvider  # noqa: E402
from app.models import GameState, ItemRecommendation, Priority, Threat  # noqa: E402
from app.services import analyze  # noqa: E402

st.set_page_config(page_title="DotaSense AI", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
.block-container {padding-top:4rem;max-width:88rem;}
.ds-card {background:#1a1f2b;border:1px solid #333c50;border-radius:10px;padding:12px 14px;overflow-wrap:anywhere;}
.ds-high {border-left:5px solid #e8473c;}
.ds-sit {border-left:5px solid #f2b134;}
.ds-missing {color:#c4cad6;font-style:italic;}
.ds-badge {display:inline-block;padding:2px 8px;border-radius:6px;font-size:.8rem;font-weight:700;margin-right:6px;}
.ds-b-high {background:#e8473c33;color:#ff8077;}
.ds-b-sit {background:#f2b13433;color:#f7c25d;}
.ds-b-unc {background:#6b728033;color:#b8bfcc;}
.ds-b-missing {background:#ab88ff26;color:#dccaff;}
.ds-status,.ds-metrics,.ds-inventory {display:flex;flex-wrap:wrap;gap:.5rem;}
.ds-status {align-items:center;gap:.5rem .75rem;}
.ds-status .ds-badge {margin:0;}
.ds-metrics {margin:.75rem 0 0;}
.ds-metrics > div {flex:1 1 6rem;min-width:0;background:#111722;border-radius:6px;padding:.45rem .65rem;}
.ds-metrics > .ds-hero {flex-basis:8rem;}
.ds-metrics dt,.ds-secondary {font-size:.875rem;color:#c4cad6;}
.ds-metrics dd {margin:0;font-size:1.125rem;font-weight:700;}
.ds-metrics .ds-clock dd {font-size:1.5rem;line-height:1.2;font-variant-numeric:tabular-nums;}
.ds-glance {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,23rem),1fr));gap:.75rem;margin-block:.75rem;}
.ds-glance h3 {font-size:1rem;color:#c4cad6;padding:0;margin:0 0 .45rem;}
.ds-item-name {display:block;font-size:1.65rem;line-height:1.15;margin:.45rem 0;}
.ds-glance ul {list-style:none;padding:0;margin:0;}
.ds-glance li {margin:0;padding:.25rem 0;}
.ds-glance li + li {border-top:1px solid #333c50;}
.ds-inventory > div {flex:1 1 8rem;min-width:0;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def resources():
    conn = connect()
    return conn, OpenDotaClient(conn)


conn, client = resources()
mock = MockProvider()
MISSING = "<span class='ds-missing'>not available</span>"


def val(v, suffix: str = "") -> str:
    return MISSING if v is None else f"{v}{suffix}"


def fmt_time(seconds: int | None) -> str:
    if seconds is None:
        return MISSING
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    return f"{sign}{seconds // 60}:{seconds % 60:02d}"


def item_priority(rec: ItemRecommendation) -> tuple[str, str, str]:
    return {
        Priority.HIGH: ("ds-high", "ds-b-high", "High priority"),
        Priority.SITUATIONAL: ("ds-sit", "ds-b-sit", "Situational"),
        Priority.LOW: ("", "ds-b-unc", "Low priority"),
    }[rec.priority]


def item_budget(rec: ItemRecommendation) -> str:
    if rec.affordable:
        return f"Affordable now · {rec.remaining_gold:,} gold left"
    if rec.remaining_gold is not None:
        return f"Need {-rec.remaining_gold:,} more gold"
    return "Gold not available"


def render_glance(state: GameState, hero_name: str, phase: str, live_status: str, history_status: str,
                  recommendations: list[ItemRecommendation], threats: list[Threat]) -> None:
    scenario = escape((state.scenario_name or "").removeprefix("MOCK: "))
    source = ("<span class='ds-badge ds-b-sit'>MOCK DATA</span>"
              f"<span>{scenario or 'Practice scenario'} · Not a real match</span>"
              if state.is_mock else "<span class='ds-badge ds-b-unc'>No mock data</span>")
    metrics = [
        ("Game time", fmt_time(state.game_time), "ds-clock"),
        ("Match", "Active" if state.match_active else "Not detected", ""),
        ("Phase", phase.replace("_", " ").title() if state.game_time is not None else MISSING, ""),
        ("Hero", escape(hero_name) if state.hero.name else MISSING, "ds-hero"),
        ("Gold", f"{state.gold:,}" if state.gold is not None else MISSING, ""),
    ]
    metric_html = "".join(
        f"<div class='{cls}'><dt>{label}</dt><dd>{value}</dd></div>" for label, value, cls in metrics
    )
    st.markdown(
        f"<div class='ds-card'><div class='ds-status'>{source}"
        f"<span class='ds-badge ds-b-unc'>Live GSI: {live_status}</span>"
        f"<span class='ds-badge ds-b-unc'>{history_status}</span></div>"
        f"<dl class='ds-metrics'>{metric_html}</dl></div>", unsafe_allow_html=True)

    if state.missing_fields:
        labels = {"enemy_heroes": "enemy lineup", "items": "inventory"}
        missing = ", ".join(labels.get(field, field.replace("_", " ")) for field in state.missing_fields)
        st.markdown(f"<span class='ds-badge ds-b-missing'>Missing data:</span> {escape(missing)}",
                    unsafe_allow_html=True)

    card_class = ""
    next_item = "<span class='ds-missing'>No recommendation available</span>"
    if recommendations:
        top = recommendations[0]
        card_class, badge_class, label = item_priority(top)
        price = f"{top.cost:,} gold" if top.cost is not None else "Cost not available"
        next_item = (f"<span class='ds-badge {badge_class}'>{label}</span>"
                     f"<strong class='ds-item-name'>{escape(top.item_name)}</strong>"
                     f"<span class='ds-secondary'>{price}</span><br><strong>{item_budget(top)}</strong>")
    if threats:
        rows = []
        for threat in threats[:2]:
            tags = ", ".join(C.THREAT_LABELS[tag] for tag in threat.tags) or "No known threat tags"
            rows.append(f"<li><strong>{escape(threat.hero_name)}</strong><br>"
                        f"<span class='ds-secondary'>{escape(tags)}</span></li>")
        top_threats = f"<ul>{''.join(rows)}</ul>"
    else:
        top_threats = ("<strong>Enemy lineup not available</strong><br>"
                       "<span class='ds-secondary'>Add visible enemies in the sidebar to see threats.</span>")
    st.markdown(f"<div class='ds-glance'>"
                f"<section class='ds-card {card_class}'><h3>Top item recommendation</h3>{next_item}</section>"
                f"<section class='ds-card'><h3>Top enemy threats</h3>{top_threats}</section>"
                f"</div>", unsafe_allow_html=True)


# ---------------- Sidebar ----------------
with st.sidebar:
    st.title("🛡️ DotaSense AI")
    st.caption("Read-only Dota 2 companion · no automation · no game modification")
    live = LiveGSIProvider().status()
    st.caption(live["detail"])
    st.divider()
    names = mock.scenario_names()
    scenario = st.selectbox("Mock scenario", names, format_func=lambda n: mock.load(n)["dotasense_mock"]["scenario_name"])
    state = MockProvider(scenario=scenario).current_state()
    hero_options = sorted(C.heroes_by_name(), key=lambda h: C.hero_display(h))
    enemies = st.multiselect("Visible enemy lineup (edit as on the scoreboard)", hero_options,
                             default=[e for e in state.enemy_heroes if e in hero_options],
                             format_func=C.hero_display, max_selections=5)
    state.enemy_heroes = enemies
    if not enemies and "enemy_heroes" not in state.missing_fields:
        state.missing_fields.append("enemy_heroes")
    use_history = st.toggle("Use OpenDota historical data", value=not settings.offline,
                            help="Recent public-match item stats and matchups. Off = rules only.")
    st.divider()
    meta = snapshot_meta()
    st.caption(f"Hero/item constants: OpenDota snapshot {meta['fetched_at'][:10]}")

result = analyze(state, conn, client, use_history=use_history)

tab_live, tab_post = st.tabs(["Live Match", "Post-Match Reports"])

with tab_live:
    st.subheader("Match at a glance")
    live_status = ("Disabled" if not settings.live_integration_enabled else
                   "Connected" if live["connected"] else "Waiting for data")
    history_status = "History-backed" if result["used_history"] else "Rules only"
    render_glance(state, result["hero_name"], result["phase"], live_status, history_status,
                  result["recommendations"], result["threats"])

    with st.expander("Item recommendation details"):
        for note in result["notes"]:
            st.caption(note)
        if not result["recommendations"]:
            st.markdown(MISSING + " — no recommendations", unsafe_allow_html=True)
        for r in result["recommendations"]:
            card_class, badge_class, label = item_priority(r)
            alt = f"<br><b>Alternative:</b> {escape(r.alternative_name)}" if r.alternative_name else ""
            st.markdown(
                f"<div class='ds-card {card_class}'><span class='ds-badge {badge_class}'>{label}</span>"
                f"<b>{escape(r.item_name)}</b> <small>({val(r.cost)} gold)</small><br><b>Why:</b> {escape(r.reason)}<br>"
                f"<b>Benefit:</b> {escape(r.benefit)}{alt}<br><small>{item_budget(r)} · score {r.score}</small></div>",
                unsafe_allow_html=True)

    with st.expander("Enemy threat and counter details"):
        if not result["threats"]:
            st.markdown(MISSING + " — add the visible enemy lineup in the sidebar", unsafe_allow_html=True)
        else:
            tcol, ccol = st.columns([1, 1])
            with tcol:
                st.markdown("**Biggest threats**")
                for t in result["threats"]:
                    abil = ", ".join(result["enemy_abilities"].get(t.hero_name, [])[:4])
                    src = "curated tags" if t.tags_source == "curated" else "inferred from OpenDota roles"
                    st.markdown(f"<div class='ds-card'><b>{escape(t.hero_name)}</b> "
                                f"<small>severity {t.severity}</small><br>{escape(t.explanation)}<br>"
                                f"<small>Abilities: {escape(abil or 'n/a')} · {src}</small></div>", unsafe_allow_html=True)
            with ccol:
                st.markdown("**Counter items**")
                for ci in result["counters"][:8]:
                    kind = "Defensive" if ci.defensive else "Offensive"
                    st.markdown(f"<div class='ds-card'><b>{escape(ci.item_name)}</b> <small>{kind}</small><br>"
                                f"{escape(ci.explanation)}<br><small>Against: {escape(', '.join(ci.against_heroes))} · "
                                f"Counters: {escape(', '.join(ci.counters))}</small></div>", unsafe_allow_html=True)

    with st.expander("Hero, inventory and match stats"):
        st.markdown(
            f"<div class='ds-card'><b>{escape(result['hero_name'])}</b><br>"
            f"Level {val(state.hero.level)} · HP {val(state.hero.health_percent, '%')} · "
            f"Mana {val(state.hero.mana_percent, '%')}<br>"
            f"GPM / XPM: {val(state.gpm)} / {val(state.xpm)} · "
            f"K / D / A: {val(state.kills)} / {val(state.deaths)} / {val(state.assists)}</div>", unsafe_allow_html=True)
        st.markdown("**Abilities**")
        if state.abilities:
            st.dataframe(pd.DataFrame([{
                "Ability": a.name.split("_", 1)[-1].replace("_", " ").title(),
                "Level": a.level,
                "Cooldown": "Ready" if not a.cooldown else f"{a.cooldown:.0f}s",
                "Ultimate": "★" if a.ultimate else "",
            } for a in state.abilities]), hide_index=True)
        else:
            st.markdown(MISSING, unsafe_allow_html=True)
        st.markdown("**Current inventory**")
        if state.items:
            inventory = "".join(f"<div class='ds-card'>{escape(C.item_display(item))}<br>"
                                f"<small>{val(C.item_cost(item))} gold</small></div>" for item in state.items)
            st.markdown(f"<div class='ds-inventory'>{inventory}</div>", unsafe_allow_html=True)
        else:
            st.markdown(MISSING, unsafe_allow_html=True)

    st.subheader("Strategic suggestions")
    for s in result["suggestions"]:
        cls = "ds-b-high" if s.confidence == "high" else "ds-b-sit" if s.confidence == "medium" else "ds-b-unc"
        label = "UNCERTAIN" if "uncertain" in s.confidence else f"{s.confidence.upper()} CONFIDENCE"
        st.markdown(f"<div class='ds-card'><span class='ds-badge {cls}'>{label}</span>"
                    f"<b>{s.category.replace('_', ' ').title()}</b>: {s.text}<br>"
                    f"<small>Based on: {'; '.join(s.reasons)}</small></div>", unsafe_allow_html=True)

with tab_post:
    # 7. Post-Match Reports
    st.subheader("7 · Post-Match Reports")
    st.caption("Fetches a real public match from OpenDota. Match details must be public on your Dota 2 profile.")
    with st.form("coach"):
        m1, m2 = st.columns(2)
        match_id = m1.text_input("Match ID")
        account_id = m2.text_input("Your Steam32 account ID (optional if you pick a hero)")
        hero_pick = st.selectbox("…or your hero in that match", ["—"] + hero_options, format_func=lambda h: h if h == "—" else C.hero_display(h))
        submitted = st.form_submit_button("Analyse match")
    if submitted:
        hero_id = C.heroes_by_name()[hero_pick]["id"] if hero_pick != "—" else None
        if not match_id.strip().isdigit():
            st.error("Enter a numeric match ID.")
        elif not account_id.strip() and hero_id is None:
            st.error("Enter your account ID or pick your hero.")
        else:
            try:
                report = coach_match(client, int(match_id), account_id=int(account_id) if account_id.strip() else None,
                                     hero_id=hero_id)
                db.save_report(conn, report)
                st.success(f"Report saved for match {report['match_id']}")
            except (OpenDotaError, ValueError) as exc:
                st.error(str(exc))
    for rep in db.list_reports(conn):
        with st.expander(f"Match {rep['match_id']} · {rep['hero']} · {rep['result']} · {rep['duration_min']} min"):
            c = st.columns(4)
            c[0].metric("K/D/A", rep["kda"])
            c[1].metric("GPM", rep["gpm"])
            c[2].metric("XPM", rep["xpm"])
            c[3].metric("Last hits", rep["last_hits"])
            st.markdown("**Final items:** " + (", ".join(rep["final_items"]) or "n/a"))
            if rep["item_timings"]:
                st.dataframe(pd.DataFrame(rep["item_timings"])[["item_name", "minute", "cost"]], hide_index=True)
            else:
                st.markdown(MISSING + " (item timings need a parsed match)", unsafe_allow_html=True)
            if rep["benchmarks_pct"]:
                st.markdown("**Percentile vs players on this hero (OpenDota benchmarks):** " +
                            ", ".join(f"{k.replace('_', ' ')} {v}%" for k, v in rep["benchmarks_pct"].items()))
            st.markdown("**Suggestions**")
            for s in rep["suggestions"]:
                st.markdown(f"- {s}")
