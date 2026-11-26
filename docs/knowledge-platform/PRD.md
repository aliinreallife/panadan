# Panadan Knowledge Platform — Product Requirements Document

| Document | Value |
| --- | --- |
| Version | 0.1 — Phase 4 review draft |
| Date | 2026-11-26 |
| Status | Proposed PRD, awaiting product-owner review |
| Product direction | Accepted public decisions D-001–D-046 (44 entries; intentional numbering gaps retained) |
| Evidence snapshot | Branch commit `7dece12c510631575ec2251b96f6ea37177c05f0` |
| Working branch | `feature/knowledge-platform` |
| Previous phases | Phase 1 audit and Phase 2 gap analysis completed; Phase 3 pilot discovery approved by product owner |
| Next phase | Phase 5 architecture, only after PRD approval |

## 1. Purpose and governing documents

Panadan is an organizational knowledge and AI infrastructure platform. It turns authorized information from multiple sources into inspectable, contextual, validated and reusable knowledge; delivers that knowledge and permitted resources to people, applications and AI clients; and preserves the customer's operational data and control over disclosure.

This PRD translates the accepted product decisions into reviewable requirements, workflows, scope and acceptance conditions. It is not a greenfield specification, implementation report, production runbook or permission to execute a real-data pilot.

Read alongside [DECISIONS.md](DECISIONS.md), [CURRENT_STATE.md](CURRENT_STATE.md), [GAP_ANALYSIS.md](GAP_ANALYSIS.md), [original reporting PRD](../PRD.md), [historical decisions](../DECISIONS.md), [STATUS.md](../STATUS.md), [SECURITY.md](../SECURITY.md), [READ_ONLY.md](../READ_ONLY.md), [DATA_DICTIONARY.md](../DATA_DICTIONARY.md), [README](../../README.md) and [AGENTS.md](../../AGENTS.md). Accepted decisions govern product direction; current operational and security constraints remain binding. If a conflict is found, surface it for review rather than silently relaxing it.

**Interpretation:** MUST denotes a proposed release requirement derived from accepted direction or a necessary safety condition. SHOULD denotes a recommended default subject to design review. Proposed details (screen grouping, output fields, numerical targets, roles and evaluation method) do not become accepted product decisions merely by appearing here. Changes to accepted choices require an entry in the canonical decision register under its maintenance protocol. Customer names, identities, private authorization artifacts, real records, pricing strategy and credentials belong in approved private deployment records, not this public repository.

## 2. Product problem, strategy and outcomes

Organizations accumulate data in operational systems, conversations, documents and online sources. Reports and isolated AI-generated summaries are useful but do not establish a maintained, reusable knowledge layer. Users need to understand what evidence supports a finding, what it applies to, whether it remains current and whether it can be used in a particular application.

Panadan follows Infrastructure First, Application Enabled (D-002), Use Case-driven Infrastructure (D-018) and Shared Core + Organization Workspace (D-023). The shared core must be reusable without a separate fork per customer. The first applications are Customer Intelligence and Content Intelligence; they share the same governed Resources, Observations and Knowledge rather than duplicating extraction or creating application-specific knowledge silos. Market Intelligence is a desired subsequent application, not an initial release commitment.

### 2.1 Goals

- Deliver a complete vertical slice from approved source collection to reusable knowledge and practical application consumption.
- Convert existing call transcripts into evidence-backed observations and useful aggregate findings while retaining scope, context, limitations and lineage.
- Give technical/AI specialists controlled configuration, quality inspection, execution and cost visibility; give content/SEO specialists actionable knowledge and briefs.
- Enable authorized independent retrieval of Resources and Knowledge through web, API and MCP, and narrow one-way distribution of validated knowledge to approved destinations.
- Preserve customer-owned originals, isolate workspaces, prevent unauthorized disclosure and bound AI expenditure.
- Demonstrate reuse through a second synthetic workspace using configuration rather than customer-specific core code.

### 2.2 Hypotheses to validate, not proven benefits

H1: The selected call corpus contains actionable questions, needs, concerns and purchase barriers. H2: Validated findings reduce content research effort and improve brief usefulness. H3: Reusing source-level observations reduces duplicate extraction cost. H4: Governed knowledge can be used consistently across web and MCP. H5: Assisted configuration can onboard a different workspace with the same core. No conversion uplift, SEO search demand, market share or organization-wide representativeness is claimed.

## 3. Existing product and transition constraints

The phase 1 audit and phase 2 gap analysis describe an existing FastAPI web/reporting service with Persian RTL UI, fixed read-only Odoo/PostgreSQL reporting access, REST, MCP Streamable HTTP, auth/consent/field projection, and an optional owned PostgreSQL foundation with source records, raw revisions, jobs, deterministic derived facts and sync checkpoints. These are reuse candidates, not proof of production readiness for a knowledge platform.

| Area | Product transition |
| --- | --- |
| Existing reporting UI, API, MCP and authentication | Preserve behavior and access restrictions; extend only after contract and regression tests. Reconcile historical docs versus actual transcript behavior. |
| Read-only source integration | Reuse audited patterns and explicit read-only transactions; verify effective DB privileges, source IDs, date/assignment semantics and update/delete contracts. |
| Owned platform DB and ingestion | Extend or refactor safely for tenant-scoped resources, representations and lineage; existing raw-revision ingestion must not persist unredacted call payloads for this pilot. |
| Global accounts and field policy | Address organization membership, tenant/row scope, invalid grant handling, legacy NULL grants, early data minimization and consistent policy across workers and interfaces. |
| Deterministic processing and checkpoints | Reuse concepts; extend for durable failure state, bounded retries, safe replay, model execution and coverage. |
| Knowledge lifecycle, objectives, applications, AI gateway, packages, destination sync | New capabilities or extensions to be designed; not present as a complete platform in audited baseline. Assess existing separate AI API infrastructure before duplication. |
| Operations | Preserve guarded release process, private config, backups and recovery; verify current runtime and compatibility separately. |

