"""Fail-closed, idempotent operator entry point for owned PostgreSQL auth.

Production activation is *not* auth cutover: the live SQLite Store, VPN
configuration, source Odoo, application images, Caddy and Plane stay unchanged.

The script never calls docker compose up/down against an existing Panadan/VPN
or PostgreSQL service. It only adds an internal bridge to live containers.
"""
from __future__ import annotations

import argparse
import fcntl
import ipaddress
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check_auth_db_network as audit  # noqa: E402

NET = "panadan-auth-db"
PG = "panadan-platform-db-1"
VPN = "panadan-vpn-1"
AUTH_FILE = ROOT / ".env.platform.auth"
AUTH_PASSWORD_KEY = "PANADAN_AUTH_RUNTIME_PASSWORD"
LOCK = ROOT / "data" / ".owned-pg-setup.lock"
SCHEMA_SQL = ROOT / "database/migrations/003_auth_foundation.sql"
GRANTS_SQL = ROOT / "database/permissions/003_auth_runtime_role.sql"
NET_PLATFORM = ROOT / "deploy/compose.auth-network.platform.yaml"
NET_PANADAN = ROOT / "deploy/compose.auth-network.panadan.yaml"
INGRESS = ROOT / "data/ingress"
PRIVATE_OVERLAYS = (
    INGRESS / "compose.panadan.yaml",
    INGRESS / "compose.web.release.yaml",
    INGRESS / "compose.web.https.yaml",
)
EXPECTED_BACKUP_DIR = ROOT / "data/platform-backups"
REQUIRED_VARS = (ROOT / ".env.platform", ROOT / ".env.app", ROOT / ".env.db")


class Refusal(Exception):
    """A fail-closed configuration or safety guard."""


