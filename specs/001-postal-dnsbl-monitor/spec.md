# Feature Specification: Postal DNSBL Monitor

**Feature Branch**: `001-postal-dnsbl-monitor`  
**Created**: 2025-12-17  
**Status**: Draft  
**Constitution Version**: 1.2.0  
**Input**: User description: "Define the full technical specification for the Postal DNSBL Monitor system in strict compliance with the current constitution (version 1.2.0). The specification must describe a stateless, containerized Python 3.14 application designed to run as a Kubernetes CronJob. The system periodically checks IPv4 addresses stored in the MySQL table postal.ip_addresses against a configurable set of DNSBL providers using dnspython, classifying results as LISTED, NOT_LISTED, or UNKNOWN according to DNS semantics."

## Clarifications

### Session 2025-12-17

- Q: What are the specific retry parameters for Jira API transient failures? -> A: 3 retries with exponential backoff (2s, 4s, 8s intervals)
- Q: Which alerting mechanism should be used for widespread DNS failures? -> A: Create Jira issue with DNS failure issue type when >50% of zones fail (labeled "MAJOR MALFUNCTION" with detailed explanation and logs)
- Q: What specific MySQL transaction isolation level should be used? -> A: READ COMMITTED (MySQL default)
- Q: What are the recommended Kubernetes resource requests and limits? -> A: Requests: 250m CPU / 256Mi memory, Limits: 500m CPU / 512Mi memory
- Q: Should the entire JQL query template be configurable or just specific parts? -> A: Configurable project and status, fixed summary pattern

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automated Email Deliverability Protection (Priority: P1)

Operations teams need to ensure email servers remain deliverable by detecting and responding to DNSBL listings before they impact email delivery rates. When an IP address becomes listed on any DNS-based blacklist, the system must automatically detect the listing, reduce the IP's priority to protect sender reputation, and create a tracking ticket so operations can investigate and remediate.

**Why this priority**: This is the core value proposition - preventing email delivery failures and protecting sender reputation is critical to the business. Without this capability, blacklisted IPs continue sending mail, damaging reputation and causing delivery failures.

**Independent Test**: Can be fully tested by inserting a known-listed IP into the database, running the job, and verifying: (1) priority is set to throttled state, (2) blocking lists are recorded, (3) a single Jira ticket is created, and (4) subsequent runs do not create duplicate tickets.

**Acceptance Scenarios**:

1. **Given** an IP address exists in postal.ip_addresses with priority=50 and is not listed on any DNSBL, **When** the monitor job runs, **Then** the IP remains at priority=50, no database changes occur, and no Jira ticket is created.

2. **Given** an IP address with priority=50 becomes newly listed on zen.spamhaus.org, **When** the monitor job runs, **Then** priority changes to LISTED_PRIORITY (e.g., 0), oldPriority is set to 50 (exactly once), blockingLists contains "zen.spamhaus.org", lastEvent describes the new listing, and exactly one Jira ticket is created with summary "IP 203.0.113.45 blacklisted by zen.spamhaus.org".

3. **Given** an IP is already listed (priority=0, oldPriority=50, blockingLists="zen.spamhaus.org"), **When** the monitor job runs and finds the same listing state, **Then** no database writes occur and no new Jira tickets or comments are created (idempotency).

4. **Given** an IP is listed on zen.spamhaus.org, **When** it becomes clean (no longer listed), **Then** priority is restored to oldPriority (50), oldPriority is set to NULL, blockingLists is cleared, lastEvent describes block removal, and the existing Jira ticket receives a comment indicating the IP is now clean.

---

### User Story 2 - Multi-Blacklist Tracking and Change Detection (Priority: P2)

When an IP is listed on multiple DNSBLs or the set of listing blacklists changes, operations teams need to track which specific blacklists have flagged the IP and be notified when the listing landscape changes, enabling targeted remediation efforts.

**Why this priority**: Understanding which blacklists flag an IP helps operations prioritize remediation (e.g., Spamhaus listings are more critical than minor DNSBLs). This builds on P1 by adding visibility into complex listing scenarios.