No forced rewrite, destructive migration, auth-provider replacement, production PG auth cutover, source-write privilege expansion or deletion of legacy functionality is required by this PRD. The current reporting login's historically observed CREATE privilege must be verified and remediated by an authorized DBA before affected real-data use. Display filters are not access control. Existing MCP client support does not prove new knowledge tools or external OAuth flows work. Runtime deployment state, mirror correctness and source semantics need fresh evidence.

## 4. Scope boundaries

### 4.1 Initial real-data pilot

| Dimension | Approved direction / boundary |
| --- | --- |
| Organization | One designated pilot organization; identity and authorization record private |
| Primary source | Existing call-center reporting integration; no assumption of other source access |
| Operator | Exactly one authorized call-center operator, selected privately; stable source-backed identity/assignment contract required |
| Historical window | Most recent 30 days of eligible calls at the agreed evaluation reference time; freeze bounds for comparable evaluation |
| Data | Existing privacy-filtered transcript as primary semantic evidence; permitted verified metadata; prior AI outputs supplementary only |
| Storage | Original unredacted transcript stays at source; only approved filtered representation, permitted metadata, source references and derivatives locally |
| Processing | Synthetic first; bounded staged samples within operator/window; incremental new/changed eligible calls separately governed |
| Applications | Customer Intelligence and Content Intelligence |
| Objectives | Seven initial templates in section 8 |
| Execution | Approved external AI APIs, centrally managed credentials, explicit model/task configuration, organization and run spending limits |
| Users | Technical/AI staff and content/SEO staff, authorized domain reviewers; assisted setup |
| Authorization | General approval reported by owner in discovery; specific rights/terms and execution approvals must be verified privately before real-data processing |

The initial 30-day window is not a retention period. A smaller eligible population is a limitation, not authorization to add operators or use older records. Proposed sample counts of 100, 1,000 and 10,000 are illustrative, cumulative or otherwise explicitly defined per evaluation plan, not commitments. An incremental flow does not automatically authorize processing beyond the agreed scope. Do not claim unique customer counts without independently verified identity; no market-wide inference from this sample.

### 4.2 Product MVP, beyond the first pilot run

The MVP includes minimal manual text/document ingestion and limited approved web pages (D-028), simple configurable objective templates and custom objectives, scheduled/manual processing, bounded discovery, typed context, review, packages, explicit minimal shared knowledge, independent web/API/MCP consumption, and a narrow one-way knowledge sync capability. These are platform deliverables; their real customer activation requires specific source/destination authorization. Demonstrate unapproved connectors or destination contracts with synthetic fixtures/test destinations, not live data. The initial call-only vertical slice precedes the other limited source capabilities; the MVP is not complete merely because the first extraction succeeds.

### 4.3 Not in MVP

Dedicated CRM, messaging, analytics/SEO or broad market/competitor connectors; autonomous crawling; audio ingestion or retranscription; local unredacted call archive; individual customer profiles or identity resolution; organization-wide processing or multi-operator analytics in the initial pilot; dedicated conversational UI; full analytics builder; first-party draft editor, CMS, editorial calendar, public publishing; advanced schema/taxonomy/visual workflow builders, knowledge graph or ontology engine, speculative vector infrastructure; unrestricted agents or SQL; automatic objective creation; self-hosted AI, intelligent routing, BYOK/custom endpoints, advanced hierarchical budget allocation or customer billing; fully self-service onboarding; bidirectional sync. Later delivery requires separate prioritization and approval; extensibility is not a promise to ship these features.

## 5. Users, workspace and permissions

Proposed logical role templates below are not final role IDs or database grants. A single person may hold multiple authorized roles; shared technical/domain review does not mean two reviewers for every item. Separation of duties and high-risk review rules must be defined before live use.

| Actor | Primary job | Minimum authorized actions |
| --- | --- | --- |
| Platform/deployment administrator | Assisted onboarding and safe operations | Provision workspace, approved integrations and managed providers, investigate health; no implicit access to every tenant's content |
| Organization administrator | Govern own workspace | Manage membership and permitted grants/configuration, organization limits and approved sharing within authority |
| Technical/AI specialist | Configure and evaluate pipeline | Configure objectives, allowed source/model/schedules; initiate bounded runs; inspect authorized failure/evaluation evidence; propose taxonomy and knowledge changes |
| Authorized domain reviewer | Assess claim validity and business context | Inspect permitted evidence, correct/reject/request review, approve within policy; not automatically granted original transcripts or identities |
| Content/SEO specialist | Use knowledge for content planning | Read authorized findings, opportunities and briefs; use permitted MCP knowledge for drafting; optional reviewer grant separate |
| API/MCP client | Consume delegated data | Only approved tools, representations, knowledge and packages within effective grants; no autonomous publication or source writes |
| Background service | Execute approved processing/sync | Narrow workspace/source/task and destination scope; recheck current authorization and policy |

**FR-01 Workspace and access:** Every tenant-owned configuration, resource, observation, knowledge revision, package, run, budget, audit event and app result MUST be associated with an isolated workspace. Identity, membership, role templates and explicit scoped grants must form a consistent effective access decision across web, API, MCP, exports and workers. Invalid or ambiguous grants fail closed. No default cross-tenant discovery, count, title, evidence, ID or error disclosure. Revoke access for subsequent operations and handle in-flight jobs according to approved policy. Grantors cannot exceed their authority. Private is default; explicit sharing only for permitted content and authorized consumers. Retain audit of configuration, grants and review decisions. D-010/011/016/023/033; G-001/002/018/020.

Acceptance: two synthetic tenants with overlapping source IDs cannot retrieve or infer each other's data through direct IDs, lists, counts, filters, exports, caches, workers or MCP. Revoked, malformed and legacy ambiguous permissions do not widen access; an authorized user can complete their scoped task. Shared knowledge is visible only to explicitly allowed recipients.

## 6. Source collection, Resources and privacy

