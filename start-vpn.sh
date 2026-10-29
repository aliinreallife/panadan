#!/bin/sh
set -eu
# Lock traffic destined for the PostgreSQL host to OpenVPN's tun interface.
# Any direct attempts to 192.168.3.9 through eth0 get rejected.
iptables -I OUTPUT 1 -d 192.168.3.9/32 ! -o tun+ -j REJECT

# Ignore server-pushed default-gateway redirection. Other pushed routes still
# apply (including the database host route); the explicit host route is a
# fallback if the VPN server doesn't push it. This only affects the container.
exec openvpn --config /vpn/client.ovpn \
  --pull-filter ignore redirect-gateway \
  --route 192.168.3.9 255.255.255.255
