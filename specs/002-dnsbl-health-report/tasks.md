# Tasks: DNSBL Health Report

**Input**: Design documents from `/specs/002-dnsbl-health-report/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: This feature does NOT explicitly request tests. Contract/integration tests are included for quality assurance per quickstart.md.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root
- Paths shown assume existing postal-dnsbl-monitor structure

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and dependency updates

- [ ] T001 Add pyyaml>=6.0.1 to dependencies in pyproject.toml
- [ ] T002 [P] Add jsonschema>=4.17.0 to dev dependencies in pyproject.toml
- [ ] T003 Run uv sync to install new dependencies

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models and infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 [P] Create DNSBLHealthRecord model with computed properties (failure_rate, status) in src/models/dnsbl_health.py
- [ ] T005 [P] Create HealthSummary model with to_json() serialization in src/models/dnsbl_health.py
- [ ] T006 [P] Create NetworkConnectivityResult model with to_json() serialization in src/models/dnsbl_health.py
- [ ] T007 [P] Create PrunedConfiguration model with to_yaml() method in src/models/dnsbl_health.py
- [ ] T008 Add ENABLE_NETWORK_CONNECTIVITY_CHECK environment variable (default: true) to Config class in src/config.py
- [ ] T009 [P] Implement NetworkChecker.check_connectivity() with DNS queries to Cloudflare (1.1.1.1) and Google (8.8.8.8) in src/utils/network_check.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - View DNSBL Health Summary (Priority: P1) 🎯 MVP

**Goal**: Enable administrators to see a JSON health summary at the end of execution showing which DNSBLs failed and why

**Independent Test**: Run the monitor with a mix of working and non-working DNSBL endpoints, then verify the end-of-run JSON summary accurately lists all failed endpoints with failure reasons

### Contract Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T010 [P] [US1] Create contract test validating JSON output against health-summary-schema.json in tests/contract/test_health_output.py
- [ ] T011 [P] [US1] Create unit test for DNSBLHealthRecord failure_rate calculation in tests/unit/test_dnsbl_health.py

### Implementation for User Story 1

- [ ] T012 [US1] Implement HealthTracker class with __init__(dnsbl_zones) initializing one DNSBLHealthRecord per zone in src/services/health_tracker.py
- [ ] T013 [US1] Implement HealthTracker.record_check(zone, success, failure_type) updating counters in src/services/health_tracker.py
- [ ] T014 [US1] Implement HealthTracker.record_ip_check_start() incrementing total IP counter in src/services/health_tracker.py
- [ ] T015 [US1] Implement HealthTracker.get_summary(network_connectivity) calculating broken_dnsbls and network_issue_detected (50% threshold logic) in src/services/health_tracker.py
- [ ] T016 [US1] Implement HealthReporter.generate_json_report(summary) with sort_keys=True for deterministic output in src/services/health_reporter.py
- [ ] T017 [US1] Modify DNSChecker.__init__() to accept optional health_tracker parameter in src/services/dns_checker.py
- [ ] T018 [US1] Modify DNSChecker.check_ip() to call health_tracker.record_check() after each DNSBL query in src/services/dns_checker.py
- [ ] T019 [US1] Implement DNSChecker._categorize_failure() mapping DNS exceptions to failure types (timeout, nxdomain_zone, invalid_response_range, invalid_response_type) in src/services/dns_checker.py
- [ ] T020 [US1] Modify main() to initialize HealthTracker with config.dnsbl_zones in src/main.py
- [ ] T021 [US1] Modify main() to pass health_tracker to DNSChecker constructor in src/main.py
- [ ] T022 [US1] Modify main() to call health_tracker.record_ip_check_start() in IP checking loop in src/main.py
- [ ] T023 [US1] Add end-of-execution logic to call NetworkChecker.check_connectivity() if config.enable_network_connectivity_check is True in src/main.py
- [ ] T024 [US1] Add end-of-execution logic to call health_tracker.get_summary(network_result) in src/main.py
- [ ] T025 [US1] Add end-of-execution logic to call HealthReporter.generate_json_report(summary) and log via logger.info() with structured logging in src/main.py

### Integration Tests for User Story 1

- [ ] T026 [US1] Create integration test with mocked DNS responses (2 healthy, 2 broken DNSBLs) verifying JSON summary accuracy in tests/integration/test_health_tracking.py
- [ ] T027 [US1] Create integration test for network issue detection (50%+ failures + supplemental checks fail) in tests/integration/test_health_tracking.py

### Unit Tests for User Story 1

- [ ] T028 [P] [US1] Create unit test for HealthTracker.record_check() counter invariants in tests/unit/test_health_tracker.py
- [ ] T029 [P] [US1] Create unit test for HealthTracker.get_summary() network issue detection logic in tests/unit/test_health_tracker.py
- [ ] T030 [P] [US1] Create unit test for HealthReporter.generate_json_report() JSON format validation in tests/unit/test_health_reporter.py
- [ ] T031 [P] [US1] Create unit test for NetworkChecker.check_connectivity() with mocked DNS queries in tests/unit/test_network_check.py

**Checkpoint**: At this point, User Story 1 should be fully functional - administrators can view JSON health summary at end of execution

---

## Phase 4: User Story 2 - Generate Pruned DNSBL List (Priority: P2)

**Goal**: Enable administrators to get a YAML-formatted pruned DNSBL list excluding broken endpoints for easy configuration updates

**Independent Test**: Run the monitor with known broken DNSBLs, verify the suggested pruned list contains only working endpoints in YAML format matching DNSBL_LISTS structure

### Contract Tests for User Story 2

- [ ] T032 [P] [US2] Create contract test validating YAML output is parseable and matches config structure in tests/contract/test_health_output.py

### Implementation for User Story 2

- [ ] T033 [US2] Implement HealthReporter.generate_pruned_yaml(health_records) creating PrunedConfiguration and calling to_yaml() in src/services/health_reporter.py
- [ ] T034 [US2] Add end-of-execution logic to call HealthReporter.generate_pruned_yaml(summary.dnsbl_health) in src/main.py
- [ ] T035 [US2] Add end-of-execution logic to log YAML pruned list via logger.info() with multi-line string in src/main.py

### Integration Tests for User Story 2

- [ ] T036 [US2] Create integration test with 3 broken DNSBLs out of 15, verify YAML contains only 12 healthy zones in tests/integration/test_health_tracking.py
- [ ] T037 [US2] Create integration test with all DNSBLs healthy, verify YAML matches current config with "no changes needed" note in tests/integration/test_health_tracking.py

### Unit Tests for User Story 2

- [ ] T038 [P] [US2] Create unit test for PrunedConfiguration.to_yaml() YAML format validation in tests/unit/test_dnsbl_health.py
- [ ] T039 [P] [US2] Create unit test for HealthReporter.generate_pruned_yaml() healthy/broken zone separation in tests/unit/test_health_reporter.py

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently - administrators get both JSON summary and YAML pruned list

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T040 [P] Add docstrings to all new classes and methods following Google style
- [ ] T041 [P] Run ruff check . and fix any linting issues
- [ ] T042 Add validation for edge case: all DNSBLs fail (100% failure rate) - ensure warning logged and empty list NOT suggested in src/services/health_tracker.py
- [ ] T043 Add validation for edge case: exactly 50% DNSBLs fail - ensure supplemental checks used as tiebreaker in src/services/health_tracker.py
- [ ] T044 Add validation for DNSBL response format (A records in 127.0.0.0/8 or NXDOMAIN only) in src/services/dns_checker.py
- [ ] T045 [P] Verify execution overhead is <10% by adding duration tracking benchmark
- [ ] T046 [P] Verify health summary generation is <2 seconds per SC-006
- [ ] T047 Update .env.example with ENABLE_NETWORK_CONNECTIVITY_CHECK documentation
- [ ] T048 Update README.md with health reporting feature description
- [ ] T049 Run quickstart.md validation steps to ensure all implementation phases complete

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001-T003) completion - BLOCKS all user stories
- **User Stories (Phase 3-4)**: All depend on Foundational phase (T004-T009) completion
  - User Story 1 (Phase 3) can proceed after Foundational
  - User Story 2 (Phase 4) can proceed after Foundational (independent of US1)
- **Polish (Phase 5)**: Depends on both user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Foundational (T004-T009) - No dependencies on other stories
- **User Story 2 (P2)**: Depends on Foundational (T004-T009) - Technically independent but uses US1's HealthReporter, so sequential execution recommended

### Within Each User Story

- Contract tests (T010-T011, T032) MUST be written and FAIL before implementation
- Models (T004-T007) before services (T012-T016, T033)
- Services before integration points (T017-T025, T034-T035)
- Implementation before integration/unit tests (T026-T031, T036-T039)

### Parallel Opportunities

**Setup Phase**:
- T001 and T002 can run in parallel (different sections of pyproject.toml)

**Foundational Phase**:
- T004, T005, T006, T007 can run in parallel (same file, different classes/models)
- T009 can run in parallel with T004-T007 (different file)
- T008 depends on nothing, can run in parallel

**User Story 1**:
- T010 and T011 can run in parallel (different test files)
- T028, T029, T030, T031 can run in parallel (different test files)

**User Story 2**:
- T038 and T039 can run in parallel (different test files)

**Polish Phase**:
- T040, T041, T045, T046, T047 can run in parallel (different concerns)

---

## Parallel Example: Foundational Phase

```bash
# Launch all model creation tasks together:
Task: "Create DNSBLHealthRecord model in src/models/dnsbl_health.py"
Task: "Create HealthSummary model in src/models/dnsbl_health.py"
Task: "Create NetworkConnectivityResult model in src/models/dnsbl_health.py"
Task: "Create PrunedConfiguration model in src/models/dnsbl_health.py"

