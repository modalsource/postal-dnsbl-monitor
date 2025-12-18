<!--
Sync Impact Report - Constitution Update
=========================================

Version Change: 1.1.0 -> 1.2.0
Type: MINOR (Specified PostgreSQL as database requirement)

Modified Principles:
- (none)

Modified Sections:
- Technical Stack & Dependencies: Specified PostgreSQL driver requirement (psycopg2/psycopg2-binary)

Added Sections:
- (none in this update)

Removed Sections:
- (none)

Templates Requiring Updates:
- ✅ plan-template.md: No changes needed (generic Technical Context section)
- ✅ spec-template.md: No changes needed (technology-agnostic requirements)
- ✅ tasks-template.md: No changes needed (language-agnostic task structure)

Follow-up TODOs:
- Ensure Dockerfile uses uv for dependency installation
- Create pyproject.toml with PEP 621 metadata and psycopg2 dependency
- Update any existing setup documentation to reference uv and PostgreSQL

Last Updated: 2025-12-17
Previous Updates:
- 2025-12-17: v1.1.0 - Added uv dependency management requirement
- 2025-12-16: v1.0.0 - Initial constitution ratification
-->

# Postal DNSBL Monitor Constitution

## Core Principles

### I. Stateless Execution (NON-NEGOTIABLE)

The system MUST NOT maintain any local persistent state between job runs. All durable state
MUST reside exclusively in the database (postal.ip_addresses) and Jira. The job must be safe
to run repeatedly, producing identical outcomes for identical input state.

**Rationale**: Kubernetes CronJobs can be killed, rescheduled, or run on different nodes.
Stateless design ensures deterministic behavior, simplifies debugging, and eliminates
race conditions from concurrent or interrupted runs.

### II. Kubernetes-Native Deployment

The system MUST be deployable as a Kubernetes CronJob with no assumptions about persistent
local storage or process continuity. The implementation MUST produce:

- A production-ready Docker image with pinned dependencies
- Kubernetes CronJob YAML or Helm chart skeleton defining schedule, resource limits,
  environment configuration (ConfigMap/Secret), and restart policies

**Rationale**: Kubernetes is the target runtime. Native CronJob deployment ensures
portability, scalability, and integration with cluster monitoring/alerting.

### III. Data Integrity & Determinism

Column updates MUST follow strict invariants:

- `oldPriority` is set exactly once when transitioning into throttled state and MUST NOT be
  overwritten while `priority == LISTED_PRIORITY`
- `blockingLists` MUST always be stored as `",".join(sorted(zones))` with no spaces to ensure
  deterministic comparison and deduplication
- `lastEvent` MUST describe only material state transitions (new listing, clearing, list-set
  change while listed)
- All DB updates MUST be idempotent: re-running the job without state changes produces no
  additional writes

**Rationale**: Deterministic data model prevents silent corruption, enables accurate diff
detection, and ensures Jira deduplication works reliably across job runs.

### IV. Jira Integration & Deduplication

Jira ticket deduplication MUST be achieved by searching Jira using JQL, NOT by DB-only
deduplication. The system MUST:

- Compute deterministic issue summary: `IP {ip} blacklisted by {sorted_zones}`
- Search Jira for open issues matching the IP using configurable JQL
- Create a new issue only if no open issue exists for that IP
- Add comments or update summary when list membership changes for an existing issue
- Never create duplicate issues for the same IP

**Rationale**: Jira is the source of truth for ticket state. DB-only deduplication fails
if tickets are manually closed or created outside the job. Searching Jira ensures accuracy.

### V. DNS Reliability & Fault Tolerance

DNS check results MUST distinguish:

- **LISTED**: A record response from DNSBL zone
- **NOT_LISTED**: NXDOMAIN response
- **UNKNOWN**: Timeout, SERVFAIL, or other transient DNS errors

UNKNOWNs MUST be logged and included in Jira descriptions but MUST NOT alone trigger throttling.
An IP is LISTED if at least one zone returns LISTED. An IP is CLEAN only if zero zones return
LISTED. The system MUST use `dnspython` for DNS lookups with configurable timeouts.

**Rationale**: DNS is unreliable. Transient failures must not cause false positives. Clear
semantic distinction between "not listed" and "unknown" enables safe decision-making.

### VI. Idempotency

Re-running the job with no external state changes (same IP statuses, same Jira state) MUST:

- Produce zero DB writes
- Create zero new Jira issues
- Produce identical log output (excluding timestamps)

**Rationale**: Kubernetes may retry failed jobs or run overlapping executions. Idempotency
prevents double-throttling, duplicate tickets, and log spam, simplifying operations.

### VII. Configuration as Code

