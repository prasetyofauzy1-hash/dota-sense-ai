from dataclasses import replace
from pathlib import Path

from streamlit.testing.v1 import AppTest

from app import config
from app.database import connection


def test_match_glance_distinguishes_mock_live_status_and_missing_lineup(monkeypatch):
    connect = connection.connect
    monkeypatch.setattr(connection, "connect", lambda: connect(":memory:"))
    monkeypatch.setattr(config, "settings", replace(config.settings, live_integration_enabled=False))
    script = Path(__file__).resolve().parents[1] / "app" / "dashboard.py"
    dashboard = AppTest.from_file(script).run()
    assert not dashboard.exception

    live_tab = dashboard.tabs[0]
    status = next(block.value for block in live_tab.markdown if "ds-status'" in block.value)
    assert "MOCK DATA" in status and "Not a real match" in status
    assert "Live GSI: Off" in status
    assert "Rules only" in status
    assert "7:30" in status and "Active" in status

    glance = next(block.value for block in live_tab.markdown if "ds-glance'" in block.value)
    assert "Top item recommendation" in glance and "Wraith Band" in glance
    assert "High priority" in glance and "Buy now" in glance
    assert "Top enemy threats" in glance and "Riki" in glance
    bkb = next(block.value for block in live_tab.markdown if "<b>Black King Bar</b>" in block.value)
    assert "Alternative:" not in bkb
    assert "Situational" in bkb and "Need 3,410 more gold" in bkb
    assert any("Mock lineup · Heuristic scouting" in block.value for block in live_tab.caption)
    assert any("Mock match · Conditional calls" in block.value for block in live_tab.caption)

    assert not any("<b>Aeon Disk</b>" in block.value for block in live_tab.markdown)
    more = next(box for box in live_tab.checkbox if box.label.startswith("Show more counter options"))
    more.check().run()
    assert not dashboard.exception
    assert any("<b>Aeon Disk</b>" in block.value for block in dashboard.tabs[0].markdown)

    dashboard.multiselect[0].set_value([]).run()
    assert not dashboard.exception
    live_tab = dashboard.tabs[0]
    assert any("Missing data:" in block.value and "enemy lineup" in block.value for block in live_tab.markdown)
    glance = next(block.value for block in live_tab.markdown if "ds-glance'" in block.value)
    assert "Core build only" in glance and "Wraith Band" in glance
    assert "Enemy lineup not available" in glance
    assert "Riki" not in glance and "Lion" not in glance
    treads = next(block.value for block in live_tab.markdown if "<b>Power Treads</b>" in block.value)
    assert "Need 260 more gold" in treads
    assert "900 gold to finish (have Boots of Speed)" in treads

    config.settings.live_state_path.unlink(missing_ok=True)  # no live push from other tests
    monkeypatch.setattr(config, "settings", replace(config.settings, live_integration_enabled=True))
    dashboard.run()
    assert not dashboard.exception
    status = next(block.value for block in dashboard.tabs[0].markdown if "ds-status'" in block.value)
    assert "No match data" in status and "Live GSI: Waiting for game" in status

    dashboard.radio[0].set_value("Mock scenario").run()
    assert not dashboard.exception
    status = next(block.value for block in dashboard.tabs[0].markdown if "ds-status'" in block.value)
    assert "MOCK DATA" in status and "Not a real match" in status
    assert "Live GSI: On · mock view" in status


def test_pro_counter_intel_defaults_to_matchup_but_allows_custom_item(monkeypatch):
    connect = connection.connect
    monkeypatch.setattr(connection, "connect", lambda: connect(":memory:"))
    monkeypatch.setattr(config, "settings", replace(config.settings, live_integration_enabled=False))
    script = Path(__file__).resolve().parents[1] / "app" / "dashboard.py"
    dashboard = AppTest.from_file(script).run()
    pro = dashboard.tabs[2]
    assert pro.label == "Pro Counter Intel"
    assert pro.selectbox[0].value == "juggernaut"
    assert pro.selectbox[1].value == "necrolyte"
    assert any("selected pro tournaments" in block.value for block in pro.caption)

    dashboard.multiselect[0].set_value(["lion"]).run()
    pro = dashboard.tabs[2]
    assert pro.selectbox[1].value == "lion"
    assert any("No matches for this selection" in block.value for block in pro.info)

    pro.selectbox[0].set_value("skeleton_king").run()
    pro = dashboard.tabs[2]
    assert pro.selectbox[1].value is None
    pro.selectbox[2].set_value("radiance").run()
    assert not dashboard.exception
    pro = dashboard.tabs[2]
    assert pro.dataframe[0].value.to_dict(orient="records") == [{
        "Item": "Radiance", "With item": "25.0% (1/4 wins)", "Without item": "0.0% (0/1 wins)",
        "Difference": "Small sample",
    }]
    assert any("8743555498" in block.value for block in pro.caption)
    assert any("not a rules-based counter" in block.value for block in pro.caption)

    pro.selectbox[0].set_value("windrunner").run()
    dashboard.tabs[2].selectbox[1].set_value("puck").run()
    assert not dashboard.exception
    pro = dashboard.tabs[2]
    assert any("Windranger against Puck" in block.value for block in pro.markdown)
    bkb = pro.dataframe[0].value.set_index("Item").loc["Black King Bar"]
    assert bkb["With item"] == "63.6% (21/33 wins)"
    assert bkb["Without item"] == "56.2% (9/16 wins)"
    assert bkb["Difference"] == "+7.4 pp"

    pro.selectbox[0].set_value("pangolier").run()
    dashboard.tabs[2].selectbox[1].set_value("medusa").run()
    pro = dashboard.tabs[2]
    assert pro.selectbox[2].value == "diffusal_blade"
    assert "Diffusal Blade (item ID 174)" in pro.selectbox[2].options
    assert "Diffusal Blade (item ID 196)" in pro.selectbox[2].options
    pro.selectbox[2].set_value("diffusal_blade_2").run()
    pro = dashboard.tabs[2]
    diffusal = pro.dataframe[0].value.set_index("Item")["With item"]
    assert diffusal["Diffusal Blade (item ID 174)"] == "100.0% (3/3 wins)"
    assert diffusal["Diffusal Blade (item ID 196)"] == "No games"

    pro.selectbox[0].set_value("hoodwink").run()
    dashboard.tabs[2].selectbox[1].set_value("nyx_assassin").run()
    pro = dashboard.tabs[2]
    assert pro.selectbox[2].value == "dust"
    detection = pro.dataframe[0].value.set_index("Item")
    assert "/19 wins)" in detection.loc["Dust of Appearance", "With item"]
    assert detection.loc["Dust of Appearance", "Difference"] == "Not shown (consumable)"
    assert detection.loc["Sentry Ward", "Difference"] == "Not shown (consumable)"
    assert any("remaining stock only, not usage" in block.value for block in pro.caption)
    pro.selectbox[2].set_value("ward_sentry").run()
    pro = dashboard.tabs[2]
    assert any("6 matches omitted" in block.value for block in pro.caption)
    assert not any("9090171021" in block.value for block in pro.caption)