# Concurrently:
Task: "Implement NetworkChecker in src/utils/network_check.py"
Task: "Add ENABLE_NETWORK_CONNECTIVITY_CHECK to src/config.py"
```

## Parallel Example: User Story 1 Tests

```bash
# Launch all contract/unit tests for US1 together:
Task: "Contract test for JSON schema validation in tests/contract/test_health_output.py"
Task: "Unit test for DNSBLHealthRecord in tests/unit/test_dnsbl_health.py"
Task: "Unit test for HealthTracker in tests/unit/test_health_tracker.py"
Task: "Unit test for HealthReporter in tests/unit/test_health_reporter.py"
Task: "Unit test for NetworkChecker in tests/unit/test_network_check.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T009) - **CRITICAL - blocks all stories**
3. Complete Phase 3: User Story 1 (T010-T031)
4. **STOP and VALIDATE**: Test User Story 1 independently
   - Run monitor with mixed healthy/broken DNSBLs
   - Verify JSON health summary appears in logs
   - Verify network issue detection works with 50% threshold
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational (T001-T009) -> Foundation ready
2. Add User Story 1 (T010-T031) -> Test independently -> Deploy/Demo (MVP!)
   - **Value**: Administrators can now see which DNSBLs are broken
3. Add User Story 2 (T032-T039) -> Test independently -> Deploy/Demo
   - **Value**: Administrators get ready-to-use YAML configuration
