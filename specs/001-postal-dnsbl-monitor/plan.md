# Implementation Plan: Postal DNSBL Monitor

**Branch**: `001-postal-dnsbl-monitor` | **Date**: 2025-12-17 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/001-postal-dnsbl-monitor/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

The Postal DNSBL Monitor is a stateless, containerized Python 3.14 application that runs as a Kubernetes CronJob to periodically check IPv4 addresses stored in the PostgreSQL `postal.ip_addresses` table against configurable DNSBL providers. The system uses dnspython for DNS lookups, classifying results as LISTED, NOT_LISTED, or UNKNOWN. It automatically throttles blacklisted IPs by updating database priority columns with deterministic idempotent updates, creates and manages Jira tracking tickets using JQL-based deduplication, and emits structured JSON logs for operational monitoring. The implementation prioritizes DNS fault tolerance (>50% UNKNOWN triggers MAJOR MALFUNCTION alerts), Jira retry with exponential backoff (2s, 4s, 8s), and READ COMMITTED transaction isolation for concurrent job safety.

## Technical Context

**Language/Version**: Python 3.14  
**Primary Dependencies**: 
- `dnspython` (DNS lookups with DNSBL zones)
- `jira` from pycontribs (Jira API client)
- `psycopg2` or `psycopg2-binary` (PostgreSQL driver)

**Dependency Management**: `uv` (REQUIRED per constitution v1.2.0)  
**Storage**: PostgreSQL (existing `postal.ip_addresses` table, READ COMMITTED isolation)  
**Testing**: `pytest` with fixtures for database/Jira/DNS mocking  
**Target Platform**: Kubernetes CronJob (containerized Docker image)  
**Project Type**: Single-project CLI batch job (stateless one-shot execution)  
**Performance Goals**: 
- Process up to 1000 IPs × 10 DNSBL zones within 5 minutes
- Concurrent DNS queries (configurable limit, default 10 parallel)
- Exit code 0 within 5min under normal load

**Constraints**: 
- Kubernetes resource limits: 500m CPU / 512Mi memory
- No local persistent storage (stateless)
- Idempotent: zero duplicate Jira issues or DB writes on re-run
- Error handling per FR-004 and FR-030 (fatal errors exit non-zero)

**Scale/Scope**: 
- Up to 1000 monitored IPs
- Up to 10 configured DNSBL zones
- Single CronJob deployment (no horizontal scaling required)
- Structured JSON logging for centralized monitoring

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Stateless Execution (NON-NEGOTIABLE)
- ✅ **PASS**: FR-001 requires stateless one-shot process with no local persistent storage
- ✅ **PASS**: All durable state in PostgreSQL (`postal.ip_addresses`) and Jira (tickets)
- ✅ **PASS**: No assumptions about process continuity or local files

### Principle II: Kubernetes-Native Deployment
- ✅ **PASS**: FR-001 specifies Kubernetes CronJob deployment
- ✅ **PASS**: Constitution mandates production Docker image with pinned dependencies via `uv.lock`
- ✅ **PASS**: Dependencies section specifies ConfigMap/Secret for configuration
- 📋 **DELIVERABLE REQUIRED**: Dockerfile, kubernetes/cronjob.yaml, kubernetes/configmap-template.yaml

### Principle III: Data Integrity & Determinism
- ✅ **PASS**: FR-014 enforces `oldPriority` single-write invariant (exactly once on clean→listed transition)
- ✅ **PASS**: FR-014 enforces `blockingLists` deterministic sorting: `",".join(sorted(zone_list))`
- ✅ **PASS**: FR-014 enforces `lastEvent` material-changes-only (new listing, clearing, zone-set change)
- ✅ **PASS**: FR-032 requires idempotent updates (re-run without state changes = zero DB writes)

### Principle IV: Jira Integration & Deduplication
- ✅ **PASS**: FR-020 requires JQL-based deduplication (search Jira, NOT DB-only)
- ✅ **PASS**: FR-021 specifies JQL template with configurable JIRA_EXCLUDED_STATUSES
- ✅ **PASS**: FR-022 requires deterministic summary: `"IP {ip} blacklisted by {sorted_zones}"`
- ✅ **PASS**: FR-023/FR-024 create issue only if no open issue exists, reuse existing on state change
- ✅ **PASS**: FR-025 prevents duplicates, uses most recent issue if multiple found