**FR-02 Sources and integration.** Provide a managed source registry (connection reference, type, workspace, allowed fields/scope, status, storage/retention policy, sync state and provenance). Technical users can inspect and operate approved integrations without seeing secrets. Collect only allowlisted fields from approved sources; parameterized reads, bounded resource size/rate and timeouts; explicit identity and revision rules. Record run status, checkpoint, errors and source coverage without sensitive payloads. Call source first; manual text/document upload and selected approved web URLs follow as limited MVP adapters. Supported document types/limits, allowed URLs and refresh policies are open; do not silently crawl or retrieve arbitrary network targets. Treat all source text and files as untrusted data. D-005/009/028/035/046; G-003/010.

**FR-03 Logical Resources.** A Resource represents one logical source item and one or more permitted representations. At minimum expose type, source reference/ID, workspace, source and observed timestamps with provenance, revision/processing history, representation type, availability, typed attributes/context, and effective access/retention status. A missing audio, transcript or metadata representation is explicitly unavailable, not fabricated. A user can browse/search/filter authorized resources, inspect permitted representation and provenance, and understand stale/missing/failed state. Resources and Knowledge have independent retrieval surfaces. Typed extension schemas must validate values; distinguish unknown, absent, not applicable and contradictory. D-001/005/022/035/037; G-009/010/016.

**FR-04 Call privacy and non-destructive ingestion.** Source-owned records must never be mutated or deleted by Panadan: no INSERT, UPDATE, DELETE, TRUNCATE, DDL or write-capable functions. Use read-only credentials and transactions and verify effective least privilege. Read only needed authorized text/metadata transiently; apply versioned deterministic rules/regex and typed placeholders before durable call-text storage and downstream AI disclosure. Do not assume regex finds every name or indirect identifier. Treat filtered text/derivatives as sensitive; block or escalate data where required privacy guarantees are unmet. Persist approved filtered representation, source/revision reference and policy version, not the raw unredacted payload (including queues, caches, exceptions, traces, backups and failed-job payloads). No re-transcription/audio required. Existing raw-revision and transcript masking implementations require review before reuse. Preserve relevant permitted context such as destination or price conditions without inventing missing values. D-035/036/037/046; G-003/004.

**FR-05 Source lifecycle and retention.** Detect authorized new/changed revisions and supported deletion/revocation signals; retain version lineage as permitted, invalidate/review stale observations and knowledge, reconcile local representations and enforce retention/purge obligations. If source update/delete semantics are unknown, surface incompleteness and avoid false assurances. Local correction, redaction, purge or reprocessing must not affect customer-owned records. No unredacted original copy under pilot workflow. Retention applies to caches, evidence, derived records, backup restoration and authorized exports as policy requires. D-001/005/016/031/037/046; G-003/004/007.

Acceptance: a synthetic call with identifying patterns is read from a test source, redacted, stored and retrieved under correct scope; original hash/content is unchanged and source writes fail. Simulate source correction, duplicate/replayed events, missing transcript and revoked access. Test representative Persian and mixed-language patterns, logs, error paths and retry payloads for unintended leakage. Approved manual and web fixtures preserve provenance; prohibited URL/file inputs fail safely. No actual source query or live copy is authorized by this PRD.

## 7. Knowledge Objectives, Pipelines and execution

**FR-06 Objectives.** Supply reusable templates for section 8, organization-specific editable instances and simple structured custom objectives. Each defines purpose, authorized source types/scope, expected typed output and constraints, relevant context/dimensions, validation policy and ownership. Validate configuration before activation; version changes and make history inspectable. No automatic creation of objectives or unrestricted schema builder. D-008/022/029/034; G-011/018.

**FR-07 Pipelines and runs.** An associated pipeline binds an objective version (or explicitly compatible objectives), approved source selection, operator/window scope where applicable, extraction/preprocessing version, explicit provider/model, output/validation policy, schedule/manual trigger and budget. Support preview of effective scope/eligible count when measurable, on-demand and scheduled execution; bounded backfill and incremental processing of new/changed items. Record separate source sync and extraction coverage/checkpoints, run status, timestamps, counts and errors, pause/resume, retry and cancel controls as applicable. A run cannot silently expand scope; approved configuration versions are pinned for reproducibility and current authorization is rechecked. Suggested user-visible status concepts: queued, running, paused, budget-blocked, completed, partial/failed, canceled; exact state machine pending architecture. Avoid starving fresh incremental processing during history backfill. D-009/019/029/030/031/040/044/045; G-011/015/019.

**FR-08 Observation extraction and reuse.** Use approved filtered transcript as primary call input. Extract typed source-level observations with evidence anchors to specific source and representation revision, relevant conditions/time, objective/schema/model/config version, classification and uncertainty. Distinguish customer statements, agent statements and independently verified facts; ASR mistakes and prior AI conclusions are not truth. Reuse only compatible, current, authorized results for other objectives/applications; process missing, new, changed or incompatible coverage rather than every resource for every objective. Validate structured outputs, bound retries and quarantine unsupported/invalid results. No fabricated evidence or silent AI-only replacement for missing transcripts. D-019/020/030/035; G-011/012/013/015.

**FR-09 Aggregation and bounded discovery.** Compute exact counts, denominators, deduplication where deterministic, coverage and time bins with code/SQL. Use bounded AI for semantic matching, candidate grouping and discovery where appropriate; record scope and method. Count eligible distinct call records, not distinct people or mentions unless specifically labeled; multiple observations/categories may overlap. Separate eligible, processed, failed, pending/excluded, and unknown populations. Report both the measured denominator and coverage; do not impute missing values or claim representativeness. Discovery may suggest new topics or candidates, not silently create new pipelines/objectives or authoritative claims. D-008/025/030/031/032/041; G-011/013.

Acceptance: configure a template and a simple custom objective, execute a synthetic run with bounded scope, resume after interruption and retry a failed item without duplicating observations or counts. New and changed revisions trigger appropriate processing; compatible observation reuse is demonstrated across both applications. Aggregates match deterministic fixtures including overlap, missing data and exclusions. An out-of-scope record is never processed.

## 8. Initial Knowledge Objective catalog

