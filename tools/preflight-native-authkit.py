"""Read-only production native AuthKit preflight, executed inside current web.

Usage: docker exec -i panadan-web-1 python - < tools/preflight-native-authkit.py
Uses current configured WorkOS API key; never logs it, user profile or tokens.
No data writes, no customer queries, no login or token issuance.
"""
import json
import os
import re
import sqlite3
import sys
from urllib.error import HTTPError
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.parse import quote
from pathlib import Path

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def fail(message):
    print("FAIL: " + message, file=sys.stderr)
    raise SystemExit(1)

def main():
    # Operator-supplied values are not credentials. No secret arguments.
    email = os.environ.get("PANADAN_PREFLIGHT_EMAIL", "").strip().lower()
    subject = os.environ.get("PANADAN_PREFLIGHT_SUBJECT", "")
    uid = os.environ.get("PANADAN_PREFLIGHT_UID", "")
    if not re.fullmatch(r"user_[A-Za-z0-9]+", subject) or not re.fullmatch(r"[1-9][0-9]{0,8}", uid) or "@" not in email:
        fail("expected administrator identity not configured")
    key = os.environ.get("WORKOS_API_KEY", "")
    issuer = os.environ.get("PANADAN_OAUTH_ISSUER", "")
    if not key.startswith("sk_") or not re.fullmatch(r"https://[a-z0-9-]+\.authkit\.app", issuer):
        fail("configured provider or API key missing")
    try:
        db = Path(os.environ.get("PANADAN_AUTH_DB", "/data/auth.sqlite"))
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
            row = conn.execute("SELECT role,is_active FROM users WHERE id=?", (int(uid),)).fetchone()
            if row != ("admin", 1):
                fail("expected local administrator missing or inactive")
            old = conn.execute("SELECT subject FROM oauth_identities WHERE issuer=? AND user_id=?",
                               (issuer, int(uid))).fetchone()
            owner = conn.execute("SELECT user_id FROM oauth_identities WHERE issuer=? AND subject=?",
                                 (issuer, subject)).fetchone()
            if (old and old[0] not in (subject, "panadan-user-" + uid)) or (
                    owner and owner[0] != int(uid)):
                fail("conflicting identity binding")
    except (OSError, ValueError, sqlite3.Error):
        fail("could not verify local administrator")
    print("PASS: existing local administrator and identity migration are compatible")

    req = Request("https://api.workos.com/user_management/users/" + quote(subject, safe=""),
                  headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
    try:
        with build_opener(NoRedirect()).open(req, timeout=12) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            fail("unexpected WorkOS response size")
        user = json.loads(raw)
    except HTTPError as exc:
        fail("WorkOS user lookup HTTP " + str(exc.code))
    except (OSError, ValueError, TypeError):
        fail("WorkOS user lookup unavailable")
    if (not isinstance(user, dict) or user.get("id") != subject
            or not isinstance(user.get("email"), str)
            or user["email"].strip().lower() != email or user.get("email_verified") is not True):
        fail("provider account does not match verified administrator")
    print("PASS: real WorkOS API key, verified administrator, and container egress")
    print("NOTE: browser callback and MCP consent still require real interactive tests")

if __name__ == "__main__":
    main()
