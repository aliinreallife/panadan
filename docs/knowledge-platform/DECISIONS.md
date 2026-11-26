# Panadan Knowledge Platform — Product and architecture decisions

Status: accepted product direction; implementation and production readiness are NOT implied.
Baseline: `44561cad16e17b7e60287dc8e0d7a7210fc5d32a` (main); development branch `feature/knowledge-platform`; preserved backup `backup/pre-knowledge-platform-2026-11-25`.
Decision source: product-owner negotiation, November 2026. This document is the source of truth for the new product direction, not a replacement for existing operational/security documentation.

## Purpose

Evolve the existing read-only reporting product into a reusable organizational knowledge platform. Collect internal/external resources, derive evidence-backed knowledge, and enable practical applications and authorized external access. Reuse existing code and infrastructure; deliver incrementally without breaking existing users. The pilot customer's identity and internal commercial strategy are not part of this public document.

## Accepted decisions

| ID | Decision | Accepted direction |
| --- | --- | --- |
| D-001 | Resources | Merge Raw Data and Resource into one product concept. Preserve raw originals, derivatives, provenance and processing history. |
| D-002 | Product strategy | Infrastructure First, Application Enabled; build a reusable core and selected applications on top. |
| D-003 | Knowledge validation | Risk-based hybrid validation: automated checks where justified; additional evidence and human review where risk requires it. |
| D-004 | Knowledge structure | Hybrid Knowledge: independently versioned atomic knowledge units plus collections/documents assembled from them. |
| D-005 | Storage | Hybrid Storage, minimal MVP: stored, referenced or synchronized resources according to security, need and agreement. |
| D-006 | Pilot | Start with one designated customer; the latest owner-designated pilot supersedes earlier proposals. Confirm customer-specific needs through deployment discovery. |
| D-007 | Knowledge authority | Panadan is the authoritative manager of its knowledge lifecycle. One-way sync of authorized, validated knowledge to the customer's database; changes made through Panadan, no bidirectional database editing. |
| D-008 | Discovery | Hybrid Discovery, goal-driven first; bounded discovery of useful findings outside predefined objectives. |
| D-009 | Processing | Hybrid Processing: event-driven, scheduled and on-demand; favor scheduled and manual processing initially, event-driven only where justified. |
| D-010 | Deployment | Assisted Self-service, closer to managed service initially; deployment team handles setup and specialist configuration, customer gains autonomy over time. |
| D-011 | Knowledge scope | Private and Shared Knowledge, minimal MVP. Private by default; shared knowledge only from permitted sources and under explicit access policies. |
| D-013 | Knowledge Packages | Support reusable, version-aware knowledge packages in MVP; consumption through authorized interfaces. |
| D-015 | Applications | Hybrid Applications: shared execution engine, ready-made configurable applications first. No full visual agent/workflow builder for MVP. |
| D-016 | Authorization | Hybrid Access Control: role templates, customizable permissions, least privilege; server-side enforcement and audit. |
| D-017 | MVP scope | End-to-End Vertical Slice for the designated pilot: resources to knowledge to real applications, with limited sources and applications. |
| D-018 | Development approach | Use Case-driven Infrastructure; start from real pilot needs and implement reusable features rather than customer-specific core forks. |
| D-019 | AI execution | Controlled Agentic Architecture: defined pipelines in core, limited agents in applications; deterministic code/SQL where AI is unnecessary. |
| D-020 | AI Gateway | Centralized multi-model architecture; initially explicitly configure provider/model per task or pipeline. Defer intelligent routing. |
| D-021 | Validation method | Evidence-based Knowledge Validation; explicit rules, inspectable evidence, source authority by subject, context, freshness and conflict handling first. |
| D-022 | Data model | Core Schema + Extensible Attributes: typed, validated extensions and contextual/temporal scope. No advanced schema builder in MVP. |
| D-023 | Organization architecture | Shared Core + Organization Workspace; configuration over custom code, isolated customer workspaces and reusable modules. |
| D-024 | Initial application priorities | Start with limited Customer Intelligence and Content Intelligence on shared reusable infrastructure; plan Market Intelligence as a subsequent extension, with its release scope and timing still open. |
| D-025 | Customer intelligence granularity | Hybrid individual and aggregate analysis, with aggregate insights prioritized for the initial MVP; retain extensibility for authorized individual analysis. |
| D-026 | Customer intelligence delivery | Hybrid delivery: evidence-backed insight feed, limited analytical dashboard and conversational access through authorized MCP initially; dedicated conversational UI later. |
| D-027 | Content intelligence scope | Hybrid Content Intelligence: evidence-backed discovery and content briefs first, limited AI/MCP-assisted draft generation in MVP; content management and approved publishing integrations later. |