**Independent Test**: Can be tested by simulating an IP listed on multiple DNSBLs, verifying blockingLists contains all zones in sorted order, and then changing the listing set to confirm the Jira ticket is updated with a comment (not a new ticket).

**Acceptance Scenarios**:

1. **Given** an IP becomes listed on both zen.spamhaus.org and bl.spamcop.net simultaneously, **When** the monitor job runs, **Then** blockingLists contains "bl.spamcop.net,zen.spamhaus.org" (sorted, comma-separated), the Jira summary includes both zones, and exactly one ticket is created.

2. **Given** an IP is listed with blockingLists="zen.spamhaus.org", **When** it becomes additionally listed on bl.spamcop.net (now listed on two zones), **Then** blockingLists updates to "bl.spamcop.net,zen.spamhaus.org", lastEvent describes the list-set change, and the existing Jira ticket receives a comment indicating the new listing (no new ticket created).

3. **Given** an IP is listed on two zones and one zone clears while the other remains, **When** the monitor job runs, **Then** blockingLists updates to reflect only the remaining zone, lastEvent describes the change, and the existing Jira ticket is updated with a comment (not closed, since IP is still listed).

---

### User Story 3 - DNS Fault Tolerance and Operational Visibility (Priority: P3)

When DNS queries to DNSBL providers fail due to network issues, timeouts, or provider outages, operations teams need to distinguish between definitive "not listed" results and transient DNS failures. The system must log these failures and alert operations without falsely clearing or throttling IPs based on incomplete data.

**Why this priority**: DNS is inherently unreliable. This scenario ensures the system degrades gracefully and provides visibility into DNS infrastructure health without causing false positives or negatives. It's lower priority because it handles edge cases rather than core functionality.

**Independent Test**: Can be tested by simulating DNS timeouts (e.g., pointing at a non-responsive DNS server), verifying UNKNOWN results are logged, and confirming IPs are not throttled or cleared based solely on UNKNOWN responses. Operations teams should receive alerts about DNS failures.

**Acceptance Scenarios**:

1. **Given** a DNS query to a DNSBL zone times out, **When** the monitor job runs, **Then** the query result is classified as UNKNOWN, the zone is logged as failed, and the IP's listing status is determined only by zones that returned definitive results (LISTED or NOT_LISTED).

2. **Given** all DNS queries for an IP return UNKNOWN (complete DNS failure), **When** the monitor job runs, **Then** no database changes occur for that IP, the failure is logged with structured data, and if more than 50% of configured DNSBL zones return UNKNOWN, a Jira issue is created with issue type for DNS failures, labeled "MAJOR MALFUNCTION", containing detailed explanation and execution logs up to that point.

3. **Given** an IP is currently listed and a subsequent job run returns UNKNOWN for all zones, **When** the monitor job runs, **Then** the IP remains listed (no change to priority/oldPriority/blockingLists), and the uncertainty is logged for operational review.

---

### Edge Cases

- **What happens when oldPriority is NULL during clearing?** System restores to CLEAN_FALLBACK_PRIORITY (configurable, e.g., 50) instead of oldPriority.

- **What happens when DNS returns non-standard responses (e.g., CNAME, SERVFAIL)?** These are classified as UNKNOWN and treated as transient failures - logged but not used for throttling decisions. If more than 50% of configured zones return UNKNOWN across the job run, a Jira issue labeled "MAJOR MALFUNCTION" is created to alert operations of potential systemic DNS infrastructure issues.

- **What happens when Jira API is unreachable?** This is a fatal error - the job exits with non-zero exit code, Kubernetes will retry per the CronJob restart policy, and operators are alerted via Kubernetes monitoring.

- **What happens when the database is unreachable?** Fatal error, job exits non-zero, no partial updates occur (all updates within a transaction or clear failure boundary).

- **What happens when an IP is manually removed from the database between job runs?** No impact - the job operates only on IPs present at runtime. If the IP is re-added later, it is treated as a new IP.

- **What happens when DRY_RUN mode is enabled?** The job performs all DNS checks and logic but does not write to the database or create Jira tickets. All actions are logged as "would execute" for testing/validation purposes.

- **What happens when the same IP has multiple concurrent job executions?** Database transactions ensure consistency. The last-committed job run wins. Jira deduplication via JQL search prevents duplicate tickets regardless of execution order.

