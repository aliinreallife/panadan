# Panadan — instructions for coding agents

Before planning, editing code, proposing architecture or changing product behavior, read:
1. [Knowledge platform decisions](docs/knowledge-platform/DECISIONS.md) — accepted new product direction and MVP boundaries.
2. [Existing decisions](docs/DECISIONS.md), [original reporting PRD](docs/PRD.md) and [status](docs/STATUS.md) — baseline and implementation history.
3. [Security requirements](docs/SECURITY.md), [read-only rules](docs/READ_ONLY.md) and relevant operational documentation.

## Mandatory decision updates

The [decision maintenance protocol](docs/knowledge-platform/DECISIONS.md#decision-maintenance-protocol-mandatory) is binding for every task. When the owner approves a new or revised decision, update the canonical register immediately in the current task, even when no code changes are requested. Read the latest register, allocate a stable new ID, record the date/rationale/scope, preserve superseded history and update affected guidance. Never record unapproved proposals as decisions. Decision documentation is part of the definition of done; verify the diff and report the ID and files changed. If the repo cannot be updated, report the decision as not persisted and supply the draft entry. Do not publish confidential decisions in this public repo. Commit/push only within authorized scope.

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
