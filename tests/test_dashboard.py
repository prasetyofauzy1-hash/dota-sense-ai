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
    assert "Top item recommendation" in glance and "Black King Bar" in glance
    assert "High priority" in glance and "Need 3,410 more gold" in glance
    assert "Top enemy threats" in glance and "Lion" in glance
    bkb = next(block.value for block in live_tab.markdown if "<b>Black King Bar</b>" in block.value)
    assert "Alternative:" in bkb and "Linken&#x27;s Sphere" in bkb

    dashboard.multiselect[0].set_value([]).run()
    assert not dashboard.exception
    live_tab = dashboard.tabs[0]
    assert any("Missing data:" in block.value and "enemy lineup" in block.value for block in live_tab.markdown)
    glance = next(block.value for block in live_tab.markdown if "ds-glance'" in block.value)
    assert "Situational" in glance and "Wraith Band" in glance
    assert "Enemy lineup not available" in glance
    assert "Lion" not in glance
    treads = next(block.value for block in live_tab.markdown if "<b>Power Treads</b>" in block.value)
    assert "Need 260 more gold" in treads

    monkeypatch.setattr(config, "settings", replace(config.settings, live_integration_enabled=True))
    dashboard.run()
    assert not dashboard.exception
    status = next(block.value for block in dashboard.tabs[0].markdown if "ds-status'" in block.value)
    assert "MOCK DATA" in status and "Not a real match" in status
    assert "Live GSI: On · mock view" in status