### Principle V: DNS Reliability & Fault Tolerance
- ✅ **PASS**: FR-009 classifies LISTED (A record), NOT_LISTED (NXDOMAIN), UNKNOWN (timeout/SERVFAIL)
- ✅ **PASS**: FR-012 requires "IP is LISTED if ≥1 zone returns LISTED; CLEAN if 0 zones LISTED"
- ✅ **PASS**: FR-010 applies configurable DNS timeout (default 5s)
- ✅ **PASS**: FR-013a creates MAJOR MALFUNCTION Jira issue when >50% zones return UNKNOWN
- ✅ **PASS**: Constitution mandates dnspython library

### Principle VI: Idempotency
- ✅ **PASS**: FR-032 requires identical outputs on re-run with no state changes
- ✅ **PASS**: SC-004 validates zero additional DB writes or Jira issues/comments
- ✅ **PASS**: FR-014 enforces idempotent DB updates

### Principle VII: Configuration as Code
- ✅ **PASS**: FR-002 requires all config from environment variables or mounted files
- ✅ **PASS**: No hardcoded database params, DNSBL zones, priorities, Jira credentials
- ✅ **PASS**: FR-003 supports DRY_RUN mode via environment flag
- 📋 **DELIVERABLE REQUIRED**: Environment variable documentation, ConfigMap template

### Principle VIII: Observability
- ✅ **PASS**: FR-028 emits structured JSON logs per IP (ip, listed_zones, unknown_zones, decision, db_changes, jira_action, duration_ms, timestamp)
- ✅ **PASS**: FR-030 distinguishes fatal (DB/Jira unreachable → exit non-zero) vs non-fatal (DNS UNKNOWN → log and continue)
- ✅ **PASS**: FR-031 logs job summary (total IPs, listed, cleaned, unchanged, Jira actions, DNS failures, duration)

**Constitution Compliance**: ✅ **ALL GATES PASS** - No violations requiring justification

## Project Structure

### Documentation (this feature)

```text
specs/001-postal-dnsbl-monitor/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output - library selections, best practices
├── data-model.md        # Phase 1 output - database schema, entities
├── quickstart.md        # Phase 1 output - setup, development, deployment
├── contracts/           # Phase 1 output - configuration schema, log format
│   ├── config-schema.yaml       # Environment variable definitions
│   └── log-format.json          # Structured logging schema
├── checklists/
│   └── requirements.md  # Specification quality validation (already created)
└── spec.md              # Feature specification (already created)
```

### Source Code (repository root)

```text
# Single-project CLI batch job structure

src/
├── __init__.py
├── main.py                    # Entry point, orchestrates execution flow
├── config.py                  # Environment variable loading, validation
├── models/
│   ├── __init__.py
│   ├── ip_record.py          # IP Address Record entity (dataclass)
│   ├── dns_result.py         # DNS Query Result (LISTED/NOT_LISTED/UNKNOWN)
│   └── state_transition.py   # State transition logic (clean↔listed)
├── services/
│   ├── __init__.py
│   ├── database.py           # PostgreSQL connection, IP queries, updates
│   ├── dns_checker.py        # DNSBL zone queries, concurrent lookups
│   ├── jira_client.py        # Jira API, JQL search, issue create/update
│   └── logger.py             # Structured JSON logging utility
└── utils/
    ├── __init__.py
    ├── ip_utils.py           # IPv4 validation, reverse DNS formatting
    └── retry.py              # Exponential backoff retry decorator

tests/
├── __init__.py
├── conftest.py               # pytest fixtures (mock DB, Jira, DNS)
├── unit/
│   ├── test_config.py
│   ├── test_ip_record.py
│   ├── test_state_transition.py
│   ├── test_dns_result.py
│   └── test_ip_utils.py
├── integration/
│   ├── test_database.py      # PostgreSQL integration (testcontainers)
│   ├── test_dns_checker.py  # Real DNS queries (integration-only)
│   └── test_jira_client.py  # Jira API integration (mock server)
└── contract/
    ├── test_idempotency.py   # Verify FR-032 (re-run = zero writes)
    ├── test_deduplication.py # Verify FR-020/FR-025 (Jira JQL search)
    └── test_invariants.py    # Verify FR-014 (oldPriority, blockingLists)

kubernetes/
├── cronjob.yaml              # CronJob definition (schedule, resources)
├── configmap-template.yaml   # Configuration template (DNSBL zones, etc.)
└── secret-template.yaml      # Secrets template (DB password, Jira token)

Dockerfile                    # Multi-stage build with uv
pyproject.toml                # PEP 621 metadata, dependencies
uv.lock                       # Locked dependency versions
README.md                     # Project overview, quickstart reference
.dockerignore
.gitignore
```

