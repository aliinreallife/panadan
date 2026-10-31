"""TCP relay for localhost-only dev DB access; all outgoing DB traffic uses the VPN namespace.

Never expose port 15432 to a public interface. This is a byte relay, not a SQL proxy.
"""
import os
import select
import socket
import socketserver
import logging

HOST = os.environ.get("PANADAN_PG_TARGET", "192.168.3.9")
PORT = int(os.environ.get("PANADAN_PG_TARGET_PORT", "5432"))

class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            remote = socket.create_connection((HOST, PORT), timeout=10)
        except (OSError, ValueError) as exc:
            # Connection errors from the remote host are not credential errors.
            # Never print addresses, secrets, socket payloads or exception text.
            logging.warning("Remote PostgreSQL TCP connect failed: %s", type(exc).__name__)
            return
        try:
            with remote:
                self.request.settimeout(None)
                remote.settimeout(None)
                streams = [self.request, remote]
                while True:
                    ready, _, _ = select.select(streams, [], [], 60)
                    if not ready: continue
                    for source in ready:
                        payload = source.recv(65536)
                        if not payload: return
                        (remote if source is self.request else self.request).sendall(payload)
        except (OSError, ValueError) as exc:
            logging.warning("PostgreSQL relay forwarding interrupted: %s", type(exc).__name__)

class ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with ThreadedServer(("0.0.0.0", 15432), Relay) as server:
        logging.info("Local development DB relay listening on 15432")
        server.serve_forever(poll_interval=0.5)
