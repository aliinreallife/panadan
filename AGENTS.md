# Panadan — instructions for coding agents

Before planning, editing code, proposing architecture or changing product behavior, read:
1. [Knowledge platform decisions](docs/knowledge-platform/DECISIONS.md) — accepted new product direction and MVP boundaries.
2. [Existing decisions](docs/DECISIONS.md), [original reporting PRD](docs/PRD.md) and [status](docs/STATUS.md) — baseline and implementation history.
3. [Security requirements](docs/SECURITY.md), [read-only rules](docs/READ_ONLY.md) and relevant operational documentation.

## Working rules
- This is an existing system, not a greenfield project. Inspect code and tests before planning; distinguish implemented, documented, proposed and production-verified behavior.
- Work on `feature/knowledge-platform` or an explicitly authorized descendant branch. Preserve main and backup; do not merge, deploy, migrate production, or change live data without explicit authorization.
- Treat the knowledge-platform decision register as authoritative for target product direction, while existing operational/security constraints remain enforced. Surface conflicts rather than silently overriding them.
- Prefer incremental, additive and reversible changes; preserve existing reporting, API, MCP, auth and access controls. Audit and classify reuse/extend/refactor/build/remove before rewriting.
- Keep source databases read-only. Use separately authorized destination integrations for knowledge sync. No arbitrary SQL execution. Enforce tenant isolation, least privilege and current connection scope on server and workers; do not loosen sensitive-data policies.
- Never commit credentials, real customer records, call transcripts, private business details or unapproved commercial strategy. This repository is public. Use synthetic test data.
- Record decision changes only after owner approval, with stable decision IDs. Keep proposals separate from accepted decisions. Update implementation status and tests based on actual evidence.
- First milestone: read-only infrastructure audit and gap analysis, then pilot discovery and scoped PRD. Do not assume candidate use cases are final.
- Follow existing project commands and locked dependencies (see README); report tests run, failures and unverified areas.