Decision identifiers preserve the original negotiation numbering; gaps intentionally do not expose internal strategy.

## Decision maintenance protocol (mandatory)

This is a living decision register, not a one-time handoff. Every contributor, including AI agents, is responsible for keeping it current.

- Read the latest register from the working branch at the start of every task. Consult relevant existing decisions before making recommendations or edits.
- When the product owner explicitly approves a new or changed product, architecture, security, data-model, UX policy, or MVP-scope decision, update this register in the same task, even if no code is requested. A clear approval in a discussion is sufficient; do not ask for redundant approval to document it. Do not treat AI recommendations, examples, silence, or unresolved alternatives as accepted decisions.
- Check existing IDs and the latest history first. Allocate the next unused sequential ID (next: D-024 as of this protocol's introduction); never reuse or renumber an ID, including historical gaps. Add a row to the accepted decisions table and a dated entry in Decision history. For a change to a prior decision, allocate a new ID, identify the superseded ID, retain its historical wording, mark it superseded, and update all affected current guidance. The active decision, not the old wording, governs future work.
- For each new decision, capture ID, date (ISO 8601), title, status (Accepted / Superseded), accepted choice, rationale, MVP vs later scope when applicable, constraints, and affected documents/components. Record the approval source in safe terms, e.g. "owner discussion"; never copy private chats or confidential details into this public repository.
- Update affected PRD, architecture, security, tests or other maintained documents if applicable; preserve the distinction between decisions and verified implementation. An approved design is not evidence of implementation or deployment. Keep proposals outside the accepted register until approved.
- Documentation is part of the definition of done: check the diff, confirm the register and related guidance agree, and report decision IDs and files changed. When authorized to commit/push, include the decision update in the same branch/PR as its implementation, or a documentation-only commit if the decision precedes code. Never merge or deploy merely to record a decision.
- If repository access, write permission, or an approved branch is unavailable, provide the proposed register entry and explicitly report it as NOT persisted. Do not claim that conversational memory alone updated the repository. If a decision is confidential, do not place its private content in this public repo; use an approved private location only if available and authorized, otherwise flag the private record as pending.
- Routine bug fixes and implementation details that do not change agreed product behavior do not require a new product decision; update relevant technical documentation and tests where needed.

### Decision history

| Date | IDs | Event |
| --- | --- | --- |
| 2026-11 | D-001–D-023 (public subset) | Initial accepted product direction imported from owner negotiation; see accepted decisions table. |
| 2026-11-25 | — | Owner requested ongoing decision maintenance; mandatory documentation and agent handoff protocol introduced. |
| 2026-11-26 | D-024 | Owner selected initial application priorities during pilot discovery. |
| 2026-11-26 | D-025 | Owner selected hybrid customer intelligence with aggregate-first delivery. |
| 2026-11-26 | D-026 | Owner selected hybrid delivery for Customer Intelligence. |
| 2026-11-26 | D-027 | Owner selected hybrid Content Intelligence with discovery and strategy prioritized. |

Append dated entries for future accepted decisions and supersessions. Do not erase prior entries.

### D-024 — Initial application priorities
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Begin with Customer Intelligence and Content Intelligence in a limited scope on a common, extensible infrastructure. Market Intelligence is also a desired application direction, with the initial two applications prioritized first.
- Rationale: Choose simpler initial applications that demonstrate reuse and provide a scalable foundation rather than creating separate application-specific knowledge silos.
- MVP scope: Initial application selection is Customer Intelligence and Content Intelligence. Exact workflows, outputs, source permissions, validation rules, measurable acceptance criteria and delivery scope remain subject to discovery and the scoped PRD.
- Deferred / out of scope: No fixed release date or committed initial-MVP scope for Market Intelligence; its source requirements and incremental scope are pending discovery. No automatic public content publication.
- Constraints and implications: Preserve independent resource and knowledge access, common evidence-backed knowledge, configurable application execution, tenant isolation, source read-only and privacy constraints under existing decisions. Do not assume access to unconfirmed sources or promise market-wide conclusions from customer conversations alone.
- Supersedes: None; refines application selection under D-015, D-017 and D-018.
- Affected documents/components: MVP boundaries below; future knowledge-platform PRD, architecture, roadmap, shared Resources/Knowledge Engine/Knowledge Base and application configuration. Phase 2 gap analysis remains a historical snapshot; D-024 resolves its initial application selection question, not all discovery requirements.

### D-025 — Customer intelligence granularity
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Support both individual and aggregate customer intelligence as an extensible product direction; prioritize aggregate analysis for initial delivery.
- Rationale: Aggregate insights support customer, content and later market intelligence with less dependency on cross-system identity matching and a reusable shared knowledge foundation.
- MVP scope: Focus on evidence-backed patterns within defined populations, periods and conditions. Preserve extensibility for authorized individual analysis; this does not require individual profiling, identity resolution or CRM enrichment in the initial release.
- Deferred / out of scope: Detailed individual workflows, identity matching and profile access rules remain to be discovered and approved. Exact aggregate categories, measures, reporting periods and thresholds are not yet selected.
- Constraints and implications: Keep observations and inferred patterns distinct, retain provenance and authorized scope, distinguish call counts from unique customer counts where identity is not reliably established, avoid unsupported population-wide inference. Aggregation alone is not anonymization; protect small groups, sensitive fields and evidence drill-down under existing authorization and data policies. No unnecessary collection of individual identifiers.
- Supersedes: None; refines D-024 and D-022.
- Affected documents/components: Customer Intelligence, shared knowledge schema, validation and application configuration; future scoped PRD, data model and acceptance tests.

### D-026 — Customer intelligence delivery
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Combine an evidence-backed Knowledge & Insight Feed, a limited Analytical Dashboard, and Conversational Intelligence through authorized MCP access initially. Defer a dedicated first-party conversational interface.
- Rationale: Make reusable, inspectable knowledge the primary value while providing complementary analytical and conversational ways to consume it. Reuse the existing web and MCP foundations instead of building a separate chatbot stack first.
- MVP scope: Provide a feed of supported findings with context, provenance and permitted evidence inspection; a limited dashboard over the same scoped data and knowledge; and conversational access via reviewed, authorized MCP tools. Exact metrics, filters, presentation, insight refresh and MCP tool contracts remain pending discovery and scoped PRD.
- Deferred / out of scope: Dedicated conversational UI, broad custom analytics builder and unrestricted natural-language querying are not required in the initial release.
- Constraints and implications: Preserve aggregate-first scope under D-025. All surfaces must use consistent authorization, evidence, definitions and freshness; distinguish observations from validated knowledge, insufficient data and uncertainty. Do not disclose restricted evidence, infer unique customer counts from call counts, or permit unrestricted SQL. Existing MCP transport is reusable, but new knowledge retrieval and client compatibility require implementation, security verification and separate release approval; no existing access is broadened by this decision.
- Supersedes: None; refines D-024 and D-025, consistent with D-015 and D-016.
- Affected documents/components: Customer Intelligence feed/dashboard, shared knowledge retrieval and aggregation, API/MCP access, future scoped PRD and acceptance tests.

### D-027 — Content intelligence scope
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Deliver hybrid Content Intelligence progressively: discover evidence-backed content opportunities, provide content strategy through briefs and outlines, and support limited AI/MCP-assisted draft generation. Reuse the same authorized Resources and Knowledge as Customer Intelligence rather than creating a separate extraction or knowledge silo.
- Rationale: The primary value is identifying why content is useful, which audience it serves, and the supporting evidence; generation is complementary and should not turn the initial product into a CMS.
- MVP scope: Content discovery and strategy, including supported topics, audience, objective, suggested format and outline where evidence permits; limited draft generation through governed AI execution and authorized MCP. Exact formats, prioritization metrics, workflows, data availability and acceptance criteria remain subject to discovery and scoped PRD.
- Deferred / out of scope: Full editorial calendar, content management, approval workflow automation and publishing integrations are later capabilities, not initial deliverables. No automatic public content publication; any future publishing integration requires separate approval and human control.
- Constraints and implications: Ground factual claims in authorized, current evidence; distinguish inferred audience demand and recommendations from verified facts; do not claim search demand, content gaps or market-wide demand without appropriate supporting sources. Generated drafts are not validated Knowledge by default and require human review before public use. Enforce source permissions, tenant isolation, privacy, provenance, provider policies and existing read-only source boundaries; avoid exposing sensitive customer evidence in public drafts. No new MCP access is implied until reviewed implementation and verification.
- Supersedes: None; refines D-024, consistent with D-015, D-019, D-021, D-025 and D-026.
- Affected documents/components: Content Intelligence discovery, briefs and draft generation, shared knowledge retrieval, AI Gateway and MCP access, future scoped PRD and acceptance tests.

### Template for future decision details

```markdown
### D-NNN — Short title
- Date: YYYY-MM-DD
- Status: Accepted
- Approval: Product owner discussion
- Decision: ...
- Rationale: ...
- MVP scope: ...
- Deferred / out of scope: ...
- Constraints and implications: ...
- Supersedes: None (or D-NNN)
- Affected documents/components: ...
```

## Target architecture (conceptual, not current implementation)

Sources (call center, CRM, web, authorized messaging, feedback, manual uploads) -> Collection & Integrations -> Resources -> Knowledge Engine -> Knowledge Base.
Knowledge Objectives and Knowledge Pipelines configure extraction; AI Gateway, authorization, storage and audit are cross-cutting. Resources and Knowledge independently feed Applications, API/MCP and authorized distribution. Panadan sends validated knowledge to customer systems using a separate, explicitly authorized destination integration.

### Resources

One logical resource can have multiple optional representations: e.g. call audio, metadata, transcript and extracted fields. Keep original data intact and track links, source IDs, timestamps, version and processing lineage. Reuse existing processed data when available; absent representations are not fabricated. Store or reference originals per customer policy. Ingestion, resource processing and knowledge production are independent operations. Protect source read-only guarantees; use only authorized source connections.

### Knowledge

Knowledge units retain subject/claim, context and conditions, temporal scope, evidence/source references, validation state, ownership/access policy, versions and history. Collections/packages reference units rather than duplicating uncontrolled claims. Knowledge changes are versioned; superseded versions remain available only according to retention and authorization policies. A proposed lifecycle includes Proposed, Under Review, Active, Disputed, Outdated, Rejected and Archived; exact state machine is pending design. Only appropriately validated and authorized knowledge may be distributed as authoritative. Risk depends on both the claim and its intended use. Do not treat model confidence as evidence reliability or operational risk.

A source is authoritative only for appropriate subjects. Contradictions require matching entity, property, applicable conditions and time; missing context is not a conflict. For example, tour price depends on travel dates, destination, exact hotel/room, traveler count/ages, flight, meals, transfer, inclusions, currency, price basis, inventory and quote validity. Distinct offers may all be correct. Do not fill unknown conditions with guesses. Live quotes and bookings belong in Resources; pricing rules and supported patterns may be Knowledge. Retrieve current facts from authorized resources instead of presenting old claims as current prices.

### Collection and processing

Support API/CRM/database integrations, approved external sources and manual ingestion. Knowledge objectives describe what the organization needs to learn; pipeline configuration selects input scope, schedule, model, validation policy and output. Scheduled/manual execution first; bounded discovery and event processing where useful. Track run status, errors and lineage; avoid reprocessing unchanged inputs when practical. Exact job semantics are pending technical design.

### Applications and AI

Applications can read both Resources and Knowledge under current permissions. Provide ready-made applications and simple organization-specific configuration (objective, allowed data/tools, instructions, model, input/output, execution and destination). Use ordinary code/SQL for deterministic tasks. Agents require explicit tool/data scopes, cost/time/step limits and approval for consequential actions. Do not automatically publish generated content or bypass knowledge review.

Centralize provider access and per-task model selection; track request/run/org/model/provider costs and budgets. Validate structured outputs where required; enforce provider/privacy policies and only permitted fallback. Assess existing AI API infrastructure before duplicating it.

### Security, organization and synchronization

Default deny; isolate organizations; enforce permissions server-side on all retrieval, processing, exports, API/MCP and background jobs. Role templates may be customized only within the grantor's authorized scope. External connections must not exceed current user permissions or their own selected grants; revocation must take effect for subsequent operations. Resource-level and field-level restrictions matter. Derived knowledge inherits source restrictions by default; widening access requires authorized review and appropriate sanitization. No private customer data or derived knowledge is shared across organizations without explicit authorization, even if anonymized. Shared sources also require usage rights.

Keep current source database read-only; knowledge export is a distinct destination with separately authorized credentials and narrow write access. Panadan manages knowledge versions and lifecycle; customer receives an authorized projection. Define sync failure/retry, deletion/revocation and version semantics before implementation. Never introduce general SQL execution or broaden existing sensitive MCP capabilities without explicit security review and approval.

## MVP boundaries and acceptance

Aim for one complete pilot flow: ingest selected sources (call center, selected online and/or manual inputs), view resources, configure objectives/pipelines, extract and validate contextual knowledge, manage units/packages, use authorized API/MCP and one-way sync, and deliver selected practical applications. D-024 selects limited Customer Intelligence and Content Intelligence as the initial applications on shared infrastructure. Market Intelligence is a subsequent desired extension; its release scope and timing remain open. D-025 prioritizes aggregate customer intelligence while preserving an extensible model for authorized individual analysis; individual profiling is not a required initial deliverable. D-026 selects a hybrid Customer Intelligence experience: evidence-backed insight feed, limited analytical dashboard and authorized MCP conversational access, with a dedicated conversational UI deferred. D-027 selects hybrid Content Intelligence: discovery and content briefs first, limited AI/MCP-assisted drafting, with full content management and publishing integrations deferred. Detailed workflows, data availability and rights, output requirements, validation and acceptance targets are still pending pilot discovery. Other proposed applications are not commitments.

Measure ingestion reliability, evidence-backed quality, reuse of knowledge across applications, freshness, access isolation, export correctness, measurable customer benefit and ability to onboard a second customer without rewriting the core. Quantitative targets need pilot validation.

Defer broad connector catalogs, full visual builders, advanced knowledge graphs, full self-service, complex two-way sync, dynamic AI routing and automatic public content publishing.

## Execution and verification

1. Audit baseline code, schemas, migrations, permissions, integrations, UI, tests and deployment documentation. Classify each component Reuse / Extend / Refactor / Build / Remove (removal requires separate approval).
2. In parallel, deployment discovery: source inventory, data rights/quality, existing workflows, target users, objectives, actual use cases and measurable baseline.
3. Produce evidence-linked gap analysis, scoped PRD, technical architecture/data model, migration and security/test plans.
4. Develop incrementally on the feature branch. Preserve existing interfaces, source read-only constraints, production behavior and rollback options.
5. Verify a complete pilot flow with synthetic or explicitly approved data before deployment; do not deploy or change production without separate authorization.

The initial audit and gap analysis are recorded in [CURRENT_STATE.md](CURRENT_STATE.md) and [GAP_ANALYSIS.md](GAP_ANALYSIS.md); pilot discovery is in progress. Do not infer implemented or deployed capabilities from these decisions. See [historical decisions](../DECISIONS.md), [original reporting MVP PRD](../PRD.md), [status](../STATUS.md), [security](../SECURITY.md) and [production operations](../PRODUCTION_OPERATIONS.md). Existing safety/operational rules remain in force until a reviewed migration explicitly supersedes them. Update this document when the product owner approves a changed decision; distinguish accepted decisions from proposals and implementation evidence.
