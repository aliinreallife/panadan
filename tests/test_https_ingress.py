"""Synthetic HTTPS ingress tests; never connect to Odoo or the VPS."""
from contextlib import asynccontextmanager
import importlib
import re

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from server.ingress import (
    allowed_hosts, external_base_url, read_public_origin, valid_form_origin,
)


@pytest.fixture
def secured(tmp_path, monkeypatch):
    monkeypatch.setenv("PANADAN_AUTH_DB", str(tmp_path / "auth.sqlite"))
    monkeypatch.setenv("PANADAN_ADMIN_USER", "admin")
    monkeypatch.setenv("PANADAN_ADMIN_PASSWORD", "synthetic-secure-password-for-tests")
    monkeypatch.setenv("PANADAN_COOKIE_SECURE", "true")
    monkeypatch.setenv("PANADAN_PUBLIC_ORIGIN", "https://dan.panafor.com")
    monkeypatch.setenv("PANADAN_MCP_ALLOWED_HOSTS", "dan.panafor.com")
    monkeypatch.setenv("PANADAN_MCP_ALLOWED_ORIGINS", "https://dan.panafor.com")
    import server.main as main
    main = importlib.reload(main)

    @asynccontextmanager
    async def isolated_lifespan(_app):
        main.store.bootstrap("admin", "synthetic-secure-password-for-tests")
        yield

    main.app.router.lifespan_context = isolated_lifespan
    with TestClient(main.app, base_url="https://dan.panafor.com") as client:
        yield client, main


def test_https_login_logout_secure_cookies_and_csrf(secured):
    c, main = secured
    response = c.get("/login")
    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()
    nonce = re.search(r'name="nonce" value="([^"]+)"', response.text).group(1)
    login = c.post("/login", data={
        "username": "admin", "password": "synthetic-secure-password-for-tests",
        "nonce": nonce,
    }, headers={"Origin": "https://dan.panafor.com"}, follow_redirects=False)
    assert login.status_code == 303
    assert "secure" in login.headers["set-cookie"].lower()
    assert c.get("/dashboard").status_code == 200
    csrf = main.store.session(c.cookies.get("panadan_session"))["csrf"]
    assert c.post("/logout", data={"csrf": csrf},
                  headers={"Origin": "https://evil.example"}).status_code == 403
    logout = c.post("/logout", data={"csrf": csrf},
                    headers={"Origin": "https://dan.panafor.com"},
                    follow_redirects=False)
    assert logout.status_code == 303


def test_untrusted_hosts_origins_and_spoofed_proxy_headers(secured):
    c, main = secured
    assert c.get("/healthz", headers={"Host": "evil.example",
               "X-Forwarded-Host": "dan.panafor.com"}).status_code == 400
    assert c.get("/healthz", headers={"Host": "dan.panafor.com"}).status_code == 200
    page = c.get("/login")
    nonce = re.search(r'name="nonce" value="([^"]+)"', page.text).group(1)
    for origin in ("http://dan.panafor.com", "https://evil.example",
                   "https://dan.panafor.com.attacker.example"):
        rejected = c.post("/login", data={
            "username": "admin", "password": "synthetic-secure-password-for-tests",
            "nonce": nonce,
        }, headers={"Origin": origin, "X-Forwarded-Proto": "https"},
           follow_redirects=False)
        assert rejected.status_code == 403
    uid = main.store.verify_login("admin", "synthetic-secure-password-for-tests")
    cookie, _csrf = main.store.create_session(uid)
    c.cookies.set("panadan_session", cookie)
    guide = c.get("/dashboard/api", headers={
        "X-Forwarded-Proto": "http", "X-Forwarded-Host": "evil.example",
    })
    assert guide.status_code == 200
    assert "https://dan.panafor.com" in guide.text
    assert "evil.example" not in guide.text


def test_http_upstream_uses_configured_origin_without_proxy_trust():
    def make_request(host, origin, extra_headers=()):
        headers = [(b"host", host.encode()), (b"origin", origin.encode())]
        headers.extend(extra_headers)
        return Request({
            "type": "http", "method": "POST", "scheme": "http",
            "path": "/login", "root_path": "", "query_string": b"",
            "client": ("172.30.0.8", 35000), "server": ("vpn", 8000),
            "headers": headers,
        })
    req = make_request("dan.panafor.com", "https://dan.panafor.com",
                       [(b"x-forwarded-proto", b"http"),
                        (b"x-forwarded-host", b"evil.example")])
    assert valid_form_origin(req, "https://dan.panafor.com")
    assert external_base_url(req, "https://dan.panafor.com") == "https://dan.panafor.com"
    assert not valid_form_origin(
        make_request("dan.panafor.com", "http://dan.panafor.com"),
        "https://dan.panafor.com")
    tunnel = make_request("127.0.0.1:18508", "http://127.0.0.1:18508")
    assert valid_form_origin(tunnel, "https://dan.panafor.com")


@pytest.mark.parametrize("bad", [
    "http://dan.panafor.com", "https://dan.panafor.com:8448",
    "https://dan.panafor.com/path", "https://evil.example@dan.panafor.com",
    "https://*.panafor.com", "https://dan.panafor.com/?q=1",
    "https://dan.panafor.com/", "https://dan.panafor.com evil",
])
def test_reject_invalid_public_origin(monkeypatch, bad):
    monkeypatch.setenv("PANADAN_PUBLIC_ORIGIN", bad)
    with pytest.raises(ValueError, match="PANADAN_PUBLIC_ORIGIN"):
        read_public_origin(cookie_secure=True)


def test_public_origin_requires_secure_cookie(monkeypatch):
    monkeypatch.setenv("PANADAN_PUBLIC_ORIGIN", "https://dan.panafor.com")
    with pytest.raises(ValueError, match="PANADAN_COOKIE_SECURE"):
        read_public_origin(cookie_secure=False)
    assert read_public_origin(cookie_secure=True) == "https://dan.panafor.com"
    assert "*" not in allowed_hosts("https://dan.panafor.com")
    assert "evil.example" not in allowed_hosts("https://dan.panafor.com")


def test_default_http_dev_mode_remains_available(monkeypatch):
    monkeypatch.delenv("PANADAN_PUBLIC_ORIGIN", raising=False)
    assert read_public_origin(cookie_secure=False) is None
    assert allowed_hosts(None) == ["*"]
