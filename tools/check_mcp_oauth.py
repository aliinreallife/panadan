#!/usr/bin/env python3
"""Read-only MCP OAuth discovery diagnostics for public HTTPS endpoints.

Never requests credentials, authorizes an OAuth client, accesses call data,
or enables OAuth mode. All network requests use Python's verified TLS stack.
"""
from __future__ import annotations

import argparse
import json

from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import InvalidKeyError
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


def require_https(url: str) -> str:
    p = urlsplit(url)
    if (p.scheme != "https" or not p.hostname or p.username or p.password
            or p.query or p.fragment or any(c.isspace() for c in url)):
        raise ValueError("Expected a trusted absolute HTTPS URL, no credentials/query/fragment")
    return url


def protected_resource_url(resource: str) -> str:
    p = urlsplit(require_https(resource))
    if not p.path.endswith("/mcp/"):
        raise ValueError("Panadan canonical MCP URL must end with /mcp/")
    return f"{p.scheme}://{p.netloc}/.well-known/oauth-protected-resource"


def validate_resource(document: dict, expected_resource: str) -> tuple[str, str]:
    if not isinstance(document, dict):
        raise ValueError("Protected-resource metadata is not an object")
    if document.get("resource") != expected_resource:
        raise ValueError("OAuth resource ID does not match the canonical /mcp/ URL")
    issuers = document.get("authorization_servers")
    if not isinstance(issuers, list) or len(issuers) != 1 or not isinstance(issuers[0], str):
        raise ValueError("Expected one explicit authorization server issuer")
    issuer = require_https(issuers[0])
    scope_list = document.get("scopes_supported")
    if not isinstance(scope_list, list) or "panadan:mcp:read" not in scope_list:
        raise ValueError("Required Panadan MCP scope missing from protected-resource metadata")
    return issuer, "panadan:mcp:read"


def authorization_server_urls(issuer: str) -> tuple[str, str]:
    p = urlsplit(require_https(issuer))
    path = p.path.strip("/")
    origin = f"{p.scheme}://{p.netloc}"
    suffix = f"/{path}" if path else ""
    # RFC 8414 inserts the well-known path before an issuer path;
    # OpenID Connect discovery appends its well-known path.
    return (
        f"{origin}/.well-known/oauth-authorization-server{suffix}",
        f"{origin}{suffix}/.well-known/openid-configuration",
    )


def validate_authorization_server(document: dict, issuer: str) -> str:
    if not isinstance(document, dict) or document.get("issuer") != issuer:
        raise ValueError("Authorization-server metadata issuer does not match protected resource")
    for key in ("authorization_endpoint", "token_endpoint"):
        endpoint = document.get(key)
        if not isinstance(endpoint, str):
            raise ValueError(f"Authorization server missing {key}")
        require_https(endpoint)
    pkce = document.get("code_challenge_methods_supported")
    if not isinstance(pkce, list) or "S256" not in pkce:
        raise ValueError("Authorization server does not advertise PKCE S256")
    methods = document.get("token_endpoint_auth_methods_supported")
    if (not isinstance(methods, list) or not methods
            or not all(isinstance(m, str) for m in methods)):
        raise ValueError("Authorization server omitted valid token endpoint authentication methods")
    grant_types = document.get("grant_types_supported")
    if grant_types is not None and (
        not isinstance(grant_types, list) or "authorization_code" not in grant_types
    ):
        raise ValueError("Authorization server does not support authorization_code")
    response_types = document.get("response_types_supported")
    if response_types is not None and (
        not isinstance(response_types, list) or "code" not in response_types
    ):
        raise ValueError("Authorization server does not support code response type")
    scopes = document.get("scopes_supported")
    if scopes is not None and (
        not isinstance(scopes, list) or "panadan:mcp:read" not in scopes
    ):
        raise ValueError("Authorization server does not advertise the Panadan MCP scope")
    jwks = document.get("jwks_uri")
    if jwks is not None:
        if not isinstance(jwks, str):
            raise ValueError("Authorization server has invalid jwks_uri")
        require_https(jwks)
    if document.get("client_id_metadata_document_supported") is True:
        if not {"none", "private_key_jwt"} & set(methods):
            raise ValueError("CIMD has no ChatGPT-compatible token endpoint authentication method")
        return "CIMD"
    registration = document.get("registration_endpoint")
    if isinstance(registration, str):
        require_https(registration)
        if not {"none", "private_key_jwt", "client_secret_basic", "client_secret_post"} & set(methods):
            raise ValueError("DCR has no supported token endpoint authentication method")
        return "DCR"
    return "pre-registered OAuth client (manual client setup required)"


def verify_challenge(header: str, metadata_url: str, scope: str) -> None:
    if not header.lower().startswith("bearer "):
        raise ValueError("Unauthenticated MCP request did not return Bearer challenge")
    if f'resource_metadata="{metadata_url}"' not in header:
        raise ValueError("401 WWW-Authenticate lacks correct resource_metadata pointer")
    if f'scope="{scope}"' not in header:
        raise ValueError("401 WWW-Authenticate lacks required MCP scope")


class HTTPSOnlyRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request(url: str) -> tuple[int, dict, bytes]:
    # Explicit cap: metadata may be public, but never store unbounded responses.
    try:
        opener = build_opener(HTTPSOnlyRedirectHandler())
        with opener.open(Request(require_https(url), headers={"Accept": "application/json"}),
                         timeout=10) as response:
            return response.status, dict(response.headers), response.read(65537)
    except HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read(65537)


