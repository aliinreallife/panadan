# Panadan v0.3 status

- [x] FastAPI, responsive Persian RTL dashboard and scoped API/MCP auth preserved from v0.2
- [x] WSL-native uv development entrypoint with Docker-isolated VPN and localhost DB relay
- [x] pyproject.toml with dev dependency group and Python 3.12 constraint
- [x] Production uv Dockerfile and GitHub Actions test/build workflow
- [x] No bundled .env, customer data, VPN profiles, keys, or real database outputs
- [ ] **Generate and commit real uv.lock on WSL** (index not reachable during packaging)
- [ ] Verify WSL dev relay and DB SSL with `./panadan.sh dev`
- [ ] Confirm dashboard login, API token and MCP handshake
- [ ] Configure private GHCR package access + image deployment
- [ ] Production: TLS, OAuth 2.1 as needed for remote MCP, external host security review
- [ ] Clarify `SoldOut`, `voice_length`, and `deal_value` semantics with source owner
