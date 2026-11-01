"""Canonical HTTPS origin for Panadan behind an untrusted HTTP reverse-proxy hop.

We deliberately do NOT consume X-Forwarded-* headers. The configured public
origin is used for CSRF checks and rendered URLs, and TrustedHostMiddleware
enforces exact Host names. This avoids depending on dynamic Docker proxy IPs.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit
from starlette.requests import Request


_LOOPBACK_HOSTS = frozenset(("localhost", "127.0.0.1", "::1"))


def read_public_origin(*, cookie_secure: bool) -> str | None:
    """Validate the single external HTTPS origin; fail closed on misconfiguration."""
    raw = os.environ.get("PANADAN_PUBLIC_ORIGIN", "").strip()
    if not raw:
        return None
    if len(raw) > 253 or any(c.isspace() or ord(c) < 32 for c in raw):
        raise ValueError("PANADAN_PUBLIC_ORIGIN must be a single exact HTTPS origin")
    parsed = urlsplit(raw)
    hostname = parsed.hostname
    if (parsed.scheme != "https" or not hostname
            or raw != f"https://{hostname}"
            or parsed.username or parsed.password or parsed.path
            or parsed.query or parsed.fragment or "*" in raw):
        raise ValueError("PANADAN_PUBLIC_ORIGIN must be https://<hostname> without a path or port")
    if not cookie_secure:
        raise ValueError("PANADAN_COOKIE_SECURE=true is required with PANADAN_PUBLIC_ORIGIN")
    return raw


def allowed_hosts(public_origin: str | None) -> list[str]:
    """Restrict production Host values while preserving localhost diagnostics."""
    if public_origin is None:
        # Development stays bound to loopback; no public ingress should exist.
        return ["*"]
    hostname = urlsplit(public_origin).hostname
    assert hostname is not None
    return [hostname, "localhost", "127.0.0.1", "[::1]", "vpn"]


def external_base_url(request: Request, public_origin: str | None) -> str:
    """Use trusted configuration, never X-Forwarded-Host/Proto, for UI links."""
    return public_origin or str(request.base_url).rstrip("/")


def valid_form_origin(request: Request, public_origin: str | None) -> bool:
    """Browser POST origins must match the external site or private loopback.

    An absent Origin remains acceptable because the separate login nonce and
    per-session CSRF tokens are mandatory and non-browser clients can omit it.
    """
    submitted = request.headers.get("origin")
    if not submitted:
        return True
    expected = external_base_url(request, public_origin)
    if public_origin and request.url.hostname in _LOOPBACK_HOSTS:
        # The HTTP SSH tunnel is bound to localhost, not to the public port.
        expected = str(request.base_url).rstrip("/")
    return submitted == expected