def run(*args: str, input_text: str | None = None, timeout: int = 35) -> str:
    try:
        p = subprocess.run(
            list(args), input=input_text, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout, cwd=ROOT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Refusal(f"Command unavailable or timed out: {args[0]}") from e
    if p.returncode:
        # Do not surface stderr: psql/Compose can echo secrets, env, or SQL.
        raise Refusal(f"Command failed ({args[0]} exit={p.returncode}); inspect local logs privately")
    return p.stdout.strip()


def compose_platform(*args: str, input_text: str | None = None) -> str:
    return run(
        "docker", "compose", "--env-file", ".env.platform",
        "-f", "compose.platform.yaml", "-f",
        str(NET_PLATFORM), *args, input_text=input_text,
    )


def compose_app(*args: str) -> str:
    files = ["-f", "compose.prod.yaml"]
    for p in PRIVATE_OVERLAYS:
        files += ["-f", str(p)]
    files += ["-f", str(NET_PANADAN)]
    return run("docker", "compose", "--env-file", ".env.app", *files, *args)


def check_private_file(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise Refusal(f"Required private file missing or symlinked: {path.name}")
    if path.stat().st_mode & 0o077:
        raise Refusal(f"Private file must be 0600: {path.name}")


def preflight() -> None:
    if shutil.which("docker") is None:
        raise Refusal("Docker CLI required")
    for path in REQUIRED_VARS:
        if not path.is_file() or path.is_symlink():
            raise Refusal(f"Required configuration missing: {path.name}")
    check_private_file(ROOT / ".env.platform")
    for path in (*PRIVATE_OVERLAYS, SCHEMA_SQL, GRANTS_SQL,
                 NET_PANADAN, NET_PLATFORM):
        if not path.is_file():
            raise Refusal(f"Missing expected file: {path.name}")
    compose_platform("config", "--quiet")
    compose_app("config", "--quiet")

    # Baseline check refuses wrong project, PG version and incomplete schema.
    db = run(
        "docker", "exec", PG, "psql", "-X", "-A", "-t",
        "-v", "ON_ERROR_STOP=1", "-U", "panadan_owner", "-d", "panadan",
        "-c", """SELECT current_database(),
                  current_setting('server_version_num')::integer / 10000,
                  (SELECT count(*) FROM information_schema.tables
                   WHERE table_schema='panadan_ingest' AND table_type='BASE TABLE');"""
    )
    if db != "panadan|18|7":
        raise Refusal("Expected owned PostgreSQL 18 with 7 ingestion tables")
    current = run(
        "docker", "exec", PG, "psql", "-X", "-A", "-t",
        "-v", "ON_ERROR_STOP=1", "-U", "panadan_owner", "-d", "panadan",
        "-c", """SELECT (to_regnamespace('panadan_auth') IS NOT NULL),
                (SELECT count(*) FROM pg_roles
                 WHERE rolname='panadan_auth_runtime');"""
    )
    if current not in ("f|0", "t|0", "t|1"):
        raise Refusal("Unexpected auth schema or role state; inspect manually")
    if current.startswith("t"):
        n = run(
            "docker", "exec", PG, "psql", "-X", "-A", "-t",
            "-v", "ON_ERROR_STOP=1", "-U", "panadan_owner", "-d", "panadan",
            "-c", """SELECT count(*) FROM information_schema.tables
                      WHERE table_schema='panadan_auth'
                        AND table_type='BASE TABLE';"""
        )
        if n != "8":
            raise Refusal("Existing auth schema has an unexpected table count")
    print(f"PASS: DB preflight (auth schema={current[0]}, runtime role={current[-1]})")


def inspect_network() -> dict | None:
    names = run("docker", "network", "ls", "--format", "{{.Name}}").splitlines()
    if NET not in names:
        return None
    import json
    return json.loads(run("docker", "network", "inspect", NET))[0]


def network_stage() -> str:
    n = inspect_network()
    if n is None:
        return "before"
    if n.get("Name") != NET or n.get("Driver") != "bridge" or not n.get("Internal"):
        raise Refusal("Pre-existing auth network is not an internal bridge")
    members = {x.get("Name") for x in (n.get("Containers") or {}).values()}
    if not members:
        return "before"
    if members == {PG, VPN}:
        return "after"
    raise Refusal("Partial or unexpected auth-network membership; inspect manually")


def audit_network(stage: str) -> None:
    try:
        audit.run(stage)
    except (ValueError, KeyError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as e:
        raise Refusal("Network safety audit failed; inspect with status command") from e


def source_routes() -> None:
    # Fail closed on conflicting Docker routes before changing network.
    route = run("docker", "exec", VPN, "ip", "-4", "route", "get", "192.168.3.9")
    if " dev tun0 " not in f" {route} ":
        raise Refusal("External read-only Odoo route is not through tun0")


def new_subnet_safe(n: dict) -> None:
    networks = [ipaddress.ip_network(x["Subnet"]) for x in n.get("IPAM", {}).get("Config", [])
                if x.get("Subnet")]
    if not networks:
        raise Refusal("Docker network has no inspectable subnet")
    # Reject a bridge that masks the Odoo destination or any non-default
    # routing destination within the live VPN namespace.
    od = ipaddress.ip_address("192.168.3.9")
    for subnet in networks:
        if subnet.version == 4 and od in subnet:
            raise Refusal("New Docker bridge subnet collides with Odoo address")
    routes = run("docker", "exec", VPN, "ip", "-4", "route")
    for line in routes.splitlines():
        first = line.split()[0]
        if first == "default":
            continue
        try:
            old = ipaddress.ip_network(first, strict=False)
        except ValueError:
            continue
        if any(old.overlaps(new) for new in networks if new.version == old.version):
            raise Refusal(f"New auth bridge overlaps an existing VPN route ({first})")


def endpoints() -> None:
    run("curl", "--fail", "--silent", "--show-error", "--max-time", "8",
        "https://dan.panafor.com/healthz", timeout=14)
    run("curl", "--fail", "--silent", "--show-error", "--max-time", "8",
        "https://plane.panafor.com/intake.html", timeout=14)


def tcp_smoke() -> None:
    image = run("docker", "inspect", "panadan-web-1",
                "--format", "{{.Config.Image}}")
    if not image:
        raise Refusal("Missing existing web image")
    run(
        "docker", "run", "--rm", "--pull", "never",
        "--network", f"container:{VPN}",
        "--entrypoint", "python", image, "-c",
        "import socket; sock=socket.create_connection("
        "('panadan-auth-postgres',5432),timeout=5); sock.close()",
        timeout=20
    )


def current_db_backup() -> None:
    run("bash", "tools/platform-db.sh", "backup", timeout=140)
    files = list(EXPECTED_BACKUP_DIR.glob("panadan-*.dump"))
    if not any(f.is_file() and f.stat().st_size > 0 for f in files):
        raise Refusal("Platform backup was not verified")
    print("PASS: fresh local PostgreSQL dump created (NOT an offsite backup)")


def auth_password() -> str:
    if AUTH_FILE.exists() or AUTH_FILE.is_symlink():
        check_private_file(AUTH_FILE)
        data = AUTH_FILE.read_text()
    else:
        secret = secrets.token_hex(32)
        data = f"{AUTH_PASSWORD_KEY}={secret}\n"
        fd = os.open(AUTH_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(data)
        print("PASS: new ignored 0600 auth role credentials generated")
    match = re.fullmatch(
        rf"{AUTH_PASSWORD_KEY}=([0-9a-f]{{64}})\n?", data
    )
    if not match:
        raise Refusal("Malformed auth role credentials (expected one 64-hex value)")
    return match.group(1)


def schema_apply() -> None:
    # psql input via stdin only; secrets are never placed in Docker command argv.
    # The PG ownership context is local-only and isolated from the Odoo source.
    secret = auth_password()
    role_sql = """
DO $bootstrap$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='panadan_auth_runtime') THEN
    CREATE ROLE panadan_auth_runtime LOGIN NOSUPERUSER NOCREATEDB
      NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END
$bootstrap$;
"""
    # Derive a salted SCRAM-SHA-256 verifier locally; never put a plaintext
    # password into an SQL statement or PostgreSQL statement logs.
    from scram_secret import verifier
    hashed = verifier(secret.encode("ascii"), secrets.token_bytes(16))
    logging = run(
        "docker", "exec", PG, "psql", "-X", "-A", "-t",
        "-v", "ON_ERROR_STOP=1", "-U", "panadan_owner", "-d", "panadan",
        "-c", "SHOW log_statement;"
    )
    if logging != "none":
        raise Refusal("Refusing role credential update while PostgreSQL statement logging is enabled")
    role_sql += (
        "ALTER ROLE panadan_auth_runtime LOGIN NOSUPERUSER NOCREATEDB "
        "NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '" + hashed + "';\n"
    )
    # These two files were reviewed/tested against an offsite PG18 restore.
    sql = SCHEMA_SQL.read_text() + "\n" + role_sql + "\n" + GRANTS_SQL.read_text()
    run(
        "docker", "exec", "-i", PG, "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
        "--single-transaction", "-U", "panadan_owner", "-d", "panadan",
        input_text=sql, timeout=90
    )
    print("PASS: additive auth schema and restricted role provisioned")


def check_role() -> None:
    # Individual privilege checks are essential: comma-separated has_* checks
    # are ANY-of in PostgreSQL and may silently overlook missing grants.
    query = """
SELECT
  has_schema_privilege('panadan_auth_runtime','panadan_auth','USAGE'),
  NOT has_schema_privilege('panadan_auth_runtime','panadan_auth','CREATE'),
  has_table_privilege('panadan_auth_runtime','panadan_auth.users','SELECT'),
  has_table_privilege('panadan_auth_runtime','panadan_auth.users','INSERT'),
  has_table_privilege('panadan_auth_runtime','panadan_auth.users','UPDATE'),
  has_table_privilege('panadan_auth_runtime','panadan_auth.users','DELETE'),
  NOT has_table_privilege('panadan_auth_runtime','panadan_auth.users','TRUNCATE'),
  NOT has_table_privilege('panadan_auth_runtime','panadan_auth.users','REFERENCES'),
  NOT has_table_privilege('panadan_auth_runtime','panadan_auth.users','TRIGGER'),
  NOT has_schema_privilege('panadan_auth_runtime','panadan_ingest','USAGE'),
  NOT has_table_privilege('panadan_auth_runtime','panadan_ingest.sources','SELECT'),
  NOT has_database_privilege('panadan_auth_runtime',current_database(),'CREATE');
"""
    result = run(
        "docker", "exec", PG, "psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1",
        "-U", "panadan_owner", "-d", "panadan", "-c", query,
    )
    if result != "|".join(["t"] * 12):
        raise Refusal("Restricted auth runtime role privilege audit FAILED")
    print("PASS: auth role DML allowed, ingestion/schema/DDL access denied")


def apply() -> None:
    preflight()
    stage = network_stage()
    audit_network(stage)
    source_routes()
    endpoints()
    current_db_backup()

    # Reuse valid internal network and existing endpoints where possible. Only
    # attachments made by this invocation can be rolled back automatically.
    created_network = False
    created_endpoints: list[str] = []
    try:
        if inspect_network() is None:
            run("docker", "network", "create", "--driver", "bridge", "--internal", NET)
            created_network = True
        net = inspect_network()
        if net is None:
            raise Refusal("Failed to create internal bridge")
        if net.get("Driver") != "bridge" or net.get("Internal") is not True:
            raise Refusal("Auth network is not internal")
        new_subnet_safe(net)
        members = {v.get("Name") for v in (net.get("Containers") or {}).values()}
        if members not in (set(), {PG, VPN}):
            raise Refusal("Network partially attached or has unexpected members")
        if not members:
            run("docker", "network", "connect", "--alias", "panadan-auth-postgres", NET, PG)
            created_endpoints.append(PG)
            run("docker", "network", "connect", NET, VPN)
            created_endpoints.append(VPN)
        audit_network("after")
        source_routes()
        endpoints()
        tcp_smoke()
        print("PASS: live network-only connectivity verified without restarting services")
        schema_apply()
        check_role()
        endpoints()
        print("PASS: owned PG auth foundation ready; live SQLite auth is unchanged")
    except Exception:
        for name in reversed(created_endpoints):
            try:
                run("docker", "network", "disconnect", NET, name, timeout=20)
            except Refusal:
                print(f"WARNING: manual review needed: {name} remains attached")
        if created_network:
            try:
                run("docker", "network", "rm", NET, timeout=20)
            except Refusal:
                print("WARNING: owned auth bridge remains; inspect before retrying")
        raise


def initialize_platform() -> None:
    # Fresh deployments only. No application or Plane container is touched.
    # Unlike a simple process check, ps -a also catches stopped containers.
    # Never mistake a stopped/failed production DB for a new installation.
    if run("docker", "ps", "-a", "--filter", "name=^/panadan-platform-db-1$",
           "--format", "{{.Names}}"):
        raise Refusal("Existing (including stopped) owned PostgreSQL container: treat as recovery")
    if run("docker", "volume", "ls", "--filter",
           "name=^panadan-platform_panadan_platform_pg18_data$",
           "--format", "{{.Name}}"):
        raise Refusal("Existing owned PostgreSQL data volume: treat as recovery")
    if (ROOT / ".env.platform").exists() or (ROOT / ".env.platform.roles").exists():
        raise Refusal("Existing platform credentials: confirm recovery, not fresh initialization")
    run("bash", "tools/platform-db.sh", "setup")
    run("bash", "tools/platform-db.sh", "up", timeout=150)
    run("bash", "tools/platform-db.sh", "init")
    if not (ROOT / ".env.platform.roles").exists():
        run("bash", "tools/platform-roles.sh", "setup")
    run("bash", "tools/platform-roles.sh", "apply")
    run("bash", "tools/platform-db.sh", "check")
    run("bash", "tools/platform-roles.sh", "check")
    print("PASS: fresh owned PG18 initialized; deploy VPN/Web separately then run plan/apply")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "apply", "verify", "init-platform"))
    parser.add_argument("--ack-restored-backup", action="store_true",
                        help="Explicitly acknowledge independent off-VPS PG restore")
    parser.add_argument("--approve-live-network", action="store_true",
                        help="Explicitly approve non-restart Docker network attachment")
    parser.add_argument("--approve-new-db", action="store_true",
                        help="Explicitly approve fresh owned database creation")
    args = parser.parse_args()
    try:
        if args.command == "init-platform":
            if not args.approve_new_db:
                raise Refusal("First-time DB startup requires --approve-new-db")
            initialize_platform()
            return 0
        preflight()
        if args.command == "plan":
            stage = network_stage()
            audit_network(stage)
            source_routes()
            endpoints()
            print("PASS: no changes made; run apply with BOTH explicit acknowledgments to proceed")
            return 0
        if args.command == "verify":
            audit_network("after")
            source_routes()
            endpoints()
            tcp_smoke()
            check_role()
            print("PASS: app services still use existing SQLite Store (no auth cutover)")
            return 0
        if not args.ack_restored_backup or not args.approve_live_network:
            raise Refusal("apply requires --ack-restored-backup AND --approve-live-network")
        # Never invoke Docker changes before acquiring exclusive process lock.
        LOCK.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with LOCK.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            apply()
    except (Refusal, BlockingIOError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
