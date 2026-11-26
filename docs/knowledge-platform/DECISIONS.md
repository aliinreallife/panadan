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
| D-028 | Progressive multi-source strategy | Start with the existing call-center integration, add manual resources and limited approved web resources in MVP, and extend to further connectors incrementally based on need and authorized availability. |
| D-029 | Hybrid Knowledge Objectives | Provide reusable objective templates, editable instances and simple structured custom objectives in MVP; each objective defines purpose, authorized sources, output schema, context and validation, with execution scheduling configured through its pipeline. |
| D-030 | Multi-stage knowledge extraction | Extract reusable source-level observations with evidence; aggregate and discover patterns; validate contextual knowledge before authoritative publication. Prefer incremental processing and deterministic computation where suitable. |
| D-031 | Progressive historical backfill | Start with a configurable recent historical window while keeping incremental processing of new and changed resources active; extend historical coverage progressively with bounded, resumable jobs, budget controls and visible coverage. |
| D-032 | Multi-dimensional aggregate validation | Assess aggregate findings using separate evidence, coverage, source authority, context, freshness, consistency and intended-use risk criteria. Keep reliability, prevalence and business importance distinct; use deterministic checks, bounded AI assistance and risk-based human review. |
| D-033 | Initial user workflows and shared review | Prioritize technical/AI configuration and content/SEO consumption workflows in the initial MVP; share human validation responsibilities between technical staff and authorized organizational domain specialists. |
| D-034 | Initial Knowledge Objective set | Start with Customer Questions, Customer Needs & Preferences, Customer Concerns, Purchase Barriers, Destination Intelligence, Price Sensitivity and Content Opportunities as the initial objective set. |
| D-035 | Transcript-first call knowledge extraction | Use privacy-filtered existing transcripts as the primary semantic evidence for call-derived knowledge; use verified metadata as context and prior AI analyses only as supplementary, attributed inputs. |
| D-036 | Progressive transcript redaction | Start with deterministic rule/regex-based redaction in MVP (A), with an extensible preprocessing boundary for later context-aware hybrid redaction (C). |
| D-037 | Selective transcript storage | Retain approved redacted transcripts, permitted metadata, source references and derived knowledge in Panadan; keep unredacted transcripts in the source system. Preserve extensibility for reference-only and explicitly authorized local-original storage policies. |
| D-038 | External AI execution | Use approved external AI API providers through the centralized AI Gateway in the MVP; self-hosted or hybrid model execution is not selected for initial delivery. |
| D-039 | Managed AI provider credentials with BYOK extension path | Use centrally managed provider credentials and organization-scoped usage/budget controls in MVP (A+); preserve an extension path for later organization-owned credentials and approved custom endpoints. |
| D-040 | Progressive evaluation with single-operator pilot | Begin with synthetic tests and progressively expand authorized call samples within one selected operator's scope; gate expansion on technical, semantic, privacy and business evaluation. Adding operators requires a separate scope decision. |
| D-041 | Hybrid knowledge taxonomy | Start with predefined editable categories and allow AI to propose new topics/subcategories within governed scope; require authorized review before changing the official taxonomy. |
| D-042 | Content Intelligence delivery boundary | Deliver evidence-backed content discovery, briefs and outlines in the initial web application; enable limited draft generation via authorized MCP clients. Defer in-panel drafting, dedicated editing and content project management. |
| D-043 | Balanced MVP success criteria | Evaluate technical reliability, evidence-backed knowledge quality and practical business value together; security and privacy are mandatory progression gates. Calibrate quantitative acceptance thresholds through staged evaluation. |
| D-044 | Initial pilot time window | Limit the first historical evaluation to the most recent 30 days of eligible calls for the selected operator; retain configurable historical-window support without automatically extending the approved pilot scope. |
| D-045 | Simple hard AI budget limits with extension path | Enforce organization and execution-level spending limits in MVP (B+), with request/token/cost accounting and pipeline attribution; preserve an extension path for advanced multi-level budget allocation. |
| D-046 | Non-destructive source preservation | The pilot may proceed toward authorized processing subject to execution prerequisites; source/customer-owned originals must never be deleted, overwritten or modified by Panadan. Redaction and local data lifecycle operations affect only Panadan-controlled representations. |
| D-047 | Modular monolith and independent workers (AP-01) | Keep a shared Python/FastAPI codebase with explicit domain module boundaries and separate collection, scheduling, knowledge-processing and outbound worker runtimes. Scale processes independently without introducing mandatory microservices. |
| D-048 | Owned PostgreSQL state and durable queue (AP-02) | Use Panadan-owned PostgreSQL 18-compatible relational state, typed validated JSONB extensions and a PostgreSQL-backed durable job queue as the initial architecture. |
| D-049 | Single identity authority and workspace identity bridge (AP-03) | Retain the existing identity authority initially, with an explicit stable principal bridge and one authoritative platform workspace-policy store. Intersect current authentication, consent and domain grants. |
| D-050 | Tenant-scoped schema and defense-in-depth RLS (AP-04) | Use a shared schema with tenant-scoped keys and foreign keys, server-side scope enforcement, PostgreSQL row-level security and narrow runtime roles. |
| D-051 | Pre-persistence redaction and separate source reader (AP-05) | Handle unredacted call text transiently inside a separately governed read-only collection/preprocessing runtime; persist only approved filtered representations and provenance in the new knowledge path. |
| D-052 | Versioned durable orchestration and idempotent effects (AP-06) | Use deterministic orchestration with versioned tasks, leased claims, fencing, bounded retries and short transactional local effects. At-least-once execution with replay-safe results; no false exactly-once external guarantee. |
| D-053 | Relational knowledge and evidence architecture (AP-07) | Use relational version/evidence links, typed extraction, deterministic aggregation and bounded semantic grouping for initial knowledge retrieval and validation. |
| D-054 | Governed provider resolution and atomic budget admission (AP-08) | Resolve explicit approved provider/model and managed credentials through the shared gateway; reserve organization and execution budget atomically before chargeable dispatch. |
| D-055 | Shared authorized query services (AP-09) | Use shared scoped query/read services for web, REST and MCP, with independent Resource and Knowledge retrieval contracts and common projections/metrics. |
| D-056 | Durable outbox and separate destination runtime (AP-10) | Use a separate outbound sync worker with a durable outbox, approved versioned projections, dedicated narrow destination credentials and idempotent/reconciled delivery. |
| D-057 | Additive knowledge schema (DM-01) | Create the new platform model in the separate Panadan-owned panadan_knowledge schema; preserve existing panadan_ingest and panadan_auth schemas and the approved identity bridge. |
| D-058 | Tenant composite integrity and explicit sharing (DM-02) | Use workspace-scoped composite primary/foreign keys, scoped runtime roles and RLS; use explicitly authorized sharing projections rather than raw cross-tenant reads. |
| D-059 | Versioned resource representations (DM-03) | Represent each source item as a logical Resource with immutable source revisions and separately versioned approved filtered representations. |
| D-060 | Versioned execution and frozen population (DM-04) | Pin objective/pipeline versions and run manifests, retain measured population membership and use fenced durable work items and attempts. |
| D-061 | Reusable observation sets and exact evidence anchors (DM-05) | Use compatible observation sets, evidence anchors tied to exact filtered representation revisions, and relational processed/matched aggregate membership. |
| D-062 | Versioned knowledge lifecycle and invalidation (DM-06) | Separate logical knowledge units from revisions, record validation/review/lifecycle transitions, and invalidate affected authoritative projections when evidence becomes unavailable or stale. |
| D-063 | Versioned taxonomy and pinned knowledge packages (DM-07) | Use governed taxonomy versions and reviewed suggestions, pinned package revision membership, and separate derived opportunity/brief records. |
| D-064 | Dual budget reservation and usage ledger (DM-08) | Atomically reserve against organization and run budgets, record immutable usage/adjustment ledger events, and retain uncertain reservations until reconciliation. |
| D-065 | Versioned delivery and retention barriers (DM-09) | Use versioned destination projections/outbox and scoped local erasure records/restore barriers. |
| D-066 | Preferred visual direction with required workflow additions (UI direction) | Adopt the owner-supplied visual reference direction: warm neutral surfaces, muted green/olive accents, restrained borders, editorial typography, compact readable Persian RTL knowledge workspace, responsive layouts. Complete all required PRD workflows in the same design language. |
| D-067 | Approved implementation roadmap and incremental delivery | Approve ROADMAP.md M00–M13 and U0–U11, use both UI references within D-066, and authorize M00 baseline/harness only. Subsequent increments and live activation remain independently gated. |

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
| 2026-11-26 | D-028 | Owner selected progressive multi-source MVP delivery. |
| 2026-11-26 | D-029 | Owner selected hybrid Knowledge Objectives. |
| 2026-11-26 | D-030 | Owner selected multi-stage knowledge extraction. |
| 2026-11-26 | D-031 | Owner selected progressive backfill plus incremental processing. |
| 2026-11-26 | D-032 | Owner selected multi-dimensional evidence validation for aggregate knowledge. |
| 2026-11-26 | D-033 | Owner selected initial user workflows and shared technical/domain review. |
| 2026-11-26 | D-034 | Owner selected the initial Knowledge Objective set for the pilot. |
| 2026-11-26 | D-035 | Owner selected transcript-first call knowledge extraction with privacy filtering and verified metadata. |
| 2026-11-26 | D-036 | Owner selected basic deterministic redaction with an upgrade path to context-aware hybrid redaction. |
| 2026-11-26 | D-037 | Owner selected selective local transcript storage. |
| 2026-11-26 | D-038 | Owner selected external AI API providers for initial execution. |
| 2026-11-26 | D-039 | Owner selected centrally managed AI providers with a future BYOK extension path. |
| 2026-11-26 | D-040 | Owner selected progressive evaluation limited initially to one call-center operator. |
| 2026-11-26 | D-041 | Owner selected hybrid knowledge taxonomy. |
| 2026-11-26 | D-042 | Owner selected discovery, briefs and MCP-based drafting as the initial Content Intelligence delivery boundary. |
| 2026-11-26 | D-043 | Owner selected balanced technical, knowledge-quality and business-value MVP success criteria. |
| 2026-11-26 | D-044 | Owner selected the most recent 30 days for the initial pilot. |
| 2026-11-26 | D-045 | Owner selected simple hard AI budget limits with an extension path to multi-level budget control. |
| 2026-11-26 | D-046 | Owner confirmed the non-destructive source preservation requirement for pilot processing. |
| 2026-11-26 | D-047 | Owner approved architecture choice AP-01 — Modular monolith and independent workers. |
| 2026-11-26 | D-048 | Owner approved architecture choice AP-02 — Owned PostgreSQL state and durable queue. |
| 2026-11-26 | D-049 | Owner approved architecture choice AP-03 — Single identity authority and workspace identity bridge. |
| 2026-11-26 | D-050 | Owner approved architecture choice AP-04 — Tenant-scoped schema and defense-in-depth RLS. |
| 2026-11-26 | D-051 | Owner approved architecture choice AP-05 — Pre-persistence redaction and separate source reader. |
| 2026-11-26 | D-052 | Owner approved architecture choice AP-06 — Versioned durable orchestration and idempotent effects. |
| 2026-11-26 | D-053 | Owner approved architecture choice AP-07 — Relational knowledge and evidence architecture. |
| 2026-11-26 | D-054 | Owner approved architecture choice AP-08 — Governed provider resolution and atomic budget admission. |
| 2026-11-26 | D-055 | Owner approved architecture choice AP-09 — Shared authorized query services. |
| 2026-11-26 | D-056 | Owner approved architecture choice AP-10 — Durable outbox and separate destination runtime. |
| 2026-11-26 | D-057 | Owner approved DM-01 — Additive knowledge schema. |
| 2026-11-26 | D-058 | Owner approved DM-02 — Tenant composite integrity and explicit sharing. |
| 2026-11-26 | D-059 | Owner approved DM-03 — Versioned resource representations. |
| 2026-11-26 | D-060 | Owner approved DM-04 — Versioned execution and frozen population. |
| 2026-11-26 | D-061 | Owner approved DM-05 — Reusable observation sets and exact evidence anchors. |
| 2026-11-26 | D-062 | Owner approved DM-06 — Versioned knowledge lifecycle and invalidation. |
| 2026-11-26 | D-063 | Owner approved DM-07 — Versioned taxonomy and pinned knowledge packages. |
| 2026-11-26 | D-064 | Owner approved DM-08 — Dual budget reservation and usage ledger. |
| 2026-11-26 | D-065 | Owner approved DM-09 — Versioned delivery and retention barriers. |
| 2026-11-26 | D-066 | Owner approved UI direction — Preferred visual direction with required workflow additions. |
| 2026-11-26 | D-067 | Owner approved Phase 7 roadmap, use of both UI references and start of Phase 8 M00. |

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

