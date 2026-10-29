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

## v0.4 in progress (review branch, not merged)

- [x] Distinct local roles and capability-based permissions, API/MCP token ownership
- [x] Local account lifecycle + session/token invalidation on disable/change
- [x] Explicit PostgreSQL READ ONLY transaction boundary
- [x] Panadan-formatted transcript view with exact Raw toggle and parser regression tests
- [x] Doran Jalali/date-time integration code and self-hosted Vazirmatn build instructions
- [x] Local MCP setup and ChatGPT/tunnel limitations documented
- [ ] Generate/install npm frontend dependencies, test the datepicker in a browser
- [ ] Run full FastAPI/MCP test suite with uv in WSL (needs Python 3.12 dependencies)
- [ ] OAuth 2.1 authorization-code + PKCE integration for ChatGPT, if required
- [ ] Security review before exposing any endpoint publicly
