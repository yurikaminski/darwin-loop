# DarwinLoop / FeedbackLoop — Product Requirements Document

| | |
| :--- | :--- |
| **Version** | 3.0.0-alpha |
| **Status** | Draft — In Review |
| **Date** | 2026-06-16 |
| **Author** | Yuri Kaminski |
| **Track** | RL / Autonomous AI Systems |
| **Supersedes** | PRD v2.0.0-alpha (May 2026) |

> **What's new in v3.0 vs v2.0.** v2.0 specified *the library*. v3.0 keeps that spec intact and adds the layer v2.0 deliberately omitted: the **open-core business model** — what is free/open (Core), what is partially open (Misto), and what is commercial (EE), plus the licensing and telemetry decisions that make the three-way model (OSS library + research + SaaS) coherent. New material is marked throughout.

---

## 0. The Three-Way Model (new in v3.0)

DarwinLoop is simultaneously three products sharing one codebase — the **open-core** model (à la Langfuse / PostHog / Sentry):

1. **Open-source library** — `darwin-feedbackloop`, local-first, BYOK. The whole reflective loop runs on the developer's machine. This is the entire v2.0 PRD.
2. **Research project** — optional, anonymized telemetry from all users feeds a central database that studies feedback-driven prompt evolution and trains the next-generation optimizer (GEPA).
3. **SaaS / Enterprise (EE)** — hosted, multi-tenant, team- and scale-oriented features sold commercially.

The strategic insight that shapes everything below:

> **The library is the Core. The central/hosted side is the EE.**
> Quase tudo que roda numa máquina, para um agente, operado pela própria pessoa → **Core (free, MIT)**.
> O que precisa de servidor, de muitos agentes, de um time, ou é o estado-da-arte da inteligência → **EE (paid)**.

The free Core maximizes adoption, which maximizes the research telemetry flywheel, which trains the paid optimizer. The tiers reinforce each other.

---

## 1. Executive Summary

`darwin/FeedbackLoop` is an open-source Python library that introduces a lightweight, zero-latency feedback loop for AI agents — without infrastructure changes, hosted services, or raw conversation storage. It intercepts agent I/O at the adapter layer, detects negative and positive feedback signals from user messages, and computes three core metrics: **NFR** (Negative Feedback Rate), **PFR** (Positive Feedback Rate), and **AINPS** (Agentic Intrinsic NPS) — plus **W-NFR** (Weighted NFR) — tracked per episode and across rolling windows (hourly, daily, 7-day, monthly, and per-token-consumption milestones).

When metrics cross configurable thresholds, the Darwin agent autonomously generates targeted prompt mutations in one of three modes: **Injection** (prepend to user context, no system-prompt change), **Soft Edit** (modifies the system prompt for new sessions), or **Hard Edit** (opens a GitHub PR for human approval). Statistical significance validation determines whether a mutation genuinely improves quality before promotion.

The result: a closed-loop, self-evolving agent infrastructure with full auditability, privacy-by-design, four developer experience levels, and optional anonymized data contribution to a central Darwin research database.

| Dimension | Description |
| :--- | :--- |
| **Core problem** | Agent prompts degrade silently; no systematic signal to know when or why. |
| **Core solution** | Intercept positive/negative signals, compute NFR/PFR/AINPS, auto-mutate via Darwin agent (3 levels). Statistical validation before promotion. |
| **Core metrics** | NFR, PFR, AINPS, W-NFR — rolling hourly/daily/7d/monthly and per-token. |
| **Mutation levels** | Injection / Soft Edit / Hard Edit. |
| **Target users** | Vibe Coder, Solo Builder, AI Product Manager, AI Platform Team, Research Engineer — across 4 levels: Basic, Intermediate, Pro, God. |
| **Deployment** | `pip install darwin-feedbackloop` — zero infra, works offline. Conversational setup wizard. |
| **Key constraint** | Zero latency impact on agent response time. All heavy ops async. |
| **Privacy model** | Hashes only — no raw message content stored or transmitted. Opt-out anonymized data sharing (default on, see §13). |
| **License model** | Core = MIT. Commercial features live in `ee/` under a separate Enterprise license (see §12). |