## Requirements *(mandatory)*

### Functional Requirements

#### Execution and Lifecycle

- **FR-001**: System MUST execute as a stateless, one-shot process suitable for Kubernetes CronJob deployment with no assumptions about local persistent storage or process continuity.

- **FR-002**: System MUST read all configuration exclusively from environment variables or mounted configuration files, including database connection parameters, DNSBL zone list, DNS timeouts, concurrency limits, priority values, Jira credentials (server, user, API token, project, issue types, excluded statuses for JQL queries), and DRY_RUN mode.

- **FR-003**: System MUST support DRY_RUN mode where all DNS checks and decision logic execute normally but no database writes or Jira actions occur, with all intended actions logged.

- **FR-004**: System MUST exit with code 0 on successful completion (all IPs processed, non-fatal DNS failures acceptable) and non-zero on fatal errors (database unreachable, Jira authentication failure, configuration errors).

#### Database Access and IP Discovery

- **FR-005**: System MUST connect to the MySQL database using connection parameters from environment variables (DSN or individual host/port/user/password/database parameters).

- **FR-006**: System MUST query all IPv4 addresses from the `postal.ip_addresses` table at job start, retrieving columns: `id`, `ip`, `priority`, `oldPriority`, `blockingLists`, `lastEvent`.

- **FR-007**: System MUST handle database connection failures as fatal errors, exiting non-zero with structured error logs.

#### DNS Resolution and Classification

- **FR-008**: System MUST use dnspython to perform DNS lookups against each configured DNSBL zone for each IP address, constructing queries in the form `<reversed-ip>.<dnsbl-zone>` (e.g., `45.113.0.203.zen.spamhaus.org` for IP 203.0.113.45).

- **FR-009**: System MUST classify each DNS query result as:
  - **LISTED**: Any A record response from the DNSBL zone (typically 127.0.0.x responses)
  - **NOT_LISTED**: NXDOMAIN response (authoritative "not found")
  - **UNKNOWN**: Timeout, SERVFAIL, network error, or any non-definitive response

- **FR-010**: System MUST apply configurable DNS query timeouts per zone (default: 5 seconds) to prevent indefinite blocking on unresponsive DNS servers.

- **FR-011**: System MUST support concurrent DNS queries (configurable concurrency limit, e.g., 10 queries in parallel) to minimize total job execution time.

- **FR-012**: System MUST aggregate per-zone results for each IP to produce a final listing decision:
  - **IP is LISTED** if at least one zone returns LISTED
  - **IP is CLEAN** if zero zones return LISTED (UNKNOWN results do not trigger priority changes)

- **FR-013**: System MUST log all UNKNOWN DNS results with structured data (IP, zone, error type, timestamp) for operational monitoring and alerting.

- **FR-013a**: System MUST detect systemic DNS failures by calculating the percentage of UNKNOWN responses across all configured DNSBL zones during a job run. When more than 50% of zones return UNKNOWN, the system MUST create a dedicated Jira issue with:
  - Issue type: DNS failure issue type (configurable via JIRA_DNS_FAILURE_ISSUE_TYPE)
  - Label: "MAJOR MALFUNCTION"
  - Summary: "DNS Infrastructure Failure Detected - {percentage}% zones unreachable"
  - Description: Detailed explanation including failed zone list, error types, timestamp, and complete execution logs up to the detection point
  - Deduplication: Search for existing open DNS failure issues in the current day to prevent duplicate alerts

#### State Management and Invariants

- **FR-014**: System MUST update database columns according to these deterministic invariants:
  - `oldPriority` is written exactly once when transitioning from clean to listed state and MUST NOT be overwritten while the IP remains throttled
  - `blockingLists` MUST always be stored as `",".join(sorted(zone_list))` with no spaces or other separators to ensure deterministic comparison
  - `lastEvent` MUST be updated only on material state transitions: new listing, clearing, or change in the set of listing zones while listed
  - All updates MUST be idempotent: re-running without state changes produces no writes