The seven objective names are accepted. Proposed observation fields below are logical minimums for PRD review, not finalized physical schemas, enum vocabularies or required values in every call. Common fields: source/revision/evidence anchor, speaker attribution if reliable, observed time/context, extraction/schema version, scope, taxonomy category or unknown, uncertainty and policy. Values must be evidence-supported and nullable when unknown.

| ID / objective | Example observation output | Useful aggregate / product output | Guardrail |
| --- | --- | --- | --- |
| KO-01 Customer Questions | Question text/paraphrase; normalized topic; explicit question type; relevant context | Recurring questions, scoped counts and FAQ candidates | A question is not a verified answer or a search query volume |
| KO-02 Customer Needs & Preferences | Expressed need/preference, priority or constraint if explicit, related product/context | Repeated needs and combinations, expressed preference patterns | Distinguish explicit statements from inference; no individual profiles |
| KO-03 Customer Concerns | Concern/risk, subject, reason and contextual conditions | Recurring concerns and their supporting evidence | A concern does not establish that the feared problem occurred |
| KO-04 Purchase Barriers | Stated obstacle, stage/context if reliable, outcome only if verified | Common stated obstacles and possible improvement topics | Do not infer causality or paid sale from AI scores/source labels |
| KO-05 Destination Intelligence | Destination mentioned, intent/question/concern, travel context if available | Destination-specific questions and scoped interest signals | Mentions are not bookings, market demand or market share |
| KO-06 Price Sensitivity | Budget/range, currency, unit/price basis, explicit price reaction and offer context when known | Budget/price-related patterns among measured calls | Do not conflate quote, willingness to pay and actual payment; no current price without fresh evidence |
| KO-07 Content Opportunities | Candidate topic, audience/intent, rationale, supported knowledge references, proposed format | Prioritized reviewable opportunities and evidence-backed briefs | Derive from authorized validated knowledge; not SEO volume or an automatic publication instruction |

Travel-related conditions are typed extensions to the reusable core, not mandatory fields for other industries. For price-related evidence distinguish destination, travel dates, hotel/room, number/age of travelers, inclusions, flight, meals, transfer, currency, price basis, validity and inventory where relevant and available. Different conditions can explain different legitimate offers. Missing conditions are unknown, not contradictions. Live quotes/bookings remain Resources; supported contextual patterns/rules may become Knowledge.

The first six objectives can reuse one compatible source-level extraction result where demonstrated; the seventh uses relevant validated knowledge and authorized evidence. No assumption that seven separate AI calls per transcript are needed. Exact objective schema, categories, context requirements, validation criteria and review ownership are architecture/data-model inputs.

## 9. Knowledge Engine, validation, taxonomy and packages

**FR-10 Atomic contextual Knowledge.** A Knowledge Unit is an independently versioned claim or supported pattern, not a raw transcript, an observation, a model summary or a package. It contains subject/claim, type, scope, applicable conditions, temporal validity/freshness, source/evidence references, validation policy/outcome, ownership/access, version and history. Candidate and authoritative knowledge are distinguishable in storage and UI. Evidence can be inspected only under current access; if evidence is removed or becomes insufficient, re-evaluate authority and distribution. D-003/004/021/022/030/032; G-012/013.

**FR-11 Evidence and risk validation.** Validate each claim according to subject and intended use. Show separately (a) reliability/evidence sufficiency, independence, authority and conflict; (b) measured prevalence, population, denominator and processing coverage; (c) business importance and relevance. Apply freshness and contextual comparability rules; avoid a universal minimum count or composite trust score. Correlated summaries or multiple observations from a single call do not become independent corroboration. Rare high-value findings may remain candidates or narrowly validated claims where supported, without overstating prevalence. Deterministic rules handle exact checks; bounded AI assists semantic analysis; authorized specialists review high-risk, uncertain or sensitive claims. Show rule/version, pass/fail/needs-review reasons and evidence; do not auto-promote unresolved claims. Proposed lifecycle concepts: proposed, under review, active, disputed, outdated, rejected, archived; exact transition/approval matrix is a design item. Only appropriately validated, current and authorized claims are distributed as authoritative. Review actions retain identity, rationale and revision; corrections create controlled versions, not silent mutation. D-003/021/032/033; G-012/013.

**FR-12 Hybrid taxonomy.** Provide simple predefined editable categories/subcategories and organization-scoped authorized review of AI suggestions. Store proposed vs approved separately; allow unknown/unmatched observations, deduplicate suggested categories, version accepted labels/relationships and preserve metric comparability after changes. No autonomous taxonomy mutation, graph engine or forced categorization. Category approval does not establish truth or prevalence. D-008/022/041; G-011/012/013/018.

**FR-13 Knowledge Packages and sharing.** Authorized users assemble named, version-aware collections by referencing Knowledge Unit versions and applicable scope, not duplicating mutable claims. Show membership, version policy, validation/currentness, owner/access and permitted consumers. Private by default; minimal explicit sharing only for approved sources/content under explicit grant. Re-evaluate access and evidence on retrieval, and invalidate/restrict stale or revoked projections. Export must not leak excluded evidence, metadata or version history. D-004/011/013/016; G-014/016.

Acceptance: a candidate with insufficient evidence is not served as authoritative; a contextual conflict differs from an offer with different conditions. Test stale evidence, duplicate correlated claims, rare findings, sensitive review, version correction and revoked access. A reviewed taxonomy change preserves historical interpretation. A package can be retrieved by permitted consumers, cannot elevate member access, and exposes version/staleness correctly.

## 10. Shared AI Gateway and spending

**FR-14 Governed external AI execution.** All product model invocations use a common gateway boundary. Central configuration of approved external providers/models/credentials, explicit task/pipeline model selection, schema validation, bounded time/steps/retries/payload, secure secret handling, and safe handling of errors are required. Evaluate existing organizational AI API infrastructure and its security, usage accounting and structured-output compatibility before building another gateway. No named provider selected by this PRD. Model/provider/data-class/purpose authorization includes intermediaries and downstream processing terms; deny egress when policy, retention/training conditions or authorization are unknown. No automatic fallback to an unapproved provider/model. Treat source text and model output as untrusted; they cannot override policies, invoke arbitrary tools, disclose secrets, write source data or publish content. Managed credentials server-side only; no BYOK or self-hosted inference initially. D-019/020/035/038/039; G-005/015.

