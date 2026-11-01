#!/usr/bin/env python3
"""Read-only MCP OAuth discovery diagnostics for public HTTPS endpoints.

Never requests credentials, authorizes an OAuth client, accesses call data,
or enables OAuth mode. All network requests use Python's verified TLS stack.
"""
from __future__ import annotations

import argparse
import json
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
    if not isinstance(methods, list) or not methods:
        raise ValueError("Authorization server omitted token endpoint authentication methods")
    if document.get("client_id_metadata_document_supported") is True:
        return "CIMD"
    registration = document.get("registration_endpoint")
    if isinstance(registration, str):
        require_https(registration)
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
    doc = None
    for candidate in authorization_server_urls(issuer):
        try:
            doc = fetch_json(candidate)
            break
        except ValueError as exc:
            # Only a real not-found should select the alternate discovery route.
            if "HTTP 404" not in str(exc):
                raise
    if doc is None:
        raise ValueError("Issuer exposes neither RFC 8414 nor OIDC discovery")
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
    args = parser.parse_args()
    try:
        run(args.url)
        return 0
    except (ValueError, HTTPError, URLError, TimeoutError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