---

## 2. Problem Statement

### 2.1 The Silent Degradation Problem
Production AI agents run on static system prompts authored at deployment time. As usage evolves — new intents, edge cases, domain drift — those prompts silently accumulate failure modes. Developers have no systematic way to observe this outside expensive manual review. The symptoms are detectable: users re-phrase questions, issue corrections ("no, that's not what I meant"), or abandon sessions. These behavioral signals are rich diagnostic data — yet they vanish, unobserved, on every turn.

### 2.2 Why Existing Approaches Fall Short
| Approach | Limitation | darwin addresses |
| :--- | :--- | :--- |
| Manual prompt review | Reactive, infrequent, no aggregation | Continuous, metric-driven |
| RLHF / LLM training | GPU, massive dataset, months | Lightweight, prompt-only, <24h iteration |
| User ratings (thumbs) | UI change, completion bias, low volume | Implicit signals, no UI change |
| Hosted eval platforms | SaaS cost, data leaves infra | Local-first, BYOK, no hosted dependency |

### 2.3 Core Hypothesis
Implicit behavioral signals in user messages (re-prompts, corrections, frustration markers) are a sufficient proxy for prompt failure. Aggregating them into normalized metrics and feeding them to a targeted LLM mutation pipeline produces meaningful prompt improvements with minimal human oversight. This is an empirical hypothesis to be validated through measurement — the library is the instrumentation layer that enables that validation, and the research database (§13) is what makes validation possible at population scale.

---

## 3. Goals & Non-Goals

### 3.1 Goals — v3.0
All v2.0 library goals carry forward (intercept I/O across Anthropic/OpenAI/LangChain/CrewAI; detect positive+negative signals; three detection modes; Local Evaluator; NFR/PFR/AINPS/W-NFR across rolling windows; three mutation levels with canary; statistical validation; versioned Prompt Registry; webhooks; GitHub PRs; SQLite/pluggable storage; anonymized central-DB contribution; conversational setup wizard; four DX levels; fully offline). 

**New in v3.0:**
- Establish the **Core / Misto / EE boundary** (§11) as the canonical reference for every module, present and future.
- Resolve **licensing** (§12): Core is true MIT; commercial code is isolated in `ee/`.
- Resolve **telemetry consent** (§13): opt-out, default-on, anonymous, with the Privacy Scrubber guaranteeing the anonymity claim.
- Define the **two revenue levers** (§11.3): quality (GEPA, premium intelligence) and scale/central (fleet, hosted, multi-tenant).

### 3.2 Non-Goals — v3.0
- No training/fine-tuning of base LLMs — darwin evolves prompt text only.
- The OSS library ships **no hosted dependency**. Hosted dashboard, multi-tenant, and central research platform are **EE**, delivered separately (see §11).
- No GitLab/Bitbucket in the first library release — GitHub only (GitLab is roadmap).

---

## 4. Target Users

Five personas across technical depth and organizational role; each maps to one of four implementation levels (progressive config surface).

| Persona | Profile | Primary need |
| :--- | :--- | :--- |
| **Vibe Coder** | Builds agents with AI coding tools (Cursor, Claude Code, Copilot). Relies on the Init wizard. | Zero-config onboarding. |
| **Solo Builder** | Indie/early startup. LangChain or direct API. Some ML intuition. | Automatic improvement without manual review. Soft Edit + basic canary. |
| **AI Product Manager** | Business owner of an AI product. Can't code; evaluates quality, approves changes. | Readable NFR/PFR/AINPS trends; approve/reject Hard Edit PRs; rollback controls. |
| **AI Platform Team** | Engineering team managing 5–20 agents. GitHub-centric. | Signal aggregation, PR-based approval, version lineage, per-agent thresholds. **→ primary EE/fleet buyer.** |
| **Research Engineer** | Explores agent evaluation / RL-adjacent loops. | Clean episode data, metric series, audit trail, raw SQL, central DB contribution. |

