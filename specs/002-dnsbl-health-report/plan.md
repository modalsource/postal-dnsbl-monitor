# Implementation Plan: DNSBL Health Report

**Branch**: `002-dnsbl-health-report` | **Date**: 2025-12-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-dnsbl-health-report/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Add end-of-execution health reporting for DNSBL endpoints. The system will track success/failure status for each DNSBL across all IP checks, output a structured JSON health summary, and generate a YAML-formatted pruned DNSBL list excluding completely broken endpoints (100% failure rate). Network issue detection uses a 50% failure threshold plus optional supplemental DNS checks to cloud providers (Cloudflare, Google) to distinguish widespread outages from individual DNSBL failures.

## Technical Context

**Language/Version**: Python 3.14  
**Primary Dependencies**: dnspython (DNS lookups), python-json-logger (structured logging), PyYAML (YAML generation)  
**Storage**: In-memory aggregation only (no persistent storage per Constitution Principle I)  
**Testing**: pytest with contract tests for JSON schema validation  
**Target Platform**: Kubernetes CronJob (Linux container)  
**Project Type**: Single project (extends existing postal-dnsbl-monitor)  
**Performance Goals**: <10% execution overhead, health summary generation <2 seconds  
**Constraints**: Stateless execution, idempotent, no local persistence  
**Scale/Scope**: Track health across 15-30 DNSBLs, 100-1000 IP checks per execution

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Initial Check (Pre-Research)

#### Principle I: Stateless Execution
✅ **COMPLIANT** - Health tracking uses in-memory aggregation only. No persistent state between runs. Each execution independently tracks DNSBL health and outputs results to logs.

#### Principle II: Kubernetes-Native Deployment
✅ **COMPLIANT** - No changes to deployment model. Feature runs within existing CronJob container, outputs to stdout/stderr (captured by Kubernetes logs).

#### Principle III: Data Integrity & Determinism
✅ **COMPLIANT** - No database writes. JSON output uses sorted keys for deterministic serialization. YAML pruned list uses sorted DNSBL names.

#### Principle IV: Jira Integration & Deduplication
✅ **COMPLIANT** - No Jira integration changes. Health reporting is log-only.

#### Principle V: DNS Reliability & Fault Tolerance
✅ **COMPLIANT** - Extends existing DNS failure categorization. Distinguishes LISTED/NOT_LISTED/UNKNOWN. Network issue detection (50% threshold + supplemental checks) aligns with "transient failures must not cause false positives" principle.

#### Principle VI: Idempotency
✅ **COMPLIANT** - Re-running with identical DNSBL responses produces identical JSON output (excluding timestamps). No side effects beyond logging.

#### Principle VII: Configuration as Code
✅ **COMPLIANT** - Adds one optional environment variable: `ENABLE_NETWORK_CONNECTIVITY_CHECK` (default: true). Supplemental DNS targets (Cloudflare 1.1.1.1, Google 8.8.8.8) are hardcoded as infrastructure constants (justified: universally stable public resolvers).

#### Principle VIII: Observability
✅ **COMPLIANT** - Outputs structured JSON health summary. No changes to existing per-IP structured logging. Health summary is machine-parseable and suitable for centralized monitoring.

---

### Post-Design Check (After Phase 1)

**Status**: ✅ **ALL PRINCIPLES REMAIN COMPLIANT**

**Design Validation**:

1. **Stateless Execution Verified**: 
   - `HealthTracker` class uses in-memory dictionaries only
   - No file I/O except stdout (logs)
   - All data structures (DNSBLHealthRecord, HealthSummary) are ephemeral

2. **Determinism Verified**:
   - JSON serialization uses `sort_keys=True` in `HealthReporter.generate_json_report()`
   - YAML uses `sorted(healthy_zones)` in `PrunedConfiguration.to_yaml()`
   - `dnsbl_health` array sorted by zone name in `HealthSummary.to_json()`

3. **Idempotency Verified**:
   - Same DNSBL responses → same `DNSBLHealthRecord` counters
   - Same counters → same JSON/YAML output (timestamps excluded from comparison)
   - No external state mutations

4. **Observability Enhanced**:
   - JSON schema defined in `contracts/health-summary-schema.json`
   - Structured logging via existing `python-json-logger`
   - Contract tests validate schema compliance

