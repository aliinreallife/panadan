"""Opt-in WorkOS Standalone Connect bridge for Panadan's existing sessions.

This is NOT a login, user, password, consent, or MCP replacement.
Enabled only with deliberate OAuth mode, HTTPS origin, and separate secrets.
Never trusts an OAuth client or email from the incoming request.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

PENDING_COOKIE = "panadan_workos_external_auth"
_PENDING_MAX_AGE = 600
_EXTERNAL_ID_RE = re.compile(r"[A-Za-z0-9_-]{16,160}\Z")
SUBJECT_PREFIX = "panadan-user-"
WORKOS_COMPLETE_URL = "https://api.workos.com/authkit/oauth2/complete"


class WorkOSBridgeError(ValueError):
    """Safe, nonsensitive error for a failed authentication bridge."""


@dataclass(frozen=True)
class WorkOSBridgeConfig:
    enabled: bool = False
    issuer: str = ""
    api_key: str = ""
    signing_key: str = ""
    public_origin: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str], *,
                 oauth_mode: str, oauth_issuer: str,
                 public_origin: str) -> "WorkOSBridgeConfig":
        raw = env.get("PANADAN_WORKOS_STANDALONE_ENABLED", "false").lower()
        if raw == "false":
            return cls()
        if raw != "true":
            raise ValueError("PANADAN_WORKOS_STANDALONE_ENABLED must be true or false")
        api_key = env.get("WORKOS_API_KEY", "")
        signing_key = env.get("PANADAN_WORKOS_PENDING_SECRET", "")
        issuer = oauth_issuer
        p = urlsplit(issuer)
        origin = urlsplit(public_origin)
        if (oauth_mode != "oauth" or not api_key.startswith("sk_")
                or len(api_key) < 16 or len(signing_key) < 32
                or p.scheme != "https" or not p.hostname or p.path not in ("", "/")
                or p.username or p.password or p.query or p.fragment
                or origin.scheme != "https" or not origin.hostname
                or origin.username or origin.password or origin.path not in ("", "/")
                or origin.query or origin.fragment):
            raise ValueError("WorkOS bridge needs OAuth mode, exact HTTPS origins and secure secrets")
        return cls(enabled=True, issuer=issuer.rstrip("/"),
                   api_key=api_key, signing_key=signing_key,
                   public_origin=public_origin.rstrip("/"))

    def issue_pending(self, external_auth_id: str, *, now: int | None = None) -> str:
        if not self.enabled or not isinstance(external_auth_id, str) or not _EXTERNAL_ID_RE.fullmatch(external_auth_id):
            raise WorkOSBridgeError("Invalid WorkOS external authorization request")
        now = int(time.time() if now is None else now)
        payload = json.dumps({"id": external_auth_id, "iat": now,
                              "nonce": secrets.token_urlsafe(16)},
                             separators=(",", ":"), sort_keys=True).encode("ascii")
        encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
        signature = hmac.new(self.signing_key.encode("utf-8"), encoded.encode("ascii"),
                             hashlib.sha256).hexdigest()
        return encoded + "." + signature

    def read_pending(self, token: str | None, *, now: int | None = None) -> str | None:
        if not self.enabled or not token or len(token) > 600 or token.count(".") != 1:
            return None
        try:
            encoded, signature = token.split(".", 1)
            correct = hmac.new(self.signing_key.encode("utf-8"),
                               encoded.encode("ascii"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, correct):
                return None
            payload = json.loads(base64.urlsafe_b64decode(
                encoded + "=" * (-len(encoded) % 4)))
            when = payload["iat"]
            external_id = payload["id"]
            now = int(time.time() if now is None else now)
            if (type(when) is not int or when > now + 10
                    or now - when > _PENDING_MAX_AGE
                    or not isinstance(external_id, str)
                    or not _EXTERNAL_ID_RE.fullmatch(external_id)):
                return None
            return external_id
        except (UnicodeError, ValueError, KeyError, TypeError, OverflowError, binascii.Error):
            return None

    @staticmethod
    def external_subject(user_id: int) -> str:
        if type(user_id) is not int or user_id <= 0:
            raise WorkOSBridgeError("Invalid Panadan account")
        return SUBJECT_PREFIX + str(user_id)

    def validate_redirect(self, url: str) -> str:
        """No open redirects: WorkOS must send us back to the pinned issuer."""
        if not isinstance(url, str) or len(url) > 2048:
            raise WorkOSBridgeError("WorkOS returned an invalid continuation")
        p, expected = urlsplit(url), urlsplit(self.issuer)
        if (p.scheme != "https" or p.netloc != expected.netloc
                or p.username or p.password or not p.path.startswith("/oauth2/")
                or p.fragment or any(ch.isspace() for ch in url)):
            raise WorkOSBridgeError("WorkOS continuation origin is not trusted")
        return url

    def complete(self, external_auth_id: str, *, user_id: int, email: str) -> str:
        """External HTTPS completion; called ONLY after Panadan browser login."""
        if not self.enabled or not _EXTERNAL_ID_RE.fullmatch(external_auth_id):
            raise WorkOSBridgeError("Invalid WorkOS external authorization request")
        if not isinstance(email, str) or not email or len(email) > 254:
            raise WorkOSBridgeError("Panadan account lacks a verified email")
        data = json.dumps({
            "external_auth_id": external_auth_id,
            "user": {"id": self.external_subject(user_id), "email": email},
        }, separators=(",", ":")).encode("utf-8")
        request = Request(WORKOS_COMPLETE_URL, data=data, method="POST", headers={
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with urlopen(request, timeout=8) as response:
                if response.status != 200:
                    raise WorkOSBridgeError("WorkOS completion failed")
                raw = response.read(8193)
            if len(raw) > 8192:
                raise WorkOSBridgeError("WorkOS completion response too large")
            result = json.loads(raw)
            return self.validate_redirect(result.get("redirect_uri"))
        except (HTTPError, URLError, TimeoutError, OSError,
                ValueError, TypeError, KeyError) as exc:
            raise WorkOSBridgeError("WorkOS completion unavailable or refused") from None
