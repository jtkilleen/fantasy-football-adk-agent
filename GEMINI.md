# Fantasy Football Personal Agent — Project Guidelines (`GEMINI.md`)

## 1. Project Overview & Domain
The **Fantasy Football Personal Agent** is an AI assistant built with the [Google Agent Development Kit (ADK) for Python](https://github.com/google/adk-python) and powered by **Gemini** models on **Google Cloud**. It assists users with managing and analyzing their fantasy football teams using a deterministic, self-contained **Synthetic Fantasy Football Data Engine**.

### Core Capabilities
- **Waiver Wire & Roster Management**: Identify available free agents, recommend pickups/drops, and analyze bench depth (e.g., *"Please analyze my bench and see who I should start or drop"*).
- **Matchup Comparisons**: Compare the user's roster and projected performance against their current weekly opponent.
- **Trade Discovery & Evaluation**: Analyze roster strengths/weaknesses across the league to propose and evaluate mutually beneficial trades with other league managers.
- **Historical & Trend Analytics**: Answer analytical and longitudinal performance queries (e.g., *"How is my quarterback trending vs. this time last year?"*).
- **Player & Team Insights**: Perform high-level searches on players and NFL teams (injuries, usage trends, news, depth chart changes) to synthesize actionable insights.

### Data Layer Constraints
- **100% Synthetic Data Engine**: All league rosters, weekly matchups, waiver wire players, multi-season weekly stats, and scouting insights are generated and managed in `fantasy_agent/data/synthetic_league_store.py`. Do not call external third-party fantasy sports APIs.
- **Deterministic & Stateful**: Seeded synthetic data ensures 100% repeatable unit tests and `adk eval` runs while allowing Human-in-the-Loop (HITL) approved actions (waiver pickups, lineup swaps, trade proposals) to mutate in-session league state.

---

## 2. Tech Stack & Repository Standards
- **Language & Environment**: Python 3.11+ managed exclusively via **`uv`**.
  - Always run commands and scripts through `uv` (e.g., `uv sync`, `uv add <pkg>`, `uv run pytest`, `uv run adk web`).
  - Maintain a clean `pyproject.toml` and `uv.lock`.
- **Agent Framework**: [Google ADK (`google-adk`)](https://github.com/google/adk-python).
- **LLM Provider**: Google **Gemini** models for all LLM calls (via `google-genai` / Vertex AI).
- **Cloud & Deployment**: Google Cloud Platform (GCP), with all infrastructure provisioned via **Terraform** (Infrastructure as Code).
- **Public Git Repository**:
  - This repository will be made **public**.
  - **NEVER** commit API keys, service account JSON files, `.env` files, hardcoded GCP project IDs, personal identifiable information (PII), or internal-only URLs/endpoints.
  - Scope the implementation as a clean, well-architected demo/reference application rather than an over-engineered commercial platform.

### Recommended Repository Layout
```text
adk_agent/
├── GEMINI.md                  # AI assistant rules and architectural guidelines
├── pyproject.toml             # uv project configuration and dependencies
├── README.md                  # Setup, architecture, and Agent CLI / deployment docs
├── docs/
│   ├── project_overview.md    # High-level project requirements
│   └── agent_rubric.md        # AgentOps Code Review Matrix (target rubric)
├── fantasy_agent/             # Main ADK agent package
│   ├── __init__.py
│   ├── agent.py               # Root coordinator agent entrypoint (root_agent)
│   ├── config.py              # Settings, model routing config, Secret Manager loader
│   ├── prompts.py             # System instructions ("constitution") per agent
│   ├── data/                  # Deterministic synthetic fantasy league & multi-season stats store
│   ├── sub_agents/            # Specialized ADK sub-agents (roster/waiver, analytics, trade)
│   ├── tools/                 # Fantasy league, analytics, and trade tools with strict schemas
│   ├── memory/                # Session state, compaction, and async memory indexing
│   ├── callbacks/             # Guardrails, HITL confirmation hooks, and tracing callbacks
│   └── observability/         # Structured JSON logging, OpenTelemetry, PII scrubbing
├── tests/
│   ├── unit/                  # Unit tests for tools, schemas, guardrails, and observability
│   └── eval/                  # ADK automated evaluation suites & golden datasets
└── terraform/                 # Terraform IaC for GCP resources & Secret Manager
```

---

## 3. AgentOps Architecture & Engineering Standards
All code in this repository is evaluated against the **AgentOps Code Review Matrix** ([`docs/agent_rubric.md`](docs/agent_rubric.md)). Every feature and module must adhere to these five pillars:

### 3.1 Tool & Interface Design
1. **Descriptive Naming**: Name tool functions after specific domain actions (e.g., `fetch_fantasy_league_rosters`, `compare_weekly_matchup`, `search_available_waiver_players`, `evaluate_league_trade_proposal`) rather than generic names like `get_data`.
2. **Comprehensive Docstrings**: Every tool function must have a detailed docstring describing its purpose, when the LLM should call it, every parameter (with types and examples), and the structure of the returned dictionary.
3. **Explicit JSON Schemas**: Use strict Python type annotations and **Pydantic** models to validate tool inputs and constrain outputs.
4. **Guided Error Handling**: Tools must never raise raw unhandled exceptions to the LLM. Catch validation errors, invalid team/player IDs, and out-of-range weeks, and return a structured dictionary containing `"status": "error"`, `"error_type"`, and an actionable `"recovery_instruction"` guiding the LLM on how to proceed.

### 3.2 Context & Memory
1. **Robust System Instructions**: Define a clear "constitution" in each agent's `instruction` prompt covering persona, fantasy football scoring/roster rules, data grounding rules, and refusal/safety boundaries.
2. **History Compaction**: Prevent context window bloat (especially from large roster/player stats payloads) by implementing token-based truncation, sliding windows, summarization, or ADK context compaction.
3. **Persistent Session State**: Integrate a persistent backing store (e.g., ADK `DatabaseSessionService` / SQLite / Cloud SQL / Vertex AI session & memory bank) to persist user context (`team_id`, scoring format, staged actions) and conversational history across turns.
4. **Async Memory Operations**: Implement expensive operations—such as indexing multi-season synthetic player trends or consolidating session memories—using `async`/`await` or background tasks so user interactions remain non-blocking.

### 3.3 Orchestration & Logic
1. **Multi-Agent Patterns**: Avoid a single monolithic agent. Use ADK multi-agent patterns (`LlmAgent` coordinator delegating to specialized sub-agents, `SequentialAgent`, or `ParallelAgent`), such as:
   - **Coordinator Agent**: Routes user intent and manages high-level conversation.
   - **League & Waiver Agent**: Fetches rosters and searches available waiver wire players.
   - **Analytics & Trend Agent**: Evaluates historical player trends, bench efficiency, and player/team insights.
   - **Trade & Matchup Strategy Agent**: Compares weekly opponent matchups and synthesizes mutually beneficial trades.
2. **Strategic Model Routing**: Route tasks to the appropriate Gemini model tier:
   - **Fast / Low-Latency Tasks (`gemini-2.5-flash`)**: Intent classification, roster lookups, waiver wire searches, and straightforward summarization.
   - **Complex Reasoning (`gemini-2.5-pro`)**: Multi-player trade synthesis, longitudinal trend analysis, and deep bench/matchup strategy planning.
3. **Guardrails & Policy Plugins**: Implement ADK callbacks (`before_model_callback`, `after_model_callback`, `before_tool_callback`) to enforce domain boundaries, validate tool inputs, and check responses for hallucinations.
4. **Human-in-the-Loop (HITL) Hooks**: Any high-stakes or state-mutating action (e.g., finalizing/sending a trade proposal, executing a roster drop/add, or modifying starting lineups) must include an explicit confirmation hook requiring human approval before execution.

### 3.4 Observability & Tracing
1. **Structured JSON Logging**: Never use bare `print()` statements in application code. Use structured JSON logging (`structlog`, `python-json-logger`, or `google-cloud-logging`) with rich contextual metadata (`session_id`, `agent_name`, `tool_name`, `team_id`).
2. **Intent vs. Outcome Capture**: In agent/tool lifecycle hooks, explicitly log both the **intended action** (before tool/sub-agent execution, including arguments) and the **actual outcome** (after execution, including status, latency, and summary).
3. **Distributed Tracing**: Instrument the agent workflow with **OpenTelemetry** (`opentelemetry-sdk` / Cloud Trace) to link spans from the initial user query through sub-agent handoffs, LLM calls, and tool executions.
4. **PII Redaction**: Include active PII scrubbing filters in both logging and memory pipelines (via Google Cloud Sensitive Data Protection / DLP API or deterministic regex/redaction processors) to strip emails, phone numbers, tokens, and personal identifiers before storage.

### 3.5 Infrastructure & CI/CD
1. **Automated Evaluation Suites**: Maintain an automated evaluation suite under `tests/eval/` (using `adk eval` and `pytest` against a golden dataset of fantasy football prompts and expected tool trajectories) to detect regressions.
2. **Infrastructure as Code (IaC)**: Define all required Google Cloud resources (Cloud Run / Vertex AI Agent Engine, Secret Manager, storage/databases, IAM least-privilege roles) in `terraform/` and document `adk` CLI and Terraform deployment workflows in `README.md`.
3. **Secure Secret Management**: Retrieve all sensitive configuration (API keys, project credentials) dynamically via **Google Cloud Secret Manager** (with safe local environment variable fallback for offline unit testing).