### 4.1 Implementation Levels
| Level | Persona | Unlocked |
| :--- | :--- | :--- |
| **Basic** | Vibe Coder | Wizard handles setup. Adapter wraps client. Defaults to Soft Edit. Metrics via webhook summary. |
| **Intermediate** | Solo Builder / AI PM | Choose mutation level. Configure rollout_fraction + detection mode. SQL views. Approve PRs. |
| **Pro** | AI Platform Team | Full FeedbackConfig. Custom patterns. Per-agent statistical test. Custom rollback thresholds. Central DB settings. Secondary canary DB. |
| **God** | Research Engineer | Raw episode DB access. Custom backends. Custom mutation templates. Custom scoring models. Direct Darwin agent config. Full export. |

> Note: the four levels are a **config surface in the Core** (all free). "God-tier *managed*" — served scoring models, central-DB control plane — is EE (§11).

---

## 5. Functional Requirements (library — Core unless noted)

### 5.1 Adapter Layer
- **FR-A1..A4:** Drop-in adapters for Anthropic, OpenAI, LangChain (covers LangGraph), CrewAI.
- **FR-A5:** Each adapter normalizes `{system_prompt_hash, user_message, assistant_response, tokens_used, agent_id, session_id, timestamp}`.
- **FR-A6:** No raw conversation content stored at any point in the adapter layer.
- **FR-A7:** Adapters must not modify the response returned to developer code.

### 5.2 Signal Detection
- **FR-S1:** Detect negative and positive signals with independent weight vectors.
- **FR-S2 / FR-S3:** Standard negative (re_prompt, correction, explicit_negative, frustration, abandonment) and positive (explicit_positive, task_completion, affirmation, re_use) taxonomies with default weights.
- **FR-S4:** Three detection modes via `detection_mode`: `regex` (sync, <10ms, default), `ml` (async bundled classifier, `darwin[ml]`), `prompt` (async BYOK LLM).
- **FR-S5:** Signal weights configurable: built-in defaults / manual per type / auto-calibrate via Darwin prompt. Stored per-agent, versioned.
- **FR-S6:** Each signal stored with episode_id, signal_type, feedback_type, weight, agent_goal, episode_context (anon summary), detected_at, detection_mode.
- **FR-S7:** Developer may add custom debug fields; each explicitly flagged for central-DB inclusion (default: NO).
- **FR-S8 (revised in v3.0):** The six standard fields (episode_id, signal_type, feedback_type, weight, detected_at, detection_mode) are the baseline contribution payload. **Nothing is mandatory** — contribution is opt-out (default on), never license-compelled (see §13). *(v2.0 said "mandatory under the utilization license"; v3.0 removes that to keep the Core true MIT.)*
- **FR-S9:** Abandonment detection via configurable session-timeout hook.

### 5.3 FER Engine (Feedback Episodes Rate)
- **FR-F1..F4:** Per-episode `NFR = Σ neg.weight / tokens`, `PFR = Σ pos.weight / tokens`, `AINPS = (Σ pos − Σ neg) / tokens`, `W-NFR = Σ(neg.weight × severity) / tokens`.
- **FR-F5:** All four metrics across five window types: hourly, daily, 7d, monthly, per-token milestone.
- **FR-F6:** Per-prompt-version metrics (baseline vs canary vs control).
- **FR-F7:** Store tokens_to_first_negative / tokens_to_first_positive per episode.
- **FR-F8:** Trigger mutation when a configurable trigger metric (NFR / W-NFR / AINPS) crosses threshold for N consecutive episodes.
- **FR-F9:** Expose all metrics via read-only Python API + pre-built SQL views.