- **FR-015**: System MUST implement these state transition rules:
  - **Clean -> Listed**: Set `priority = LISTED_PRIORITY`, set `oldPriority = <current priority>` (one-time write), set `blockingLists = <sorted zones>`, set `lastEvent = "new block from list(s) <zones>"`
  - **Listed -> Clean**: Set `priority = oldPriority` (or CLEAN_FALLBACK_PRIORITY if oldPriority is NULL), set `oldPriority = NULL`, set `blockingLists = ""`, set `lastEvent = "block removed"`
  - **Listed -> Listed (zone set changed)**: Update `blockingLists = <new sorted zones>`, update `lastEvent = "blocking list change: <zones>"`
  - **No change**: No database writes

- **FR-016**: System MUST use LISTED_PRIORITY, CLEAN_FALLBACK_PRIORITY, and other priority values from configuration (environment variables), not hardcoded values.

#### Jira Integration and Deduplication

- **FR-017**: System MUST authenticate to Jira using credentials and server URL from environment variables (JIRA_SERVER, JIRA_USER, JIRA_API_TOKEN or equivalent).

- **FR-018**: System MUST treat Jira authentication failures as fatal errors, exiting non-zero.

- **FR-019**: System MUST use configurable Jira project key, issue types, and status exclusion list from environment variables (JIRA_PROJECT, JIRA_ISSUE_TYPE for blacklist issues, JIRA_DNS_FAILURE_ISSUE_TYPE for DNS infrastructure failures, JIRA_EXCLUDED_STATUSES for JQL queries).

- **FR-020**: System MUST deduplicate Jira issues by searching Jira for open issues associated with the IP using JQL queries, NOT by database-only deduplication.

- **FR-021**: System MUST construct JQL queries to find open issues for a given IP using configurable project (JIRA_PROJECT) and status exclusion criteria (JIRA_EXCLUDED_STATUSES, comma-separated list of status names to exclude, e.g., "Done,Closed,Resolved"), with a fixed summary pattern match. JQL template format: `project = "{JIRA_PROJECT}" AND status NOT IN ({JIRA_EXCLUDED_STATUSES}) AND summary ~ "IP {ip}"`.

- **FR-022**: System MUST construct Jira issue summaries in the deterministic form: `"IP {ip} blacklisted by {sorted_zones}"` where `{sorted_zones}` is the comma-separated sorted list of DNSBL zones (e.g., "IP 203.0.113.45 blacklisted by bl.spamcop.net,zen.spamhaus.org").

- **FR-023**: System MUST create a new Jira issue when an IP becomes listed and no open issue exists for that IP, including:
  - Summary: `"IP {ip} blacklisted by {sorted_zones}"`
  - Description: Detailed listing information including all zones, DNS query results, UNKNOWN zones (if any), timestamp, and relevant context
  - Project and issue type from configuration

- **FR-024**: System MUST reuse existing open Jira issues when an IP's listing state changes:
  - If the zone set changes while listed: Add a comment describing the new zone membership, do not create a new issue
  - If the IP clears: Add a comment indicating the IP is now clean, do not create a new issue or close the issue (closing is a manual operations decision)

- **FR-025**: System MUST NOT create duplicate Jira issues for the same IP. If multiple open issues are found (edge case, manual intervention), the system MUST log a warning and use the most recently created issue.

- **FR-026**: System MUST include UNKNOWN DNS results in Jira issue descriptions/comments for operational visibility, clearly distinguishing between LISTED, NOT_LISTED, and UNKNOWN responses per zone.

- **FR-027**: System MUST handle Jira API rate limits and transient errors gracefully, logging errors and retrying with 3 attempts using exponential backoff (2s, 4s, 8s intervals for a maximum 14s total delay), treating repeated failures as fatal after exhausting retries.

#### Observability and Logging

- **FR-028**: System MUST emit structured, machine-parseable logs (JSON format preferred) for every IP processed, including fields:
  - `ip`: The IP address checked
  - `listed_zones`: Array of zones where IP is LISTED
  - `unknown_zones`: Array of zones that returned UNKNOWN
  - `decision`: Final decision (LISTED or CLEAN)
  - `db_changes`: Boolean indicating whether database was updated
  - `jira_action`: Action taken (created_issue, updated_issue, no_action)
  - `duration_ms`: Time taken to process this IP
  - `timestamp`: ISO 8601 timestamp