4. Add Polish (T040-T049) -> Final validation -> Deploy

### Parallel Team Strategy

With 2 developers:

1. Both complete Setup + Foundational together (T001-T009)
2. Once Foundational is done:
   - Developer A: User Story 1 (T010-T031)
   - Developer B: User Story 2 (T032-T039) - can start contract tests while A works on implementation
3. Both handle Polish tasks (T040-T049) in parallel by concern

---

## Notes

- [P] tasks = different files or independent sections, no dependencies
- [US1]/[US2] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Contract tests written first ensure tests fail before implementing
- Commit after completing each task or logical group (e.g., all models in T004-T007)
- Stop at checkpoints to validate story independently
- Avoid: same file conflicts (coordinate on src/main.py tasks), cross-story dependencies

---

## Task Summary

**Total Tasks**: 49

**Task Count by Phase**:
- Setup: 3 tasks
- Foundational: 6 tasks
- User Story 1 (P1): 22 tasks
- User Story 2 (P2): 8 tasks
- Polish: 10 tasks

**Parallel Opportunities**:
- Setup: 2 tasks can run in parallel
- Foundational: 5 tasks can run in parallel
- User Story 1: 6 test tasks can run in parallel
- User Story 2: 2 test tasks can run in parallel
- Polish: 5 tasks can run in parallel

**MVP Scope**: User Story 1 only (32 tasks including Setup + Foundational + US1)

**Independent Test Criteria**:
- **US1**: Run with mixed DNSBLs → JSON summary shows broken zones with failure reasons
- **US2**: Run with broken DNSBLs → YAML pruned list excludes broken zones