### 5.4 Mutation Engine
- **FR-M1:** All mutation work runs in the **Darwin agent** (background, separate from the production agent). Main thread never blocked.
- **FR-M2:** Darwin agent uses BYOK LLM; falls back to rule-based templates if no key.
- **FR-M3..M5:** Generate via `DARWIN_MUTATION_PROMPT`; extract `{mutation_level, proposed_change, confidence, reasoning}`; store full lineage + trigger context.
- **FR-M6..M7:** Three levels. Injection/Soft Edit auto-apply when `confidence ≥ auto_apply_threshold`; Hard Edit always requires PR merge.
- **FR-M8..M9:** Rollback when post-mutation metric degrades **AND** a statistical test confirms significance; both must fire.
- **Short loop (FR-M10..M14):** Session Injection Manager fires on significant negative signals or explicit user requests; injection chain evolves within the session; persisted to `session_injection_log` at session end (Darwin-generated text, safe to store).
- **Long loop (FR-M15..M18):** Injection Pattern Analyzer reads accumulated injection logs, extracts recurring themes, and enriches the mutation prompt with empirical evidence before a Soft/Hard Edit proposal.

> **v3.0 boundary note — the key split.** The mutation *machinery* (injection/soft/hard apply, short loop, auto-apply, rollback) is **Core**. The mutation *intelligence* is split: the **basic single-shot mutator** (one LLM call via `DARWIN_MUTATION_PROMPT`) is **Core**; **GEPA** — genetic/Pareto, multi-candidate, reflective evolution — is **EE**. The Pattern Analyzer is **Misto** (basic clustering Core; GEPA-grade semantic analysis EE). See §11.

### 5.5 Notifier
- **FR-N1..N3:** Emit Feedback Event webhook on every detected signal (primary real-time signal for PMs); configurable which signal types emit.
- **FR-N4..N5:** Emit Mutation Event webhook on lifecycle transitions (triggered, injection_applied, soft_edit_applied, pr_opened, pr_merged, promoted, rolled_back).
- **FR-N6:** Multiple endpoints per event type.
- **FR-N7:** Fire-and-forget; failed deliveries logged at WARNING. **Retry queue is EE** *(v2.0: "v3")*.
- **FR-N8:** Payload schemas stable across minor versions.

### 5.6 GitHub Integration
- **FR-G1..G6:** Open PR on approval; structured title + body (signal distribution, FER comparison, rollback instructions, diff); merge triggers auto-apply + version bump; token scoped to `repo:contents write + pull_requests write`.

### 5.7 Storage
- **FR-D1:** Default SQLite at `~/.feedbackloop/{agent_id}.db`.
- **FR-D2:** Pluggable PostgresBackend, SupabaseBackend (self-managed = Core; **managed/hosted high-volume = EE**).
- **FR-D3..D6:** Alembic migrations; schema version tracked; pre-built SQL views; all storage async.

### 5.8 Canary Rollout
- **FR-C1..C11:** `rollout_fraction` (0.0 = Hard Edit gate; (0,1) = canary; 1.0 = full). Random-at-start, sticky session assignment. Per-group FER. Promotion (take-profit) and rollback (stop-loss) in deterministic or statistical modes. Canary data in a separate secondary DB. **Single-instance canary = Core; cross-instance / fleet canary coordination = EE.**

### 5.9 Prompt Version Management
- **FR-V1..V6:** Append-only Prompt Registry per agent. **Prompt text never stored** — only SHA-256 hash, version, source, parent_id, created_at. Auditable lineage tree. Injection hashes versioned separately. **Local registry = Core; cloud-synced cross-machine/team registry = EE** *(v2.0 Open Question Q3)*.

### 5.10 Darwin Setup Wizard
- **FR-W1..W5:** `darwin init` launches a conversational wizard (agent ID, framework, mutation level, telemetry tiers, webhook URL). Generates `darwin.config.py/json`. AI-coding-environment friendly. Defaults to Basic level. **In v3.0 the wizard also presents the three telemetry tiers as pre-checked checkboxes (see §13).**

---

## 6. Non-Functional Requirements