All configuration MUST be via environment variables or mounted files. No hardcoded values
are permitted for:

- Database connection (DSN or individual params)
- DNSBL zone list (comma-separated or file path)
- DNS timeout and concurrency limits
- Priority values (LISTED_PRIORITY, CLEAN_FALLBACK_PRIORITY)
- Jira credentials and project settings
- DRY_RUN mode flag

**Rationale**: Environment-driven configuration enables GitOps workflows, per-environment
customization, and safe testing without code changes.

### VIII. Observability

The system MUST emit structured logs for every IP checked, including:

- `ip`, `listed_zones`, `unknown_zones`, `decision` (LISTED/CLEAN), `db_changes`,
  `jira_action`, `duration_ms`

Fatal errors (DB unreachable, Jira auth failure) MUST exit non-zero. Non-fatal DNS failures
MUST NOT fail the job. Logs MUST be machine-parseable (JSON preferred) for centralized
monitoring.

**Rationale**: Kubernetes logs are the primary debugging interface. Structured logs enable
alerting on failures, performance analysis, and audit trails for compliance.

## Technical Stack & Dependencies

**Language**: Python 3.14 (target runtime)

**Dependency Management**: uv (REQUIRED)

The project MUST use uv for dependency management. This ensures:

- Extremely fast dependency resolution and installation (10-100x faster than pip/poetry)
- Deterministic dependency resolution via `uv.lock`
- Reproducible builds across development and production environments
- Built-in virtual environment management
- PEP 621 compliance via `pyproject.toml`

**Required Libraries**:

- `dnspython`: DNS lookups with DNSBL zones
- `jira` (pycontribs): Jira API client for ticket management
- PostgreSQL driver: `psycopg2` or `psycopg2-binary` (production Postal instance uses PostgreSQL)

**Container**: Docker image using `uv pip compile` and `uv pip install` or `uv sync --frozen`

**Deployment**: Kubernetes CronJob with ConfigMap/Secret for configuration

All dependencies MUST be pinned to specific versions via `uv.lock` to ensure reproducible builds.

## Acceptance Criteria & Testing

The implementation MUST satisfy these testable acceptance criteria:

1. **Clean IP**: Given an IP not listed on any DNSBL, THEN no throttling occurs, no Jira
   issue is created, and no DB writes occur (idempotency).

2. **New Listing**: Given an IP becomes listed on at least one DNSBL, THEN:
   - `priority` changes to `LISTED_PRIORITY`
   - `oldPriority` stores the previous priority value exactly once
   - `blockingLists` contains comma-separated sorted zones
   - `lastEvent` matches pattern "new block from list(s) <zones>"
   - Exactly one open Jira issue exists for that IP (deduped via Jira search)

3. **List-Set Change**: Given an IP remains listed but the set of listing zones changes,
   THEN:
   - `blockingLists` updates deterministically
   - Jira does not create a new issue; adds comment with status update instead

4. **Clearing**: Given an IP becomes clean while currently throttled, THEN:
   - `priority` restores to `oldPriority` (or `CLEAN_FALLBACK_PRIORITY` if NULL)
   - `oldPriority` is set to NULL
   - `blockingLists` is cleared (empty string)
   - `lastEvent` matches "block removed" pattern
   - Jira issue is commented with status update but not duplicated

5. **Idempotency**: Re-running the job without state changes produces no additional Jira
   issues, no additional comments, and no DB writes.

6. **DNS Fault Tolerance**: Transient DNS failures (UNKNOWN) are logged and included in
   Jira descriptions but do not alone trigger throttling. Any DNS failure must be alerted via either Jira or Email to the operations team so that they can decide if they need to edit the DNSBL list.

## Governance

This constitution supersedes all other development practices for the Postal DNSBL Monitor
project. All code changes, pull requests, and design decisions MUST be verified for
compliance with the principles above.

**Amendment Procedure**:

1. Proposed amendments MUST be documented with rationale and impact analysis
2. Amendments require approval from project maintainers
3. Version number MUST be incremented per semantic versioning:
   - **MAJOR**: Backward-incompatible governance or principle removal/redefinition
   - **MINOR**: New principle added or materially expanded guidance
   - **PATCH**: Clarifications, wording, typo fixes, non-semantic refinements
4. All dependent templates and documentation MUST be updated before amendment is finalized

**Compliance Review**:

- All feature specifications MUST reference relevant principles
- All implementation plans MUST include a "Constitution Check" gate
- Code reviews MUST verify adherence to data integrity invariants, idempotency, and
  observability requirements

**Version**: 1.2.0 | **Ratified**: 2025-12-16 | **Last Amended**: 2025-12-17
