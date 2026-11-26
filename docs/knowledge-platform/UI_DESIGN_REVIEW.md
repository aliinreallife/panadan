# Panadan — UI Design Direction Review

Date: 2026-11-26 | Status: Visual direction approved by owner as D-066, with required additions; detailed UI and production assets remain subject to review.
Basis: owner-supplied composite visual reference reviewed against [PRD.md](PRD.md) §12, [ARCHITECTURE.md](ARCHITECTURE.md), and [DECISIONS.md](DECISIONS.md). The image itself is not republished to the public repository. Its figures and examples are illustrative, not operational metrics. This review does not replace product requirements. D-066 records the subsequent explicit owner approval of the direction and required additions; it does not approve final logo assets or authorize implementation.

## 1. Visual direction

Retain the reference's visual character: quiet warm neutral surfaces, muted green/olive accents, restrained borders, editorial typography, professional knowledge-workspace character, compact but readable information hierarchy, Persian RTL with mixed English technical labels, and responsive adaptations. The leaf-like identity and wordmark are a preferred concept, not final production vector artwork. Verify exact design tokens from the original editable source, contrast, typography licensing and accessible component states before implementation. Avoid extracting precise color/typography tokens from a small generated composite image.

The supplied reference is a product concept board. Its miniatures do not demonstrate complete interaction, accessibility, permission enforcement or production readiness. Navigation structure and final component choices remain open to better UX solutions consistent with the same direction.

## 2. Fit against approved MVP

| Reference section | Fit | Completion requirement |
| --- | --- | --- |
| Organization Overview | Strong | Add explicit workspace, pilot population/period, actual processing coverage and status, review priorities, budget-blocked work and role-appropriate next actions. Avoid unsupported totals. |
| Resources Explorer | Strong | Detail with source/representation/revision lineage, availability and authorized evidence access; search/filter/pagination; no source edit or delete. |
| Knowledge Base | Strong | Separate proposed/review/active/disputed/outdated; show subject, contextual conditions, version, scope, freshness and permissions. |
| Evidence & Validation | Foundation | Show supporting/contradictory evidence, independence and source authority, reliability/prevalence/importance separately, denominator/coverage, review rationale and history. Do not reduce trust to one percentage. |
| Knowledge Package Builder | Strong | Version-aware selection of permitted knowledge, pinned versions, stale/revoked state, recipient access and preview of permitted projection. |
| Customer Intelligence | Foundation | Add scoped insight feed, limited analytical charts/filtering, distinct call denominator and coverage, detail drill-down; no customer profiles or market-wide inference from pilot. |
| Content Intelligence | Foundation | Add opportunity list/detail, full brief, intended audience, outline, source knowledge and evidence, uncertainty, authorized MCP drafting instructions. No in-panel article editor or publishing. |
| Integrations | Foundation | Add source configuration, approved scope, manual text/doc and approved web setup, sync state/history, source contract warnings and errors; no secrets rendered. |
| AI Gateway | Foundation | Add provider/model approval and explicit selection, request/run/pipeline attribution, org and execution caps, estimated/reported/uncertain charges, budget-blocked state. No billing/BYOK UI in MVP. |
| API/MCP | Foundation | Add connection setup, effective grants and consent, independent resource/knowledge scope, package/evidence preview, activity, revocation and connection errors; separately authorized destination sync. |
| Organization Settings | Foundation | Add workspace switch/access boundaries, member grants, roles, privacy/disclosure policy, audit and restricted admin views. |
| Mobile and UI states | Strong starting point | Extend to detail/review and configuration workflows; keyboard/accessibility, responsive tables, error/partial/stale/permission/budget states. |

## 3. Essential missing or under-specified workflows

- Knowledge Objectives: template catalog (seven accepted initial objectives), editable instance and simple structured custom objective; permitted sources, expected typed output, context, validation, version and status.
- Pipelines & Runs: pipeline list/detail, scope and approved source selection, objective/model/policy configuration, schedule, run preview, execution budget, run status and coverage, failed items, pause/resume and history. No full visual workflow builder.
- Knowledge Taxonomy: category/subcategory browser, AI suggestions with evidence, authorized review and versioned edits; no automatic mutation.
- Review Queue: actionable list of assigned/authorized candidates with validation reason and risk, evidence detail, review history; not just a static knowledge list.
- Distribution: separate one-way destination configuration, approved projection preview, delivery status, retry/reconciliation, revoked/stale versions; no source mutation.
- Legacy Reporting and System Health: preserve existing authorized reporting/calls/operators/token workflows and operational health; new tenants do not automatically inherit legacy access.

Sections can be grouped, renamed or combined. The workflow coverage, not the number of screens, is the requirement.

## 4. Interaction and data-display guardrails

1. Show operator, exact period, population and coverage whenever findings depend on sampled calls. Counts are calls, not people, unless independently established. The pilot is one authorized operator and 30 days, not all customer data.
2. Unknown, incomplete, no data, stale, restricted and failed states must be distinct. Hide unauthorized resource existence, counts, titles and evidence.
3. Resources and Knowledge are distinct; original source data cannot be altered/deleted by Panadan. Redaction happens only on permitted local representations.
4. Every authoritative finding has inspectable permitted evidence and contextual scope. Review states cannot override access or privacy policy.
5. AI costs are governed by org and execution caps; show budget-blocked, uncertain and reconciled outcomes accurately. No real cost numbers from the reference image.
6. Preserve accessible RTL, mixed Persian/English layout, readable density, keyboard focus, non-color-only status, legible mobile details and loading/error states.
7. No actual customer content or private configuration in mockups or public artifacts. Use synthetic data. Role-appropriate navigation is not authorization; backend checks are mandatory.
8. Do not present future applications, unapproved providers, connections or functions as implemented/available.

## 5. Handoff

Approved direction (D-066): adopt this visual language, extend it with the missing workflows above, and review individual desktop/mobile screens and a component/token specification before final detailed UI approval. Design team may reorganize navigation and interactions without sacrificing requirements. Exact tokens, logo assets, components and screen implementations are not approved merely by direction approval.

Implementation roadmap should include UI deliverables alongside each functional vertical slice, rather than redesigning the full application after backend completion. See PRD §12 for governing functionality and Phase 6 data model for proposed data/permission states.