### D-028 — Progressive multi-source strategy
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Design the Resources and collection foundations for multiple source types from the beginning, while integrating sources progressively. Begin with the existing call-center reporting integration; add manual text, documents and supplementary information, plus limited collection from selected approved web pages in the initial MVP.
- Rationale: Reuse the existing source adapter to deliver quickly; manual resources demonstrate multi-source capability without requiring a dedicated connector for each system; selected web pages provide an additional source type without a broad crawler.
- MVP scope: Call-center data available under current and approved access, manual resource ingestion and limited approved web resources. Preserve available original and derivative representations, contextual metadata, source identity and provenance. Exact supported file formats, limits, web pages, refresh methods, retention, source permissions and rollout sequence within MVP remain subject to discovery and scoped PRD. Availability of audio or other unconfirmed representations is not assumed.
- Deferred / out of scope: Dedicated CRM and organizational data connectors, messaging/Telegram, SEO and analytics, and expanded market/competitor collection are subsequent integration candidates; priority depends on use-case evidence and authorization. Broad autonomous web crawling and comprehensive connector catalogs are not initial deliverables.
- Constraints and implications: Follow D-001, D-005, D-008, D-009, D-016, D-021 and D-022: preserve read-only source access, tenant isolation, provenance, usage rights, privacy and source-specific validation. Treat uploaded files and web content as untrusted data; enforce bounded parsing/retrieval, approved destinations, URL/network safety and applicable access restrictions. Never treat manually supplied or web content as validated Knowledge by default. No live source access, upload, crawl, or permission expansion is authorized by this decision alone. A manual or web resource may supplement a call-derived claim only if its subject, conditions and authority support that claim.
- Supersedes: None; refines the selected-source scope under D-017, D-018 and D-024.
- Affected documents/components: Resources, collection adapters, ingestion policies, workspace integration configuration, Knowledge Engine, future scoped PRD, architecture, data model and acceptance tests.

### D-029 — Hybrid Knowledge Objectives
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Offer predefined reusable Knowledge Objective templates, organization-specific customization of templates, and simple structured custom objectives. An objective defines what to learn, its authorized source scope, expected output schema, contextual constraints and validation rules; associated pipeline configuration controls scheduling and execution.
- Rationale: Templates provide predictable initial results and reduce setup effort, while structured custom objectives let different organizations and industries reuse the shared core without code forks. Natural-language instructions alone are insufficient for reliable, inspectable knowledge extraction.
- MVP scope: A limited template catalog, editable organization-owned objective instances, simple custom objective configuration, selection of permitted sources, typed and validated output configuration, context and validation settings, and scheduled/manual execution via associated pipelines. Exact template contents, schema editing affordances, permission roles and validation rule primitives remain for scoped PRD and technical design. Assisted setup remains consistent with D-010.
- Deferred / out of scope: Advanced schema or visual pipeline builders, automatic creation of objectives/pipelines and automatic objective recommendations are not initial deliverables. Bounded discovery of useful findings within approved scope remains allowed under D-008 and is distinct from creating new objectives.
- Constraints and implications: Follow D-003, D-008, D-009, D-016, D-019, D-021, D-022 and D-023. Objective/pipeline settings cannot expand data access, weaken required validation or override provider and organization policies. Version objective definitions and output/validation configurations so runs and findings remain traceable; validate configurations before execution. Respect current source grants at execution and retrieval. Preserve evidence and uncertainty; an extracted candidate is not automatically validated Knowledge. No code or production change is authorized here.
- Supersedes: None; refines D-008, D-009, D-022 and D-023.
- Affected documents/components: Knowledge Objectives, template catalog, workspace configuration, Knowledge Pipelines, schema and validation configuration, future scoped PRD, architecture, data model and acceptance tests.

### D-030 — Multi-stage knowledge extraction
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Extract structured observations from individual resources or their applicable representations, retaining source revision, context and evidence. Aggregate observations and discover patterns across permitted populations and time windows, then apply evidence-based, risk-aware validation before admitting a claim as authoritative Knowledge. Reuse observations across objectives and applications when their scope and semantics are compatible.
- Rationale: Separate semantic extraction from counting, pattern analysis and knowledge validation to retain traceability, reduce unnecessary model calls and support multiple applications on the same scalable core.
- MVP scope: Simple governed extraction, reusable version-aware observations, deterministic aggregation and counting where suitable, bounded semantic pattern discovery, and validation before authoritative publication. Prefer incremental processing of new, changed or missing/incompatible extraction coverage; unchanged compatible results may be reused. Exact observation schema, run identity, invalidation/recomputation semantics, deduplication, aggregation measures, quality thresholds, schedules and backfill policy remain pending scoped PRD and technical design.
- Deferred / out of scope: Advanced clustering, distributed analytics infrastructure and broad autonomous discovery are not required for initial delivery. Do not assume every observation must become a Knowledge Unit or every resource must be processed for every objective.
- Constraints and implications: Follow D-003, D-004, D-008, D-009, D-016, D-019, D-021, D-022, D-025 and D-029. Observations, aggregates, candidate claims and validated Knowledge are distinct; a model-generated observation is not automatically reliable. Retain evidence, configuration/model versions, source revisions, population and temporal scope. Define denominators and prevent duplicate counting; distinguish calls from unique customers. Re-evaluate stale or invalidated evidence and permissions on reuse, processing and retrieval; never widen source scope via aggregation. Use ordinary code/SQL for exact counts and deterministic transformations, and AI for semantic tasks where justified. Preserve read-only source access, tenant isolation, privacy and governed provider access. No actual processing or live data access is authorized by this decision alone.
- Supersedes: None; refines D-004, D-008, D-009 and D-029.
- Affected documents/components: Knowledge Engine, resource derivatives/observations, aggregation, evidence validation, pipeline execution, shared Knowledge Base, application retrieval, future scoped PRD, architecture, data model and acceptance tests.

### D-031 — Progressive historical backfill
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Process a configurable recent historical window first to obtain early useful results, maintain incremental processing of new and changed resources, and expand older historical coverage progressively as needed. Support organization/objective-specific processing policies within approved budgets and source permissions.
- Rationale: Avoid making full historical processing a prerequisite to useful output; control initial cost and processing load while preserving long-term analytical potential and keeping current information fresh.
- MVP scope: Configurable initial historical window, incremental new/changed-resource processing, reuse of compatible prior observations, manual and scheduled bounded backfill, budget limits, pause/resume and visible processing coverage. Report eligible, processed, failed and pending scope where measurable, including relevant time periods and incomplete coverage in downstream insights. Exact window defaults, cost limits, batch sizes, concurrency, checkpoint and retry semantics remain for scoped PRD and technical design.
- Deferred / out of scope: Intelligent source prioritization and advanced distributed scheduling are later capabilities. Full historical coverage is neither a universal requirement nor a promise to process all available records automatically.
- Constraints and implications: Follow D-005, D-009, D-016, D-020, D-021, D-028 and D-030. Ingestion/replication checkpoints and AI extraction coverage are distinct. Define safe ordering, replay, deduplication, version compatibility, overlap handling, late updates and durable progress; incremental work must not be starved by backfill. Recheck current access, retention, source and provider policy at execution; prevent unintended spend and duplicate committed observations on retries. Coverage must be scoped to known eligible resources and compatible extraction versions; unknown source completeness must remain unknown. Do not equate processed calls with unique customers or present partial data as a representative population without evidence. Pause/resume and budget enforcement need bounded in-flight behavior. No live processing, source write or production change is authorized by this decision alone.
- Supersedes: None; refines D-009 and D-030.
- Affected documents/components: Ingestion and processing coordination, Knowledge Pipelines, backfill and incremental scheduling, AI Gateway budget controls, coverage and run visibility, aggregate analysis, future scoped PRD, architecture, data model and acceptance tests.

