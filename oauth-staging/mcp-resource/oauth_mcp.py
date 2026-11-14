"""OAuth 2.1 MCP resource-server verification.

The authorization server is an external, standards-compliant identity provider.
Panadan does not issue OAuth tokens, perform OAuth redirects, or handle refresh
tokens. It only validates issued access tokens and checks local access grants.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import time
from urllib.parse import urlsplit

import jwt
from jwt import InvalidTokenError, PyJWKClient


def _https_url(value: str, *, name: str) -> str:
    """Require an explicit trusted HTTPS configuration, not request headers."""
    url = urlsplit(value)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or any(c.isspace() for c in value)):
        raise ValueError(f"{name} must be an absolute HTTPS URL without credentials, query or fragment")
    return value


@dataclass(frozen=True)
class OAuthConfig:
    mode: str = "legacy"
    issuer: str = ""
    jwks_url: str = ""
    resource: str = ""
    scope: str = "panadan:mcp:read"
    max_ttl_seconds: int = 3600

    @classmethod
    def from_env(cls) -> "OAuthConfig":
        mode = os.getenv("PANADAN_MCP_AUTH_MODE", "legacy").strip().lower()
        if mode not in {"legacy", "oauth"}:
            raise ValueError("PANADAN_MCP_AUTH_MODE must be legacy or oauth")
        if mode == "legacy":
            return cls()
        ttl = int(os.getenv("PANADAN_OAUTH_MAX_TOKEN_TTL", "3600"))
        config = cls(
            mode=mode,
            issuer=os.getenv("PANADAN_OAUTH_ISSUER", "").strip(),
            jwks_url=os.getenv("PANADAN_OAUTH_JWKS_URL", "").strip(),
            resource=os.getenv("PANADAN_OAUTH_RESOURCE", "").strip(),
            scope=os.getenv("PANADAN_OAUTH_SCOPE", "panadan:mcp:read").strip(),
            max_ttl_seconds=ttl,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.mode != "oauth":
            return
        for name, value in (
            ("PANADAN_OAUTH_ISSUER", self.issuer),
            ("PANADAN_OAUTH_JWKS_URL", self.jwks_url),
            ("PANADAN_OAUTH_RESOURCE", self.resource),
        ):
            _https_url(value, name=name)
        if not self.resource.endswith("/mcp/"):
            raise ValueError("PANADAN_OAUTH_RESOURCE must end in /mcp/")
        if (not self.scope or any(c.isspace() for c in self.scope)
                or len(self.scope) > 128):
            raise ValueError("PANADAN_OAUTH_SCOPE must be one non-empty OAuth scope")
        if not 60 <= self.max_ttl_seconds <= 3600:
            raise ValueError("OAuth maximum access token TTL must be 60–3600 seconds")

    @property
    def metadata_url(self) -> str:
        if self.mode != "oauth":
            return ""
        parts = urlsplit(self.resource)
        return f"{parts.scheme}://{parts.netloc}/.well-known/oauth-protected-resource"

    def metadata(self) -> dict:
        if self.mode != "oauth":
            raise ValueError("OAuth is not enabled")
        return {
            "resource": self.resource,
            "authorization_servers": [self.issuer],
            "scopes_supported": [self.scope],
            "bearer_methods_supported": ["header"],
        }


class OAuthVerifier:
    """JWT validation against a *fixed* trusted JWKS URL.

    No discovery endpoint, key URL, user ID or role is ever taken from a token.
    All signature algorithms are pinned. Provider JWTs must contain the exact
    audience/resource, issuer, timestamps, user subject and required scope.
    """

    def __init__(self, config: OAuthConfig):
        if config.mode != "oauth":
            raise ValueError("OAuth verifier requires enabled OAuth configuration")
        config.validate()
        self.config = config
        self.jwks = PyJWKClient(
            config.jwks_url,
            cache_jwk_set=True,
            lifespan=300,
            cache_keys=False,
            timeout=4,
        )

    def verify(self, raw: str) -> str | None:
        details = self.verify_details(raw)
        return details['subject'] if details else None

    def verify_details(self, raw: str) -> dict | None:
        """Return verified subject and signed OAuth client identity, if provided."""
        if not raw or len(raw) > 8192 or raw.count(".") != 2:
            return None
        try:
            header = jwt.get_unverified_header(raw)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                return None
            key = self.jwks.get_signing_key_from_jwt(raw)
            payload = jwt.decode(
                raw,
                key.key,
                algorithms=["RS256"],
                issuer=self.config.issuer,
                audience=self.config.resource,
                options={"require": ["iss", "aud", "exp", "iat", "sub"]},
                leeway=30,
            )
            sub = payload.get("sub")
            if not isinstance(sub, str) or not 1 <= len(sub) <= 256:
                return None
            now = int(time.time())
            issued = payload["iat"]
            expiry = payload["exp"]
            if (not isinstance(issued, int) or isinstance(issued, bool)
                    or not isinstance(expiry, int) or isinstance(expiry, bool)
                    or expiry - issued > self.config.max_ttl_seconds
                    or issued > now + 30 or expiry <= now):
                return None
            # Some providers emit a space-separated scope claim; others use scp.
            raw_scopes = payload.get("scope", payload.get("scp", ""))
            scopes = (raw_scopes.split() if isinstance(raw_scopes, str) else
                      raw_scopes if isinstance(raw_scopes, list) else [])
            if self.config.scope not in scopes:
                return None
            if payload.get("token_use", "access") != "access":
                return None
            # Client identity must be part of the signed JWT. Never use a
            # model argument, display name, header or unverified claim.
            azp, client_id = payload.get("azp"), payload.get("client_id")
            if azp is not None and client_id is not None and azp != client_id:
                return None
            client = azp if azp is not None else client_id
            if (client is not None and
                    (type(client) is not str or not 1 <= len(client) <= 160)):
                return None
            return {"subject": sub, "client_id": client}
        except (InvalidTokenError, ValueError, TypeError, KeyError, OSError, TimeoutError, jwt.PyJWKClientError):
            return None