- **FR-029**: System MUST log DNS failures with sufficient detail for debugging: IP, zone, query type, error message, timeout value.

- **FR-030**: System MUST distinguish between fatal errors (exit non-zero, Kubernetes retry) and non-fatal errors (log and continue):
  - **Fatal**: Database unreachable, Jira authentication failure, critical configuration missing
  - **Non-fatal**: Individual DNS query failures (UNKNOWN results), transient Jira API errors within retry limits

- **FR-031**: System MUST log a summary at job completion including: total IPs checked, total listed, total cleaned, total unchanged, total Jira issues created/updated, total DNS failures, overall duration.

#### Idempotency and Safety

- **FR-032**: System MUST be safe to run repeatedly with identical inputs, producing identical outputs and zero additional Jira issues or database writes on subsequent runs with no state changes.

- **FR-033**: System MUST handle overlapping or concurrent job executions safely using READ COMMITTED transaction isolation level (MySQL default), ensuring no lost updates or partial states through proper transaction boundaries.

### Key Entities *(include if feature involves data)*

- **IP Address Record**: Represents a mail server IP address in the postal.ip_addresses table. Key attributes: unique IP address (IPv4 dotted-quad), current priority (listing status - lower values indicate more severe restrictions), oldPriority (backup for restoration), blockingLists (comma-separated sorted DNSBL zones), lastEvent (human-readable state transition description). Relationships: One IP to zero-or-one open Jira issue (deduped via Jira search).

- **DNSBL Zone**: Represents a DNS-based blacklist provider (e.g., zen.spamhaus.org, bl.spamcop.net). Key attributes: zone domain name. No database representation; loaded from configuration. Each zone is queried independently for each IP.

- **DNS Query Result**: Represents the outcome of querying a specific IP against a specific DNSBL zone. Attributes: IP, zone, classification (LISTED/NOT_LISTED/UNKNOWN), response data (A record or error), timestamp. Transient; not persisted.

- **Jira Issue**: Represents a tracking ticket for a blacklisted IP. Key attributes: issue key, summary (deterministic format), description (listing details), status (open/closed). Maintained in Jira; deduplication via JQL search.

- **State Transition Event**: Represents a material change in IP blacklist status. Attributes: IP, previous state, new state, zone set delta, timestamp. Captured in lastEvent field and Jira comments.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operations teams can identify and remediate blacklisted IPs within 15 minutes of listing detection, reducing email delivery failures by 90% compared to manual monitoring.

- **SC-002**: System processes all configured IPs (up to 1000 IPs) against all configured DNSBL zones (up to 10 zones) within 5 minutes per job run, enabling frequent monitoring (e.g., every 15 minutes).

- **SC-003**: Zero duplicate Jira tickets are created for the same IP across any number of job runs, verified by auditing Jira project for duplicate issue summaries.

- **SC-004**: Idempotency is verified: running the job twice without state changes produces zero additional database writes and zero new Jira issues or comments.

- **SC-005**: DNS fault tolerance is confirmed: transient DNS failures (UNKNOWN) do not cause false throttling or false clearing, and all UNKNOWN results are logged for operational review.

- **SC-006**: State restoration accuracy: 100% of IPs that clear from blacklists return to their original priority (oldPriority) or fallback priority if oldPriority was NULL.

- **SC-007**: Job execution reliability: 99% of scheduled job runs complete successfully (exit code 0) under normal conditions, with fatal errors (database/Jira unavailable) causing non-zero exits and Kubernetes retry.

- **SC-008**: Log visibility: All job executions produce structured JSON logs that can be parsed and analyzed by centralized logging systems (e.g., ELK, Splunk) for alerting and audit trails.

- **SC-008a**: Resource efficiency: Job executes within allocated Kubernetes resources (250m CPU / 256Mi memory requests, 500m CPU / 512Mi memory limits) without OOMKills or CPU throttling under normal load conditions (up to 1000 IPs, 10 zones).

### Validation and Testing

- **SC-009**: All acceptance scenarios defined in User Stories 1-3 pass automated tests before deployment.