### D-032 — Multi-dimensional aggregate validation
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Validate aggregate knowledge through multiple inspectable dimensions rather than frequency alone, an AI verdict alone, universal manual review or a single opaque score. Consider evidence count and independence, eligible population and denominator, processing coverage, subject-specific source authority, contextual and temporal alignment, freshness, contradictory evidence and intended-use risk. Keep evidence reliability, prevalence and business importance separately interpretable.
- Rationale: Repeated statements do not prove truth; rare findings may be commercially important; partial or biased coverage does not justify population-wide claims. Complement exact deterministic checks with bounded semantic AI assistance and human review where risk or uncertainty requires it.
- MVP scope: Expose applicable criteria, evidence references, scope, time window, coverage and validation outcomes with versioned rules. Use code/SQL for counts, denominators, coverage and deterministic checks; explicit policies for authority, freshness and risk; bounded AI for semantic matching, deduplication assistance and contradiction detection; authorized human review for sensitive, uncertain or high-risk cases. Retain rare findings as candidates when appropriate without overstating prevalence or promoting them automatically. Exact thresholds, evidence independence rules, review roles, sampling protocol and publication gates remain pending scoped PRD and technical design.
- Deferred / out of scope: A universal composite 0–100 trust score, advanced statistical inference and fully autonomous adjudication are not required for MVP. Do not treat every criterion as a numerical score or apply a universal minimum evidence count regardless of claim type or intended use.
- Constraints and implications: Follow D-003, D-016, D-021, D-022, D-025, D-030 and D-031. Keep claim truth distinct from frequency of reported perceptions; preserve unknown versus contradictory conditions; distinguish call counts from unique customers and state denominators, missingness and coverage limits. Do not extrapolate to an entire customer population or market without supporting methodology. Handle source revisions, stale evidence, duplicate records, privacy-sensitive small groups and changed grants; evidence drill-down remains authorized. Human review cannot override source permissions or fabricate evidence. Model confidence does not establish reliability or risk. Findings that fail mandatory checks or require outstanding review are not authoritative Knowledge. No real data processing or publication is authorized by this decision alone.
- Supersedes: None; refines D-003, D-021 and D-030 for aggregate analysis.
- Affected documents/components: Knowledge Engine, validation policies, aggregate measures, evidence and review UI, Customer Intelligence, Content Intelligence and later Market Intelligence, future scoped PRD, architecture, data model and acceptance tests.

### D-033 — Initial user workflows and shared review
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Prioritize technical/AI team workflows and content/SEO specialist workflows in the initial MVP. Human knowledge validation is a shared responsibility between technical staff and authorized organizational domain specialists.
- Rationale: Technical users can configure and inspect the knowledge pipeline, while domain specialists can assess business meaning, evidence suitability and practical usefulness. Content workflows provide an initial consumer of reusable knowledge.
- MVP scope: Support authorized technical configuration and inspection, knowledge review, and content discovery/brief/draft consumption within the shared organization workspace. Provide inspectable evidence and review actions consistent with D-003, D-016 and D-032. The initial user priorities do not grant additional access by themselves.
- Deferred / out of scope: Broader organizational rollout and dedicated interfaces for each job function are not required initially. Exact reviewer assignments, role templates, approval quorum, escalation, separation of duties and workflow ownership remain pending discovery and scoped PRD. Shared responsibility does not imply that every item requires two approvals.
- Constraints and implications: Technical and domain review must operate under explicit organization, source and field grants; technical staff are not automatically authorized to inspect all sensitive customer data. Record review outcomes, rationale and reviewer identity in authorized audit history. Preserve mandatory validation gates and source restrictions; no automatic publication or unauthorized widening of knowledge access. No client identity, named personnel or confidential deployment details are recorded here. No real-data access or production changes are authorized by this decision alone.
- Supersedes: None; refines D-010, D-016, D-024, D-027 and D-032.
- Affected documents/components: Organization workspace, role templates and permission policy, knowledge review, technical configuration, Content Intelligence, future scoped PRD and acceptance tests.

### D-034 — Initial Knowledge Objective set
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Prioritize seven initial Knowledge Objectives: Customer Questions; Customer Needs & Preferences; Customer Concerns; Purchase Barriers; Destination Intelligence; Price Sensitivity; and Content Opportunities.
- Rationale: These objectives provide a focused starting set for Customer Intelligence and Content Intelligence, covering customer questions, preferences, concerns and decision barriers while also supporting destination-related understanding and evidence-led content discovery.
- MVP scope: Include these seven objectives in the initial pilot objective catalog, using the reusable template/customization model in D-029. The first six are customer-intelligence objectives; Content Opportunities is a content-intelligence objective that should draw on relevant authorized, validated knowledge and evidence. Exact output schemas, dimensions, filters, source mappings, time windows, measures and acceptance thresholds remain to be defined during pilot discovery and scoped PRD.
- Deferred / out of scope: Other candidate objectives, including customer segmentation, organizational expertise, competitor intelligence, emerging trends and customer experience, are not part of this initial selected set unless separately approved. This decision does not commit to a fixed number of templates or fully specified pipeline configurations before source and workflow validation.
- Constraints and implications: Follow D-021, D-022, D-025, D-027, D-028, D-029, D-030 and D-032. Objectives must operate only on currently authorized sources and fields, preserve evidence, context, temporal scope and uncertainty, and respect aggregate-first delivery. Destination Intelligence must not imply market-wide demand or competitor conclusions from call data alone. Content Opportunities must not assert search volume, SEO demand or factual claims without appropriate supporting sources; derived content recommendations are not validated Knowledge by default. The objective names are a discovery scope decision, not evidence that required source data or access is available or that the objectives are already implemented. No additional customer data access or processing is authorized by this decision.
- Supersedes: None; refines D-024, D-027 and D-029.
- Affected documents/components: Knowledge Objective template catalog, Customer Intelligence, Content Intelligence, source mappings, validation policies, future scoped PRD, architecture, data model and acceptance tests.

### D-035 — Transcript-first call knowledge extraction (B+)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: For call-derived knowledge, prioritize the existing speech-to-text transcript after appropriate privacy filtering/redaction. Use source metadata (such as call identifiers, date/time and duration) as contextual information only when its provenance and semantics are sufficiently verified. Existing upstream AI summaries, classifications, recommendations and other inferred fields are optional supplementary inputs, not primary or independently corroborating evidence.
- Rationale: Much of the available upstream analysis is generated by AI. Re-extracting knowledge from transcripts reduces dependence on upstream interpretations, preserves more conversational context and supports reuse across organizations without requiring an upstream call-analysis product. Transcription is itself model-generated and remains subject to errors; it is evidence of the recorded conversation, not proof of every assertion in it.
- MVP scope: Reuse authorized existing transcripts without requiring audio ingestion or retranscription. Preserve lineage to the source resource and transcript revision, distinguish system-recorded metadata from AI-generated/inferred values, apply data minimization and redaction before downstream semantic processing, and retain enough permitted context for the selected objectives. When transcript content is unavailable or unreliable, expose the coverage/quality limitation; do not silently replace primary evidence with prior AI conclusions. Earlier AI outputs may assist discovery or review, with explicit attribution and verification against suitable primary evidence.
- Deferred / out of scope: Audio retrieval, storage or independent retranscription are not required for the initial MVP. Exact redaction method, approved execution environment/provider, field allowlist, retention policy, source contract and quality thresholds remain pending discovery and scoped PRD.
- Constraints and implications: Follow D-001, D-003, D-005, D-016, D-020, D-021, D-025, D-028, D-030, D-032 and D-034. Obtain explicit source-owner authorization for transcript access, processing, retention and any external provider disclosure before using live data. A read grant is not automatically a processing or disclosure grant. Keep source data read-only and preserve authorized originals without overwriting them. Treat redacted transcripts as potentially sensitive, not necessarily anonymous; protect restricted evidence, logs, derivatives, identifiers and access to unredacted representations. Do not infer metadata accuracy merely from field names or presume that dates, durations, sales labels or other fields have a particular provenance. Validate field-level provenance and semantics. Correlated AI outputs from the same transcript are not independent corroboration. Do not use identifiers for customer profiling by default. This decision does not grant new permissions or authorize live ingestion, external transmission, production processing or deployment.
- Supersedes: None; refines D-028, D-030 and D-034.
- Affected documents/components: Call-center source adapter, Resources and representations, privacy preprocessing, AI Gateway, Knowledge Engine, evidence lineage and validation, future scoped PRD, architecture, data model and acceptance tests.

### D-036 — Progressive transcript redaction (A → C)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Begin with basic deterministic rules and regex-based masking of unnecessary sensitive identifiers before downstream semantic extraction. Design the preprocessing boundary so contextual rules and semantic detection in an approved execution environment can be added later without redesigning the knowledge core.
- Rationale: Keep initial implementation, cost and execution predictable while preserving an upgrade path for identifiers and sensitive context not detectable by simple patterns.
- MVP scope: Use a bounded, versioned deterministic redaction stage with typed placeholders and applicable known sensitive-field patterns. Assess reuse of the existing transcript masking implementation against pipeline needs; do not presume it is sufficient for bulk processing. Preserve authorized business-relevant context where possible, keep original source representations unchanged and restricted, track redaction policy/version and lineage, and test on synthetic representative Persian and mixed-language cases. Exact rule catalog, configuration affordances, quality gates and handling of unsupported or uncertain content remain pending scoped PRD and technical design.
- Deferred / out of scope: AI-based semantic redaction, comprehensive context-aware hybrid redaction and advanced organization-specific privacy policy authoring are later capabilities, subject to approval and demonstrated need. Extensibility does not imply implementation of those capabilities now.
- Constraints and implications: Follow D-016, D-020, D-028, D-030, D-032 and D-035. Rule-based masking is best effort, cannot reliably identify every name or contextual identifier, and does not establish anonymization. Treat filtered text and derivatives as potentially sensitive. Require source-owner approval and provider-specific processing/disclosure authorization; do not send text to an unapproved external service merely because regex redaction ran. Where required privacy guarantees cannot be met, block or route the resource for authorized review rather than silently exposing it. Minimize input fields, enforce tenant and evidence permissions, avoid sensitive payloads in logs, preserve applicable retention/deletion obligations, and keep source access read-only. No production changes, live processing or external disclosure are authorized by this decision alone.
- Supersedes: None; refines D-035.
- Affected documents/components: Resources preprocessing, transcript masking, privacy policies, extraction pipelines, AI Gateway, evidence access, future scoped PRD, architecture, data model and acceptance tests.

