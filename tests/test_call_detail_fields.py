"""Call-detail field contract: source-clock detail only, no sensitive leak or DB writes."""
from contextlib import contextmanager
from pathlib import Path

from server import database


def test_call_time_only_selected_for_single_call_metadata(monkeypatch):
    queries = []
    class Conn:
        def execute(self, sql, params=()):
            queries.append((sql, params))
            return self
        def fetchone(self):
            return {"id": 42, "CALLDATE": "2026-10-31", "call_time": 43200,
                    "deal_value": 0}
        def fetchall(self):
            return [{"id": 42, "CALLDATE": "2026-10-31", "deal_value": 0}]

    @contextmanager
    def connect():
        yield Conn()

    monkeypatch.setattr(database, "connect", connect)
    public = database.get_call(42, sensitive=False)
    assert public["call_time"] == 43200
    assert public["deal_value"] == 0  # Raw reporting value unchanged.
    assert "call_time" not in database.PUBLIC_COLUMNS
    assert "tellnum" not in database.PUBLIC_COLUMNS
    assert "tellnum" not in database.DETAIL_COLUMNS
    assert "customertell" not in database.DETAIL_COLUMNS
    sql, params = queries[-1]
    assert '"call_time"' in sql
    assert '"customertell"' not in sql
    assert '"tellnum"' not in sql
    assert params == (42,)

    database.list_calls()
    list_query, _ = queries[-1]
    assert '"call_time"' not in list_query
    assert '"tellnum"' not in list_query

    database.get_call(42, sensitive=True)
    sensitive_sql, _ = queries[-1]
    assert '"call_time"' in sensitive_sql
    assert '"customertell"' in sensitive_sql
    assert '"tellnum"' not in sensitive_sql
    assert all("UPDATE " not in sql.upper() and "DELETE " not in sql.upper()
               for sql, _ in queries)


def test_call_details_ui_keeps_misleading_fields_out_of_primary_content():
    app = Path("static/app.js").read_text()
    assert "labels.call_time" in app
    assert "formatSourceCallClock(data.call_time)" in app
    assert "hasDisplayableDealValue(val)" in app
    assert "key!=='deal_value'" in app
    assert "item.title='مقدار مستقیم از سامانه مبدأ" in app
    assert "dialablePhone(val)" in app
    assert "detailRequestId" in app
    assert "drawerReturnFocus" in app
    assert "e.key==='Escape'" in app
    assert "e.key!=='Tab'" in app


def test_call_detail_mobile_responsiveness_and_accessibility_contract():
    css = Path("static/style.css").read_text()
    html = Path("templates/dashboard.html").read_text()
    assert ".detail-chip-clock" in css
    assert ".detail-clock-hint" in css
    assert ".drawer-open{overflow:hidden}" in css
    assert "safe-area-inset-bottom" in css
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'id="close-drawer"' in html
