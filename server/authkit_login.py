"""Hosted WorkOS AuthKit sign-in for one explicitly pinned administrator.

No provider tokens are persisted. Browser login and MCP consent remain separate.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, HTTPRedirectHandler, build_opener

FLOW_COOKIE = "__Host-panadan_authkit_flow"
AUTHORIZE = "https://api.workos.com/user_management/authorize"
AUTHENTICATE = "https://api.workos.com/user_management/authenticate"


class AuthKitError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class AuthKitConfig:
    enabled: bool = False
    client_id: str = ""
    api_key: str = ""
    admin_email: str = ""
    admin_subject: str = ""
    origin: str = ""
    admin_uid: int = 0
    multi_user: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str], *, origin: str | None, secure: bool,
                 oauth_mode: str, standalone: bool) -> "AuthKitConfig":
        mode = env.get("PANADAN_WEB_AUTH_MODE", "local")
        if mode == "local":
            return cls()
        if mode != "authkit":
            raise ValueError("Unknown web authentication mode")
        client = env.get("WORKOS_CLIENT_ID", "")
        key = env.get("WORKOS_API_KEY", "")
        email = env.get("PANADAN_AUTHKIT_ADMIN_EMAIL", "").strip().lower()
        subject = env.get("PANADAN_AUTHKIT_ADMIN_SUBJECT", "")
        uid = env.get("PANADAN_AUTHKIT_ADMIN_UID", "")
        if (not secure or not isinstance(origin, str) or not origin.startswith("https://") or standalone
                or oauth_mode != "oauth"
                or env.get("PANADAN_AUTH_BACKEND", "sqlite") != "sqlite"
                or not re.fullmatch(r"client_[A-Za-z0-9]+", client)
                or not key.startswith("sk_") or len(key) < 16
                or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
                or not re.fullmatch(r"user_[A-Za-z0-9]+", subject)
                or not re.fullmatch(r"[1-9][0-9]{0,8}", uid)):
            raise ValueError("Invalid AuthKit administrator configuration")
        multi = env.get("PANADAN_AUTHKIT_MULTI_USER", "false")
        if multi not in ("true", "false"):
            raise ValueError("Invalid multi-user configuration")
        return cls(True, client, key, email, subject, origin, int(uid), multi == "true")

    @property
    def callback(self) -> str:
        return self.origin + "/auth/workos/callback"

    def begin(self) -> tuple[str, str]:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        query = urlencode({
            "provider": "authkit", "response_type": "code",
            "client_id": self.client_id, "redirect_uri": self.callback,
            "screen_hint": "sign-in",
            **({} if self.multi_user else {"login_hint": self.admin_email}),
            "prompt": "login",
            "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        payload = f"{state}.{verifier}.{int(time.time())}"
        return AUTHORIZE + "?" + query, payload + "." + self._flow_signature(payload)

    def _flow_signature(self, payload: str) -> str:
        return hmac.new(self.api_key.encode("utf-8"),
                        ("panadan-authkit-flow-v1:" + payload).encode("ascii"),
                        hashlib.sha256).hexdigest()

    def verifier_for(self, cookie: str | None, state: str | None) -> str:
        if not cookie or not state or len(cookie) > 220:
            raise AuthKitError("Login expired")
        parts = cookie.split(".")
        if (len(parts) != 4 or not re.fullmatch(r"[A-Za-z0-9_-]{43}", parts[0])
                or not re.fullmatch(r"[A-Za-z0-9_-]{64}", parts[1])
                or not re.fullmatch(r"[0-9]{1,12}", parts[2])
                or not re.fullmatch(r"[a-f0-9]{64}", parts[3])
                or not re.fullmatch(r"[A-Za-z0-9_-]{43}", state)):
            raise AuthKitError("Login expired")
        now = int(time.time())
        if (int(parts[2]) > now + 5 or now - int(parts[2]) > 600
                or not hmac.compare_digest(parts[0], state)
                or not hmac.compare_digest(parts[3], self._flow_signature(".".join(parts[:3])))):
            raise AuthKitError("Login expired")
        return parts[1]

    def verified_identity(self, user: object) -> tuple[str, str]:
        if (not isinstance(user, dict) or not isinstance(user.get("id"), str)
                or not re.fullmatch(r"user_[A-Za-z0-9]{1,120}", user["id"])
                or not isinstance(user.get("email"), str)
                or len(user["email"]) > 254
                or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", user["email"].strip())
                or user.get("email_verified") is not True):
            raise AuthKitError("Account not authorized")
        subject, email = user["id"], user["email"].strip().lower()
        if (subject == self.admin_subject) != (email == self.admin_email):
            raise AuthKitError("Administrator identity mismatch")
        if not self.multi_user and subject != self.admin_subject:
            raise AuthKitError("Account not authorized")
        return subject, email

    def verify_user(self, user: object) -> None:
        if (not isinstance(user, dict) or user.get("id") != self.admin_subject
                or not isinstance(user.get("email"), str)
                or user["email"].strip().lower() != self.admin_email
                or user.get("email_verified") is not True):
            raise AuthKitError("Account not authorized")

    def exchange(self, code: str, verifier: str) -> tuple[str, str] | None:
        if not code or len(code) > 2048:
            raise AuthKitError("Invalid login code")
        req = Request(AUTHENTICATE, method="POST", headers={
            "Content-Type": "application/json", "Accept": "application/json",
        }, data=json.dumps({
            "client_id": self.client_id, "client_secret": self.api_key,
            "grant_type": "authorization_code", "code": code,
            "code_verifier": verifier,
        }).encode("utf-8"))
        try:
            with build_opener(NoRedirect()).open(req, timeout=12) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise AuthKitError("Invalid authentication response")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise AuthKitError("Invalid authentication response")
        except (HTTPError, URLError, OSError, ValueError, TypeError):
            raise AuthKitError("AuthKit login failed") from None
        if self.multi_user:
            return self.verified_identity(result.get("user"))
        self.verify_user(result.get("user"))
        return None
