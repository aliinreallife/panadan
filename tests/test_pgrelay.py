import ast
from pathlib import Path


def test_relay_parses():
    ast.parse(Path('tools/pgrelay.py').read_text())


def test_dev_compose_binds_loopback_only():
    y = Path('compose.dev.yaml').read_text()
    assert '127.0.0.1:${PANADAN_PG_PROXY_PORT:-15432}:15432' in y
    assert 'network_mode: service:vpn' in y
    assert 'pull_policy: never' in y


def test_vpn_has_fail_closed_database_egress_rule():
    s = Path('start-vpn.sh').read_text()
    assert 'iptables -I OUTPUT 1 -d 192.168.3.9/32 ! -o tun+ -j REJECT' in s
