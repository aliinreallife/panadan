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

## 6. Supplemental interaction concept (owner-supplied reference, 2026-11-26)

The additional textual Product Design Concept complements the previously approved D-066 visual direction. It is useful design input, not a new accepted product decision or replacement for the PRD, architecture, data model or roadmap. Exact screen layout, navigation, tokens, dark mode and any expanded capability remain proposals for detailed UI review. The source document is not republished verbatim; examples below describe design intent, not real metrics or customer information.

### 6.1 Recommended design synthesis

- Knowledge Journal: warm editorial visual identity, meaningful discoveries rather than a KPI-only dashboard.
- Intelligence Workbench: efficient multi-pane research and review, persistent search/filter/selection state, inspectable evidence and context.
- Intelligence Hub: modular applications, shared discovery and role-appropriate access to infrastructure.

Design around three questions: what do we know, why do we know it, and what can we do with it? Maintain the approved Persian-first RTL design direction; retain current reporting access for authorized legacy users.

### 6.2 Proposed navigation and reusable interaction patterns

Five primary environments are a candidate for U0 navigation review, not final routes or permission grants:

| Environment | Candidate grouping |
| --- | --- |
| Home / خانه | Role-appropriate daily intelligence briefing, discoveries, assigned review and operational next actions |
| Explore / کاوش | Authorized resource search, topic discovery and independently identified Resource/Knowledge/Package results |
| Knowledge / دانش | Knowledge Base, evidence/review queue, taxonomy, packages |
| Applications / برنامه‌ها | Customer Intelligence and Content Intelligence; no enabled future apps by implication |
| Infrastructure / زیرساخت | Source integrations, objectives, pipelines/runs, AI gateway/usage, API/MCP and separate destination distribution |

Organization settings, workspace selection, effective access previews, audit and authorized legacy reporting/health remain discoverable. Role-specific defaults are suggested presentation choices, not additional access grants or separate identities. Verify permissions at the service boundary for all navigation, count, query and detail paths.

Recommended shared Knowledge Inspector: category/filter navigation on the right, results in the middle and contextual detail/evidence on the left on suitable desktop widths. Preserve filter, selection and scroll when switching findings; provide full-page or drawer detail and sequential technical forms on narrow screens. Reuse inspector components across Knowledge Base, review, applications and packages, but do not reuse cached payloads across permission changes. Distinguish claim, contextual conditions, source/evidence, reliability, prevalence, importance, freshness, coverage and revision. Review supporting, contradictory and insufficient evidence separately, with permitted context and recorded rationale. Show no arbitrary universal confidence score.

Other useful interaction guidance: Home as a briefing with actionable role-scoped findings and operational alerts; guided source configuration with scope preview and approval; objective forms framed as research questions with progressive disclosure of typed schema and validation settings; readable pipeline stages (not a visual node editor) with separate pause/cancel/retry, failed items, costs and history; Content Intelligence opportunity-to-brief-to-authorized-MCP journey without manual copying or a CMS; effective connection permissions and revocation preview; mobile optimized for reading, discovery, monitoring and lightweight review while keeping required configurations accessible.

### 6.3 Candidate token system for U0 review

The supplemental text proposes Forest #293F34, Sage #A4B5A0, Ink #202822, Canvas #F6F5F1, Surface #FFFFFF, Border #DADFD7. These are alternate candidate tokens alongside the first visual reference, not a final replacement palette. It also proposes Vazirmatn/Inter, 4px spacing, 40px default controls, minimum 44px mobile touch targets, 6–12px corners, subtle functional shadows, consistent outline icons, muted data visualization and roughly 150–250ms functional motion. Evaluate contrast (especially sage and semantic colors on light backgrounds), Persian/Latin typography, existing assets and reduced-motion support. The semantic status palette needs accessible exact tokens and non-color indicators. Dark-mode concept is optional/deferred unless separately prioritized; no requirement to deliver it in the MVP. Exact logo, fonts, tokens and responsive breakpoints require detailed review.

### 6.4 Scope reconciliation — do not copy conflicting mockup behavior

| Concept suggestion | Governing implementation boundary |
| --- | --- |
| Active CRM and other broad source integrations | D-028: initial call source, bounded manual text/doc and selected approved web MVP. CRM and additional connectors deferred. Future items cannot appear active. |
| Inspector or reviewer opens original transcript | D-035/D-037/D-051: display only authorized filtered representations and bounded permitted context/provenance; no raw original persistence, new raw export or implicit source access. Source remains read-only. |
| Package follows approved updates automatically | D-063: pinned exact knowledge revisions in MVP; authorized new package version for updates, no silent follow-latest. |
| Semantic universal search and cross-category relationships/merges | D-053/D-063: start with scoped bounded text/structured search and simple versioned category hierarchy/suggestions. No speculative vector/graph dependency; richer retrieval/relationships and automatic structural changes require separate review. |
| Monthly budget and audio processing costs | D-045/D-064: organization and execution caps, exact period/currency/rates still open; no audio ingestion or retranscription. Show estimated/reported/unknown and uncertain charges, no invented usage. |
| Connected ChatGPT or other named clients, invitation/self-service flows | D-016/D-055: only verified approved connections and granted data scope; existing identity authority/assisted setup preserved. No assumption of compatibility, access or new self-service identity mechanism. |
| Six-week or organization-wide trends and causal claims | D-025/D-040/D-044: first real pilot one operator/30 days; actual scoped population and measured denominator/coverage, no market-wide or causal inference merely from mentions. Synthetic examples are not evidence. |
| Future application directory and dark mode | Future apps explicitly unavailable, optional discovery only if useful; no new app or theme commitment from this reference. |

Keep the independently authorized one-way destination distribution and legacy reporting/health workflows from the original review even though the supplemental concept does not fully specify them. Missing or restricted data is not contradiction or negative finding. Do not expose hidden resource existence via counts, search snippets, status, inspector or errors.

### 6.5 Implementation handoff

Use the supplemental concept as a design input within existing [ROADMAP.md](ROADMAP.md) U0–U11. U0 reviews navigation and exact token/components; U1 reviews briefing/workspace/access; U2 resource inspector/source setup; U3 research objectives and execution plans; U4 budgets; U5/U6 reusable evidence inspector and review/taxonomy; U7/U8 shared customer/content journeys; U9 pinned package and effective client-grant previews; U10 destination/integration setup; U11 responsive/accessibility and full journey verification. Detailed designs use synthetic data only. No roadmap scope or milestone approval is changed by this addendum; Phase 7 remains awaiting approval. No new D-ID until the owner explicitly accepts a substantive additional choice.
