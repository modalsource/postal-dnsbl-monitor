# Tasks: Postal DNSBL Monitor

**Input**: Design documents from `/specs/001-postal-dnsbl-monitor/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅  
**Generated**: 2025-12-17

**Tests**: This specification includes comprehensive testing requirements per Constitutional Principles. All contract tests are mandatory to verify idempotency, deduplication, and invariants.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `- [ ] [ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Single-project CLI batch job structure (per plan.md):
- Source: `src/` at repository root
- Tests: `tests/` at repository root
- Kubernetes: `kubernetes/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependency management, and basic structure

- [ ] T001 Create project directory structure with src/, tests/, kubernetes/ directories
- [ ] T002 Initialize Python 3.14 project with pyproject.toml per research.md section 6
- [ ] T003 [P] Configure uv dependency management with uv.lock for dnspython, jira, psycopg2-binary, python-json-logger
- [ ] T004 [P] Create .gitignore with Python, IDE, and Kubernetes-specific exclusions
- [ ] T005 [P] Create .dockerignore for multi-stage Docker build optimization
- [ ] T006 [P] Create README.md with project overview and quickstart reference link
- [ ] T007 [P] Create src/__init__.py as package marker
- [ ] T008 [P] Create tests/__init__.py as test package marker

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Configuration and Logging Foundation

- [ ] T009 Create src/config.py to load and validate environment variables per contracts/config-schema.yaml
- [ ] T010 [P] Create src/services/logger.py for structured JSON logging per contracts/log-format.json and research.md section 4
- [ ] T011 [P] Create src/utils/__init__.py as utils package marker
- [ ] T012 [P] Create src/utils/ip_utils.py with IPv4 validation and reverse DNS formatting per research.md section 1
- [ ] T013 [P] Create src/utils/retry.py with exponential backoff decorator (2s, 4s, 8s) per research.md section 2, including unit test verifying retry timing matches spec clarification

### Data Models Foundation

- [ ] T014 Create src/models/__init__.py as models package marker
- [ ] T015 [P] Create src/models/dns_result.py with DNSStatus enum (LISTED/NOT_LISTED/UNKNOWN) per data-model.md section 2
- [ ] T016 [P] Create src/models/ip_record.py with IP Address Record dataclass per data-model.md section 1

### Services Foundation

- [ ] T017 Create src/services/__init__.py as services package marker
- [ ] T018 Create src/services/database.py with PostgreSQL connection, context manager, READ COMMITTED isolation per research.md section 3
- [ ] T019 Create src/services/dns_checker.py with dnspython + ThreadPoolExecutor for concurrent DNSBL queries per research.md section 1
- [ ] T020 Create src/services/jira_client.py with JQL search, issue create/update, exponential backoff per research.md section 2

### Testing Infrastructure

- [ ] T021 Create tests/conftest.py with pytest fixtures for PostgreSQL (testcontainers), Jira mocking, DNS mocking per research.md section 7
- [ ] T022 [P] Create tests/unit/__init__.py as unit test package marker
- [ ] T023 [P] Create tests/integration/__init__.py as integration test package marker
- [ ] T024 [P] Create tests/contract/__init__.py as contract test package marker

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Automated Email Deliverability Protection (Priority: P1) 🎯 MVP

**Goal**: Automatically detect DNSBL listings, throttle affected IPs, create Jira tickets, and ensure idempotency

**Independent Test**: Insert known-listed IP, run job, verify priority throttled, blockingLists populated, single Jira ticket created, re-run produces no duplicates

### Contract Tests for User Story 1 (MANDATORY for Constitutional Compliance)

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T025 [P] [US1] Contract test for oldPriority single-write invariant in tests/contract/test_invariants.py per data-model.md section "Data Integrity Verification"
- [ ] T026 [P] [US1] Contract test for blockingLists deterministic sorting in tests/contract/test_invariants.py per FR-014
- [ ] T027 [P] [US1] Contract test for idempotency (re-run with same state = zero writes) in tests/contract/test_idempotency.py per FR-032
- [ ] T028 [P] [US1] Contract test for Jira deduplication via JQL search in tests/contract/test_deduplication.py per FR-020

### Unit Tests for User Story 1

- [ ] T029 [P] [US1] Unit test for config validation in tests/unit/test_config.py with mock environment variables, including JIRA_DNS_FAILURE_ISSUE_TYPE per FR-013a
- [ ] T030 [P] [US1] Unit test for IP reverse DNS formatting in tests/unit/test_ip_utils.py per data-model.md section 2
- [ ] T031 [P] [US1] Unit test for DNS classification logic (LISTED/NOT_LISTED/UNKNOWN) in tests/unit/test_dns_result.py per FR-009
- [ ] T032 [P] [US1] Unit test for state transition logic (clean→listed, listed→clean) in tests/unit/test_state_transition.py per data-model.md section "State Transition Rules"

### Integration Tests for User Story 1

- [ ] T033 [US1] Integration test for database UPDATE idempotency in tests/integration/test_database.py using testcontainers per research.md section 7
- [ ] T034 [US1] Integration test for Jira issue create/search roundtrip in tests/integration/test_jira_client.py with responses library mocking per research.md section 2

### Implementation for User Story 1

- [ ] T035 [US1] Implement get_all_ips() in src/services/database.py to query postal.ip_addresses table per FR-006
- [ ] T036 [US1] Implement update_ip_listed() with idempotent conditional UPDATE in src/services/database.py per FR-015 clean→listed transition
- [ ] T037 [US1] Implement update_ip_clean() with oldPriority restoration in src/services/database.py per FR-015 listed→clean transition
- [ ] T038 [US1] Implement update_ip_zone_change() for listed→listed transitions in src/services/database.py per FR-015
- [ ] T039 [US1] Implement check_dnsbl() for single IP-zone query in src/services/dns_checker.py per research.md section 1
- [ ] T040 [US1] Implement check_ip_concurrent() with ThreadPoolExecutor in src/services/dns_checker.py per FR-011
- [ ] T041 [US1] Implement find_open_issue_for_ip() with JQL search in src/services/jira_client.py per FR-021
- [ ] T042 [US1] Implement create_issue() with deterministic summary format in src/services/jira_client.py per FR-022
- [ ] T043 [US1] Implement add_comment() for issue updates in src/services/jira_client.py per FR-024
- [ ] T044 [US1] Create src/models/state_transition.py with state transition decision logic per data-model.md section 3
- [ ] T045 [US1] Implement main execution loop in src/main.py orchestrating database fetch, DNS checks, state transitions, Jira actions per FR-001
- [ ] T046 [US1] Add per-IP structured logging in src/main.py per FR-028 and contracts/log-format.json
- [ ] T047 [US1] Add job summary logging in src/main.py per FR-031
- [ ] T048 [US1] Implement DRY_RUN mode logic in src/main.py per FR-003
- [ ] T049 [US1] Implement fatal error handling (database unreachable, Jira auth failure) with exit code 1 in src/main.py per FR-004, FR-030

**Checkpoint**: At this point, User Story 1 should be fully functional - IPs can be throttled, tickets created, idempotency verified

---

## Phase 4: User Story 2 - Multi-Blacklist Tracking and Change Detection (Priority: P2)

**Goal**: Track multiple DNSBL listings per IP, detect zone membership changes, update Jira without duplicates

**Independent Test**: Simulate IP listed on multiple zones, verify blockingLists contains sorted zones, change listing set, confirm Jira comment added (not new ticket)

### Integration Tests for User Story 2

- [ ] T050 [P] [US2] Integration test for multi-zone listing scenario in tests/integration/test_multi_zone.py verifying sorted blockingLists
- [ ] T051 [P] [US2] Integration test for zone-set change (add zone) in tests/integration/test_zone_change.py verifying Jira comment, not new issue

### Implementation for User Story 2

- [ ] T052 [US2] Enhance aggregate_dns_results() in src/models/state_transition.py to detect zone-set changes (added/removed zones) per data-model.md section "State Transition Event"
- [ ] T053 [US2] Implement detect_zone_delta() helper in src/models/state_transition.py to calculate added/removed zones
- [ ] T054 [US2] Update main loop in src/main.py to call update_ip_zone_change() when zone set changes while listed
- [ ] T055 [US2] Update Jira comment logic in src/services/jira_client.py to describe zone membership changes per FR-024
- [ ] T056 [US2] Add zone-change-specific logging in src/main.py per contracts/log-format.json
- [ ] T057 [US2] Update unit tests in tests/unit/test_state_transition.py to cover multi-zone and zone-change scenarios

**Checkpoint**: At this point, User Stories 1 AND 2 should both work - single and multiple zone listings, with change tracking

---

## Phase 5: User Story 3 - DNS Fault Tolerance and Operational Visibility (Priority: P3)

**Goal**: Distinguish DNS failures (UNKNOWN) from definitive results, log failures, alert on systemic DNS issues (>50% UNKNOWN)

**Independent Test**: Simulate DNS timeouts, verify UNKNOWN classification, confirm IPs not throttled/cleared based on UNKNOWN, validate MAJOR MALFUNCTION Jira issue when >50% zones fail

### Integration Tests for User Story 3

- [ ] T058 [P] [US3] Integration test for DNS timeout handling in tests/integration/test_dns_timeout.py verifying UNKNOWN classification
- [ ] T059 [P] [US3] Integration test for MAJOR MALFUNCTION alert in tests/integration/test_dns_failure_alert.py when >50% zones return UNKNOWN per FR-013a

### Implementation for User Story 3

- [ ] T060 [US3] Enhance check_dnsbl() in src/services/dns_checker.py to handle Timeout, SERVFAIL, NoAnswer exceptions as UNKNOWN per FR-009
- [ ] T061 [US3] Implement calculate_unknown_percentage() in src/main.py to track UNKNOWN rate across all zones
- [ ] T062 [US3] Implement create_dns_failure_issue() in src/services/jira_client.py with MAJOR MALFUNCTION label per FR-013a and data-model.md section 5
- [ ] T063 [US3] Add DNS failure detection logic in src/main.py to create alert when >50% zones UNKNOWN
- [ ] T064 [US3] Implement DNS failure deduplication (search for same-day DNS failure issues) in src/services/jira_client.py per data-model.md section 5
- [ ] T065 [US3] Add dns_failure_log entries in src/services/logger.py per contracts/log-format.json section "dns_failure_log"
- [ ] T066 [US3] Update main loop in src/main.py to log UNKNOWN zones per FR-013, FR-029
- [ ] T067 [US3] Add UNKNOWN zone tracking to per-IP logs in src/main.py per contracts/log-format.json
- [ ] T068 [US3] Update unit tests in tests/unit/test_dns_result.py to cover all UNKNOWN error types

**Checkpoint**: All user stories should now be independently functional - listings, multi-zone tracking, DNS fault tolerance

---

## Phase 6: Deployment & Infrastructure (Kubernetes CronJob)

**Purpose**: Containerization, Kubernetes manifests, deployment readiness

### Docker Build

- [ ] T069 [P] Create Dockerfile with multi-stage build (builder + runtime) per research.md section 6
- [ ] T070 [P] Add uv installation and uv sync --frozen in builder stage per research.md section 6
- [ ] T071 [P] Configure non-root user (UID 1000) in runtime stage for security per research.md section 6
- [ ] T072 Test Docker build locally with docker build -t postal-dnsbl-monitor:latest .
- [ ] T073 Test Docker run locally with --env-file .env per quickstart.md section "Docker Build"

### Kubernetes Manifests

- [ ] T074 [P] Create kubernetes/configmap.yaml from contracts/config-schema.yaml template with DNSBL zones, priorities, Jira config
- [ ] T075 [P] Create kubernetes/secret.yaml template for DB_PASSWORD and JIRA_API_TOKEN per contracts/config-schema.yaml
- [ ] T076 Create kubernetes/cronjob.yaml with schedule, resource limits (250m CPU / 256Mi requests, 500m / 512Mi limits), restartPolicy per research.md section 5
- [ ] T077 Configure concurrencyPolicy: Forbid in kubernetes/cronjob.yaml to prevent overlapping executions
- [ ] T078 Add envFrom ConfigMap and Secret references in kubernetes/cronjob.yaml per research.md section 5

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories, final validation

### Documentation

- [ ] T079 [P] Verify README.md includes quickstart link and project summary
- [ ] T080 [P] Add inline code comments for complex state transition logic in src/models/state_transition.py
- [ ] T081 [P] Add docstrings to all public functions in src/services/ modules

### Testing and Validation

- [ ] T082 Run full test suite with pytest tests/ -v --cov=src --cov-report=term-missing
- [ ] T083 Validate contract tests pass (idempotency, deduplication, invariants) per Constitutional Principles
- [ ] T084 Run quickstart.md local development setup validation
- [ ] T085 Test DRY_RUN mode end-to-end per quickstart.md section "Troubleshooting"
- [ ] T086 Validate structured logs match contracts/log-format.json schema

### Performance and Resource Validation

- [ ] T087 Test job execution time with 1000 IPs × 10 zones (must complete <5min per SC-002)
- [ ] T088 Validate memory usage stays within 512Mi limit under load per SC-008a
- [ ] T088a Verify no OOMKills or CPU throttling during load test by inspecting Kubernetes pod events and metrics per SC-008a
- [ ] T089 Verify DNS concurrency parameter (default 10 workers) per FR-011

### Security Hardening

- [ ] T090 [P] Verify Dockerfile runs as non-root user
- [ ] T091 [P] Validate Secret values are not logged (mask DB_PASSWORD, JIRA_API_TOKEN in logs)
- [ ] T092 [P] Ensure no hardcoded credentials in source code per Constitutional Principle VII

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - User Story 1 (P1): Can start after Foundational - MVP target
  - User Story 2 (P2): Can start after Foundational - Builds on US1 patterns but independently testable
  - User Story 3 (P3): Can start after Foundational - Adds fault tolerance, independently testable
- **Deployment (Phase 6)**: Depends on at least User Story 1 completion (MVP), ideally all stories
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Reuses US1 database/Jira services but adds zone-change logic
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Extends US1 DNS checker with fault tolerance

### Within Each User Story

- Contract tests MUST be written and FAIL before implementation (TDD for constitutional compliance)
- Models before services
- Services before main orchestration
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

#### Phase 1 (Setup)
- T003 (uv config), T004 (.gitignore), T005 (.dockerignore), T006 (README), T007 (src/__init__), T008 (tests/__init__) can run in parallel

#### Phase 2 (Foundational)
- T010 (logger), T011 (utils/__init__), T012 (ip_utils), T013 (retry) can run in parallel after T009 (config)
- T015 (dns_result), T016 (ip_record) can run in parallel after T014 (models/__init__)
- T022 (unit/__init__), T023 (integration/__init__), T024 (contract/__init__) can run in parallel

#### Phase 3 (User Story 1)
- All contract tests T025-T028 can run in parallel (different files)
- All unit tests T029-T032 can run in parallel (different files)
- Database methods T035-T038 can be developed in parallel within src/services/database.py
- DNS checker methods T039-T040 can be developed in parallel within src/services/dns_checker.py

#### Phase 4 (User Story 2)
- Integration tests T050-T051 can run in parallel (different files)

#### Phase 5 (User Story 3)
- Integration tests T058-T059 can run in parallel (different files)

#### Phase 6 (Deployment)
- Dockerfile stages T069-T071 can be developed in parallel
- Kubernetes manifests T074-T075 can be created in parallel

#### Phase 7 (Polish)
- Documentation tasks T079-T081 can run in parallel
- Security validation T090-T092 can run in parallel

---

## Parallel Example: User Story 1 Contract Tests

```bash
# Launch all contract tests for User Story 1 together:
# These tests MUST fail before implementation starts

Task T025: "Contract test for oldPriority single-write invariant in tests/contract/test_invariants.py"
Task T026: "Contract test for blockingLists deterministic sorting in tests/contract/test_invariants.py"
Task T027: "Contract test for idempotency in tests/contract/test_idempotency.py"
Task T028: "Contract test for Jira deduplication in tests/contract/test_deduplication.py"

# Expected outcome: All 4 tests FAIL (functions not implemented yet)
# Then proceed with implementation tasks T035-T049
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T008)
2. Complete Phase 2: Foundational (T009-T024) - **CRITICAL BLOCKER**
3. Complete Phase 3: User Story 1 (T025-T049)
   - Write contract tests FIRST (T025-T028), ensure they FAIL
   - Implement foundation (T035-T043)
   - Build main orchestration (T044-T049)
   - Verify contract tests now PASS
