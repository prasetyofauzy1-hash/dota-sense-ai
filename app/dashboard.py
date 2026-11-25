"""Streamlit dashboard: `streamlit run app/dashboard.py`."""
from __future__ import annotations

import sys
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
from app.gsi.provider import LiveGSIProvider, MockProvider  # noqa: E402
from app.services import analyze  # noqa: E402

st.set_page_config(page_title="DotaSense AI", page_icon="🛡️", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 3.5rem;}
.ds-card {background:#1a1f2b;border:1px solid #2a3142;border-radius:10px;padding:12px 14px;margin-bottom:10px;}
.ds-high {border-left:5px solid #e8473c;}
.ds-sit {border-left:5px solid #f2b134;}
.ds-missing {color:#8a93a6;font-style:italic;}
.ds-badge {display:inline-block;padding:2px 8px;border-radius:999px;font-size:0.75rem;font-weight:600;margin-right:6px;}
.ds-b-high {background:#e8473c33;color:#ff8077;}
.ds-b-sit {background:#f2b13433;color:#f7c25d;}
.ds-b-unc {background:#6b728033;color:#b8bfcc;}
.ds-b-ok {background:#2ecc7133;color:#5be08f;}
.ds-b-off {background:#6b728033;color:#b8bfcc;}
.ds-mock {background:#f2b13422;border:1px solid #f2b134;color:#f7c25d;border-radius:8px;padding:8px 12px;margin-bottom:12px;font-weight:600;}
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


# ---------------- Sidebar ----------------
with st.sidebar:
    st.title("🛡️ DotaSense AI")
    st.caption("Read-only Dota 2 companion · no automation · no game modification")
    live = LiveGSIProvider().status()
    st.markdown("**Connection status**")
    st.markdown("<span class='ds-badge ds-b-ok'>● Mock data</span> active", unsafe_allow_html=True)
    st.markdown(f"<span class='ds-badge ds-b-off'>○ Live GSI</span> {live['detail']}", unsafe_allow_html=True)
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

if state.is_mock:
    st.markdown(f"<div class='ds-mock'>⚠ MOCK DATA — {state.scenario_name}. "
                "This is a hand-written practice scenario, not a real match.</div>", unsafe_allow_html=True)
for note in result["notes"]:
    st.info(note)

tab_live, tab_post = st.tabs(["Live Match", "Post-Match Reports"])

with tab_live:
    # 1. Live Match Overview
    st.subheader("1 · Live Match Overview")
    c = st.columns(6)
    c[0].markdown(f"**Match**<br>{'Active' if state.match_active else 'Not detected'}", unsafe_allow_html=True)
    c[1].markdown(f"**Game time**<br>{fmt_time(state.game_time)}", unsafe_allow_html=True)
    c[2].markdown(f"**Phase**<br>{result['phase'].replace('_', ' ').title()}", unsafe_allow_html=True)
    c[3].markdown(f"**Gold**<br>{val(state.gold)}", unsafe_allow_html=True)
    c[4].markdown(f"**GPM / XPM**<br>{val(state.gpm)} / {val(state.xpm)}", unsafe_allow_html=True)
    c[5].markdown(f"**K / D / A**<br>{val(state.kills)} / {val(state.deaths)} / {val(state.assists)}",
                  unsafe_allow_html=True)
    if state.missing_fields:
        st.caption("Missing data: " + ", ".join(state.missing_fields))

    left, right = st.columns([1, 1])
    with left:
        # 2. Hero Information
        st.subheader("2 · Hero Information")
        st.markdown(
            f"<div class='ds-card'><b style='font-size:1.2rem'>{result['hero_name']}</b><br>"
            f"Level {val(state.hero.level)} · HP {val(state.hero.health_percent, '%')} · "
            f"Mana {val(state.hero.mana_percent, '%')}</div>", unsafe_allow_html=True)
        if state.abilities:
            st.dataframe(pd.DataFrame([{
                "Ability": a.name.split("_", 1)[-1].replace("_", " ").title(),
                "Level": a.level,
                "Cooldown": "Ready" if not a.cooldown else f"{a.cooldown:.0f}s",
                "Ultimate": "★" if a.ultimate else "",
            } for a in state.abilities]), hide_index=True, use_container_width=True)
        else:
            st.markdown(MISSING, unsafe_allow_html=True)
    with right:
        # 3. Current Inventory
        st.subheader("3 · Current Inventory")
        if state.items:
            cols = st.columns(3)
            for i, item in enumerate(state.items):
                cols[i % 3].markdown(f"<div class='ds-card'>{C.item_display(item)}<br>"
                                     f"<small>{val(C.item_cost(item))} gold</small></div>", unsafe_allow_html=True)
        else:
            st.markdown(MISSING, unsafe_allow_html=True)

    # 4. Recommended Items
    st.subheader("4 · Recommended Items")
    if not result["recommendations"]:
        st.markdown(MISSING + " — hero unknown", unsafe_allow_html=True)
    for r in result["recommendations"]:
        high = r.priority.value == "high"
        badge = "<span class='ds-badge ds-b-high'>HIGH PRIORITY</span>" if high else \
            "<span class='ds-badge ds-b-sit'>SITUATIONAL</span>"
        if r.affordable:
            gold_txt = f"Affordable now · {r.remaining_gold} gold left after buying"
        elif r.remaining_gold is not None:
            gold_txt = f"Need {-r.remaining_gold} more gold"
        else:
            gold_txt = "Gold not available"
        alt = f"<br><b>Alternative:</b> {r.alternative_name}" if r.alternative_name else ""
        st.markdown(
            f"<div class='ds-card {'ds-high' if high else 'ds-sit'}'>{badge}<b>{r.item_name}</b> "
            f"<small>({val(r.cost)} gold)</small><br><b>Why:</b> {r.reason}<br>"
            f"<b>Benefit:</b> {r.benefit}{alt}<br><small>{gold_txt} · score {r.score}</small></div>",
            unsafe_allow_html=True)
    st.caption("History-backed" if result["used_history"] else "Rules only (no historical data used)")

    # 5. Enemy Threat Analysis
    st.subheader("5 · Enemy Threat Analysis")
    if not result["threats"]:
        st.markdown(MISSING + " — add the visible enemy lineup in the sidebar", unsafe_allow_html=True)
    else:
        tcol, ccol = st.columns([1, 1])
        with tcol:
            st.markdown("**Biggest threats**")
            for t in result["threats"]:
                abil = ", ".join(result["enemy_abilities"].get(t.hero_name, [])[:4])
                src = "curated tags" if t.tags_source == "curated" else "inferred from OpenDota roles"
                st.markdown(f"<div class='ds-card'><b>{t.hero_name}</b> "
                            f"<small>severity {t.severity}</small><br>{t.explanation}<br>"
                            f"<small>Abilities: {abil or 'n/a'} · {src}</small></div>", unsafe_allow_html=True)
        with ccol:
            st.markdown("**Counter items**")
            for ci in result["counters"][:8]:
                kind = "Defensive" if ci.defensive else "Offensive"
                st.markdown(f"<div class='ds-card'><b>{ci.item_name}</b> <small>{kind}</small><br>"
                            f"{ci.explanation}<br><small>Against: {', '.join(ci.against_heroes)} · "
                            f"Counters: {', '.join(ci.counters)}</small></div>", unsafe_allow_html=True)

    # 6. Strategic Suggestions
    st.subheader("6 · Strategic Suggestions")
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