| ID | Attribute | Requirement |
| :--- | :--- | :--- |
| NFR-01 | Latency | Signal detection <10ms P99. No measurable impact on agent latency. |
| NFR-02 | Throughput | Background queue ≥500 episodes/min without degradation. |
| NFR-03 | Reliability | Queue full → tasks dropped with warning; agent never blocked. |
| NFR-04 | Privacy | No raw content persisted; conversation represented only as SHA-256 hash. |
| NFR-05 | Portability | Fully offline; network only for optional LLM calls + data sync. |
| NFR-06 | Compatibility | Python 3.9+. No mandatory GPU/ML dependency. |
| NFR-07 | Schema stability | SQL schema backward-compatible within major version. |
| NFR-08 | Observability | All background ops emit structured DEBUG logs. |
| NFR-09 | Cost | Zero infra cost by default. LLM calls cost only on mutation. |
| NFR-10 | Testability | All components injectable/mockable. |
| **NFR-11** | **GEPA superiority (new)** | The paid GEPA optimizer must demonstrably beat the Core basic mutator on a maintained benchmark (`benchmarks/runner.py`). The paywall depends on this gap being measurable and reproducible. |

---

## 7. System Architecture

Four layers: **Adapter** (per-framework I/O interception), **Core Engine** (signal detection, FER, mutation generation), **Dispatch** (webhooks, GitHub PRs, auto-apply), **Storage** (SQLite/Postgres/Supabase). Critical invariant: **thread isolation** — the main thread handles only synchronous signal detection; everything else runs in a background worker pool via a non-blocking queue. Queue overflow drops tasks with a WARNING; the agent thread never waits.

### 7.1 Dual Feedback Loop
| Loop | Horizon | Mechanism | Outcome |
| :--- | :--- | :--- | :--- |
| **Short** | Intra-session | Reactive injection on each significant signal | Ephemeral — no system-prompt change |
| **Long** | Inter-session | Pattern analysis → Soft/Hard Edit | Permanent prompt change |

The short loop = branch-level signal (ephemeral, local). The long loop extracts what the short loop learned repeatedly and makes it permanent — a compounding improvement cycle.

### 7.2 Data Flow
1. User message → adapter. 2. Adapter extracts hash/message/response/tokens/session. 3. `SignalDetector.detect()` sync <10ms. 4. Episode + signals → BackgroundQueue. 5. Worker writes episode, computes FER, checks threshold. 6. If crossed → mutation generation (BYOK). 7. Result → webhook + GitHub PR (or auto-apply). 8. Rollback monitor samples post-mutation FER; reverts if worse.

---

## 8. Data Model (abridged)

Tables: `prompt_versions`, `episodes` (with `group ∈ {canary, control, full}`), `feedback_signals`, `positive_signals`, `fer_metrics` (NFR/PFR/AINPS/W-NFR + rolling columns + tokens_to_first_*), `mutations` (lineage, status, rollout_fraction, canary/control FER), `session_injection_log` (Darwin-generated injection text, chain lineage, outcome). Pre-built SQL views: `metrics_by_version`, `rolling_metrics`, `signal_distribution`, `mutation_outcomes`, `canary_vs_control`. Full DDL preserved from v2.0 §9.

---

## 9. Public API (abridged)

`FeedbackConfig` dataclass exposes: agent_id, agent_goal, implementation_level; detection (mode, weights, custom_patterns); mutation (level, auto_apply_threshold, llm_api_key BYOK, llm_model); trigger (metric, thresholds, breach_count, token_milestone); rollback (multiplier, stat_test, alpha); storage (backend, canary_storage_backend); notifications (webhook_urls, github_token/repo); **data sharing (`contribute_to_central_db: bool = True`, tier flags — see §13)**; canary (rollout_fraction/min_sessions/promote_threshold/mode). Read API: `get_rolling_fer`, `get_fer_by_version`, `get_signal_distribution`, `get_mutations`, `get_improvement_trend`.

---

## 10. Security & Privacy

Privacy-by-design: the Local Evaluator reads raw conversation **in-process** to generate causal signals, extracts an anonymized structural summary, and **discards the raw content**. Only anonymized summaries + aggregate metrics leave the local environment. Enforced at the adapter layer before storage/network.