- **SC-010**: Constitutional compliance is verified: all data integrity invariants (oldPriority single-write, blockingLists deterministic sorting, lastEvent material changes only) are enforced and tested.

- **SC-011**: DRY_RUN mode produces accurate "would execute" logs that match actual execution when DRY_RUN is disabled, enabling safe testing in production environments.

## Dependencies and Assumptions *(mandatory)*

### Dependencies

- **MySQL Database**: System requires access to a MySQL instance containing the `postal.ip_addresses` table with columns: `id`, `ip`, `priority`, `oldPriority`, `blockingLists`, `lastEvent`. Table schema is assumed to exist; system does not create or migrate tables.

- **Jira Instance**: System requires a Jira instance with API access, a configured project, and permissions to create/search/comment on issues.

- **DNS Infrastructure**: System requires reliable DNS resolution to query DNSBL providers. DNS timeouts and failures are tolerated but logged for operational visibility.

- **Kubernetes Cluster**: System is deployed as a Kubernetes CronJob with resource requests of 250m CPU and 256Mi memory, and limits of 500m CPU and 512Mi memory, sufficient to execute DNS queries, database operations, and Jira API calls within configured schedule intervals.

- **Configuration Sources**: System requires environment variables or mounted ConfigMaps/Secrets containing all configuration parameters (database, Jira, DNSBLs, priorities, timeouts).

### Assumptions

- **DNSBL Zone List**: The list of DNSBL zones is curated and validated by operations. System does not validate zone reachability or reputation; invalid zones result in UNKNOWN responses.

- **IP Address Format**: All IPs in the postal.ip_addresses table are valid IPv4 addresses in dotted-quad notation. System does not support IPv6 (may be a future enhancement).

- **Priority Semantics**: Lower priority values indicate more severe sending restrictions (e.g., priority=0 means most restricted/listed state). LISTED_PRIORITY is typically 0, and CLEAN_FALLBACK_PRIORITY is a higher value (e.g., 50).

- **Jira Workflow**: Jira issues are manually closed by operations after remediation. System does not auto-close issues even when IPs clear; it only adds comments. The JIRA_EXCLUDED_STATUSES configuration defines which status names indicate "closed" issues (default: "Done,Closed,Resolved") to adapt to different Jira workflow configurations.

- **Job Schedule**: CronJob schedule is configured to allow sufficient time for job completion before the next run starts (e.g., run every 15 minutes with 5-minute max job duration, leaving 10-minute buffer to prevent overlapping executions).

- **Database Transaction Isolation**: MySQL is configured with READ COMMITTED isolation level (default). This prevents dirty reads while allowing concurrent job executions to update different IPs independently, with "last committed wins" semantics for any overlapping updates to the same IP.

- **No Schema Changes**: System does not create, alter, or drop database tables. All required schema is assumed to exist and be compatible.

- **Single Database and Jira Instance**: System connects to one database and one Jira instance per deployment. Multi-tenant or multi-instance scenarios require separate CronJob deployments.

## Out of Scope

- **IPv6 Support**: IPv6 addresses are not supported in this release. Only IPv4 addresses are monitored.

- **DNSBL Zone Health Monitoring**: System does not monitor the health or reachability of DNSBL zones themselves. UNKNOWN results are logged but zone validation is a separate operational concern.

- **Automatic Issue Closing**: System does not auto-close Jira issues when IPs clear. Closing is a manual decision by operations to confirm remediation.

- **Database Schema Management**: System does not create or migrate the postal.ip_addresses table. Schema is assumed to exist and be maintained separately.

- **Email Alerting for DNS Failures**: While DNS failures are logged, configurable email alerting for UNKNOWN results is not included in this release. Operations may configure Kubernetes-level alerts based on log patterns.

- **Multi-Jira Project Support**: System creates issues in a single configured Jira project. Routing issues to different projects based on IP characteristics is not supported.

- **Historical Data Retention**: System does not maintain historical records of blacklist status changes. Current state is in the database; historical tracking is available via Jira issue comments and system logs.

- **Web UI or API**: System is a batch job with no interactive interface. All configuration is file/environment-based, and all output is via logs and Jira.