**FR-15 Budget and usage.** Record organization, run/task, pipeline/application attribution where relevant, provider/model, request status, tokens where reported, estimated/reported/unknown cost and timing, with no sensitive payload logging. Enforce finite organization and execution limits before admitting chargeable requests including retries; account for reservations, concurrency, in-flight cost and uncertain actuals. Missing cost is not zero; fail closed when safe admission cannot be established. Show usage/remaining budget, budget-blocked state and authorized pause/resume after a limit change. Completed work and independent reporting remain available. Reconcile provider actuals and surface discrepancies; an application admission limit is not a guarantee of the provider's final invoice. Budget units, periods, rate sources and initial approved amounts remain open. No billing/wallet, advanced hierarchy or separate pipeline quota in MVP. D-031/039/045; G-005/015/019.

Acceptance: synthetic/mock provider tests cover schema invalidity, timeout, unapproved model/data combination, injection-like source text, concurrent budget exhaustion, retries, missing price and reconciliation. Unauthorized requests never reach provider; budget-blocked jobs retain completed work. Usage is isolated and auditable. A real provider evaluation requires separate approval and finite cap even for a small synthetic chargeable test.

## 11. Applications and user workflows

**FR-16 Shared application execution.** Provide ready-made configurable Customer Intelligence and Content Intelligence applications on a shared execution/retrieval foundation. Each app uses explicitly authorized Resources/Knowledge, objectives, instructions, allowed tools/models, execution and output settings. Deterministic operations stay deterministic. Limit agent scope, time, cost and tools; consequential actions require separate approval. No unrestricted agent builder. D-002/015/018/019/023/024; G-018.

**FR-17 Customer Intelligence.** Web evidence-backed insight feed and limited analytical dashboard, plus authorized MCP conversational consumption. Feed card should display concise finding, subject/category, conditions, period, scope/denominator/coverage, prevalence, reliability/validation status, business relevance, freshness and permitted evidence/drill-down. Dashboard proposes scoped counts and trends by objective/topic/time and coverage, only when source semantics support them. Filters must be enforced server-side and consistent with feed and MCP; default to selected pilot scope, no operator comparison or customer profiles. Clearly distinguish unavailable, no findings, incomplete and stale data. No unrestricted NL-to-SQL or dedicated chat interface. D-024/025/026/032/034/040/044; G-016/018/019.

**FR-18 Content Intelligence.** Present evidence-backed content opportunity list and brief detail with linked knowledge, intended audience, objective, rationale, suggested topic/format/outline, scope/time, evidence and limitations. Use relevant validated knowledge from the shared core; do not invent SEO search volume, keyword ranking or demand. A brief is a strategy artifact, not proof of a claim. Provide authorized MCP retrieval suitable for client-assisted drafting, subject to independent disclosure policy and compatible client verification. Drafts are not authoritative knowledge; require human review and current factual verification before public use. No in-panel draft generation, dedicated editor, content project management, scheduling or publication integration. Governed AI can create briefs/opportunities. D-024/027/033/034/042; G-016/018/019/020.

### 11.1 End-to-end user journeys

1. **Assisted setup:** deployment administrator creates an isolated workspace and approved memberships; technical specialist configures source and policy, verifies operator/time boundary, selects objective template/pipeline, approved model and cap; preview scope and confirm execution approval.
2. **Technical pilot:** run synthetic checks, admit a bounded approved sample, inspect ingestion/extraction progress, redaction status, coverage and errors. Pause at limits, fix configuration by versioning, resume or replay safely. Observe cost and evaluation evidence.
3. **Knowledge review:** inspect a candidate and permitted evidence, assess source authority, context, freshness, reliability/prevalence/importance and conflict, request correction or approve/reject under risk policy. View version/audit history. Review category suggestions separately.
4. **Customer Intelligence:** authorized user selects scope/objective, reads findings and scoped measures, opens evidence if granted, understands gaps and retrieves consistent knowledge through MCP.
5. **Content Intelligence:** authorized content specialist discovers a supported opportunity, opens a brief and outline, reviews permitted evidence, uses a compatible authorized MCP client to draft content, verifies facts and reviews before any external publication outside Panadan.
6. **Distribution:** authorized user assembles a package; API/MCP client consumes an authorized projection; approved one-way destination receives only selected current validated knowledge. Monitor version, failure and revocation state.

Illustrative synthetic case: calls mention concern about unexpected travel costs. Observations link exact permitted evidence and conditions. Count distinct eligible/processed calls mentioning the concern; after validation, display a scoped insight, then propose an explanatory guide brief. Do not assert actual market costs or demand. This scenario is a test fixture, not customer evidence.

## 12. Web information architecture and experience

Proposed screen grouping, not a final visual design. Reuse existing web shell where compatible, preserve current reporting, Persian RTL conventions and responsive access. Product terminology below is English for the specification; exact Persian labels and visual design will be reviewed. No need for separate page per row if an equivalent coherent workflow is delivered.

