#!/usr/bin/env python3
"""Create a PostgreSQL SCRAM-SHA-256 verifier from a private stdin password.

The only supported input is a cryptographically random 64-character lowercase
hex password. Prints ONLY the salted verifier, never the original password.
"""
import base64
import hashlib
import hmac
import os
import re
import sys


def verifier(password: bytes, salt: bytes, iterations: int = 4096) -> str:
    if not re.fullmatch(rb"[0-9a-f]{64}", password):
        raise ValueError("Expected 64 lowercase hexadecimal password bytes")
    if len(salt) != 16 or iterations < 4096:
        raise ValueError("Expected a 16-byte salt and at least 4096 iterations")
    salted = hashlib.pbkdf2_hmac("sha256", password, salt, iterations)
    client = hmac.digest(salted, b"Client Key", "sha256")
    stored = hashlib.sha256(client).digest()
    server = hmac.digest(salted, b"Server Key", "sha256")
    encode = lambda raw: base64.b64encode(raw).decode("ascii")
    return f"SCRAM-SHA-256${iterations}:{encode(salt)}${encode(stored)}:{encode(server)}"


def main() -> int:
    password = sys.stdin.buffer.read(65)
    if not re.fullmatch(rb"[0-9a-f]{64}", password):
        print("Invalid locally generated password format", file=sys.stderr)
        return 2
    sys.stdout.write(verifier(password, os.urandom(16)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