def fetch_json(url: str) -> dict:
    status, _, raw = request(url)
    if status != 200:
        raise ValueError(f"Discovery URL returned HTTP {status}: {url}")
    if len(raw) > 65536:
        raise ValueError(f"Discovery document too large: {url}")
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid JSON discovery document: {url}") from exc
    if not isinstance(result, dict):
        raise ValueError("Discovery response must be a JSON object")
    return result


def discover_authorization_server(issuer: str) -> dict:
    """Fetch only public metadata; never attempt authorization or token exchange."""
    for candidate in authorization_server_urls(issuer):
        try:
            return fetch_json(candidate)
        except ValueError as exc:
            # A real 404 can fall back from RFC 8414 to OIDC discovery.
            # Do not downgrade or mask invalid issuer/TLS/metadata failures.
            if "HTTP 404" not in str(exc):
                raise
    raise ValueError("Issuer exposes neither RFC 8414 nor OIDC discovery")


def check_provider(issuer: str) -> None:
    """Preflight a candidate IdP BEFORE enabling Panadan OAuth or touching prod."""
    issuer = require_https(issuer)
    metadata = discover_authorization_server(issuer)
    registration = validate_authorization_server(metadata, issuer)
    jwks_url = metadata.get("jwks_uri")
    if not isinstance(jwks_url, str):
        raise ValueError("Provider does not advertise JWKS URI required for Panadan RS256 verification")
    require_https(jwks_url)
    jwks = fetch_json(jwks_url)
    keys = jwks.get("keys")
    def usable_rs256_public_key(key) -> bool:
        if (not isinstance(key, dict)
                or key.get("kty") != "RSA"
                or not isinstance(key.get("kid"), str) or not key["kid"]
                or key.get("alg", "RS256") != "RS256"
                or key.get("use", "sig") != "sig"
                or any(secret in key for secret in ("d", "p", "q", "dp", "dq", "qi", "oth"))):
            return False
        try:
            # Validate n/e cryptographically rather than trusting kty=RSA alone.
            public = RSAAlgorithm.from_jwk(json.dumps(key))
            return public.key_size >= 2048
        except (InvalidKeyError, ValueError, TypeError, KeyError):
            return False

    if not isinstance(keys, list) or not any(usable_rs256_public_key(key) for key in keys):
        raise ValueError("Provider JWKS has no valid public RSA signing key usable for RS256")
    print("PASS: Public issuer metadata, PKCE S256, registration and RS256 JWKS preflight")
    print("Issuer:", issuer)
    print("JWKS URI:", jwks_url)
    print("Client identification:", registration)
    if registration.startswith("pre-registered"):
        print("ACTION: Provision compatible ChatGPT and Claude client identities manually")
    if metadata.get("authorization_response_iss_parameter_supported") is not True:
        print("ACTION: Use the client-specific callback URL shown by each client")
    print("UNVERIFIED: authorization/consent, resource -> aud, scope in access JWT,")
    print("            stable subject, account binding, refresh, revocation and real MCP tool calls")
    print("SAFETY: Production must remain on legacy bearer mode until staged acceptance")


def run(resource: str) -> None:
    resource = require_https(resource)
    metadata = protected_resource_url(resource)
    status, _, raw = request(metadata)
    if status == 404:
        raise ValueError("No OAuth protected-resource metadata (HTTP 404). "
                         "Panadan may be in legacy bearer mode; configure an external "
                         "authorization server before changing its auth mode.")
    if status != 200 or len(raw) > 65536:
        raise ValueError(f"Protected-resource metadata returned HTTP {status}")
    issuer, scope = validate_resource(json.loads(raw), resource)
    suffix = metadata.replace("/.well-known/oauth-protected-resource",
                              "/.well-known/oauth-protected-resource/mcp")
    if fetch_json(suffix).get("resource") != resource:
        raise ValueError("Path-specific protected resource metadata disagrees")
    doc = discover_authorization_server(issuer)
    method = validate_authorization_server(doc, issuer)
    code, headers, _ = request(resource)
    if code != 401:
        raise ValueError(f"Unauthenticated MCP request must be 401; got {code}")
    challenge = next((v for k, v in headers.items()
                      if k.lower() == "www-authenticate"), "")
    verify_challenge(challenge, metadata, scope)
    print("PASS: Resource metadata, issuer discovery, PKCE S256, and MCP 401 challenge")
    print("Issuer:", issuer)
    print("Client identification:", method)
    if method.startswith("pre-registered"):
        print("NOTE: Automatic ChatGPT/Claude registration is NOT configured")
    if doc.get("authorization_response_iss_parameter_supported") is not True:
        print("NOTE: No RFC 9207 issuer response guarantee; use client-specific redirect URI")
    print("NOTE: This does not test consent, callbacks, tokens, audience, or tools")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default="https://dan.panafor.com/mcp/",
                        help="Canonical HTTPS MCP resource URL ending with /mcp/")
    parser.add_argument("--issuer",
                        help="Preflight an IdP's PUBLIC HTTPS discovery/JWKS only, "
                             "without enabling OAuth or contacting production Panadan")
    args = parser.parse_args()
    try:
        if args.issuer:
            check_provider(args.issuer)
        else:
            run(args.url)
        return 0
    except (ValueError, HTTPError, URLError, TimeoutError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