| Data type | Treatment |
| :--- | :--- |
| User messages | Not stored (hashed) |
| Assistant responses | Not stored (discarded) |
| System prompts | SHA-256 hash only |
| Tokens consumed | Integer |
| Signal types | Enum label |
| Mutation reasoning | LLM output text (no PII) |

Credentials: LLM/GitHub keys never logged; GitHub token min-scoped. Local SQLite file at `0600`. **The Privacy Scrubber (§13) runs on L3 free-text summaries before they leave the machine — the technical guarantee behind the "anonymous" claim.**

---

## 11. Open-Core Model & Monetization Boundary (NEW — canonical)

### 11.1 The mechanical rule
For any module, present or future:

> **Runs on one machine, for one agent, operated by the person → Core (MIT, free).**
> **Needs a server, many agents, a team, or is state-of-the-art intelligence → EE (paid).**
> **Splits along a basic/advanced line inside the module → Misto.**

### 11.2 Exhaustive module map
Source tags: **[PRD]** = specified in PRD v2.0 · **[PRD→]** = present in v2.0 as future/roadmap/non-goal/open-question · **[NEW]** = new product decision in v3.0.

| Category | 🔓 Core (MIT, free) | ◐ Misto | 🔒 EE (paid) |
| :--- | :--- | :--- | :--- |
| **Instrumentation & capture** | Adapters Anthropic/OpenAI/LangChain/CrewAI [PRD]; normalization [PRD] | — | Bespoke / SLA adapters [NEW] |
| **Signal detection** | Regex [PRD]; prompt/BYOK [PRD]; taxonomy & weights [PRD]; custom patterns [PRD]; ML classifier basic [PRD→] | — | ML classifier premium (retrained on population) [NEW]; population auto-calibration [NEW] |
| **Measurement (FER)** | NFR/PFR/AINPS/W-NFR [PRD]; rolling windows [PRD]; SQL views [PRD]; tokens_to_first [PRD] | — | Cross-instance benchmark [PRD→]; industry benchmarks [NEW] |
| **Evolution intelligence** | Basic single-shot mutator [PRD]; rule-based fallback [PRD] | Pattern Analyzer (basic Core / GEPA-grade EE) [PRD] | GEPA genetic/Pareto [PRD name, NEW as paid tier]; multi-objective [NEW]; managed Darwin no-BYOK [NEW] |
| **Evolution machinery** | Injection [PRD]; Soft Edit [PRD]; Hard Edit / GitHub PR [PRD]; short loop [PRD]; auto-apply [PRD]; rollback [PRD] | — | — |
| **Validation & rollout** | Canary router single-instance [PRD]; statistical tests [PRD]; promote/rollback [PRD]; secondary canary DB [PRD] | — | Fleet canary (cross-instance) [NEW] |
| **Versioning & storage** | Prompt Registry local [PRD]; lineage tree [PRD]; SQLite [PRD]; Postgres/Supabase self [PRD→]; Alembic migrations [PRD] | — | Managed Postgres / high-volume [NEW]; cloud-synced registry [PRD→] |
| **Notification & integration** | Webhooks fire-and-forget [PRD]; feedback/mutation events [PRD]; multiple endpoints [PRD]; GitHub PR [PRD] | — | Guaranteed retry queue [PRD→]; proactive alerting [NEW]; managed Slack/Teams [NEW] |
| **Onboarding & DX** | Darwin Init wizard [PRD]; Basic→God config levels [PRD]; config generation [PRD] | — | God-tier managed (served scoring models, central control) [NEW] |
| **Fleet & scale** | — | — | Multi-agent panel [NEW]; cross-agent optimization [NEW]; degradation ranking [NEW] |
| **Collaboration & teams** | — | — | Hosted dashboard [PRD→]; approval workflows [NEW]; RBAC/roles [NEW]; shared audit [NEW] |
| **Enterprise & compliance** | — | Managed compliance/retention (local scrubber Core / contractual guarantees EE) [NEW] | SSO/SAML [NEW]; audit logs [NEW]; data residency [NEW]; on-prem/VPC managed [NEW]; SLA + support [NEW] |
| **Data & research** | Contribution client L1/L2/L3 [PRD]; Privacy Scrubber local [PRD] | Community dataset (published open / curation+serving EE) [PRD→] | Central DB ingestion + research platform [PRD]; cross-instance aggregation [PRD→]; mutation leaderboard [PRD→] |

