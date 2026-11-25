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