4. **STOP and VALIDATE**: Test User Story 1 independently per spec.md acceptance scenarios 1-4
5. Complete Phase 6: Deployment (T069-T078) for MVP deployment
6. Deploy/demo MVP

### Incremental Delivery

1. **Foundation**: Complete Setup (Phase 1) + Foundational (Phase 2) → T001-T024 complete
2. **MVP Deployment**: Add User Story 1 (Phase 3) → T025-T049 complete → Test independently → Deploy (MVP!)
3. **Multi-Zone Tracking**: Add User Story 2 (Phase 4) → T050-T057 complete → Test independently → Deploy
4. **Fault Tolerance**: Add User Story 3 (Phase 5) → T058-T068 complete → Test independently → Deploy
5. **Final Polish**: Complete Phase 7 → T079-T092 complete → Production-ready

Each story adds value without breaking previous stories.

### Parallel Team Strategy

With multiple developers:

1. **Week 1**: Team completes Setup (Phase 1) + Foundational (Phase 2) together (T001-T024)
2. **Week 2-3**: Once Foundational is done:
   - **Developer A**: User Story 1 (T025-T049) - MVP focus
   - **Developer B**: User Story 2 (T050-T057) - Starts in parallel, may wait for US1 patterns
   - **Developer C**: User Story 3 (T058-T068) - Starts in parallel, may wait for US1 patterns