**Provenance summary:** the Core is faithful to PRD v2.0 (it *is* the library). The EE surface is ~⅓ PRD seeds (future/roadmap) and ~⅔ new v3.0 product decisions — because a library PRD specifies the library, not the monetization layer.

### 11.3 The two revenue levers
Gating only GEPA (a quality axis) yields flat, one-time upgrade revenue. v3.0 pairs it with a scale axis so revenue expands with usage:

| Lever | Converts | Revenue shape | Modules |
| :--- | :--- | :--- | :--- |
| **Quality** | Individual power users | Per-seat upgrade | GEPA, ML classifier premium, managed Darwin (no BYOK) |
| **Scale / Central** | Teams & enterprise | Grows with usage (seats, agents) | Fleet, central DB/research, hosted dashboard, multi-tenant, SSO/RBAC/SLA |

---

## 12. Licensing (NEW)

- **Core = MIT.** The entire library is OSI-open, local-first, BYOK. Maximizes adoption and the telemetry flywheel.
- **EE = commercial.** All paid modules live in an isolated `ee/` directory under a separate Enterprise license (GitLab/Langfuse pattern). `ee/` is born commercial — new advanced features are created there, never relicensed out of MIT.
- **Irreversibility rule.** Code shipped under MIT stays MIT for that version. "Evolving as SaaS" means **new features are born in `ee/`**, never closing what was already open.
- **Repo shape:**
  ```
  darwin-loop/            LICENSE = MIT (root)
  ├── lib/         MIT    SDK → PyPI (darwin-feedbackloop)
  ├── backend/     MIT    self-hosted server (MVP)
  ├── mcp-server/  MIT
  ├── optimizers/  MIT    basic mutator (GEPA interface; basic impl)
  └── ee/          Commercial   GEPA advanced, fleet, central, multi-tenant…
      └── LICENSE
  ```

> **Open decision:** package name. PRD says `darwin-feedbackloop`; repo README says `darwin-client-lib`. Canonical here is `darwin-feedbackloop` — confirm before publishing to PyPI.

---

## 13. Telemetry & Consent (NEW — decided)

**Decision:** telemetry is **opt-out, default ON, anonymous**. This keeps the Core **true MIT** (nothing is license-compelled) while preserving the research flywheel.

### 13.1 Contribution tiers (cumulative)
| Tier | Sends (adds to previous) | Research value | Sensitivity |
| :--- | :--- | :--- | :--- |
| **L1 — metrics** | episode hash, NFR delta, mutation outcome, statistical significance | "Do mutations work?" | Minimal |
| **L2 — + categories** | intent cluster ID, failure pattern label | "For which failure types?" | Low |
| **L3 — + context** | anonymized structural summary from Local Evaluator (no raw content, no PII) | "Why?" — trains GEPA | Medium |

Always-present standard fields: `episode_id, signal_type, feedback_type, weight, detected_at, detection_mode`.

### 13.2 Consent UX & safeguards
- **Setup wizard shows three pre-checked checkboxes** (L1, L2, L3). The dev unchecks any tier they don't want. Collection is visible and granular at the point of collection — informed opt-out, not silent collection.
- **One umbrella toggle** + env override `DARWIN_TELEMETRY=0` to disable entirely; documented at the top of the README.
- **First-run notice** (short, two lines): `ℹ Anonymous telemetry active (helps improve DarwinLoop). Disable: DARWIN_TELEMETRY=0`.
- **Privacy Scrubber on L3** runs **before** any free-text summary leaves the machine — defense-in-depth keeping the "anonymous" claim true. If a summary would leak quasi-identifiers, the scrubber strips them.
- **Off by default for SaaS/enterprise** customers (contractual); default-on applies only to OSS self-hosters.

