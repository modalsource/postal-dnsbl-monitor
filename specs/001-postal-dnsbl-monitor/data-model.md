# Data Model: Postal DNSBL Monitor

**Date**: 2025-12-17  
**Purpose**: Define entities, attributes, relationships, validation rules, and state transitions

---

## Entity Definitions

### 1. IP Address Record

**Source**: PostgreSQL `postal.ip_addresses` table (existing schema, read/write)

**Attributes**:

| Column | Type | Nullable | Description | Validation |
|--------|------|----------|-------------|------------|
| `id` | INTEGER | No | Primary key | Auto-increment |
| `ip` | VARCHAR(15) | No | IPv4 address | Must match regex `^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$` |
| `priority` | INTEGER | No | Throttling level | 0-100 range (0 = fully throttled) |
| `oldPriority` | INTEGER | Yes | Backup priority for restoration | NULL when clean, set once on clean→listed transition |
| `blockingLists` | TEXT | No (empty string default) | Comma-separated sorted DNSBL zones | Format: `",".join(sorted(zones))` or `""` |
| `lastEvent` | TEXT | Yes | Human-readable state transition description | Updated only on material changes |

**Invariants** (Constitutional Principle III - Data Integrity):

1. **Single-Write oldPriority** (FR-014):
   - `oldPriority` is written **exactly once** when transitioning from clean to listed state
   - While `priority == LISTED_PRIORITY`, `oldPriority` MUST NOT be overwritten
   - On clean state, `oldPriority` MUST be NULL

2. **Deterministic blockingLists** (FR-014):
   - MUST be stored as `",".join(sorted(zone_list))` with **no spaces**
   - Example: `"bl.spamcop.net,dnsbl.sorbs.net,zen.spamhaus.org"`
   - Empty when IP is clean: `""`
   - Enables deterministic comparison across job runs

3. **Material-Changes-Only lastEvent** (FR-014):
   - Updated **only** on these transitions:
     - Clean → Listed: `"new block from list(s) <zones>"`
     - Listed → Clean: `"block removed"`
     - Listed → Listed (zone set changed): `"blocking list change: <zones>"`
   - NOT updated when re-running job with unchanged state (idempotency)

**State Machine**:

```
       ┌─────────────────┐
       │   CLEAN STATE   │
       │ priority=50     │
       │ oldPriority=NULL│
       │ blockingLists=""│
       └────────┬────────┘
                │
                │ DNS check: ≥1 zone returns LISTED
                ↓
       ┌─────────────────────────────────┐
       │      LISTED STATE               │
       │ priority=LISTED_PRIORITY (0)    │
       │ oldPriority=50 (set ONCE)       │
       │ blockingLists="zen.spamhaus.org"│
       └────────┬────────────────────────┘
                │
                │ Zone set changes (still listed)
                ↓
       ┌─────────────────────────────────┐
       │      LISTED STATE               │
       │ priority=0 (unchanged)          │
       │ oldPriority=50 (preserved!)     │
       │ blockingLists="bl.spamcop.net,  │
       │               zen.spamhaus.org" │
       └────────┬────────────────────────┘
                │
                │ DNS check: 0 zones return LISTED
                ↓
       ┌─────────────────┐
       │   CLEAN STATE   │
       │ priority=50     │← Restored from oldPriority
       │ oldPriority=NULL│← Cleared
       │ blockingLists=""│
       └─────────────────┘
```

