# Panadan repository instructions

Before planning or modifying code, read and follow [AGENTS.md](../AGENTS.md) and [the accepted product decisions](../docs/knowledge-platform/DECISIONS.md). Preserve existing security and read-only source guarantees, distinguish target design from implemented behavior, and avoid customer-specific core forks. Work on the authorized feature branch; do not deploy or change production without separate approval. Never commit real customer data or secrets.

Mandatory: whenever the product owner approves a new or changed decision, update `docs/knowledge-platform/DECISIONS.md` in the same task (even without code changes), following the decision maintenance protocol in that file and `AGENTS.md`. Preserve stable IDs and history, update affected guidance, and report any inability to persist the decision. Do not publish confidential details.