| Area / proposed screen | Core content and actions | Primary user |
| --- | --- | --- |
| Workspace overview | Selected workspace, pilot scope, source/coverage health, pending review and budget status; links to work | Technical / organization admin |
| Resources | Authorized list/search/filter; type, source, revision, freshness, availability; permitted detail and lineage | Technical / authorized consumers |
| Integrations | Source registry, allowed scope, sync status, manual import/approved URLs, errors; masked configuration | Deployment / technical |
| Knowledge Objectives | Seven templates, instances, simple custom configuration, version/status | Technical |
| Pipelines & Runs | Objective binding, scope/model/schedule/budget, preview, run, pause/resume, history and errors | Technical |
| Knowledge Base | Candidate/validated distinction, context, evidence, version and lifecycle | Technical / domain / content as permitted |
| Review queue & Taxonomy | Assigned/authorized candidates, validation reasons, category proposals, review actions/history | Technical / domain |
| Packages & Distribution | Versioned membership, private/shared policy, API/MCP access and authorized sync status | Authorized managers |
| Customer Intelligence | Insight feed, limited analytical dashboard, coverage/context, permitted evidence drilldown | Technical / content |
| Content Intelligence | Opportunity discovery and brief/outline detail, evidence and instructions for authorized MCP usage | Content / SEO |
| AI configuration & Usage | Centrally managed provider/model metadata, allowed scopes, budget/usage, run attribution (secrets never rendered) | Authorized administrators / technical |
| Users & Access / Connections | Membership/grants, tool/client scope, revocation and audit; preserve existing auth behavior | Authorized admin / user |
| Existing reporting and system health | Existing calls/operators/reporting/token interfaces, deployment status and audit as appropriate | Existing users / admin |

All screens require meaningful loading, empty, error, partial, permission-denied and stale-data states as applicable. Show source/period/coverage and confidence limitations near affected findings. Do not expose disallowed resource existence or sensitive details in error text, counts, search autocomplete or UI. Destructive local actions need clear scope and confirmation; there is no source delete action. Use keyboard accessible controls, meaningful labels, readable mobile layouts and non-color-only status indicators. UX acceptance includes users completing assigned journeys without direct database access or developer intervention beyond assisted configuration.

## 13. API, MCP and one-way destination distribution

**FR-19 Independent retrieval and delegation.** Web/API/MCP offer logically separate authorized Resource and Knowledge retrieval, with scoped list/filter, detail and evidence as allowed, package retrieval and bounded analytical queries. Define stable versioned contracts, pagination/limits and machine-readable context, validation state, freshness and coverage. Apply workspace/source/row/field/evidence/package permissions before access and projection, not merely UI filtering. Maintain existing reporting contracts and token/consent boundaries; new tools require explicit review and compatible client verification. Proposed capability inventory: list authorized resources; inspect a permitted resource representation; list/search validated knowledge; get knowledge detail with permitted evidence; retrieve package; query scoped customer insight measures; retrieve approved content opportunities/briefs. These are product capabilities, not committed endpoint/tool names. Candidates may be exposed only through separately authorized review interfaces, not as authoritative knowledge. No general SQL, unrestricted raw transcript export or implicit permission escalation. External MCP access is independent disclosure and requires client/data authorization. D-011/013/016/026/042; G-002/016/020.

**FR-20 Destination synchronization.** Panadan manages its knowledge lifecycle and version authority. Support a minimal separate one-way connector/contract to a designated approved destination that receives selected authorized validated projections. Do not use source credentials or change existing customer-owned fields/records. Write only explicitly designated Panadan-managed destination records/fields with narrow privileges, version/idempotency identity, bounded retries and visible delivery state. Distinguish pending, delivered, failed, stale and revoked/outdated projection; reconcile without modifying unrelated records. Define deletion/revocation and stale-version protection before live use; no implied deletion propagation or ability to revoke copies outside enforceable destination contract. Test with an isolated synthetic destination before any actual connection; target, projection, grants and retention remain unapproved. D-007/013/016/046; G-006/017.

Acceptance: authorized test API/MCP clients retrieve the same scoped validated findings as web; unauthorized/cross-tenant/revoked grants fail and no forbidden fields appear. Verify actual approved MCP client connection, consent, discovery, invocation, error and revocation flow before claiming compatibility. Demonstrate idempotent outbound write, replay, outdated version, failure/retry and revocation behavior against synthetic destination, with no source or unrelated target mutations.

## 14. Non-functional requirements and release safety

| ID | Mandatory property | Verification expectation |
| --- | --- | --- |
| NFR-01 | Tenant isolation, least privilege, fail-closed auth and independent source/processing/disclosure grants | Negative tests across every interface and worker; two synthetic workspaces; policy/revocation tests |
| NFR-02 | Non-destructive source and narrow separate destination writes | Effective privilege audit before live use; transaction/SQL guards and regression tests; synthetic destination isolation |
| NFR-03 | Privacy and retention | Minimize fields, no durable unredacted call data in this workflow; restrict filtered data; secure transit/storage and secrets, no sensitive logs; verify purge/backup restore behavior under approved policy |
| NFR-04 | Evidence integrity and correctness | Versioned lineage and rules; reproducible counts; explicit uncertainty, conflicts and freshness; review before authoritative use |
| NFR-05 | Reliable, bounded processing | Idempotency, checkpoints, bounded work, failure isolation, observable retries/poison items, pause/resume; concurrency and budget tests; no duplicate inflation |
| NFR-06 | AI and external content safety | Allowlisted provider/data/tool scopes; prompt injection treated as untrusted input; structured validation; file/URL limits, network/SSRF defenses; no unsafe fallback |
| NFR-07 | Operability and audit | Metadata-only run/usage/security audit, actionable state/error visibility, alert-worthy failure signals and retention; sensitive audit actions must be enforceable, not silently lost |
| NFR-08 | Performance and scalability | Measure latency, queue age, throughput, resource use and cost at each stage; bounded pagination/batches; configurable second workspace without fork. No unmeasured performance promise |
| NFR-09 | Compatibility and accessibility | Preserve reporting/auth/API/MCP behavior; test approved external clients; responsive RTL, keyboard navigation and meaningful states |
| NFR-10 | Deployment and recovery | Locked dependencies, CI, additive migrations, tested rollback/restore on isolated data, approved runtime readiness and backups; no unapproved production migration/deploy |

The P0 gates G-001–G-007 block affected real-data/live capabilities until verified. Security and privacy failures cannot be offset by business value. Performance/SLO values, operational retention and exact recovery targets remain design/approval items.

## 15. Pilot evaluation, acceptance and progression

