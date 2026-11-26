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
Knowledge Objectives and Knowledge Pipelines configure extraction; AI Gateway, authorization, storage and audit are cross-cutting. D-038 selects approved external AI APIs for initial execution through the centralized gateway; private/hybrid inference is not an MVP commitment. D-039 uses centrally managed provider credentials with organization-scoped usage/budget controls and a later BYOK extension path. Resources and Knowledge independently feed Applications, API/MCP and authorized distribution. Panadan sends validated knowledge to customer systems using a separate, explicitly authorized destination integration.

### Resources

One logical resource can have multiple optional representations: e.g. call audio, metadata, transcript and extracted fields. Keep original data intact and track links, source IDs, timestamps, version and processing lineage. Reuse existing processed data when available; absent representations are not fabricated. Under D-035, call-derived semantic knowledge prioritizes authorized privacy-filtered transcripts; verified metadata provides context, while prior AI analyses remain attributed supplementary inputs rather than independent evidence. D-036 starts with deterministic redaction and preserves an extension boundary for later context-aware hybrid redaction; filtered transcripts remain potentially sensitive. Under D-037, the initial call workflow stores approved filtered representations and permitted metadata/references locally, while unredacted originals remain at the source. Store or reference other originals per customer policy. Ingestion, resource processing and knowledge production are independent operations. Protect source read-only guarantees; use only authorized source connections.

### Knowledge

Knowledge units retain subject/claim, context and conditions, temporal scope, evidence/source references, validation state, ownership/access policy, versions and history. Collections/packages reference units rather than duplicating uncontrolled claims. Knowledge changes are versioned; superseded versions remain available only according to retention and authorization policies. A proposed lifecycle includes Proposed, Under Review, Active, Disputed, Outdated, Rejected and Archived; exact state machine is pending design. Only appropriately validated and authorized knowledge may be distributed as authoritative. Risk depends on both the claim and its intended use. Do not treat model confidence as evidence reliability or operational risk. Under D-032, aggregate validation keeps reliability, prevalence and business importance distinct and exposes evidence, population, coverage, source authority, context, freshness, consistency and intended-use risk criteria; deterministic checks, bounded AI assistance and risk-based human review are complementary.

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

Aim for one complete pilot flow: ingest selected sources (call center, selected online and/or manual inputs), view resources, configure objectives/pipelines, extract and validate contextual knowledge, manage units/packages, use authorized API/MCP and one-way sync, and deliver selected practical applications. D-024 selects limited Customer Intelligence and Content Intelligence as the initial applications on shared infrastructure. Market Intelligence is a subsequent desired extension; its release scope and timing remain open. D-025 prioritizes aggregate customer intelligence while preserving an extensible model for authorized individual analysis; individual profiling is not a required initial deliverable. D-026 selects a hybrid Customer Intelligence experience: evidence-backed insight feed, limited analytical dashboard and authorized MCP conversational access, with a dedicated conversational UI deferred. D-027 selects hybrid Content Intelligence: discovery and content briefs first, limited AI/MCP-assisted drafting, with full content management and publishing integrations deferred. D-028 selects progressive multi-source delivery: call-center data first, manual resources and limited approved web resources in MVP, further dedicated connectors later as justified. D-029 selects hybrid Knowledge Objectives, with reusable templates, customizable instances and simple structured custom objectives linked to governed pipelines. D-030 selects multi-stage extraction: source-level observations, aggregation and pattern discovery, then evidence-based knowledge validation, with compatible observation reuse and incremental processing. D-031 selects progressive historical backfill plus ongoing incremental processing, with configurable windows, bounded budget, pause/resume and visible coverage. D-032 selects multi-dimensional aggregate validation with separately interpretable reliability, prevalence and business importance, inspectable evidence and risk-based review. D-033 prioritizes technical/AI and content/SEO workflows with shared technical and authorized domain-specialist human validation. D-034 selects seven initial Knowledge Objectives: Customer Questions, Customer Needs & Preferences, Customer Concerns, Purchase Barriers, Destination Intelligence, Price Sensitivity and Content Opportunities. D-035 selects transcript-first call knowledge extraction with privacy filtering, verified contextual metadata and supplementary attributed upstream AI outputs. D-036 selects deterministic rules-based redaction in MVP with a later upgrade path to context-aware hybrid redaction. D-037 selects selective local transcript storage: approved filtered transcripts and derived data locally, unredacted originals at the source. D-038 selects external AI API execution through the centralized gateway, conditional on explicit provider and data disclosure authorization. D-039 selects centrally managed AI provider credentials and organization-level usage/budget controls in MVP, with BYOK and custom endpoints deferred. D-040 selects progressive evaluation initially limited to one authorized call-center operator; sample-size expansion is gated and adding operators requires separate approval. Detailed workflows, data availability and rights, output requirements, validation and acceptance targets are still pending pilot discovery. Other proposed applications are not commitments.

Measure ingestion reliability, evidence-backed quality, reuse of knowledge across applications, freshness, access isolation, export correctness, measurable customer benefit and ability to onboard a second customer without rewriting the core. Quantitative targets need pilot validation.

Defer broad connector catalogs, full visual builders, advanced knowledge graphs, full self-service, complex two-way sync, dynamic AI routing and automatic public content publishing.

## Execution and verification

1. Audit baseline code, schemas, migrations, permissions, integrations, UI, tests and deployment documentation. Classify each component Reuse / Extend / Refactor / Build / Remove (removal requires separate approval).
2. In parallel, deployment discovery: source inventory, data rights/quality, existing workflows, target users, objectives, actual use cases and measurable baseline.
3. Produce evidence-linked gap analysis, scoped PRD, technical architecture/data model, migration and security/test plans.
4. Develop incrementally on the feature branch. Preserve existing interfaces, source read-only constraints, production behavior and rollback options.
5. Verify a complete pilot flow with synthetic or explicitly approved data before deployment; do not deploy or change production without separate authorization.

The initial audit and gap analysis are recorded in [CURRENT_STATE.md](CURRENT_STATE.md) and [GAP_ANALYSIS.md](GAP_ANALYSIS.md); pilot discovery is in progress. Do not infer implemented or deployed capabilities from these decisions. See [historical decisions](../DECISIONS.md), [original reporting MVP PRD](../PRD.md), [status](../STATUS.md), [security](../SECURITY.md) and [production operations](../PRODUCTION_OPERATIONS.md). Existing safety/operational rules remain in force until a reviewed migration explicitly supersedes them. Update this document when the product owner approves a changed decision; distinguish accepted decisions from proposals and implementation evidence.