**Structure Decision**: Single-project CLI batch job. No frontend/backend separation needed - this is a stateless CronJob with no interactive interface. All code in `src/` follows domain-driven organization: models (entities/logic), services (infrastructure), utils (shared helpers). Tests mirror source structure with unit/integration/contract separation per constitution testing requirements.

## Complexity Tracking

> **Not applicable** - Constitution Check shows all gates pass with no violations requiring justification.

---

## Phase 0: Outline & Research

**Goal**: Resolve all technical unknowns and establish best practices for implementation.

### Research Tasks

1. **DNS Library Selection & Best Practices**
   - **Question**: How to use dnspython for concurrent DNSBL lookups with timeout handling?
   - **Research Areas**:
     - dnspython async vs threading for concurrent queries
     - Exception handling for NXDOMAIN, SERVFAIL, timeout
     - Reverse DNS formatting for DNSBL queries (e.g., 203.0.113.45 → 45.113.0.203.zen.spamhaus.org)
     - Performance optimization for 1000 IPs × 10 zones within 5 minutes

2. **Jira API Client Best Practices**
   - **Question**: How to implement JQL search, exponential backoff retry, and rate limit handling with jira-python?
   - **Research Areas**:
     - `jira` library authentication (token-based)
     - JQL query construction with dynamic variables (JIRA_PROJECT, JIRA_EXCLUDED_STATUSES)
     - Exponential backoff implementation (2s, 4s, 8s)
     - Rate limit detection and handling
     - Issue create/update/comment API patterns

3. **PostgreSQL Transaction Management**
   - **Question**: How to ensure READ COMMITTED isolation with proper transaction boundaries for idempotent updates?
   - **Research Areas**:
     - psycopg2 connection pooling for CronJob context
     - Transaction management patterns (context managers)
     - Preventing lost updates during concurrent job executions
     - Batch update strategies for 1000 IPs

4. **Structured Logging for Kubernetes**
   - **Question**: Best practices for JSON logging that integrates with Kubernetes log aggregation (ELK, Splunk)?
   - **Research Areas**:
     - Python logging configuration for JSON output
     - Correlation IDs for job run tracking
     - Log level mapping (fatal vs non-fatal errors)
     - Performance impact of per-IP logging at scale

5. **Kubernetes CronJob Deployment Patterns**
   - **Question**: How to configure CronJob with ConfigMap/Secret, resource limits, and restart policies?
   - **Research Areas**:
     - CronJob schedule syntax (e.g., every 15 minutes)
     - Resource requests (250m CPU, 256Mi memory) and limits (500m CPU, 512Mi memory)
     - Restart policy for fatal errors (OnFailure vs Never)
     - ConfigMap for DNSBL zones and priorities
     - Secret management for DB password and Jira API token

6. **Docker Multi-Stage Build with uv**
   - **Question**: How to create production Docker image using uv for dependency management?
   - **Research Areas**:
     - Multi-stage Dockerfile pattern (build vs runtime)
     - uv installation in Docker (official install method)
     - `uv sync --frozen` for reproducible builds
     - Image size optimization (alpine vs slim-python)

7. **Testing Strategy for Stateless CronJob**
   - **Question**: How to test idempotency, deduplication, and invariants in integration tests?
   - **Research Areas**:
     - pytest fixtures for PostgreSQL (testcontainers)
     - Jira API mocking strategies (responses library or mock server)
     - DNS mocking for deterministic DNSBL tests
     - Contract test design for constitutional compliance

**Output**: `research.md` document with decisions, rationales, and code examples for each research area.

---

## Phase 1: Design & Contracts

**Prerequisites**: `research.md` complete

### 1. Data Model Design (`data-model.md`)

**Entities** (from spec Key Entities section):

1. **IP Address Record**
   - Source: PostgreSQL `postal.ip_addresses` table
   - Fields: `id` (int), `ip` (IPv4 string), `priority` (int), `oldPriority` (nullable int), `blockingLists` (string), `lastEvent` (string)
   - Validation Rules:
     - `ip` must be valid IPv4 dotted-quad (e.g., 203.0.113.45)
     - `blockingLists` format: `",".join(sorted(zones))` or empty string
     - `oldPriority` is NULL when `priority != LISTED_PRIORITY`
   - State Transitions:
     - Clean → Listed: `priority=LISTED_PRIORITY, oldPriority=<old priority>, blockingLists=<sorted zones>, lastEvent="new block from list(s) <zones>"`
     - Listed → Clean: `priority=oldPriority or CLEAN_FALLBACK_PRIORITY, oldPriority=NULL, blockingLists="", lastEvent="block removed"`
     - Listed → Listed (zone change): `blockingLists=<new sorted zones>, lastEvent="blocking list change: <zones>"`