3. **Week 4**: Team completes Deployment (Phase 6) together (T069-T078)
4. **Week 5**: Team completes Polish (Phase 7) together (T079-T092)

Stories complete and integrate independently.

---

## Task Summary

**Total Tasks**: 92  
**By Phase**:
- Phase 1 (Setup): 8 tasks
- Phase 2 (Foundational): 16 tasks (BLOCKING)
- Phase 3 (User Story 1 - P1): 25 tasks (MVP)
- Phase 4 (User Story 2 - P2): 8 tasks
- Phase 5 (User Story 3 - P3): 11 tasks
- Phase 6 (Deployment): 10 tasks
- Phase 7 (Polish): 14 tasks

**Parallel Opportunities**: 35+ tasks marked [P] can run in parallel within their phase

**Independent Test Criteria**:
- **US1**: Insert test IP → Run job → Verify throttled + Jira ticket → Re-run → Verify idempotency (no duplicates)
- **US2**: Simulate multi-zone listing → Verify sorted blockingLists → Change zones → Verify Jira comment (not new ticket)
- **US3**: Simulate DNS timeouts → Verify UNKNOWN classification → Trigger >50% failure → Verify MAJOR MALFUNCTION alert

**Suggested MVP Scope**: Phase 1 + Phase 2 + Phase 3 (User Story 1) + Phase 6 (Deployment) = 59 tasks

---

## Notes

- **[P] tasks** = different files, no dependencies within phase
- **[Story] label** maps task to specific user story for traceability
- Each user story should be independently completable and testable per spec.md acceptance scenarios
- Contract tests are MANDATORY (Constitutional Principles III, IV, VI) - write tests FIRST, ensure FAIL, then implement
- Verify contract tests PASS before considering phase complete
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- DRY_RUN mode useful for testing without side effects
- Constitution compliance verified via contract tests (T025-T028, T083)