### D-037 — Selective local transcript storage
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Use selective local storage for initial call transcript workflows. Keep the original unredacted transcript in its source system; store approved privacy-filtered transcript representations, permitted verified metadata, source references, observations and knowledge in Panadan's own storage. Preserve architectural support for reference-only and explicitly authorized original-local-storage policies for future organization-specific needs.
- Rationale: Support repeated extraction, evidence inspection and reduced dependence on continuous source availability without routinely duplicating unredacted conversations. Reuse filtered representations where compatible with the current source revision, redaction version, purpose and authorization.
- MVP scope: Fetch only authorized required source fields through read-only interfaces, perform bounded redaction before durable transcript storage, and persist approved filtered representations and provenance in the isolated organization workspace. Retain source identity/revision references and redaction version, enforce access and retention policies, and provide explicit missing/stale evidence behavior. No durable unredacted transcript copy as part of this MVP workflow, including intermediate payloads, caches, failed jobs, logs or backups. Transient handling of original text must occur only in an approved processing boundary. Exact storage layout, source revision contract, retention periods, deletion/reconciliation semantics and failure recovery remain pending scoped PRD and technical design.
- Deferred / out of scope: Local storage of unredacted original transcripts and a comprehensive organization-specific storage policy builder are not initial deliverables. Reference-only behavior remains an architectural option; no requirement to ship a full storage-mode selector initially.
- Constraints and implications: Follow D-001, D-005, D-016, D-028, D-030, D-031, D-035 and D-036. Redacted transcripts are potentially sensitive, not anonymous. Require explicit source-owner permission for local retention, processing and any provider disclosure; enforce tenant isolation, encryption/access controls appropriate to the data, minimization and deletion/retention obligations across representations, derivatives, caches and backups. Handle source revisions, revocations and deletion signals without presenting stale or inaccessible evidence as current; if the source contract is incomplete, report limitations and do not invent deletion guarantees. Avoid retaining raw identity fields by default. Preserve read-only source access and existing reporting behavior. Review existing ingestion and revision storage before reuse to prevent accidentally persisting unredacted payloads. This decision alone does not authorize live source access, data copying, external transmission, migration or deployment.
- Supersedes: None; refines D-005, D-028, D-035 and D-036.
- Affected documents/components: Resource representations, call source adapter, preprocessing and ingestion boundary, local storage and retention, evidence provenance, incremental synchronization, future scoped PRD, architecture, data model and acceptance tests.

### D-038 — External AI execution (A)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Use external AI API providers through the centralized multi-provider AI Gateway for initial semantic extraction, validation assistance and application AI tasks. Retain D-020's explicit provider/model configuration and avoid binding the knowledge core directly to a particular vendor.
- Rationale: Minimize initial infrastructure complexity and avoid operating dedicated inference/GPU infrastructure while evaluating model quality, cost and workflow value.
- MVP scope: Approved external API integrations behind a common gateway boundary; explicit model/provider selection for governed tasks; enforce the previously agreed budget, data authorization and structured extraction validation requirements. Evaluate reuse of existing organizational AI gateway infrastructure before duplicating functionality; no specific gateway, intermediary, vendor or model is selected or approved by this decision. Exact API contracts, model evaluation, accounting and allowed provider/data combinations remain pending scoped PRD and technical design.
- Deferred / out of scope: Self-hosted inference and hybrid external/private model execution are not selected for the initial release. Intelligent routing remains deferred under D-020. Future changes require separate approval; no self-hosting implementation commitment is implied.
- Constraints and implications: Follow D-016, D-019, D-020, D-031 and D-035 through D-037. Provider access must be deny-by-default until the applicable organization/source owner approves processing and external disclosure, including any intermediaries and downstream providers, data categories, purpose, retention/training terms and relevant security requirements. Enforce permitted provider/model and data scope before egress; minimize payloads, protect secrets, avoid sensitive payload logging, and validate structured output and lineage. Redaction is not anonymization or automatic authorization to send customer data. Do not silently fall back to an unapproved provider/model when a request fails. Where permissions or required safeguards are missing, block real-data execution; use synthetic data for development/evaluation. The infrastructure choice is not approval to disclose real data, enable a provider, incur spending, deploy or modify production.
- Supersedes: None; refines D-020 and D-035.
- Affected documents/components: AI Gateway, provider adapters, task configuration, authorization and egress policy, budget tracking, knowledge pipelines, future scoped PRD, architecture and acceptance tests.

### D-039 — Managed AI provider credentials with BYOK extension path (A+)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Use centrally managed AI provider credentials through the Panadan AI Gateway in MVP, with explicit provider/model selection per pipeline, organization-scoped usage accounting, budget controls and provider allowlists. Preserve an extensible credential-resolution boundary for later hybrid managed/BYOK operation and approved custom endpoints; do not implement BYOK in the initial release.
- Rationale: Simplify initial customer onboarding and credential administration, retain centralized security and spending controls, and avoid redesigning the knowledge core when organization-owned credentials become necessary.
- MVP scope: Centrally administered provider configuration and protected credentials, governed pipeline model selection, organization-attributed usage and cost accounting, budget enforcement and applicable provider/data allowlists. Evaluate reuse of an existing AI gateway before duplicating provider integration or usage-accounting capabilities. No specific gateway/vendor/model is approved here. Exact accounting units, concurrency/reservations, retry costs, budget behavior, credential store and configuration permissions remain pending scoped PRD and technical design.
- Deferred / out of scope: Organization-supplied API keys, custom API endpoints and hybrid credential routing are later capabilities requiring separate approval and security review. No customer billing or wallet product commitment is implied by usage accounting; no intelligent model routing in MVP under D-020.
- Constraints and implications: Follow D-016, D-019, D-020, D-031 and D-035 through D-038. Keep credentials server-side in an approved secret store, restrict administrative access, prevent secrets or sensitive request/response payloads entering logs or clients, and isolate tenant attribution and spending. Provider/model/data-purpose authorization and external disclosure approval are independent of credential ownership. Account for intermediaries and downstream providers; deny unapproved egress and prevent fallback across unauthorized credentials, organizations or endpoints. Any future BYOK/custom endpoint path must preserve authorization and endpoint security controls, including protection against arbitrary network access. No real-data disclosure, spending, provider activation, production change or live processing is authorized by this decision alone.
- Supersedes: None; refines D-020, D-031 and D-038.
- Affected documents/components: AI Gateway, credential management, organization policies, usage/cost accounting, budget enforcement, pipeline configuration, future scoped PRD, architecture and acceptance tests.

### D-040 — Progressive evaluation with single-operator pilot
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Evaluate the initial knowledge extraction flow progressively, starting with synthetic tests and then bounded, authorized samples of calls associated with one selected call-center operator. Increase sample size only after reviewing the preceding stage. Keep the initial operator scope fixed; expansion to additional operators is a separate decision, not an automatic consequence of passing evaluation.
- Rationale: Reduce initial processing cost, contain exposure and allow prompt, schema, evidence and workflow corrections before larger runs. A single-operator pilot can demonstrate technical feasibility and practical usefulness without requiring organization-wide processing.
- MVP scope: Establish a staged evaluation protocol covering technical validity (redaction, structured output, lineage, failures), semantic extraction accuracy and coverage, evidence grounding and unsupported claims, processing cost and latency, privacy and practical business value. Use diverse authorized calls within the selected operator's available history; illustrative sample targets of 100, 1,000 and 10,000 calls are adjustable, not mandatory quotas or authorization to expand beyond the chosen operator. If the eligible pool is smaller, report the limitation and adjust the stage rather than adding operators automatically. Select exact operator, dates, sample design, independent human reference/review protocol, measurable acceptance thresholds and budget before real-data evaluation.
- Deferred / out of scope: Organization-wide call processing, multi-operator comparison, generalized customer/market conclusions and a full automated evaluation product are not initial pilot commitments. Expansion requires separate approval and relevant scope, privacy, quality and source checks.
- Constraints and implications: Follow D-016, D-017, D-025, D-030 through D-039. Confirm stable source-backed operator identity and assignment semantics before enforcing the pilot scope. Existing display-name/team/operator filters are not authorization boundaries. Enforce the authorized single-operator scope server-side in source selection, ingestion, processing and retrieval, with default-deny for ambiguous or unmapped records; verify isolation and no cross-scope access. Label findings with the operator-scoped population, period, denominators and coverage; do not infer representativeness of the whole organization, unique customers or market from a single operator. Use synthetic data until source-owner processing, storage and external provider disclosure permissions and budget are explicitly approved. Keep source read-only; no actual live processing, copying, external disclosure, spending or deployment is authorized by this decision alone. Do not record the operator identity or customer-specific details in the public repository.
- Supersedes: None; refines D-017, D-025, D-031, D-032 and D-034.
- Affected documents/components: Pilot scope and sampling, source adapter and authorization, evaluation protocol, knowledge pipelines, evidence review, usage accounting, future scoped PRD, architecture, data model, roadmap and acceptance tests.

### D-041 — Hybrid knowledge taxonomy (C)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Use a hybrid taxonomy with predefined, editable categories and bounded AI suggestions for newly discovered topics or subcategories. New suggested categories become part of the official taxonomy only after authorized review and approval.
- Rationale: Maintain consistent classification and reliable reporting while allowing discovery of unexpected themes without requiring all categories to be known in advance or allowing uncontrolled model-generated category proliferation.
- MVP scope: Simple governed categories/subcategories, organization-scoped customization, and reviewable AI category suggestions grounded in authorized observations/evidence. Keep proposed and accepted categories distinct; support handling of unmatched/uncertain observations without forced classification. Preserve stable category identity, version/lineage and consistent metric interpretation across approved taxonomy changes. Exact initial categories, review roles, duplicate handling, merge/reclassification policy and UI affordances remain pending scoped PRD and technical design.
- Deferred / out of scope: Advanced knowledge graphs, ontology engines, complex taxonomy builders and autonomous taxonomy mutation are not MVP commitments. AI suggestions of categories do not imply automated creation of objectives or pipelines, which remain deferred under D-029.
- Constraints and implications: Follow D-008, D-016, D-021 through D-023, D-025, D-029, D-030, D-032, D-034 and D-040. Taxonomy changes must be tenant-isolated, version-aware, traceable and authorized. A category suggestion is not itself validated Knowledge or evidence of prevalence. Preserve source permissions, contextual distinctions, evidence and uncertainty; avoid double counting across categories and silently changing historical denominators. Single-operator observations do not establish organization-wide demand. No live processing or production changes are authorized by this decision alone.
- Supersedes: None; refines D-008, D-022, D-029 and D-030.
- Affected documents/components: Knowledge taxonomy, observation classification, objective templates, discovery and review UI, aggregate reporting, future scoped PRD, architecture, data model and acceptance tests.