2. **DNS Query Result** (transient, not persisted)
   - Fields: `ip` (string), `zone` (string), `classification` (enum: LISTED/NOT_LISTED/UNKNOWN), `response_data` (optional A record or error), `timestamp` (datetime)
   - Classification Logic:
     - LISTED: A record response (typically 127.0.0.x)
     - NOT_LISTED: NXDOMAIN response
     - UNKNOWN: Timeout, SERVFAIL, network error

3. **State Transition Event** (transient, captured in logs and Jira)
   - Fields: `ip`, `previous_state`, `new_state`, `zone_set_delta`, `timestamp`
   - Triggers: Material state changes only (new listing, clearing, zone membership change)

4. **Jira Issue** (external, managed via Jira API)
   - Fields: `issue_key`, `summary` (deterministic format), `description`, `status`, `labels`
   - Summary Format: `"IP {ip} blacklisted by {sorted_zones}"`
   - Deduplication: JQL search `project = "{JIRA_PROJECT}" AND status NOT IN ({JIRA_EXCLUDED_STATUSES}) AND summary ~ "IP {ip}"`

**Relationships**:
- One IP Address Record → Zero-or-One Open Jira Issue (via JQL search)
- One IP Address Record → Many DNS Query Results (one per DNSBL zone, per job run)

### 2. API Contracts (`contracts/` directory)

**File: `contracts/config-schema.yaml`**

Environment variable schema (OpenAPI-style):

```yaml
environment_variables:
  # Database Configuration
  DB_HOST:
    type: string
    required: true
    description: PostgreSQL server hostname
  DB_PORT:
    type: integer
    default: 5432
    description: PostgreSQL server port
  DB_NAME:
    type: string
    required: true
    description: Database name (typically "postal")
  DB_USER:
    type: string
    required: true
    description: Database username
  DB_PASSWORD:
    type: string
    required: true
    sensitive: true
    description: Database password
  DB_DSN:
    type: string
    required: false
    description: "Optional DSN (overrides individual DB_* params)"

  # DNSBL Configuration
  DNSBL_ZONES:
    type: string
    required: true
    description: "Comma-separated DNSBL zones (e.g., zen.spamhaus.org,bl.spamcop.net)"
  DNS_TIMEOUT:
    type: integer
    default: 5
    description: "DNS query timeout in seconds"
  DNS_CONCURRENCY:
    type: integer
    default: 10
    description: "Max concurrent DNS queries"

  # Priority Configuration
  LISTED_PRIORITY:
    type: integer
    default: 0
    description: "Priority value for listed IPs (typically 0 = fully throttled)"
  CLEAN_FALLBACK_PRIORITY:
    type: integer
    default: 50
    description: "Fallback priority when oldPriority is NULL on clearing"

  # Jira Configuration
  JIRA_SERVER:
    type: string
    required: true
    description: "Jira server URL (e.g., https://company.atlassian.net)"
  JIRA_USER:
    type: string
    required: true
    description: "Jira username or email"
  JIRA_API_TOKEN:
    type: string
    required: true
    sensitive: true
    description: "Jira API token"
  JIRA_PROJECT:
    type: string
    required: true
    description: "Jira project key (e.g., OPS)"
  JIRA_ISSUE_TYPE:
    type: string
    required: true
    description: "Issue type for blacklist issues (e.g., Incident)"
  JIRA_DNS_FAILURE_ISSUE_TYPE:
    type: string
    required: true
    description: "Issue type for DNS failures (e.g., Alert)"
  JIRA_EXCLUDED_STATUSES:
    type: string
    default: "Done,Closed,Resolved"
    description: "Comma-separated status names to exclude from JQL (indicates closed issues)"

  # Operational Configuration
  DRY_RUN:
    type: boolean
    default: false
    description: "If true, no DB writes or Jira actions (log only)"
```

**File: `contracts/log-format.json`**

Structured log schema (per-IP log entry):

