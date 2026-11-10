"""Fine-grained permission grouping tests. No credentials or real Odoo."""
import json
from pathlib import Path

import pytest

from server.permission_catalog import (
    ADMIN_ONLY, CONFIDENTIAL, PERMISSION_CATEGORIES,
    PERMISSION_GROUPS, ROLE_RECOMMENDED_GROUP,
    catalog_capabilities, group_options, matching_group,
)
from server.security import CAPABILITIES, ROLE_GRANTS, Store, permissions, validate_user_grants


def test_every_capability_has_one_explicit_risk_category():
    actual = [item["id"] for category in PERMISSION_CATEGORIES
              for item in category["items"]]
    assert len(actual) == len(set(actual))
    assert catalog_capabilities() == set(CAPABILITIES)
    assert [category["id"] for category in PERMISSION_CATEGORIES] == [
        "safe", "internal", "confidential", "integrations", "administration"]
    assert ADMIN_ONLY == {"users:manage", "tokens:manage"}
    assert CONFIDENTIAL == {"calls:sensitive", "calls:transcript:read"}
    assert all(category["description"] and category["label"]
               for category in PERMISSION_CATEGORIES)


def test_predefined_groups_are_valid_explicit_non_admin_access_templates():
    groups = group_options()
    assert len(groups) == len(PERMISSION_GROUPS)
    assert len({group["id"] for group in groups}) == len(groups)
    assert all(not (set(group["grants"]) & ADMIN_ONLY) for group in groups)
    for group in groups:
        assert group["label"] and group["description"]
        assert len(group["grants"]) == len(set(group["grants"]))
        assert set(group["grants"]) <= set(CAPABILITIES)
        validate_user_grants("reader", group["grants"])
        assert matching_group("reader", set(group["grants"])) == group["id"]
    assert set(ROLE_RECOMMENDED_GROUP) == {"analyst", "reader", "metrics"}
    assert set(ROLE_RECOMMENDED_GROUP.values()) <= {
        group["id"] for group in groups}
    assert matching_group("analyst", {"calls:read"}) == "reader"
    assert matching_group("admin", set(CAPABILITIES)) == "admin"
    assert matching_group("reader", set()) == "custom"


def test_group_is_one_time_snapshot_and_other_users_do_not_change(tmp_path):
    db = Store(str(tmp_path / "permissions.sqlite"))
    db.bootstrap("admin", "some-long-admin-password")
    group = next(g for g in PERMISSION_GROUPS if g["id"] == "confidential")
    uid = db.create_user("testconfidential", "some-long-user-password",
                         "analyst", list(group["grants"]))
    other = db.create_user("testordinary", "some-long-user-password",
                           "analyst", list(ROLE_GRANTS["analyst"]))
    rows = {item["id"]: item for item in db.list_users()}
    first = permissions(rows[uid]["role"], rows[uid]["grants"])
    second = permissions(rows[other]["role"], rows[other]["grants"])
    assert first == set(group["grants"])
    assert "calls:sensitive" in first and "calls:sensitive" not in second
    assert "mcp:use" in second and "mcp:use" not in first
    # Selecting a new preset for one account must not change the other.
    admin = db.verify_login("admin", "some-long-admin-password")
    db.update_user(uid, "reader", ["calls:read"], True, admin)
    rows = {item["id"]: item for item in db.list_users()}
    assert permissions(rows[uid]["role"], rows[uid]["grants"]) == {"calls:read"}
    assert permissions(rows[other]["role"], rows[other]["grants"]) == second


@pytest.mark.parametrize("caps", [
    ["calls:sensitive"],
    ["calls:transcript:read"],
    ["mcp:use", "calls:read"],
    ["mcp:use", "metrics:read"],
    ["tokens:manage"],
    ["users:manage"],
])
def test_invalid_or_privileged_non_admin_combinations_rejected(caps):
    with pytest.raises(ValueError):
        validate_user_grants("analyst", caps)


def test_legacy_corrupt_grants_do_not_escalate_access():
    bad = json.dumps([
        "tokens:manage", "users:manage", "calls:sensitive",
        "calls:transcript:read", "metrics:read", "mcp:use",
    ])
    assert permissions("reader", bad) == {"metrics:read"}
    assert permissions("admin", bad) == set(CAPABILITIES)


def test_admin_page_has_category_descriptions_and_customizable_group_selectors():
    html = Path("templates/users.html").read_text()
    script = Path("static/users.js").read_text()
    assert "permission_categories" in html
    assert "permission_groups" in html
    assert "access-group-catalog" in html
    assert "data-group-select" in html
    assert "data-role-select" in html
    assert 'name="grants"' in html
    assert "محرمانه" in Path("server/permission_catalog.py").read_text()
    assert "گروه" in html
    assert "window.confirm" in script
    assert "innerHTML" not in script
