# Implementation Status

- [x] FastAPI routes and dashboard templates
- [x] Hashed admin credentials, revocable cookie sessions, login throttle, CSRF checks
- [x] Scoped and expiring API/MCP bearer tokens
- [x] MCP tools served on Streamable HTTP and guarded at ASGI HTTP boundary
- [x] Parameterized hardcoded read-only Odoo view queries
- [x] Docker Compose isolated OpenVPN network + local-only port binding
- [x] Initial tests and GitHub Actions workflow
- [ ] Verify full Docker build and integration against user's WSL environment
- [ ] Verify MCP client handshake with chosen consumer client
- [ ] Configure proper HTTPS, host validation and OAuth when opening externally
- [ ] Validate source-system meaning of `SoldOut`, `voice_length`, `deal_value`

- [x] Rebrand to Panadan and rename GitHub repository target
- [x] Add local Docker image fallback without Docker Hub base pulls
- [ ] Run `up-local` on user's Docker Desktop / WSL setup