```json
{
  "type": "object",
  "required": ["timestamp", "ip", "decision", "db_changes", "jira_action"],
  "properties": {
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp"
    },
    "ip": {
      "type": "string",
      "pattern": "^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$",
      "description": "IPv4 address checked"
    },
    "listed_zones": {
      "type": "array",
      "items": {"type": "string"},
      "description": "DNSBL zones where IP is LISTED"
    },
    "unknown_zones": {
      "type": "array",
      "items": {"type": "string"},
      "description": "DNSBL zones that returned UNKNOWN"
    },
    "decision": {
      "type": "string",
      "enum": ["LISTED", "CLEAN"],
      "description": "Final listing decision"
    },
    "db_changes": {
      "type": "boolean",
      "description": "Whether database was updated"
    },
    "jira_action": {
      "type": "string",
      "enum": ["created_issue", "updated_issue", "no_action"],
      "description": "Jira action taken"
    },
    "duration_ms": {
      "type": "integer",
      "description": "Time to process this IP in milliseconds"
    }
  }
}
```

### 3. Quickstart Guide (`quickstart.md`)

**Contents**:
1. Prerequisites (Python 3.14, uv, PostgreSQL, Kubernetes cluster, Jira instance)
2. Local Development Setup
   - Clone repository
   - Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Create virtual environment: `uv venv`
   - Install dependencies: `uv sync`
   - Configure environment variables (`.env` file)
   - Run locally: `uv run python src/main.py`
3. Testing
   - Run unit tests: `uv run pytest tests/unit`
   - Run integration tests: `uv run pytest tests/integration` (requires PostgreSQL testcontainer)
   - Run contract tests: `uv run pytest tests/contract`
4. Docker Build
   - Build image: `docker build -t postal-dnsbl-monitor:latest .`
   - Run container: `docker run --env-file .env postal-dnsbl-monitor:latest`
5. Kubernetes Deployment
   - Create ConfigMap: `kubectl apply -f kubernetes/configmap.yaml`
   - Create Secret: `kubectl apply -f kubernetes/secret.yaml`
   - Deploy CronJob: `kubectl apply -f kubernetes/cronjob.yaml`
   - View logs: `kubectl logs -l job-name=dnsbl-monitor-<job-id>`
6. Troubleshooting
   - DRY_RUN mode for testing
   - Viewing Jira issues created
   - Checking database state

### 4. Agent Context Update

Run `.specify/scripts/bash/update-agent-context.sh opencode` to update agent context with:
- Python 3.14
- uv dependency management
- dnspython
- jira (pycontribs)
- psycopg2
- pytest
- Kubernetes CronJob patterns

---

## Phase 2: Task Breakdown (OUT OF SCOPE for /speckit.plan)

**Note**: Task breakdown is generated by the `/speckit.tasks` command, NOT by `/speckit.plan`. This plan document ends after Phase 1 deliverables.

**Phase 2 Entry Criteria**:
- `research.md` complete with all library selections documented
- `data-model.md` complete with entity definitions and state transitions
- `contracts/` directory complete with config schema and log format
- `quickstart.md` complete with setup instructions
- Agent context updated with project technologies

**Phase 2 Output** (when `/speckit.tasks` is run):
- `tasks.md` with prioritized task list
- Tasks mapped to acceptance criteria from spec
- Dependencies between tasks identified
- Estimated effort per task

---

## Deliverables Summary

### Phase 0 Deliverables
- ✅ `research.md` - Technical research and decisions

### Phase 1 Deliverables
- ✅ `data-model.md` - Entity definitions and state transitions
- ✅ `contracts/config-schema.yaml` - Environment variable schema
- ✅ `contracts/log-format.json` - Structured log schema
- ✅ `quickstart.md` - Development and deployment guide
- ✅ Agent context updated (via update-agent-context.sh)

### Implementation Deliverables (created during task execution, not planning)
- `src/` - Python source code
- `tests/` - pytest test suite
- `Dockerfile` - Production Docker image
- `kubernetes/` - CronJob, ConfigMap, Secret manifests
- `pyproject.toml` - PEP 621 project metadata
- `uv.lock` - Locked dependencies

---

## Next Steps

1. Run Phase 0 research to create `research.md`
2. Run Phase 1 design to create `data-model.md`, `contracts/`, and `quickstart.md`
3. Update agent context with project technologies
4. Re-validate Constitution Check after design (expected: all gates still pass)
5. User runs `/speckit.tasks` to generate task breakdown in `tasks.md`