### D-042 — Content Intelligence delivery boundary (A)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Deliver content opportunity discovery, evidence-backed content briefs and suggested outlines through the initial Content Intelligence web application. Support limited AI-assisted draft generation through authorized MCP clients rather than building a dedicated in-panel drafting interface or content editor.
- Rationale: Deliver differentiated value through organizational knowledge and evidence while allowing content specialists to use familiar AI writing tools. Minimize implementation scope and avoid duplicating a CMS or general-purpose writing assistant.
- MVP scope: Present actionable content opportunities and briefs grounded in the same authorized, validated knowledge used by Customer Intelligence. Provide the supporting context, intended audience, rationale, suggested format/outline and permitted evidence references, with explicit scope and uncertainty. Supply reviewed MCP retrieval/tools sufficient to support client-side drafting with relevant authorized knowledge. Exact brief fields, prioritization, tool contracts, compatibility tests and acceptance thresholds remain pending scoped PRD and technical design.
- Deferred / out of scope: First-party draft generation UI, dedicated editor, content project management, editorial calendar, publishing integrations and automatic publication are not initial deliverables. This does not remove the governed AI execution needed to create opportunities and briefs.
- Constraints and implications: Follow D-015, D-016, D-024 through D-027, D-029, D-032 through D-041. Distinguish observed questions/concerns, validated knowledge, suggested content and generated drafts. Do not infer search volume, SEO demand, market-wide prevalence or current factual claims without suitable evidence; single-operator findings retain their limited scope. Require authorized source and evidence access, privacy minimization and approved external disclosure for both AI providers and MCP clients. Drafts are not validated knowledge by default and must be reviewed before public use. New MCP capabilities require explicit implementation, security review and real-client verification; current transport support does not establish readiness. No live processing, external disclosure or publication is authorized by this decision alone.
- Supersedes: None; narrows the initial delivery surface under D-027.
- Affected documents/components: Content Intelligence application, opportunity and brief presentation, shared knowledge retrieval, MCP tool contracts, access policy, future scoped PRD, architecture, roadmap and acceptance tests.

### D-043 — Balanced MVP success criteria (C)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Evaluate pilot success across technical reliability, knowledge quality and business value together. Security, privacy and authorization are mandatory gates for progression, not trade-offs against quality, cost or business usefulness.
- Rationale: A technically functioning pipeline alone does not demonstrate usable knowledge; useful-looking outputs without reliable evidence and security are insufficient for safe expansion.
- MVP scope: Define a staged evaluation protocol under D-040 with technical measures (schema-valid outputs, processing success, evidence traceability, replay/idempotency, usage/cost and latency), knowledge-quality measures (precision, recall, evidence support, critical errors and authorized specialist review), and practical business measures (usefulness of customer insights, actionable content opportunities, usable briefs, measured research time and feedback from initial technical and content users). Define measurement units, denominators, sampling, human reference labels and reviewer adjudication before each evaluation stage. Review outcomes before expanding sample size or approving broader scope. Every authoritative knowledge unit must retain inspectable permitted evidence; mandatory security and privacy checks must pass.
- Provisional targets, not approved numerical release gates: 99% schema-valid outputs, 98% processing success, 100% evidence traceability for validated knowledge, 90% extraction precision, 80% extraction recall and 95% evidence grounding were discussion starting points. Calibrate exact numerical gates using the initial evaluation and obtain approval before larger runs; do not interpret aggregate targets as permission to publish unsupported claims. Zero observed unauthorized accesses and zero observed critical validated-knowledge errors are safety expectations, not statistical proof of absence; any confirmed violation must be investigated and resolved before progression. Exact business targets and baseline measurement remain open.
- Constraints and implications: Follow D-003, D-016, D-025, D-031 through D-040 and D-042. Use synthetic tests first; any real-data evaluation requires explicit source, retention, provider/disclosure and budget authorization. Respect the single-operator boundary and report coverage, uncertainty and limitations. Do not conflate successful schema validation with semantic accuracy, evidence linkage with evidence support, or call count with unique customers. No automatic expansion to further operators or deployment based on scores. Record evaluation evidence and known limitations without publishing customer data in the public repository. This decision does not authorize real-data processing, spending, external disclosure or production changes.
- Supersedes: None; refines D-017, D-032 and D-040.
- Affected documents/components: Pilot acceptance plan, evaluation datasets and metrics, security tests, extraction and validation pipelines, Customer/Content Intelligence workflows, future scoped PRD, roadmap and acceptance tests.

### D-044 — Initial pilot time window (A)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Limit the initial historical pilot population to eligible calls from the most recent 30 days for the single selected operator under D-040. Retain configurable window support under D-031; this choice does not authorize processing older history or automatically expanding the pilot.
- Rationale: Prioritize recent conversations and constrain initial cost, data exposure and evaluation complexity while retaining a path to later historical analysis.
- MVP scope: Apply an explicit operator and time-range boundary to the first pilot's historical extraction and evaluation. Resolve and record the actual window bounds, reference date/time, source timestamp semantics, timezone, eligible population, processed coverage and missing data before execution. Freeze the evaluation population/window for reproducible comparisons where feasible; incremental processing of new eligible calls remains separately governed under D-031. Sample size remains adjustable within the approved population and evaluation gates under D-040 and D-043.
- Deferred / out of scope: Older historical windows, seasonal/year-over-year comparisons and automatic historical expansion are not part of the first approved pilot population. Longer windows require separate scope approval. The pilot window does not establish a data-retention period or deletion policy.
- Constraints and implications: Follow D-016, D-025, D-031, D-035 through D-040 and D-043. Confirm source-backed operator identity, date field meaning and timezone before applying the boundary. Exclude or separately flag ambiguous and missing timestamps rather than guessing eligibility. Do not silently widen the window or add operators if the eligible population is small. Limit conclusions to the actual operator, period and measured coverage; do not infer seasonality or organization-wide/market-wide behavior from this sample. All source, retention, provider disclosure and budget approvals remain prerequisites to real-data processing. Source access remains read-only. No copying, external disclosure, spending, production changes or live processing is authorized by this decision alone.
- Supersedes: None; narrows initial pilot scope under D-031 and D-040 without changing the configurable platform architecture.
- Affected documents/components: Pilot population and sampling, pipeline window configuration, source adapter, evaluation reports, future scoped PRD, roadmap and acceptance tests.

### D-045 — Simple hard AI budget limits with extension path (B+)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Start with centrally enforced organization-level and execution-level AI spending limits, including limits for pilot/evaluation runs. Record request-level token usage and cost where available and attribute usage/cost to the relevant organization and pipeline. Stop admitting new chargeable requests when the applicable budget is exhausted or cannot safely accommodate the request. Preserve an extension path to advanced multi-level allocation across pipelines and applications.
- Rationale: Keep initial spending predictable and auditable without building a full billing system or complex allocation engine; support controlled evaluation before progressively increasing the volume of processed data.
- MVP scope: Configurable organization and run limits, request-level usage/cost records, pipeline-level reporting, pre-dispatch budget enforcement and visible budget-blocked execution state. Support safe pause/resume of bounded processing after authorized budget changes, preserving completed work. Account for concurrent requests, retries, reserved estimates, in-flight spend and provider-reported actuals so parallel execution cannot silently bypass limits. Distinguish estimated, reported and unknown costs; missing usage/pricing must not be treated as free. Reconcile actual charges and surface discrepancies or overrun risk, rather than promising exact provider-side spend caps where the provider cannot guarantee them. Exact monetary units, period/reset rules, estimation/reservation mechanism, concurrency limits and administrative permissions remain pending scoped PRD and technical design.
- Pilot budgeting: Use measured cost from a bounded initial sample to inform later stage budgets. A finite explicitly approved cap is required even for the initial chargeable sample; no monetary amount, provider pricing assumption or spending authorization is established by this decision. Budget approval is separate from approval to access, retain or externally disclose real data.
- Deferred / out of scope: Advanced hierarchical allocation, separate application/pipeline budget quotas, customer billing, wallet and invoicing are not initial deliverables. Pipeline cost attribution does not imply a separate pipeline spending cap in MVP.
- Constraints and implications: Follow D-016, D-019, D-020, D-031, D-038 through D-040 and D-043 through D-044. Enforce limits server-side at the centralized AI Gateway for all applicable chargeable executions, including retries; use conservative estimates and fail closed when cost authorization cannot be established. Do not bypass the limit by switching providers, credentials or task categories. Restrict budget configuration and usage visibility to authorized roles, isolate organizations, protect sensitive payloads and credentials, and preserve auditability. Reaching a limit blocks new AI requests rather than discarding completed knowledge or disabling unrelated read-only reporting. No live processing, spending, external disclosure or deployment is authorized by this decision alone.
- Supersedes: None; refines D-031 and D-039.
- Affected documents/components: AI Gateway, usage ledger and cost estimation, budget enforcement, processing scheduler, run state and recovery, organization settings, pilot evaluation, future scoped PRD, architecture, data model and acceptance tests.

### D-046 — Non-destructive source preservation
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner discussion during pilot discovery
- Decision: Keep customer-owned original/source data intact. Panadan must not delete, alter, redact in place, overwrite or otherwise mutate the organization's existing source records, transcripts, audio, metadata, analyses or other independently owned information. Processing, privacy filtering, normalization and knowledge extraction operate on permitted reads and Panadan-controlled representations only.
- Rationale: Preserve the customer's operational records and source of truth independently of the derived knowledge lifecycle. Enable safe reprocessing, evidence traceability and reversal of Panadan-side changes without impacting the existing system.
- MVP scope: Strictly read-only source adapter and database access; perform redaction before durable storage of authorized filtered transcripts under D-036/D-037; maintain source/revision lineage without altering originals. Local retention, correction, revocation, deletion and reprocessing apply to Panadan-controlled copies, derivatives and knowledge as required by applicable policy. Source-side changes or deletions made by the source owner must be handled through reconciliation and evidence invalidation according to verified source contracts, not by attempting to undo or propagate deletions to the source.
- Authorization boundary: General processing approval is a prerequisite, not unrestricted access or proof that every specific provider, data class, retention period, MCP client or intermediary is authorized. Before real-data execution, privately verify and document the applicable source-owner scope, retention and external disclosure/provider terms, stable operator identity and time-window semantics, budget, security gates and explicit execution approval. Do not publish customer-specific permissions, identities, records or private commercial details in this public repository. No provider or live execution is authorized solely by this decision.
- Constraints and implications: Follow D-001, D-005, D-007, D-016, D-028 and D-035 through D-045. Enforce source write prohibition in credentials/privileges, application and worker code, fixed read-only transactions and integration tests. No source INSERT, UPDATE, DELETE, TRUNCATE, DDL, write-capable functions or deletion propagation. Historical source privileges require verification and least-privilege remediation by an authorized DBA before live use. The separately authorized destination integration under D-007 is not a source-write exception: restrict it to explicitly designated Panadan-managed knowledge records/fields, never unrelated or pre-existing customer-owned data. Any local deletion or retention obligation remains applicable to Panadan's own copies and derivatives; preserving source originals does not authorize indefinite local retention or prevent the source owner from exercising their own deletion rights. No migration, production change, data transfer or spending occurs as a result of recording this decision.
- Supersedes: None; reinforces D-001, D-005, D-007, D-028 and D-037.
- Affected documents/components: Source connectors and database privileges, ingestion/redaction, resource representations and retention, reconciliation, destination integration, future scoped PRD, architecture, data model, roadmap and security acceptance tests.