**Edge Case**: If `oldPriority` is NULL during clearing (shouldn't happen under normal operation), restore to `CLEAN_FALLBACK_PRIORITY` (configurable, default 50).

---

### 2. DNS Query Result

**Source**: Transient in-memory object (not persisted)

**Attributes**:

| Field | Type | Description | Values |
|-------|------|-------------|--------|
| `ip` | str | IPv4 address being checked | e.g., "203.0.113.45" |
| `zone` | str | DNSBL zone domain | e.g., "zen.spamhaus.org" |
| `classification` | Enum | Query result classification | LISTED \| NOT_LISTED \| UNKNOWN |
| `response_data` | str | DNS response or error description | A record (e.g., "127.0.0.2") or exception type |
| `timestamp` | datetime | When query completed | ISO 8601 format |

**Classification Logic** (FR-009):

- **LISTED**: DNS query returns A record (typically 127.0.0.x range used by DNSBLs)
- **NOT_LISTED**: DNS query returns NXDOMAIN (authoritative "not found")
- **UNKNOWN**: Timeout, SERVFAIL, NoAnswer, or any non-definitive response

**Aggregation Rules** (FR-012):

- IP is **LISTED** if `≥1` zone returns LISTED
- IP is **CLEAN** if `0` zones return LISTED (UNKNOWN results ignored for throttling decision)

**DNS Query Construction** (FR-008):

- Reverse IP octets: `203.0.113.45` → `45.113.0.203`
- Append zone: `45.113.0.203.zen.spamhaus.org`
- Query type: A record

---

### 3. State Transition Event

**Source**: Transient, captured in logs and Jira comments (not persisted in DB)

**Attributes**:

| Field | Type | Description |
|-------|------|-------------|
| `ip` | str | IPv4 address |
| `previous_state` | str | State before transition (CLEAN or LISTED) |
| `new_state` | str | State after transition (CLEAN or LISTED) |
| `zone_set_delta` | dict | Changes in zone membership (`added`, `removed`) |
| `timestamp` | datetime | When transition occurred |

**Trigger Conditions** (Material Changes):

1. **Clean → Listed**: IP becomes listed on ≥1 zone
2. **Listed → Clean**: All zones return NOT_LISTED or UNKNOWN
3. **Listed → Listed (zone change)**: Set of listing zones changes (added or removed zones)

**Non-Triggers** (Idempotency):

- Re-running job with same zone results → No event generated
- UNKNOWN results (transient DNS failures) → No state change

---

### 4. Jira Issue

**Source**: External system (Jira), managed via REST API

**Attributes**:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `issue_key` | str | Jira issue identifier | "OPS-123" |
| `summary` | str | Deterministic issue summary | "IP 203.0.113.45 blacklisted by zen.spamhaus.org" |
| `description` | text | Detailed listing information | Zones, DNS results, UNKNOWN zones, timestamp |
| `status` | str | Workflow status | "Open", "In Progress", "Done", etc. |
| `labels` | list[str] | Issue labels | ["MAJOR MALFUNCTION"] for DNS failures |

**Summary Format** (FR-022 - Deterministic):

```
"IP {ip} blacklisted by {sorted_zones}"
```

Where `{sorted_zones}` is comma-separated: `"bl.spamcop.net,zen.spamhaus.org"`

**Deduplication Strategy** (FR-020, FR-021):

1. Construct JQL query with configurable excluded statuses:
   ```jql
   project = "{JIRA_PROJECT}" 
   AND status NOT IN ({JIRA_EXCLUDED_STATUSES}) 
   AND summary ~ "IP {ip}"
   ```
2. If **0 issues** found: Create new issue
3. If **1 issue** found: Reuse for comments (zone changes, clearing)
4. If **>1 issues** found (edge case): Log warning, use most recently created

**Issue Types**:

- **Blacklist Issue**: Standard issue type (configurable via `JIRA_ISSUE_TYPE`)
- **DNS Failure Issue**: Separate issue type (configurable via `JIRA_DNS_FAILURE_ISSUE_TYPE`) with label "MAJOR MALFUNCTION"

---

### 5. DNS Failure Alert

**Source**: Jira issue created when >50% of zones return UNKNOWN (FR-013a)

**Trigger Condition**:

```python
unknown_percentage = (unknown_zone_count / total_zones) * 100
if unknown_percentage > 50:
    create_dns_failure_issue()
```

**Attributes**:

| Field | Content |
|-------|---------|
| Issue Type | `JIRA_DNS_FAILURE_ISSUE_TYPE` |
| Label | "MAJOR MALFUNCTION" |
| Summary | "DNS Infrastructure Failure Detected - {percentage}% zones unreachable" |
| Description | Failed zone list, error types, timestamp, execution logs |

**Deduplication**:

- Search for existing open DNS failure issues created on same calendar day
- If found: Add comment with updated status
- If not found: Create new issue

---

## Relationships

### IP Address Record ↔ Jira Issue

**Cardinality**: One-to-Zero-or-One

- One IP Address Record → Zero-or-One **open** Jira Issue
- Relationship established via JQL search (not foreign key)
- Multiple **closed** issues may exist for same IP (historical tracking)

**Relationship Rules**:

1. Create new issue **only if** JQL search returns 0 open issues for IP
2. Reuse existing open issue for comments on zone changes or clearing
3. Never create duplicate open issues (constitutional violation)

### IP Address Record ↔ DNS Query Results

**Cardinality**: One-to-Many (transient)

- One IP Address Record → Many DNS Query Results (one per DNSBL zone per job run)
- Results are **not persisted**, only aggregated for decision-making
- Results logged in structured JSON for debugging

### DNS Query Results → State Transition Event

**Aggregation Flow**:

```
[DNS Query Results for IP]
    ↓
Aggregate: Count LISTED zones
    ↓
Decision: LISTED if ≥1, CLEAN if 0
    ↓
Compare with current DB state
    ↓
If changed → Generate State Transition Event
    ↓
Update DB + Create/Update Jira Issue
```

---

## Configuration Data Model

**Source**: Environment variables (ConfigMap/Secret)

| Category | Variables | Type | Default |
|----------|-----------|------|---------|
| **Database** | DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_DSN | str, int | N/A (required) |
| **DNSBL** | DNSBL_ZONES (comma-separated), DNS_TIMEOUT, DNS_CONCURRENCY | str, int | 5s, 10 |
| **Priorities** | LISTED_PRIORITY, CLEAN_FALLBACK_PRIORITY | int | 0, 50 |
| **Jira** | JIRA_SERVER, JIRA_USER, JIRA_API_TOKEN, JIRA_PROJECT, JIRA_ISSUE_TYPE, JIRA_DNS_FAILURE_ISSUE_TYPE, JIRA_EXCLUDED_STATUSES | str | "Done,Closed,Resolved" |
| **Operational** | DRY_RUN | bool | false |

**Validation Requirements**:

- `DNSBL_ZONES`: Non-empty, valid domain names
- `DB_HOST`: Reachable PostgreSQL server
- `JIRA_SERVER`: Valid HTTPS URL
- `LISTED_PRIORITY < CLEAN_FALLBACK_PRIORITY`: Sanity check

---

## Logging Data Model

**Per-IP Log Entry** (FR-028):

```json
{
  "timestamp": "2025-12-17T10:30:45Z",
  "job_run_id": "uuid-here",
  "ip": "203.0.113.45",
  "listed_zones": ["zen.spamhaus.org"],
  "unknown_zones": [],
  "decision": "LISTED",
  "db_changes": true,
  "jira_action": "created_issue",
  "duration_ms": 1234
}
```

**Job Summary Log** (FR-031):

```json
{
  "timestamp": "2025-12-17T10:35:00Z",
  "job_run_id": "uuid-here",
  "total_ips": 1000,
  "listed": 5,
  "cleaned": 2,
  "unchanged": 993,
  "jira_created": 3,
  "jira_updated": 4,
  "dns_failures": 0,
  "duration_sec": 285.4
}
```

---

## State Transition Rules (Detailed)

### Transition 1: Clean → Listed

**Preconditions**:
- Current state: `blockingLists == ""`
- DNS check: ≥1 zone returns LISTED

**Updates** (FR-015):
```python
SET priority = LISTED_PRIORITY
SET oldPriority = <current priority>  # Single-write invariant
SET blockingLists = ",".join(sorted(listed_zones))
SET lastEvent = f"new block from list(s) {blockingLists}"
```

**Jira Action** (FR-023):
- Search for open issue with JQL
- If not found: Create new issue with summary "IP {ip} blacklisted by {sorted_zones}"

**Idempotency Check**:
- Only execute UPDATE if `blockingLists != new_sorted_zones`

---

### Transition 2: Listed → Listed (Zone Change)

**Preconditions**:
- Current state: `blockingLists != ""`
- DNS check: ≥1 zone returns LISTED (different set than current)

**Updates** (FR-015):
```python
# priority unchanged
# oldPriority PRESERVED (not overwritten!)
SET blockingLists = ",".join(sorted(new_listed_zones))
SET lastEvent = f"blocking list change: {blockingLists}"
```

**Jira Action** (FR-024):
- Find existing open issue via JQL
- Add comment: "Zone membership changed: now listed on {sorted_zones}"

**Idempotency Check**:
- Only execute UPDATE if `blockingLists != new_sorted_zones`

---

### Transition 3: Listed → Clean

**Preconditions**:
- Current state: `blockingLists != ""`
- DNS check: 0 zones return LISTED

**Updates** (FR-015):
```python
SET priority = oldPriority OR CLEAN_FALLBACK_PRIORITY  # If oldPriority is NULL
SET oldPriority = NULL  # Clear backup
SET blockingLists = ""
SET lastEvent = "block removed"
```

**Jira Action** (FR-024):
- Find existing open issue via JQL
- Add comment: "IP is now clean (no longer listed)"
- Do NOT close issue (manual operations decision)

**Idempotency Check**:
- Only execute UPDATE if `blockingLists != ""`

---

### No Transition: Clean → Clean (No-Op)

**Preconditions**:
- Current state: `blockingLists == ""`
- DNS check: 0 zones return LISTED

**Updates**: None (idempotent no-op per FR-032)

**Jira Action**: None

**Logging**: Log "no_action" for jira_action, db_changes=false

---

### No Transition: Listed → Listed (Same Zones)

**Preconditions**:
- Current state: `blockingLists == "zone1,zone2"`
- DNS check: Same zones return LISTED

**Updates**: None (idempotent no-op per FR-032)

**Jira Action**: None

**Logging**: Log "no_action" for jira_action, db_changes=false

---

## Data Integrity Verification

**Constitutional Compliance Tests** (required by constitution):

1. **Test oldPriority Single-Write** (Principle III):
   - Assert oldPriority set on first clean→listed transition
   - Assert oldPriority preserved on listed→listed (zone change)
   - Assert oldPriority cleared on listed→clean transition

2. **Test blockingLists Deterministic Sorting** (Principle III):
   - Insert unsorted zones: `["zen.spamhaus.org", "bl.spamcop.net"]`
   - Assert stored value: `"bl.spamcop.net,zen.spamhaus.org"`

3. **Test Idempotency** (Principle VI):
   - Run update_ip_listed twice with same zones
   - Assert second call returns False (no update)
   - Assert rowcount == 0 on second UPDATE

4. **Test Jira Deduplication** (Principle IV):
   - Create issue for IP
   - Run job again with same IP listed
   - Assert only 1 open issue exists via JQL search

---

## Summary

This data model defines:

- ✅ 4 core entities (IP Address Record, DNS Query Result, State Transition Event, Jira Issue)
- ✅ Strict invariants for oldPriority, blockingLists, lastEvent
- ✅ Deterministic state machine with 3 material transitions
- ✅ Idempotency guarantees (no-op when state unchanged)
- ✅ Jira deduplication via JQL search (not DB foreign keys)
- ✅ DNS failure alerting (>50% UNKNOWN threshold)

All definitions comply with constitutional principles and functional requirements (FR-014, FR-015, FR-020-FR-027).
