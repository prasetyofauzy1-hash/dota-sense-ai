"""Streamlit dashboard: `streamlit run app/dashboard.py`."""
from __future__ import annotations

import os
import sys
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
from app.gsi import dota_cfg  # noqa: E402
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
LIVE_SOURCE, MOCK_SOURCE = "Live (Dota 2)", "Mock scenario"


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
    live_provider = LiveGSIProvider()
    live = live_provider.status()
    st.markdown("**Connection status**")
    live_badge = "<span class='ds-badge ds-b-ok'>● Live GSI</span>" if live["connected"] else \
        "<span class='ds-badge ds-b-off'>○ Live GSI</span>"
    st.markdown(f"{live_badge} {live['detail']}", unsafe_allow_html=True)
    sources = ([LIVE_SOURCE] if settings.live_integration_enabled else []) + [MOCK_SOURCE]
    source = st.radio("Data source", sources, horizontal=True)
    live_mode = source == LIVE_SOURCE
    if live_mode:
        state = live_provider.current_state()
        auto_refresh = st.toggle("Auto-refresh on new game data", value=True)
    else:
        st.markdown("<span class='ds-badge ds-b-sit'>● Mock data</span> active", unsafe_allow_html=True)
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
    if os.getenv("DOTASENSE_DESKTOP") == "1" and st.button("Quit DotaSense AI"):
        from app import desktop

        desktop.request_quit()


def render_gsi_setup(connected: bool) -> None:
    with st.expander("Connect Dota 2 (Game State Integration)", expanded=not connected):
        dota_dir = dota_cfg.find_dota_dir()
        st.markdown("1. Write the DotaSense config file into Dota 2:")
        if dota_dir is None:
            st.warning("Dota 2 install not found. Save the file below into "
                       "`...\\steamapps\\common\\dota 2 beta\\game\\dota\\cfg\\gamestate_integration\\`.")
        elif dota_cfg.is_installed(dota_dir):
            st.success(f"Config installed: `{dota_cfg.cfg_path(dota_dir)}`")
        elif st.button("Install config into Dota 2"):
            try:
                st.success(f"Config written to `{dota_cfg.install(dota_dir)}`")
            except OSError as exc:
                st.error(f"Could not write the config: {exc}")
        st.download_button("Download config file", dota_cfg.cfg_text(), file_name=dota_cfg.CFG_NAME)
        st.markdown(f"2. In Steam: right-click **Dota 2 → Properties → Launch options**, add "
                    f"`{dota_cfg.LAUNCH_OPTION}`.\n"
                    "3. Restart Dota 2 and start a match (or Demo Hero). This panel turns green when data arrives.")
        st.caption(f"DotaSense listens on {settings.gsi_url} (this PC only). It reads only what Dota 2 "
                   "sends about your own hero; enemy heroes still come from the sidebar.")


if live_mode and auto_refresh and hasattr(st, "fragment"):
    seen = live_provider.received_at()

    @st.fragment(run_every=2)
    def _watch_live() -> None:
        if live_provider.received_at() != seen:
            st.rerun()

    _watch_live()

result = analyze(state, conn, client, use_history=use_history)

if state.is_mock:
    st.markdown(f"<div class='ds-mock'>⚠ MOCK DATA — {state.scenario_name}. "
                "This is a hand-written practice scenario, not a real match.</div>", unsafe_allow_html=True)
for note in result["notes"]:
    st.info(note)

tab_live, tab_post = st.tabs(["Live Match", "Post-Match Reports"])

with tab_live:
    if live_mode:
        render_gsi_setup(live["connected"])
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