### D-047 — Modular monolith and independent workers (AP-01)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 5 architecture and AP-01–AP-10.
- Decision: Keep a shared Python/FastAPI codebase with explicit domain module boundaries and separate collection, scheduling, knowledge-processing and outbound worker runtimes. Scale processes independently without introducing mandatory microservices.
- Rationale: Reuse the existing stack and reduce operational overhead; split services only when measured load, security isolation or failure characteristics justify it.
- MVP scope and constraints: Logical module names and process counts remain implementation details; separate credentials and network permissions by runtime; preserve legacy reporting and guarded deployment.
- Supersedes: None; refines D-002, D-018, D-019, D-023.
- Affected documents/components: [ARCHITECTURE.md](ARCHITECTURE.md), Phase 6 data model, roadmap, relevant runtime modules and acceptance tests.
- Authorization boundary: Design approval only; no implementation, production migration, live data handling, provider request, spending or deployment authorized by this entry.

### D-048 — Owned PostgreSQL state and durable queue (AP-02)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 5 architecture and AP-01–AP-10.
- Decision: Use Panadan-owned PostgreSQL 18-compatible relational state, typed validated JSONB extensions and a PostgreSQL-backed durable job queue as the initial architecture.
- Rationale: Reuse the existing owned database and transactional consistency rather than adding unneeded infrastructure.
- MVP scope and constraints: Exact schema, migrations, indexes, workload bounds and roles require review. No required Redis, broker, graph/vector database or object storage initially; future additions depend on evidence. Never use Odoo for platform state.
- Supersedes: None; refines D-005, D-022, D-031.
- Affected documents/components: [ARCHITECTURE.md](ARCHITECTURE.md), Phase 6 data model, roadmap, relevant runtime modules and acceptance tests.
- Authorization boundary: Design approval only; no implementation, production migration, live data handling, provider request, spending or deployment authorized by this entry.

### D-049 — Single identity authority and workspace identity bridge (AP-03)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 5 architecture and AP-01–AP-10.
- Decision: Retain the existing identity authority initially, with an explicit stable principal bridge and one authoritative platform workspace-policy store. Intersect current authentication, consent and domain grants.
- Rationale: Avoid a speculative auth replacement while establishing tenant authorization.
- MVP scope and constraints: No binding by unverified email/name, duplicate login authority, silent fallback or production use of the staging-only PG auth selector. Recheck revocations and isolate legacy global reporting. Block activation and review an authorized single-authority migration if the bridge cannot meet safety requirements.
- Supersedes: None; refines D-010, D-016, D-023.
- Affected documents/components: [ARCHITECTURE.md](ARCHITECTURE.md), Phase 6 data model, roadmap, relevant runtime modules and acceptance tests.
- Authorization boundary: Design approval only; no implementation, production migration, live data handling, provider request, spending or deployment authorized by this entry.

### D-050 — Tenant-scoped schema and defense-in-depth RLS (AP-04)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 5 architecture and AP-01–AP-10.
- Decision: Use a shared schema with tenant-scoped keys and foreign keys, server-side scope enforcement, PostgreSQL row-level security and narrow runtime roles.
- Rationale: Enable reusable organization configuration while rejecting cross-tenant data references and accidental queries.
- MVP scope and constraints: Exact policies, pool context reset, privileged dispatcher boundaries and role grants require Phase 6 design and negative tests. RLS is not protection from compromised arbitrary SQL; no client-controlled trusted context. Explicitly authorized sharing is a projection/grant boundary, not a raw tenant bypass.
- Supersedes: None; refines D-011, D-016, D-023.
- Affected documents/components: [ARCHITECTURE.md](ARCHITECTURE.md), Phase 6 data model, roadmap, relevant runtime modules and acceptance tests.
- Authorization boundary: Design approval only; no implementation, production migration, live data handling, provider request, spending or deployment authorized by this entry.

### D-051 — Pre-persistence redaction and separate source reader (AP-05)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 5 architecture and AP-01–AP-10.
- Decision: Handle unredacted call text transiently inside a separately governed read-only collection/preprocessing runtime; persist only approved filtered representations and provenance in the new knowledge path.
- Rationale: Prevent accidental raw transcript persistence and isolate source access from AI processing.
- MVP scope and constraints: No raw text in queues, caches, logs, backups or failed jobs. Knowledge workers do not receive source DB credentials. Deterministic filtering remains best effort and must meet approved privacy policy before real use. Existing source records and legacy data stay untouched.
- Supersedes: None; refines D-035, D-036, D-037, D-046.
- Affected documents/components: [ARCHITECTURE.md](ARCHITECTURE.md), Phase 6 data model, roadmap, relevant runtime modules and acceptance tests.
- Authorization boundary: Design approval only; no implementation, production migration, live data handling, provider request, spending or deployment authorized by this entry.

### D-052 — Versioned durable orchestration and idempotent effects (AP-06)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 5 architecture and AP-01–AP-10.
- Decision: Use deterministic orchestration with versioned tasks, leased claims, fencing, bounded retries and short transactional local effects. At-least-once execution with replay-safe results; no false exactly-once external guarantee.
- Rationale: Support safe resumption, incremental processing, durable error visibility and cost accounting.
- MVP scope and constraints: Do not hold transactions over network calls. Separate source checkpoint and processing coverage; reconcile uncertain external effects and costs before retry. Exact state transitions and leases require design/tests.
- Supersedes: None; refines D-009, D-019, D-030, D-031, D-045.
- Affected documents/components: [ARCHITECTURE.md](ARCHITECTURE.md), Phase 6 data model, roadmap, relevant runtime modules and acceptance tests.
- Authorization boundary: Design approval only; no implementation, production migration, live data handling, provider request, spending or deployment authorized by this entry.

### D-053 — Relational knowledge and evidence architecture (AP-07)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 5 architecture and AP-01–AP-10.
- Decision: Use relational version/evidence links, typed extraction, deterministic aggregation and bounded semantic grouping for initial knowledge retrieval and validation.
- Rationale: Support inspectable lineage and exact counts without speculative graph or embedding infrastructure.
- MVP scope and constraints: No required graph/ontology/vector store initially. Preserve context, uncertainty, scope, source authority and review. Evaluate future search/indexing choices with measured workload and permission tests.
- Supersedes: None; refines D-004, D-021, D-022, D-030, D-032, D-041.
- Affected documents/components: [ARCHITECTURE.md](ARCHITECTURE.md), Phase 6 data model, roadmap, relevant runtime modules and acceptance tests.
- Authorization boundary: Design approval only; no implementation, production migration, live data handling, provider request, spending or deployment authorized by this entry.

### D-054 — Governed provider resolution and atomic budget admission (AP-08)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 5 architecture and AP-01–AP-10.
- Decision: Resolve explicit approved provider/model and managed credentials through the shared gateway; reserve organization and execution budget atomically before chargeable dispatch.
- Rationale: Enforce consistent disclosure, model and spending policy across feature modules.
- MVP scope and constraints: Existing gateway reuse is conditional on verified capabilities; no provider selected. Recheck authorization before egress, reconcile actual/uncertain charges, avoid unapproved fallback. No direct feature-to-provider calls, billing or BYOK in MVP.
- Supersedes: None; refines D-020, D-038, D-039, D-045.
- Affected documents/components: [ARCHITECTURE.md](ARCHITECTURE.md), Phase 6 data model, roadmap, relevant runtime modules and acceptance tests.
- Authorization boundary: Design approval only; no implementation, production migration, live data handling, provider request, spending or deployment authorized by this entry.

### D-055 — Shared authorized query services (AP-09)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 5 architecture and AP-01–AP-10.
- Decision: Use shared scoped query/read services for web, REST and MCP, with independent Resource and Knowledge retrieval contracts and common projections/metrics.
- Rationale: Prevent duplicated application data silos and inconsistent permission/aggregation semantics.
- MVP scope and constraints: Preserve legacy interfaces; new contracts and compatible client flows require verification. No unrestricted SQL, implicit raw transcript access or unauthorized evidence projection. Exact routes/tool names remain open.
- Supersedes: None; refines D-013, D-015, D-016, D-026, D-042.
- Affected documents/components: [ARCHITECTURE.md](ARCHITECTURE.md), Phase 6 data model, roadmap, relevant runtime modules and acceptance tests.
- Authorization boundary: Design approval only; no implementation, production migration, live data handling, provider request, spending or deployment authorized by this entry.

### D-056 — Durable outbox and separate destination runtime (AP-10)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 5 architecture and AP-01–AP-10.
- Decision: Use a separate outbound sync worker with a durable outbox, approved versioned projections, dedicated narrow destination credentials and idempotent/reconciled delivery.
- Rationale: Preserve source immutability and handle delivery retry/out-of-order effects safely.
- MVP scope and constraints: Never mutate unrelated customer-owned data or reuse source credentials. Destination contract, version ordering, revocation and live rights must be verified; synthetic target first. No two-way sync or promise to recall external copies.
- Supersedes: None; refines D-007, D-013, D-016, D-046.
- Affected documents/components: [ARCHITECTURE.md](ARCHITECTURE.md), Phase 6 data model, roadmap, relevant runtime modules and acceptance tests.
- Authorization boundary: Design approval only; no implementation, production migration, live data handling, provider request, spending or deployment authorized by this entry.

### D-057 — Additive knowledge schema (DM-01)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 6, DM-01–DM-09 and preferred UI direction with required additions.
- Decision: Create the new platform model in the separate Panadan-owned panadan_knowledge schema; preserve existing panadan_ingest and panadan_auth schemas and the approved identity bridge.
- Rationale: Isolate new development from existing reporting and avoid destructive migration or an unapproved auth cutover.
- MVP scope and constraints: Add migrations incrementally; never edit applied migrations or automatically assign legacy data to a tenant. Verify owned DB target, mapping and backup/restore before any approved migration.
- Supersedes: None; refines D-046–D-049.
- Affected documents/components: [DATA_MODEL.md](DATA_MODEL.md), architecture, roadmap, corresponding migrations/services and tests.
- Authorization boundary: Design approval only; no implementation, live data, spending, migration, deployment or source write authorized by this entry.

