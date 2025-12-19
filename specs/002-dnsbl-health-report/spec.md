# Feature Specification: DNSBL Health Report

**Feature Branch**: `002-dnsbl-health-report`  
**Created**: 2025-12-19  
**Status**: Draft  
**Input**: User description: "I wish for the script to list all the unavailable or broken DNSBLs and a new suggested pruned-from-the-dead-endpoints list in the logs at the end of the execution so that one can change the DNSBL list to a less broken one"

## Clarifications

### Session 2025-12-19

- Q: What format should the health summary output use in the logs? -> A: Structured JSON output with fields for each DNSBL's health metrics, making it machine-parseable
- Q: What format should the suggested pruned DNSBL list use? -> A: YAML format matching the existing configuration file structure (DNSBL_LISTS in config)
- Q: How should the system distinguish "temporary network issues affecting all DNSBLs" from individual DNSBL failures? -> A: 50% threshold and optional (default:true, set by envvar) supplemental DNS calls to known cloud providers (Cloudflare, Google)
- Q: What constitutes "invalid or malformed data" from a DNSBL that should be treated as a failure? -> A: Any response other than valid DNS A record (127.x.x.x for listed) or NXDOMAIN (not listed)
- Q: When should health tracking data be collected for each DNSBL? -> A: Track success/failure for each individual IP check in real-time as it occurs

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View DNSBL Health Summary (Priority: P1)

As a system administrator running the postal-dnsbl-monitor, I want to see a summary at the end of execution showing which DNSBLs failed to respond or are unavailable, so I can identify problematic endpoints and take action.

**Why this priority**: This is the core value proposition - administrators need visibility into which DNSBLs are broken to maintain system health and reliability. Without this, they're operating blind to endpoint failures.

**Independent Test**: Can be fully tested by running the monitor with a mix of working and non-working DNSBL endpoints, then verifying that the end-of-run summary accurately lists all failed endpoints with appropriate failure reasons.

**Acceptance Scenarios**:

1. **Given** the monitor runs with 10 configured DNSBLs where 2 are unreachable, **When** the execution completes, **Then** the log displays a summary section listing the 2 failed DNSBLs with their failure reasons (e.g., timeout, DNS resolution failure, invalid response)

2. **Given** the monitor runs with all DNSBLs responding successfully, **When** the execution completes, **Then** the log displays a summary indicating all DNSBLs are healthy with zero failures

3. **Given** the monitor encounters network issues during execution, **When** 50% or more DNSBLs fail and supplemental DNS checks to cloud providers (Cloudflare, Google) also fail, **Then** the summary identifies this as a temporary network issue rather than marking individual DNSBLs as broken

---

### User Story 2 - Generate Pruned DNSBL List (Priority: P2)

As a system administrator, I want the system to automatically generate a suggested pruned DNSBL list excluding broken endpoints, so I can quickly update my configuration without manually editing it.

**Why this priority**: This adds automation value on top of the visibility from P1. While seeing broken endpoints is critical, having a ready-to-use pruned list saves manual work and reduces configuration errors.

**Independent Test**: Can be tested by running the monitor with known broken DNSBLs in the configuration, then verifying the suggested pruned list contains only working endpoints in a format ready for configuration updates.

**Acceptance Scenarios**:

1. **Given** the monitor identifies 3 broken DNSBLs out of 15 configured, **When** the execution completes, **Then** the log displays a suggested pruned list in YAML format containing only the 12 working DNSBLs matching the DNSBL_LISTS configuration structure

2. **Given** a DNSBL consistently fails across multiple check attempts during the run, **When** generating the pruned list, **Then** that DNSBL is excluded from the suggested configuration

3. **Given** all configured DNSBLs are working, **When** the execution completes, **Then** the suggested pruned list matches the current configuration with a note indicating no changes needed

---

### Edge Cases

- What happens when all DNSBLs fail (complete network outage)? The system should check supplemental DNS connectivity to cloud providers (Cloudflare, Google) and distinguish this scenario, avoiding recommending an empty DNSBL list
- What happens when exactly 50% of DNSBLs fail? The system should use supplemental DNS checks as a tiebreaker to determine if it's a network issue or individual DNSBL failures
- How does the system handle DNSBLs that respond but return invalid data? These should be flagged as broken - only valid DNS A records (127.x.x.x for listed) or NXDOMAIN (not listed) are acceptable responses
- What happens when a DNSBL endpoint changes format or response structure? The system should detect responses outside the valid set (A record in 127.x.x.x range or NXDOMAIN) as failures
- What happens when DNS resolution for the DNSBL zone itself fails? This should be clearly distinguished from blacklist lookup failures
- How should the system handle a DNSBL that works for some IPs but fails for others during the same run? The system should only mark it as broken if it fails for ALL IP checks (100% failure rate)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST track the success/failure status of each DNSBL endpoint in real-time for every individual IP check performed during execution
- **FR-002**: System MUST categorize DNSBL failures by type (e.g., DNS timeout, connection refused, invalid response format, DNS resolution failure)
- **FR-003**: System MUST display a health summary at the end of each execution as structured JSON output listing all DNSBLs with their health metrics (status, failure reasons, failure counts, total checks, failure rate)
- **FR-004**: System MUST classify a DNSBL as "broken" only if it fails to respond for 100% of IP checks performed during the execution
- **FR-005**: System MUST generate a suggested pruned DNSBL list containing only the endpoints that did not meet the "broken" threshold (i.e., responded successfully for at least one IP check)
- **FR-006**: System MUST format the pruned list as YAML matching the DNSBL_LISTS configuration structure for direct copy-paste replacement into the configuration file
- **FR-007**: System MUST distinguish between temporary network issues and individual DNSBL endpoint failures by checking if 50% or more of DNSBLs fail during execution
- **FR-007a**: System MUST support optional supplemental DNS connectivity checks to known cloud providers (Cloudflare, Google) to verify general network/DNS availability, enabled by default and configurable via environment variable
- **FR-008**: System MUST handle the scenario where all DNSBLs fail by warning the administrator rather than suggesting an empty list
- **FR-009**: System MUST validate DNSBL responses and treat as failures any response other than a valid DNS A record (127.x.x.x range for listed IPs) or NXDOMAIN (for not-listed IPs)

### Key Entities

- **DNSBL Health Record**: Represents the health status of a single DNSBL endpoint for a single IP check, including success/failure status, failure type, timestamp, and response time
- **DNSBL Execution Summary**: Aggregates all health records for a DNSBL across all IP checks in the current execution, including total checks performed, failure count, failure rate, and list of failure types encountered
- **Pruned Configuration**: Represents the suggested DNSBL list with broken endpoints (100% failure rate) removed, formatted for configuration file replacement

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Administrators can identify all broken DNSBL endpoints within 5 seconds of viewing the execution summary
- **SC-002**: Suggested pruned DNSBL lists can be applied to configuration files without manual editing or reformatting
- **SC-003**: Execution time increases by no more than 10% when adding health tracking and summary generation
- **SC-004**: Administrators can reduce configuration maintenance time by 70% compared to manually tracking DNSBL health
- **SC-005**: System correctly identifies DNSBLs with 100% failure rate as broken with zero false negatives
- **SC-006**: Health summary displays within 2 seconds after the last IP check completes