D-040/D-043/D-044 govern staged evaluation. Establish a private evaluation manifest before each stage: actual operator ID and verified scope, frozen date window/timezone and eligible population, sampling method/seed or selection rule, test vs tuning split, objectives/versions, provider/model/data permissions, approved cap, reviewer/reference-label method, metric denominators and acceptance criteria. Use diverse permitted call lengths/topics/quality within the same population; avoid treating selected sample as random or representative unless demonstrated. Keep a held-out human-labeled sample where feasible and document label disagreement and adjudication. No real records in public repo or CI.

| Stage | Purpose | Exit condition |
| --- | --- | --- |
| E0 Synthetic | Verify read-only boundary, scope, redaction, schemas, provenance, negative security, budget, replay and end-to-end paths | Required tests pass; provider calls only if separately authorized; no real-data action |
| E1 Small technical sample (illustratively up to 100) | Validate source contract and extraction behavior; measure actual cost and failures | Explicit real-data/provider/budget approval; report eligible count and evaluate approved gates before expanding |
| E2 Quality sample (illustratively up to 1,000) | Evaluate semantic accuracy, recall, evidence support, reviewer consistency and coverage | Pass reviewed quality and safety gates; sample remains within same approved window/operator |
| E3 Business evaluation (illustratively up to 10,000 if eligible) | Assess usefulness of aggregate insights, briefs and shared access; measure baseline vs pilot tasks | Technical, quality and business outcomes reviewed; no automatic approval of further data scope |
| E4 Ongoing bounded operation | Approved incremental work and separately approved backfill | Readiness, operational and cost gates verified; new operators or older history require separate approval |

Use smaller samples if insufficient eligible records. Numbers above are adjustable proposals, not committed sizes or authorization. An E3 business success decision is distinct from production release readiness.

### 15.1 Metrics and provisional quantitative targets

| Dimension | Measure / proposed definition | Initial discussion target |
| --- | --- | --- |
| Technical | Schema-valid outputs / attempted outputs, report first-pass and after bounded retries | 99% provisional |
| Technical | Successfully processed eligible items / attempted eligible items; separate exclusions, failures and pending | 98% provisional |
| Technical | Validated knowledge with inspectable permitted evidence / validated knowledge | 100%; evidence is mandatory for authority |
| Technical | Duplicate observations/counts after replay; cost/request and cost/call; p50/p95 latency, throughput, coverage | Measure and review; no fixed cost/SLO yet |
| Quality | Correct extracted observations / evaluated extracted observations against human reference | 90% precision provisional |
| Quality | Correctly recovered reference observations / relevant human-labeled observations | 80% recall provisional |
| Quality | Semantically supported evaluated claims / evaluated claims; separate from merely linking evidence | 95% grounding provisional; unsupported claims cannot become authoritative |
| Safety | Confirmed unauthorized access/disclosure, source mutation, critical validated-knowledge errors; adversarial and negative tests | Zero observed; investigate and resolve any violation before progression |
| Business | Authorized specialists rate usefulness/actionability of insights and briefs against agreed task rubric; actual research time vs baseline and qualitative feedback | Baseline and thresholds to be agreed before evaluation |
| Reuse | Same permitted knowledge used by both apps and an approved client; second synthetic workspace configured without core fork | Demonstrate with traceable scenario |

Define precision/recall matching rules per objective, evidence review sample, scope and denominators before measurement. Separate extraction quality from claim-validation quality; report sample sizes, uncertainty, observed errors and incomplete coverage. The numerical discussion targets are not approved release thresholds; calibrate after initial evaluation and obtain approval before larger runs. Zero observed incidents is a safety expectation, not proof of zero risk.

### 15.2 End-to-end acceptance matrix

| Test | Must demonstrate | Requirements / gaps |
| --- | --- | --- |
| AT-01 | Workspace membership, cross-tenant denial, scoped grants, invalid/revoked credentials, no evidence leakage | FR-01/19, NFR-01; G-001/002/020 |
| AT-02 | Read-only source, verified scope, redaction before durable storage, unchanged originals, retention/reconciliation | FR-02–05, NFR-02/03; G-003/004 |
| AT-03 | Resource provenance, typed extensions, permitted manual/web fixtures and denied unsafe inputs | FR-02/03, NFR-06; G-009/010 |
| AT-04 | Template/custom objective, scheduled/manual run, 30-day/operator boundary, budget and pause/resume, separate ingestion vs processing coverage | FR-06/07/15; G-011/015 |
| AT-05 | Version-aware extraction reuse, exact aggregates, duplicate and changed revision tests, missing/unknown cases | FR-08/09, NFR-04/05; G-011/012/013 |
| AT-06 | Candidate vs authoritative knowledge, context/conflict, evidence authority, risk review and version lifecycle | FR-10/11; G-012/013 |
| AT-07 | Governed taxonomy suggestions and changes, package references and minimal private/explicit shared scope | FR-12/13; G-014/018 |
| AT-08 | Approved gateway admission, invalid output, retries, unapproved disclosure and concurrent budget limits | FR-14/15, NFR-06; G-005/015 |
| AT-09 | Customer insight feed/dashboard and evidence-backed Content Intelligence brief from shared knowledge, appropriate limited population | FR-16–18; G-018/019 |
| AT-10 | Authorized independent Resource/Knowledge retrieval and real approved MCP client flow; existing reporting/auth compatibility | FR-19, NFR-09; G-016/020 |
| AT-11 | Isolated one-way sync to synthetic/approved destination with scoped version/replay/revocation behavior and no unrelated writes | FR-20; G-006/017 |
| AT-12 | Staged evaluation report, security/quality/business gates, cost, second-workspace reuse, backup/restore and rollback evidence | NFR-07/08/10; G-007/008/019 |

All tests are specifications, not executed results. Technical evidence should identify build/commit, test environment, synthetic/authorized data status, actual outcomes and limitations.

## 16. Open items and decision/activation gates

The PRD may be reviewed with these unresolved items explicitly tracked. Do not invent private deployment details. Product approval, design approval, real-data evaluation authorization and production release authorization are separate.