### D-058 — Tenant composite integrity and explicit sharing (DM-02)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 6, DM-01–DM-09 and preferred UI direction with required additions.
- Decision: Use workspace-scoped composite primary/foreign keys, scoped runtime roles and RLS; use explicitly authorized sharing projections rather than raw cross-tenant reads.
- Rationale: Enforce isolation and same-parent integrity at multiple layers.
- MVP scope and constraints: Exact DDL, role grants and RLS must be tested, including missing context, pooled connection reset, revocation and negative FKs. Sharing cannot expand underlying access; no client-selected trusted context.
- Supersedes: None; refines D-011, D-016, D-050.
- Affected documents/components: [DATA_MODEL.md](DATA_MODEL.md), architecture, roadmap, corresponding migrations/services and tests.
- Authorization boundary: Design approval only; no implementation, live data, spending, migration, deployment or source write authorized by this entry.

### D-059 — Versioned resource representations (DM-03)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 6, DM-01–DM-09 and preferred UI direction with required additions.
- Decision: Represent each source item as a logical Resource with immutable source revisions and separately versioned approved filtered representations.
- Rationale: Preserve provenance and enable reprocessing without touching originals.
- MVP scope and constraints: No durable unredacted call text; verify stable source IDs and ordering, redaction, permitted fields and retention. Payload immutability does not override authorized local erasure.
- Supersedes: None; refines D-001, D-005, D-035–D-037, D-046, D-051.
- Affected documents/components: [DATA_MODEL.md](DATA_MODEL.md), architecture, roadmap, corresponding migrations/services and tests.
- Authorization boundary: Design approval only; no implementation, live data, spending, migration, deployment or source write authorized by this entry.

### D-060 — Versioned execution and frozen population (DM-04)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 6, DM-01–DM-09 and preferred UI direction with required additions.
- Decision: Pin objective/pipeline versions and run manifests, retain measured population membership and use fenced durable work items and attempts.
- Rationale: Make execution reproducible, scoped and replay-safe.
- MVP scope and constraints: Separate source checkpoints from processing coverage; frozen manifests do not override current authorization. Unknown eligible totals remain unknown. Implement short claim/finalize transactions, bounded retries and explicit recovery.
- Supersedes: None; refines D-029–D-031, D-040, D-044, D-052.
- Affected documents/components: [DATA_MODEL.md](DATA_MODEL.md), architecture, roadmap, corresponding migrations/services and tests.
- Authorization boundary: Design approval only; no implementation, live data, spending, migration, deployment or source write authorized by this entry.

### D-061 — Reusable observation sets and exact evidence anchors (DM-05)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 6, DM-01–DM-09 and preferred UI direction with required additions.
- Decision: Use compatible observation sets, evidence anchors tied to exact filtered representation revisions, and relational processed/matched aggregate membership.
- Rationale: Avoid duplicate extraction and inflated counts; make claims inspectable.
- MVP scope and constraints: Validate structured outputs and Unicode codepoint spans, maintain explicit compatibility and current permissions. Use deterministic distinct-call counts and denominators; no customer identity or market-wide inference.
- Supersedes: None; refines D-030, D-032, D-034, D-053.
- Affected documents/components: [DATA_MODEL.md](DATA_MODEL.md), architecture, roadmap, corresponding migrations/services and tests.
- Authorization boundary: Design approval only; no implementation, live data, spending, migration, deployment or source write authorized by this entry.

### D-062 — Versioned knowledge lifecycle and invalidation (DM-06)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 6, DM-01–DM-09 and preferred UI direction with required additions.
- Decision: Separate logical knowledge units from revisions, record validation/review/lifecycle transitions, and invalidate affected authoritative projections when evidence becomes unavailable or stale.
- Rationale: Preserve contextual knowledge and support correction without silently rewriting claims.
- MVP scope and constraints: No unsupported authoritative claims, automatic resurrection of prior versions or single opaque trust score. Retention may erase payloads; exact risk rules, reviewers and physical state constraints remain subject to implementation verification.
- Supersedes: None; refines D-003, D-004, D-021, D-032, D-053.
- Affected documents/components: [DATA_MODEL.md](DATA_MODEL.md), architecture, roadmap, corresponding migrations/services and tests.
- Authorization boundary: Design approval only; no implementation, live data, spending, migration, deployment or source write authorized by this entry.

### D-063 — Versioned taxonomy and pinned knowledge packages (DM-07)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 6, DM-01–DM-09 and preferred UI direction with required additions.
- Decision: Use governed taxonomy versions and reviewed suggestions, pinned package revision membership, and separate derived opportunity/brief records.
- Rationale: Keep historical meaning and reuse shared knowledge without creating a content silo.
- MVP scope and constraints: No automatic taxonomy mutation or silent follow-latest package changes in MVP. Recheck underlying evidence/access and freshness. No in-panel drafting, CMS or publishing.
- Supersedes: None; refines D-013, D-027, D-041, D-042, D-053, D-055.
- Affected documents/components: [DATA_MODEL.md](DATA_MODEL.md), architecture, roadmap, corresponding migrations/services and tests.
- Authorization boundary: Design approval only; no implementation, live data, spending, migration, deployment or source write authorized by this entry.

### D-064 — Dual budget reservation and usage ledger (DM-08)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 6, DM-01–DM-09 and preferred UI direction with required additions.
- Decision: Atomically reserve against organization and run budgets, record immutable usage/adjustment ledger events, and retain uncertain reservations until reconciliation.
- Rationale: Prevent concurrency bypass, support audit and distinguish estimated/actual/unknown spend.
- MVP scope and constraints: No exact provider-side cap guarantee, no missing cost treated as free, no double counting org and run charges. All application AI executes through governed run/configuration. Currency, rate, caps and provider contract still open.
- Supersedes: None; refines D-039, D-045, D-054.
- Affected documents/components: [DATA_MODEL.md](DATA_MODEL.md), architecture, roadmap, corresponding migrations/services and tests.
- Authorization boundary: Design approval only; no implementation, live data, spending, migration, deployment or source write authorized by this entry.

### D-065 — Versioned delivery and retention barriers (DM-09)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 6, DM-01–DM-09 and preferred UI direction with required additions.
- Decision: Use versioned destination projections/outbox and scoped local erasure records/restore barriers.
- Rationale: Keep customer originals intact and prevent stale delivery or restored revoked data.
- MVP scope and constraints: Separate credentials, approved projection only, version/idempotency/reconciliation checks, no unrelated destination mutations. No implied external recall or indefinite local retention; verify private destination and retention contracts.
- Supersedes: None; refines D-007, D-037, D-046, D-056.
- Affected documents/components: [DATA_MODEL.md](DATA_MODEL.md), architecture, roadmap, corresponding migrations/services and tests.
- Authorization boundary: Design approval only; no implementation, live data, spending, migration, deployment or source write authorized by this entry.

### D-066 — Preferred visual direction with required workflow additions (UI direction)
- Date: 2026-11-26
- Status: Accepted
- Approval: Product owner explicitly approved Phase 6, DM-01–DM-09 and preferred UI direction with required additions.
- Decision: Adopt the owner-supplied visual reference direction: warm neutral surfaces, muted green/olive accents, restrained borders, editorial typography, compact readable Persian RTL knowledge workspace, responsive layouts. Complete all required PRD workflows in the same design language.
- Rationale: Provide a distinctive coherent interface without sacrificing required knowledge, operations or access workflows.
- MVP scope and constraints: UI_DESIGN_REVIEW.md governs fit and additions: objectives, pipelines/runs, taxonomy, review queue, distribution and legacy reporting/health; deepen existing detail, budget and access workflows. Direction approved, not final logo, exact tokens, navigation, component specs or all individual screens. Use synthetic examples and verify accessibility/contrast/licensing. Do not publish the supplied image or treat its figures as real.
- Supersedes: None; refines D-015, D-023, D-026, D-029, D-033, D-042, D-055.
- Affected documents/components: [UI_DESIGN_REVIEW.md](UI_DESIGN_REVIEW.md), PRD UI requirements, roadmap and frontend acceptance.
- Authorization boundary: Design approval only; no implementation, live data, spending, migration, deployment or source write authorized by this entry.

### D-067 — Approved implementation roadmap and incremental delivery
- Date: 2026-11-26
- Status: Accepted
- Approval: Owner explicitly approved Phase 7 Implementation Roadmap, use of both UI references and commencement of Phase 8 milestone M00.
- Decision: Follow the dependency-ordered M00–M13 implementation roadmap and U0–U11 UI track. Use both the approved visual reference and the supplemental interaction concept in UI design, within D-066 and existing MVP requirements. Start with M00 baseline, isolated test harness and implementation status evidence; proceed to later increments only after their prerequisites and separate authorization.
- Rationale: Deliver reversible, independently testable vertical slices while preserving existing reporting, source immutability and operational safety.
- MVP scope and constraints: Synthetic-first, default-off capabilities, evidence-based gates, approved feature branch only. Preserve main and backup. Exact design tokens, screen/navigation details, private data contracts, provider, budget and runtime approvals remain open. Supplemental UI reference does not add semantic/vector search, automatic package updates, raw transcript exposure, additional active connectors, audio processing or other deferred capabilities.
- Supersedes: None; operationalizes D-017 and D-047–D-066.
- Affected documents/components: [ROADMAP.md](ROADMAP.md), [UI_DESIGN_REVIEW.md](UI_DESIGN_REVIEW.md), implementation status and test evidence.
- Authorization boundary: M00 only. No M01 implementation, live queries, production migrations, paid provider calls, external disclosure, PR creation, merge, deployment or source changes authorized by this entry.

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

Phase 5 architecture is approved: [ARCHITECTURE.md](ARCHITECTURE.md) maps AP-01–AP-10 to D-047–D-056. Use a modular monolith with independent workers, owned PostgreSQL durable state/queue, a single identity authority with workspace bridge, tenant-scoped relational keys and RLS, pre-persistence call redaction, fenced/idempotent processing, relational evidence, governed budget admission, shared query services and a separate destination outbox. Phase 6 data model DM-01–DM-09 is accepted as D-057–D-065: additive knowledge schema, composite integrity and sharing projection, versioned resources/execution/observations/knowledge/taxonomy/packages, dual-budget ledger and delivery/retention controls. D-066 adopts the preferred UI direction with the additions in [UI_DESIGN_REVIEW.md](UI_DESIGN_REVIEW.md). Detailed implementation contracts and activation prerequisites remain open; no new capability is production-verified.

Sources (call center, CRM, web, authorized messaging, feedback, manual uploads) -> Collection & Integrations -> Resources -> Knowledge Engine -> Knowledge Base.
Knowledge Objectives and Knowledge Pipelines configure extraction; AI Gateway, authorization, storage and audit are cross-cutting. D-038 selects approved external AI APIs for initial execution through the centralized gateway; private/hybrid inference is not an MVP commitment. D-039 uses centrally managed provider credentials with organization-scoped usage/budget controls and a later BYOK extension path. D-045 specifies simple organization and execution spending limits with request-level accounting, pipeline attribution and an extension path for advanced allocation. Resources and Knowledge independently feed Applications, API/MCP and authorized distribution. Panadan sends validated knowledge to customer systems using a separate, explicitly authorized destination integration. Under D-046, writes are limited to designated Panadan-managed knowledge records/fields and must not mutate existing customer-owned data or the read-only source.

