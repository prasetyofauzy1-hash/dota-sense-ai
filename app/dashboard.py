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
from app.data.opendota import OpenDotaClient, OpenDotaError, parse_match_id, snapshot_meta  # noqa: E402
from app.database import models as db  # noqa: E402
from app.database.connection import connect  # noqa: E402
from app.engine.coach import coach_match, parse_account_id  # noqa: E402
from app.gsi.provider import MockProvider  # noqa: E402
from app.models import DataSource, GameState, ItemRecommendation, Priority, Threat  # noqa: E402
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
.ds-b-ok {background:#2ecc7133;color:#5be08f;}
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


def item_price(rec: ItemRecommendation) -> str:
    if rec.cost is None:
        return "Cost not available"
    if rec.owned_components and rec.upgrade_cost is not None:
        components = escape(", ".join(rec.owned_components))
        return f"{rec.cost:,} gold · {rec.upgrade_cost:,} gold to finish (have {components})"
    return f"{rec.cost:,} gold"


def buy_now_badge(rec: ItemRecommendation) -> str:
    return "<span class='ds-badge ds-b-ok'>Buy now</span>" if rec.affordable else ""


def item_budget(rec: ItemRecommendation) -> str:
    if rec.affordable:
        return f"Affordable now · {rec.remaining_gold:,} gold left"
    if rec.remaining_gold is not None:
        return f"Need {-rec.remaining_gold:,} more gold"
    return "Gold not available"


def live_gsi_status(state: GameState) -> str:
    if not settings.live_integration_enabled:
        return "Off"
    if state.is_mock:
        return "On · mock view"
    if state.source == DataSource.LIVE_GSI:
        return "Receiving data"
    return "Waiting for game"


def render_glance(state: GameState, hero_name: str, phase: str, live_status: str, history_status: str,
                  recommendations: list[ItemRecommendation], threats: list[Threat]) -> None:
    if state.is_mock:
        scenario = escape((state.scenario_name or "").removeprefix("MOCK: "))
        source = ("<span class='ds-badge ds-b-sit'>MOCK DATA</span>"
                  f"<span>{scenario or 'Practice scenario'} · Not a real match</span>")
    elif state.source == DataSource.LIVE_GSI:
        source = "<span class='ds-badge ds-b-unc'>LIVE DATA</span>"
    else:
        source = "<span class='ds-badge ds-b-unc'>No match data</span>"
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
        next_item = (f"<span class='ds-badge {badge_class}'>{label}</span>"
                     f"{buy_now_badge(top)}"
                     f"<strong class='ds-item-name'>{escape(top.item_name)}</strong>"
                     f"<span class='ds-secondary'>{item_price(top)}</span><br><strong>{item_budget(top)}</strong>")
    if not state.enemy_heroes:
        next_item += "<br><span class='ds-secondary'>Core build only · Add enemies in the sidebar for counter items.</span>"
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
    st.divider()
    names = mock.scenario_names()
    scenario = st.selectbox("Mock scenario", names, format_func=lambda n: mock.load(n)["dotasense_mock"]["scenario_name"])
    state = MockProvider(scenario=scenario).current_state()
    live_status = live_gsi_status(state)
    st.caption(f"Live GSI: {live_status}")
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
                f"<div class='ds-card {card_class}'><span class='ds-badge {badge_class}'>{label}</span>{buy_now_badge(r)}"
                f"<b>{escape(r.item_name)}</b> <small>({item_price(r)})</small><br><b>Why:</b> {escape(r.reason)}<br>"
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
            } for a in state.abilities]), hide_index=True, width="stretch")
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
        match_id = m1.text_input("Match ID or OpenDota/Dotabuff URL", placeholder="e.g. 9104260611")
        account_id = m2.text_input("Your Steam32 or Steam64 ID (optional if you pick a hero)", placeholder="e.g. 123456789")
        h1, h2 = st.columns([3, 1])
        hero_pick = h1.selectbox("…or your hero in that match", ["—"] + hero_options,
                                 format_func=lambda h: h if h == "—" else C.hero_display(h))
        force_refresh = h2.checkbox("Force refresh", help="Bypass cache (useful after requesting a parse on OpenDota)")
        submitted = st.form_submit_button("Analyse match")
    if submitted:
        hero_id = C.heroes_by_name()[hero_pick]["id"] if hero_pick != "—" else None
        try:
            parsed_mid = parse_match_id(match_id)
            parsed_acc = parse_account_id(account_id)
        except ValueError as exc:
            st.error(str(exc))
        else:
            if parsed_acc is None and hero_id is None:
                st.error("Enter your account ID or pick your hero.")
            else:
                try:
                    with st.spinner("Fetching match from OpenDota…"):
                        report = coach_match(
                            client, parsed_mid, account_id=parsed_acc,
                            hero_id=hero_id, force_refresh=force_refresh,
                        )
                    db.save_report(conn, report)
                    st.success(f"Report saved for match {report['match_id']} ({report['hero']})")
                except (OpenDotaError, ValueError) as exc:
                    st.error(str(exc))

    saved_reports = db.list_reports(conn)
    if not saved_reports:
        st.caption("No reports yet. Enter a recent public match ID above to generate your first post-match review.")
    for idx, rep in enumerate(saved_reports):
        role_tag = f" ({rep['role']})" if rep.get("role") else ""
        mode_tag = f" · {rep['game_mode']}" if rep.get("game_mode") else ""
        parse_tag = "Parsed" if rep.get("parsed") else "Unparsed"
        header = (
            f"Match {rep['match_id']} · {rep['hero']}{role_tag} · "
            f"{rep['result']} · {rep['duration_min']} min{mode_tag} · {parse_tag}"
        )
        with st.expander(header, expanded=(idx == 0)):
            r1 = st.columns(4)
            r1[0].metric("K / D / A", rep["kda"])
            r1[1].metric("GPM", rep.get("gpm", "—"))
            r1[2].metric("XPM", rep.get("xpm", "—"))
            r1[3].metric("Last hits", rep.get("last_hits", "—"))
            r2 = st.columns(4)
            r2[0].metric("Kill part.", f"{rep['kill_participation_pct']}%" if rep.get("kill_participation_pct") is not None else "—")
            r2[1].metric("Hero damage", f"{rep['hero_damage']:,}" if rep.get("hero_damage") is not None else "—")
            r2[2].metric("Tower damage", f"{rep['tower_damage']:,}" if rep.get("tower_damage") is not None else "—")
            wards = rep.get("wards")
            r2[3].metric("Wards (Obs/Sen)", f"{wards['obs']} / {wards['sen']}" if wards is not None else "n/a")

            items_line = ", ".join(rep.get("final_items") or []) or "n/a"
            extras = []
            if rep.get("neutral_item"):
                extras.append(f"Neutral: {rep['neutral_item']}")
            if rep.get("consumed_buffs"):
                extras.append("Buffs: " + ", ".join(rep["consumed_buffs"]))
            st.markdown("**Final items:** " + items_line + (f" · {' · '.join(extras)}" if extras else ""))

            if rep.get("item_timings"):
                df_timings = pd.DataFrame(rep["item_timings"])[["item_name", "minute", "cost"]].rename(
                    columns={"item_name": "Item", "minute": "Minute", "cost": "Cost (gold)"}
                )
                st.dataframe(df_timings, hide_index=True, use_container_width=True)
            elif rep.get("parsed"):
                st.caption("No major completed items recorded in this parsed match.")
            else:
                req_url = rep.get("parse_request_url") or f"https://www.opendota.com/request#{rep['match_id']}"
                st.markdown(
                    f"{MISSING} — match is not parsed on OpenDota "
                    f"(<a href='{req_url}' target='_blank'>request a parse</a>, then re-run with Force refresh).",
                    unsafe_allow_html=True,
                )

            if rep.get("benchmarks_pct"):
                st.markdown(
                    "**Benchmarks vs players on this hero** *(higher % = better, including fewer deaths)*: "
                    + " · ".join(f"{k.replace('_', ' ')} **{v}%**" for k, v in rep["benchmarks_pct"].items())
                )

            st.markdown("**Coaching suggestions**")
            for s in rep.get("suggestions") or []:
                st.markdown(f"- {s}")
            od_url = rep.get("opendota_url") or f"https://www.opendota.com/matches/{rep['match_id']}"
            st.caption(f"Source: {rep.get('source', 'OpenDota')} · [View full match on OpenDota]({od_url})")
