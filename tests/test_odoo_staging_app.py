"""Unit tests for guarded local-only staging entrypoint (no live sockets)."""
from pathlib import Path
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from server.odoo_staging_app import (
    _dsn_file, create_staging_app, staging_settings,
)
from server.security import Store


def _prepared(directory: Path) -> dict[str, str]:
    auth = directory / "auth.sqlite"
    Store(str(auth))
    auth.chmod(0o600)
    report = directory / "reader.dsn"
    sensitive = directory / "sensitive.dsn"
    report.write_text(
        "host=127.0.0.1 port=55432 dbname=panadan_ci "
        "user=panadan_report_reader password=synthetic-only "
        "sslmode=prefer",
        encoding="utf-8",
    )
    sensitive.write_text(
        "host=127.0.0.1 port=55432 dbname=panadan_ci "
        "user=panadan_mirror_sensitive_reader password=synthetic-only "
        "sslmode=prefer",
        encoding="utf-8",
    )
    report.chmod(0o600)
    sensitive.chmod(0o600)
    return {
        "PANADAN_LOCAL_MIRROR_STAGING_ENABLE": "YES",
        "PANADAN_LOCAL_MIRROR_STAGING_ISOLATED": "YES",
        "PANADAN_AUTH_BACKEND": "sqlite",
        "PANADAN_LOCAL_MIRROR_STAGING_AUTH_DB": str(auth),
        "PANADAN_LOCAL_MIRROR_STAGING_REPORT_DSN_FILE": str(report),
        "PANADAN_LOCAL_MIRROR_STAGING_SENSITIVE_DSN_FILE": str(sensitive),
    }


def test_staging_launcher_is_unguessably_isolated_from_production_settings():
    # Temporary directory is deliberately under the only approved prefix.
    with tempfile.TemporaryDirectory(
        prefix="panadan-mirror-staging-", dir="/tmp",
    ) as directory:
        base = Path(directory)
        env = _prepared(base)
        auth, report, sensitive = staging_settings(env)
        assert auth.endswith("/auth.sqlite")
        assert "panadan_ci" in report and "panadan_ci" in sensitive

        with pytest.raises(ValueError, match="not enabled"):
            staging_settings({**env, "PANADAN_LOCAL_MIRROR_STAGING_ENABLE": "NO"})
        with pytest.raises(ValueError, match="not enabled"):
            staging_settings({**env, "PANADAN_LOCAL_MIRROR_STAGING_ISOLATED": "NO"})
        with pytest.raises(ValueError, match="not enabled"):
            staging_settings({**env, "PANADAN_AUTH_BACKEND": "postgres-staging"})
        with pytest.raises(ValueError, match="not enabled"):
            staging_settings({
                **env, "PANADAN_PUBLIC_ORIGIN": "https://dan.panafor.com",
            })
        with pytest.raises(ValueError, match="disposable"):
            staging_settings({
                **env, "PANADAN_LOCAL_MIRROR_STAGING_AUTH_DB": "/data/auth.sqlite",
            })

        role_file = base / "reader.dsn"
        role_file.chmod(0o644)
        with pytest.raises(ValueError, match="Private"):
            staging_settings(env)
        role_file.chmod(0o600)

        role_file.write_text(
            "host=192.168.3.9 port=5432 dbname=odoo "
            "user=report_user password=synthetic-only sslmode=require",
        )
        with pytest.raises(ValueError, match="loopback"):
            staging_settings(env)
        role_file.write_text(
            "host=127.0.0.1 port=55432 dbname=panadan_ci "
            "user=panadan_report_reader password=synthetic-only sslmode=prefer",
        )
        with pytest.raises(ValueError, match="libpq"):
            staging_settings({**env, "PGHOSTADDR": "192.168.3.9"})


def test_staging_launcher_drops_remote_peers_before_any_auth_or_pg_query():
    with tempfile.TemporaryDirectory(
        prefix="panadan-mirror-staging-", dir="/tmp",
    ) as directory:
        env = _prepared(Path(directory))
        app = create_staging_app(env)

        # No database is running at the synthetic fixture port. If a request
        # touches PG, these tests would fail rather than returning 401/403.
        with TestClient(app, client=("203.0.113.4", 4567)) as public:
            result = public.get(
                "/api/v1/local-mirror/calls",
                headers={"Authorization": "Bearer not-a-valid-token"},
            )
            assert result.status_code == 403
            assert result.json() == {"detail": "Local staging only"}

        with TestClient(app, client=("127.0.0.1", 4567)) as private:
            result = private.get("/api/v1/local-mirror/calls")
            assert result.status_code == 401
            assert result.headers["cache-control"] == "no-store"
            assert private.get("/openapi.json").status_code == 404



def test_staging_mcp_requires_scoped_token_and_only_advertises_sanitized_tools():
    import json

    with tempfile.TemporaryDirectory(
        prefix="panadan-mirror-staging-", dir="/tmp",
    ) as directory:
        env = _prepared(Path(directory))
        store = Store(env["PANADAN_LOCAL_MIRROR_STAGING_AUTH_DB"])
        store.bootstrap("mcpadmin", "a-long-synthetic-admin-password")
        admin = store.verify_login("mcpadmin", "a-long-synthetic-admin-password")
        _, token = store.create_token(
            "synthetic-mcp", "mcp:read", 7, owner_id=admin)
        app = create_staging_app(env)

        headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        }

        def post(client, method, token_value, request_id=1, params=None):
            return client.post(
                "/mcp/", headers=headers | {
                    "Authorization": "Bearer " + token_value,
                },
                json={
                    "jsonrpc": "2.0", "id": request_id,
                    "method": method, "params": params or {},
                },
            )

        with TestClient(app, base_url="http://localhost:19087",
                        client=("127.0.0.1", 1234)) as client:
            assert post(client, "tools/list", "wrong").status_code == 401
            initialized = post(client, "initialize", token, params={
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": "Synthetic local mirror smoke", "version": "1.0",
                },
            })
            assert initialized.status_code == 200
            listed = post(client, "tools/list", token, request_id=2)
            assert listed.status_code == 200
            data = listed.json()
            tools = data["result"]["tools"]
            assert {tool["name"] for tool in tools} == {
                "list_mirror_calls",
                "get_mirror_call_summary",
                "count_mirror_calls",
            }
            assert all(tool["annotations"]["readOnlyHint"] for tool in tools)
            assert not any("transcript" in tool["name"] for tool in tools)

            # Fake 55432 has NO PostgreSQL. A valid MCP token must not
            # accidentally fall back to production Odoo or return raw data.
            result = post(client, "tools/call", token, request_id=3,
                          params={"name": "count_mirror_calls", "arguments": {}})
            assert result.status_code == 200
            result_data = result.json()["result"]
            assert "local_mirror_unavailable" in json.dumps(result_data)

            store.revoke(store.list_tokens()[0]["id"])
            assert post(client, "tools/list", token, request_id=4).status_code == 401