**New Dependencies Justified**:
- **pyyaml>=6.0.1**: Required for FR-006 (YAML pruned list generation). Standard library, secure, minimal footprint.
- **jsonschema>=4.17.0** (dev only): Required for contract tests validating JSON schema compliance.

**No Constitution Violations Introduced**.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── models/
│   ├── dns_result.py          # Existing - DNS check results
│   └── dnsbl_health.py         # NEW - Health tracking models
├── services/
│   ├── dns_checker.py          # MODIFIED - Add health tracking hooks
│   ├── health_tracker.py       # NEW - DNSBL health aggregation
│   └── health_reporter.py      # NEW - JSON/YAML output generation
├── utils/
│   └── network_check.py        # NEW - Supplemental DNS connectivity
└── main.py                     # MODIFIED - Integrate health reporting

tests/
├── contract/
│   └── test_health_output.py  # NEW - Validate JSON schema
├── integration/
│   └── test_health_tracking.py # NEW - End-to-end health reporting
└── unit/
    ├── test_health_tracker.py  # NEW - Aggregation logic
    ├── test_health_reporter.py # NEW - Output formatting
    └── test_network_check.py   # NEW - Supplemental DNS checks
```

**Structure Decision**: Single project structure (existing postal-dnsbl-monitor). Health reporting is integrated as additional modules within the existing `src/` hierarchy. No new top-level directories required.

## Complexity Tracking

> **No violations detected. This section intentionally left empty per constitution compliance.**

---

## Phase 0: Research (COMPLETED)

**Status**: ✅ Complete  
**Output**: [research.md](./research.md)

All technical unknowns resolved:
- JSON output structure designed (nested object with execution_summary + dnsbl_health array)
- YAML pruned list format defined (matches DNSBL_ZONES config structure)
- Network issue detection strategy (50% threshold + supplemental DNS checks)
- Invalid response validation (A records in 127.0.0.0/8 only)
- Health tracking architecture (real-time per-check with in-memory aggregator)
- Dependencies selected (pyyaml>=6.0.1, jsonschema>=4.17.0 dev-only)
- Performance optimization strategy (<10% overhead, lazy evaluation)
- Configuration approach (ENABLE_NETWORK_CONNECTIVITY_CHECK env var)

---

## Phase 1: Design & Contracts (COMPLETED)

**Status**: ✅ Complete  
**Outputs**:
- [data-model.md](./data-model.md) - Entity definitions and service interfaces
- [contracts/health-summary-schema.json](./contracts/health-summary-schema.json) - JSON schema for validation
- [quickstart.md](./quickstart.md) - Developer implementation guide
- [AGENTS.md](/home/fulgidus/Documenti/postal-dnsbl-monitor/AGENTS.md) - Updated agent context

**Design Artifacts**:

1. **Data Models**:
   - `DNSBLHealthRecord`: Per-DNSBL health metrics aggregator
   - `HealthSummary`: Top-level execution summary with all DNSBL health data
   - `NetworkConnectivityResult`: Supplemental DNS check results
   - `PrunedConfiguration`: YAML-formatted pruned list generator

2. **Services**:
   - `HealthTracker`: Real-time health data aggregation
   - `HealthReporter`: JSON/YAML output generation
   - `NetworkChecker`: Supplemental DNS connectivity verification

3. **Contracts**:
   - JSON Schema (contracts/health-summary-schema.json) defines strict validation for health summary output
   - YAML format follows existing DNSBL_ZONES configuration structure

4. **Integration Points**:
   - `src/config.py`: Add ENABLE_NETWORK_CONNECTIVITY_CHECK env var
   - `src/services/dns_checker.py`: Add health_tracker callback hooks
   - `src/main.py`: Integrate health reporting at end of execution

**Constitution Re-Check**: ✅ All principles remain compliant post-design

---

## Phase 2: Task Breakdown (PENDING)

**Status**: ⏳ Awaiting `/speckit.tasks` command

This phase is **NOT** part of the `/speckit.plan` command scope. Tasks will be generated separately via `/speckit.tasks` after plan approval.

**Expected Output**: `tasks.md` with granular implementation tasks, test requirements, and acceptance criteria.
