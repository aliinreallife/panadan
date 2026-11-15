"""Fail closed when reviewed production security modules and staging copy drift."""
from __future__ import annotations
import ast
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]


def test_real_security_and_mcp_tools_are_byte_identical_to_panadan():
    for filename in ("oauth_mcp.py", "security.py",
                     "field_permissions.py", "mcp_tools.py"):
        assert (BASE / "server" / filename).read_bytes() == (
            REPO / "server" / filename).read_bytes(), filename


def test_real_http_bearer_gate_matches_production_ast():
    def klass(file):
        source = file.read_text()
        root = ast.parse(source)
        return next(node for node in root.body if isinstance(node, ast.ClassDef)
                    and node.name == "MCPBearerGate")
    a = klass(REPO / "server" / "main.py")
    b = klass(BASE / "server" / "main.py")
    assert ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False)


def test_staging_never_includes_real_reporting_database_or_production_config():
    content = (BASE / "server" / "database.py").read_text()
    assert "psycopg" not in content
    assert "SYNTHETIC_ONLY = True" in content
    assert not (BASE / "server" / "auth_store.py").exists()