| ID | Open item / required evidence | Proposed accountable role | Blocks |
| --- | --- | --- | --- |
| O-01 | Select exact operator privately, verify stable ID/assignment, eligible population, source call ID uniqueness and timestamp meaning/timezone | Source owner + technical | Real historical/incremental selection |
| O-02 | Verify read-only DB grants, field allowlist, transcript availability/quality, update/delete/joined change and checkpoint semantics, source load and mirror parity | DBA + technical | Live collection |
| O-03 | Document actual data rights, permitted processing/storage, retention, deletion, access/review and backup policy; general approval alone insufficient for specific egress | Data owner + security | Real-data handling |
| O-04 | Approve provider/model/intermediaries, disclosure categories, purpose, retention/training and security terms; assess existing AI API reuse and structured output | Data owner + technical/security | External AI or MCP real-data disclosure |
| O-05 | Set initial finite budget/currency/period/rates, estimation and concurrency policy; determine chargeable sample cap | Budget owner + technical | Chargeable requests |
| O-06 | Refine seven objective templates, category seeds, typed attributes and metric rules; source-to-field mapping and context | Technical + domain reviewer | Architecture/data model; real evaluation |
| O-07 | Agree validation/risk policies, state transitions, review assignments/quorum, evidence access and freshness rules | Domain + technical/security | Authoritative distribution |
| O-08 | Agree exact sampling, reference labels, thresholds and business baseline/task rubric; stage exit review owners | Technical + content/domain | Stage execution/expansion |
| O-09 | Approve manual formats/size limits, web allowlist/rights/refresh, any actual source additions | Data owner + technical | Those connector activations |
| O-10 | Approve external client identities/consent/tool scope and test OAuth/runtime compatibility | Security + technical | Real MCP access |
| O-11 | Approve destination interface, dedicated role, projection and version/revocation contract | Destination owner + security | Real outbound sync |
| O-12 | Verify production revision/config, backup/restore, auth strategy, migration/rollback, readiness and operational limits | Deployment/DBA + security | Production changes/release |

Exact roles are proposed responsibilities, not actual assignments. Track private evidence in an authorized private record; keep public docs generic. Resolve affected blockers before the relevant action. Approval of this PRD does not close them or permit running a live query, copying data, spending funds, sending provider requests, merging or deploying.

## 17. Decision traceability and gap disposition

All 44 public accepted entries are mapped below. D-012 and D-014 are intentionally absent; no meanings are inferred. The historical audit and gap analysis remain unchanged snapshots.

| Accepted decision(s) | PRD coverage |
| --- | --- |
| D-001, D-005, D-022 | FR-02–05, FR-10; logical resources, hybrid storage, typed context |
| D-002, D-015, D-018, D-023 | Sections 2–5, FR-01/16; reusable core and configured applications |
| D-003, D-004, D-021 | FR-10–13; atomic contextual knowledge, evidence/risk validation |
| D-006, D-017 | Section 4 and AT-12; designated pilot vertical slice |
| D-007 | FR-20, NFR-02, AT-11; one-way authorized destination |
| D-008, D-009 | FR-06–09/12; goal-driven bounded discovery and scheduled/manual runs |
| D-010, D-016 | Section 5, FR-01/19, NFR-01; assisted setup, scoped grants |
| D-011, D-013 | FR-13/19; private default, minimal explicit sharing, version-aware packages |
| D-019, D-020 | FR-07/08/14/16; deterministic where possible, governed AI gateway |
| D-024, D-025, D-026 | FR-16/17, sections 4/8; aggregate-first Customer Intelligence |
| D-027, D-042 | FR-18/19; Content Intelligence briefs and MCP drafting |
| D-028 | FR-02/03, section 4; progressive source integration |
| D-029, D-030, D-031 | FR-06–09; objectives, observations, incremental/backfill |
| D-032, D-033 | FR-10/11, section 5/15; multidimensional validation, shared review |
| D-034 | Section 8; seven initial objectives |
| D-035, D-036, D-037 | FR-03–05/08; transcript-first, deterministic redaction, selective storage |
| D-038, D-039, D-045 | FR-14/15; managed external APIs and hard admission budgets |
| D-040, D-043, D-044 | Sections 4/15/16; single operator, 30 days, staged balanced evaluation |
| D-041 | FR-12; governed hybrid taxonomy |
| D-046 | FR-04/05/20, NFR-02; immutable-to-Panadan customer originals |

Gap mapping: P0 G-001–G-007 are release/activation gates in sections 5–6, 10, 13–16. P1 G-008 is scoped by approved discovery and remaining open items; G-009/010 covered by FR-02–05; G-011 by FR-06–09; G-012/013 by FR-10–12; G-014 by FR-13; G-015 by FR-14/15; G-016 by FR-19; G-017 by FR-20; G-018 by FR-01/16–18 and screen/workflow requirements; G-019 by section 15 and NFRs; G-020 by FR-19/NFR-09. G-021–G-026 remain conditional/deferred improvements per gap analysis, without waiving baseline auth, reliability, security or operational prerequisites. No gap is declared implemented or closed by this document.

## 18. Handoff and phase exit

Phase 4 output is this review draft. Review scope, requirements, user journeys, proposed screen inventory, objective outputs, non-goals, acceptance and unresolved items against the decision register. Record any owner-approved substantive change using the mandatory decision maintenance protocol. Upon explicit Phase 4 approval, prepare Phase 5 `ARCHITECTURE.md` (system boundaries, component responsibilities, data/control flows, authorization and privacy boundaries, integration contracts, failure/recovery and migration strategy, Mermaid diagrams); then Phase 6 `DATA_MODEL.md` and Phase 7 `ROADMAP.md`, each separately reviewed. Phase 8 implementation proceeds only by approved increments with tests and commits. Detailed schema, endpoint signatures, task/job state machines, technology choices and delivery dates are not settled by this PRD.

Work only on the authorized feature branch. Preserve main and backup; do not merge, deploy, change production DB, access live data or incur AI costs without separate authorization. The PRD is a product specification, not implementation evidence.