### 13.3 Legal basis
The legal basis is **"anonymous data, outside LGPD/GDPR scope"** (LGPD Art. 12), **not** consent — which is why default-on pre-checked boxes are acceptable here (pre-ticked boxes are not valid *consent*, but consent isn't required for genuinely anonymous data). The checkboxes are a transparency/ethics measure. This holds **only as long as** the privacy model and L3 scrubber keep the data truly non-re-identifiable.

---

## 14. Trade-off Analysis (carried from v2.0 + new)

Carried: sync signal detection; regex over ML for the <10ms path; LLM (BYOK) mutation with rule-based fallback; SQLite default; GitHub PR approval; hash-only prompt storage; random-sticky canary routing; FER-ratio + min-sessions promotion. **New:** Core=MIT/EE=commercial split (adoption + flywheel vs value capture); telemetry opt-out default-on (volume vs trust — mitigated by visible per-tier opt-out + scrubber); GEPA-as-paywall (requires provable benchmark gap, NFR-11).

---

## 15. Version Roadmap

| Version | Target | Scope |
| :--- | :--- | :--- |
| v1.0 | Q3 2026 | Adapters, regex detector, FER engine, SQLite, webhooks, GitHub PR, auto-apply + rollback. (Core) |
| v1.1 | Q4 2026 | Postgres/Supabase backends, GitLab adapter, webhook retry, expanded rule templates. |
| v2.0 (lib) | Q1 2027 | Fine-tuned classifier, multi-turn signal context, statistical rollback, community dataset. |
| **EE track** | 2027+ | GEPA advanced optimizer, fleet management, central research DB, cross-instance aggregation, mutation leaderboard, hosted dashboard, multi-tenant, SSO/RBAC. |

---

## 16. Open Questions & Pending Decisions

**Carried (v2.0):** minimum episode volume for statistical significance (Q1); multi-turn signal attribution ambiguity (Q2); cloud-sync of prompt lineage (Q3, now scoped as EE); auto_apply_threshold default (Q4); adversarial FER gaming (Q5).

**New (v3.0) — to confirm:**
1. **Two-lever paywall** — confirm pairing GEPA (quality) with the scale/central lever, vs betting on GEPA alone.
2. **Exact basic↔GEPA line** — confirm: Core = single-shot `DARWIN_MUTATION_PROMPT`; EE = genetic/Pareto/multi-candidate reflective search.
3. **Package name** — `darwin-feedbackloop` (PRD) vs `darwin-client-lib` (README).
4. **Telemetry default tier** — DECIDED: all three (L1+L2+L3) default-on as pre-checked checkboxes; dev unchecks. Scrubber mandatory on L3.

---

## Appendix A — Glossary

FER, NFR, PFR, AINPS, W-NFR, Episode, Mutation, Injection, Soft Edit, Hard Edit, Darwin agent, BYOK, Rollback, Adapter, Signal, rollout_fraction, canary/control group, promotion, take-profit/stop-loss, Prompt Registry, Darwin Init, agent_goal, episode_context, Short/Long loop, Injection chain, Session Injection Manager, Injection Pattern Analyzer, session_injection_log, task_completion_lift — definitions preserved from PRD v2.0 Appendix A.

**New terms (v3.0):** **Core** (MIT, free, local/single-agent/self-operated), **Misto** (module split basic-Core / advanced-EE), **EE** (Enterprise Edition — commercial, server/fleet/team/state-of-the-art), **GEPA** (genetic-Pareto reflective prompt optimizer; the paid evolution intelligence), **two-lever model** (quality + scale revenue axes), **utilization-license tension** (the resolved v2.0 conflict between mandatory contribution and MIT).

---

*DarwinLoop / FeedbackLoop — PRD v3.0.0-alpha · 2026-06-16 · This document describes intended design. Implementation subject to change.*