### Resources

One logical resource can have multiple optional representations: e.g. call audio, metadata, transcript and extracted fields. Keep original data intact and track links, source IDs, timestamps, version and processing lineage. Reuse existing processed data when available; absent representations are not fabricated. Under D-035, call-derived semantic knowledge prioritizes authorized privacy-filtered transcripts; verified metadata provides context, while prior AI analyses remain attributed supplementary inputs rather than independent evidence. D-036 starts with deterministic redaction and preserves an extension boundary for later context-aware hybrid redaction; filtered transcripts remain potentially sensitive. Under D-037, the initial call workflow stores approved filtered representations and permitted metadata/references locally, while unredacted originals remain at the source. Store or reference other originals per customer policy. Ingestion, resource processing and knowledge production are independent operations. Protect source read-only guarantees; use only authorized source connections. D-046 prohibits any Panadan mutation or deletion of customer-owned originals; filtering and lifecycle operations apply only to Panadan-controlled copies and derivatives under applicable policies.

### Knowledge

Knowledge units retain subject/claim, context and conditions, temporal scope, evidence/source references, validation state, ownership/access policy, versions and history. Collections/packages reference units rather than duplicating uncontrolled claims. Knowledge changes are versioned; superseded versions remain available only according to retention and authorization policies. A proposed lifecycle includes Proposed, Under Review, Active, Disputed, Outdated, Rejected and Archived; exact state machine is pending design. Under D-041, predefined editable categories coexist with bounded AI topic suggestions; authorized review is required before taxonomy changes become official. Only appropriately validated and authorized knowledge may be distributed as authoritative. Risk depends on both the claim and its intended use. Do not treat model confidence as evidence reliability or operational risk. Under D-032, aggregate validation keeps reliability, prevalence and business importance distinct and exposes evidence, population, coverage, source authority, context, freshness, consistency and intended-use risk criteria; deterministic checks, bounded AI assistance and risk-based human review are complementary.

A source is authoritative only for appropriate subjects. Contradictions require matching entity, property, applicable conditions and time; missing context is not a conflict. For example, tour price depends on travel dates, destination, exact hotel/room, traveler count/ages, flight, meals, transfer, inclusions, currency, price basis, inventory and quote validity. Distinct offers may all be correct. Do not fill unknown conditions with guesses. Live quotes and bookings belong in Resources; pricing rules and supported patterns may be Knowledge. Retrieve current facts from authorized resources instead of presenting old claims as current prices.

### Collection and processing

Support API/CRM/database integrations, approved external sources and manual ingestion progressively. Under D-028, prioritize the existing call-center integration, manual resources and limited approved web resources in MVP; add other dedicated connectors when justified. Knowledge objectives describe what the organization needs to learn. Under D-029, provide reusable templates, customizable instances and simple structured custom objectives defining purpose, authorized sources, output schema, context and validation rules; associated pipeline configuration selects execution scope, schedule and model within those constraints. Scheduled/manual execution first; bounded discovery and event processing where useful. Track run status, errors and lineage. Under D-030, extract reusable source-level observations, aggregate and discover patterns, and validate candidate knowledge; prefer incremental processing and deterministic computation where suitable. Reuse only compatible, current, authorized extraction results. D-031 adds progressive historical backfill from a configurable recent window alongside incremental processing, with budget controls, pause/resume and explicit coverage reporting. Exact job semantics are pending technical design.

### Applications and AI

Applications can read both Resources and Knowledge under current permissions. Provide ready-made applications and simple organization-specific configuration (objective, allowed data/tools, instructions, model, input/output, execution and destination). Use ordinary code/SQL for deterministic tasks. Agents require explicit tool/data scopes, cost/time/step limits and approval for consequential actions. Do not automatically publish generated content or bypass knowledge review.

Centralize provider access and per-task model selection; track request/run/org/model/provider costs and budgets. Validate structured outputs where required; enforce provider/privacy policies and only permitted fallback. Assess existing AI API infrastructure before duplicating it.

### Security, organization and synchronization

Default deny; isolate organizations; enforce permissions server-side on all retrieval, processing, exports, API/MCP and background jobs. Role templates may be customized only within the grantor's authorized scope. External connections must not exceed current user permissions or their own selected grants; revocation must take effect for subsequent operations. Resource-level and field-level restrictions matter. Derived knowledge inherits source restrictions by default; widening access requires authorized review and appropriate sanitization. No private customer data or derived knowledge is shared across organizations without explicit authorization, even if anonymized. Shared sources also require usage rights.

Keep current source database read-only; knowledge export is a distinct destination with separately authorized credentials and narrow write access. Panadan manages knowledge versions and lifecycle; customer receives an authorized projection. Define sync failure/retry, deletion/revocation and version semantics before implementation. Never introduce general SQL execution or broaden existing sensitive MCP capabilities without explicit security review and approval.

## MVP boundaries and acceptance

Aim for one complete pilot flow: ingest selected sources (call center, selected online and/or manual inputs), view resources, configure objectives/pipelines, extract and validate contextual knowledge, manage units/packages, use authorized API/MCP and one-way sync, and deliver selected practical applications. D-024 selects limited Customer Intelligence and Content Intelligence as the initial applications on shared infrastructure. Market Intelligence is a subsequent desired extension; its release scope and timing remain open. D-025 prioritizes aggregate customer intelligence while preserving an extensible model for authorized individual analysis; individual profiling is not a required initial deliverable. D-026 selects a hybrid Customer Intelligence experience: evidence-backed insight feed, limited analytical dashboard and authorized MCP conversational access, with a dedicated conversational UI deferred. D-027 selects hybrid Content Intelligence: discovery and content briefs first, limited AI/MCP-assisted drafting, with full content management and publishing integrations deferred. D-028 selects progressive multi-source delivery: call-center data first, manual resources and limited approved web resources in MVP, further dedicated connectors later as justified. D-029 selects hybrid Knowledge Objectives, with reusable templates, customizable instances and simple structured custom objectives linked to governed pipelines. D-030 selects multi-stage extraction: source-level observations, aggregation and pattern discovery, then evidence-based knowledge validation, with compatible observation reuse and incremental processing. D-031 selects progressive historical backfill plus ongoing incremental processing, with configurable windows, bounded budget, pause/resume and visible coverage. D-032 selects multi-dimensional aggregate validation with separately interpretable reliability, prevalence and business importance, inspectable evidence and risk-based review. D-033 prioritizes technical/AI and content/SEO workflows with shared technical and authorized domain-specialist human validation. D-034 selects seven initial Knowledge Objectives: Customer Questions, Customer Needs & Preferences, Customer Concerns, Purchase Barriers, Destination Intelligence, Price Sensitivity and Content Opportunities. D-035 selects transcript-first call knowledge extraction with privacy filtering, verified contextual metadata and supplementary attributed upstream AI outputs. D-036 selects deterministic rules-based redaction in MVP with a later upgrade path to context-aware hybrid redaction. D-037 selects selective local transcript storage: approved filtered transcripts and derived data locally, unredacted originals at the source. D-038 selects external AI API execution through the centralized gateway, conditional on explicit provider and data disclosure authorization. D-039 selects centrally managed AI provider credentials and organization-level usage/budget controls in MVP, with BYOK and custom endpoints deferred. D-040 selects progressive evaluation initially limited to one authorized call-center operator; sample-size expansion is gated and adding operators requires separate approval. D-041 selects a hybrid taxonomy with predefined editable categories and AI-proposed additions subject to authorized review. D-042 limits initial Content Intelligence delivery to discovery, briefs and outlines in the web application plus authorized MCP-assisted drafting; in-panel drafting and editorial management are deferred. D-043 selects balanced technical, knowledge-quality and business-value evaluation with mandatory security/privacy progression gates; numeric acceptance thresholds remain provisional pending calibration and approval. D-044 limits the initial historical pilot to the most recent 30 days of eligible calls for one authorized operator; longer windows require separate scope approval. D-045 selects simple hard organization and execution AI budget limits, with usage/cost accounting and pipeline attribution; advanced allocation and billing remain deferred. D-046 reinforces non-destructive source preservation and separates local processing/lifecycle operations from immutable-to-Panadan customer originals. Detailed workflows, data availability and rights, output requirements, validation and acceptance targets are still pending pilot discovery. Other proposed applications are not commitments.

Measure ingestion reliability, evidence-backed quality, reuse of knowledge across applications, freshness, access isolation, export correctness, measurable customer benefit and ability to onboard a second customer without rewriting the core. Under D-043, evaluate all three success dimensions together and require security/privacy gates to pass before progression. Quantitative targets need pilot validation and approval.

Defer broad connector catalogs, full visual builders, advanced knowledge graphs, full self-service, complex two-way sync, dynamic AI routing and automatic public content publishing.

## Execution and verification

1. Audit baseline code, schemas, migrations, permissions, integrations, UI, tests and deployment documentation. Classify each component Reuse / Extend / Refactor / Build / Remove (removal requires separate approval).
2. In parallel, deployment discovery: source inventory, data rights/quality, existing workflows, target users, objectives, actual use cases and measurable baseline.
3. Produce evidence-linked gap analysis, scoped PRD, technical architecture/data model, migration and security/test plans.
4. Develop incrementally on the feature branch. Preserve existing interfaces, source read-only constraints, production behavior and rollback options.
5. Verify a complete pilot flow with synthetic or explicitly approved data before deployment; do not deploy or change production without separate authorization.

The initial audit and gap analysis are recorded in [CURRENT_STATE.md](CURRENT_STATE.md) and [GAP_ANALYSIS.md](GAP_ANALYSIS.md); pilot discovery and PRD have been approved, and Phase 5 architecture choices AP-01–AP-10 are accepted as D-047–D-056. Phase 6 data model and UI direction are approved as D-057–D-066. Phase 7 roadmap is approved as D-067. Phase 8 M00 baseline/harness is authorized; subsequent implementation increments and live activation remain separately gated. Do not infer implemented or deployed capabilities from these decisions. See [historical decisions](../DECISIONS.md), [original reporting MVP PRD](../PRD.md), [status](../STATUS.md), [security](../SECURITY.md) and [production operations](../PRODUCTION_OPERATIONS.md). Existing safety/operational rules remain in force until a reviewed migration explicitly supersedes them. Update this document when the product owner approves a changed decision; distinguish accepted decisions from proposals and implementation evidence.
