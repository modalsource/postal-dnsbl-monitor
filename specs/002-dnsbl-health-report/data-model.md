# Data Model: DNSBL Health Report

**Feature**: 002-dnsbl-health-report  
**Date**: 2025-12-19  
**Status**: Complete

## Overview

This document defines the data structures for DNSBL health tracking and reporting. All entities are in-memory only (no database persistence per Constitution Principle I).

---

## Entity: DNSBLHealthRecord

**Purpose**: Tracks health metrics for a single DNSBL zone across all IP checks in the current execution.

### Fields

| Field | Type | Description | Validation Rules |
|-------|------|-------------|------------------|
| `zone` | str | DNSBL zone name (e.g., "zen.spamhaus.org") | Non-empty, valid DNS name |
| `checks_performed` | int | Total number of IP checks attempted | ≥ 0 |
| `successful_checks` | int | Number of successful responses (LISTED or NOT_LISTED) | ≥ 0, ≤ checks_performed |
| `failed_checks` | int | Number of failed checks (timeouts, invalid responses) | ≥ 0, = checks_performed - successful_checks |
| `failure_types` | Dict[str, int] | Count of each failure type | Keys: timeout, nxdomain_zone, invalid_response_range, invalid_response_type |
| `failure_rate` | float | Computed property: failed_checks / checks_performed | 0.0 to 1.0, NaN if checks_performed == 0 |
| `status` | str | Computed property: "healthy" if failure_rate < 1.0, else "broken" | One of: healthy, broken |

### Invariants

1. `checks_performed = successful_checks + failed_checks` (always)
2. `sum(failure_types.values()) = failed_checks` (failure types must account for all failures)
3. `failure_rate` is read-only (computed from failed_checks / checks_performed)
4. `status` is read-only (derived from failure_rate)

### State Transitions

**None** - This is a pure aggregator with no lifecycle states. Records are created at initialization and updated monotonically (counters only increase).

### Relationships

- **One-to-Many**: HealthTracker → DNSBLHealthRecord (tracker contains one record per DNSBL zone)
- **No persistence**: Records exist only in memory during execution

---

## Entity: HealthSummary

**Purpose**: Aggregates all DNSBL health data plus execution metadata for JSON output.

### Fields

| Field | Type | Description | Validation Rules |
|-------|------|-------------|------------------|
| `timestamp` | datetime | Execution end timestamp (ISO 8601) | Must be valid UTC datetime |
| `total_dnsbls` | int | Total number of configured DNSBL zones | > 0 |
| `broken_dnsbls` | int | Count of zones with failure_rate == 1.0 | ≥ 0, ≤ total_dnsbls |
| `network_issue_detected` | bool | True if ≥50% DNSBLs failed AND supplemental checks failed | Boolean |
| `total_ip_checks` | int | Total IP addresses checked across all DNSBLs | ≥ 0 |
| `execution_duration_ms` | int | Time from first check to summary generation (milliseconds) | ≥ 0 |
| `dnsbl_health` | List[DNSBLHealthRecord] | Per-DNSBL health records | Length = total_dnsbls |
| `network_connectivity` | NetworkConnectivityResult | Supplemental DNS check results | Optional (None if check disabled) |

### Invariants

1. `len(dnsbl_health) == total_dnsbls` (one record per configured zone)
2. `broken_dnsbls == count(r for r in dnsbl_health if r.status == "broken")`
3. If `network_issue_detected == True`, then `network_connectivity.check_enabled == True`
4. `dnsbl_health` list is sorted by zone name (alphabetical) for deterministic output

### JSON Serialization

```python
def to_json(self) -> dict:
    """Serialize to JSON-compatible dict."""
    return {
        "execution_summary": {
            "timestamp": self.timestamp.isoformat(),
            "total_dnsbls": self.total_dnsbls,
            "broken_dnsbls": self.broken_dnsbls,
            "network_issue_detected": self.network_issue_detected,
            "total_ip_checks": self.total_ip_checks,
            "execution_duration_ms": self.execution_duration_ms
        },
        "dnsbl_health": [
            {
                "zone": r.zone,
                "status": r.status,
                "checks_performed": r.checks_performed,
                "successful_checks": r.successful_checks,
                "failed_checks": r.failed_checks,
                "failure_rate": r.failure_rate,
                "failure_types": dict(r.failure_types)
            }
            for r in sorted(self.dnsbl_health, key=lambda x: x.zone)
        ],
        "network_connectivity": self.network_connectivity.to_json() if self.network_connectivity else None
    }
```

---

## Entity: NetworkConnectivityResult

**Purpose**: Captures results of supplemental DNS checks to cloud providers.

### Fields

| Field | Type | Description | Validation Rules |
|-------|------|-------------|------------------|
| `check_enabled` | bool | Whether supplemental checks were performed | Boolean |
| `cloudflare_reachable` | bool | True if 1.1.1.1 responded to DNS query | Boolean (None if check_enabled=False) |
| `google_reachable` | bool | True if 8.8.8.8 responded to DNS query | Boolean (None if check_enabled=False) |

### Invariants

1. If `check_enabled == False`, then `cloudflare_reachable` and `google_reachable` must be `None`
2. If `check_enabled == True`, both reachability fields must be `bool` (not None)

### JSON Serialization

```python
def to_json(self) -> dict:
    """Serialize to JSON-compatible dict."""
    return {
        "check_enabled": self.check_enabled,
        "cloudflare_reachable": self.cloudflare_reachable,
        "google_reachable": self.google_reachable
    }
```

---

## Entity: PrunedConfiguration

**Purpose**: Represents the YAML-formatted suggested DNSBL list with broken endpoints removed.

### Fields

| Field | Type | Description | Validation Rules |
|-------|------|-------------|------------------|
| `healthy_zones` | List[str] | DNSBL zones with failure_rate < 1.0 | Non-empty list of valid DNS names |
| `removed_zones` | List[str] | DNSBL zones with failure_rate == 1.0 | May be empty if all zones healthy |
| `generated_at` | datetime | Timestamp of pruned list generation | Valid UTC datetime |

### Invariants

1. `healthy_zones` and `removed_zones` are disjoint sets (no overlap)
2. `healthy_zones + removed_zones` equals the original configured DNSBL list
3. Both lists are sorted alphabetically for deterministic output

### YAML Serialization

```python
def to_yaml(self) -> str:
    """Generate YAML-formatted pruned configuration."""
    header = [
        "# Suggested DNSBL Configuration (Broken endpoints removed)",
        f"# Generated: {self.generated_at.isoformat()}",
        f"# Removed: {', '.join(self.removed_zones) if self.removed_zones else 'None'}",
    ]
    
    yaml_dict = {"dnsbl_zones": sorted(self.healthy_zones)}
    
    import yaml
    yaml_output = yaml.safe_dump(yaml_dict, default_flow_style=False, sort_keys=False)
    
    return "\n".join(header) + "\n" + yaml_output
```

**Example Output**:
```yaml
# Suggested DNSBL Configuration (Broken endpoints removed)
# Generated: 2025-12-19T10:30:00Z
# Removed: dead.example.com, broken.dnsbl.org
dnsbl_zones:
- bl.spamcop.net
- dnsbl.sorbs.net
- zen.spamhaus.org
```

---

## Service: HealthTracker

**Purpose**: Aggregates DNSBL health data in real-time during execution.

### Methods

#### `__init__(dnsbl_zones: List[str])`
Initialize tracker with configured DNSBL zones.

**Preconditions**:
- `dnsbl_zones` is non-empty list of valid DNS names

**Postconditions**:
- Creates one `DNSBLHealthRecord` per zone
- All counters initialized to 0

#### `record_check(zone: str, success: bool, failure_type: str | None = None)`
Record a single DNS check result.

**Parameters**:
- `zone`: DNSBL zone name (must exist in initialized zones)
- `success`: True if LISTED or NOT_LISTED, False if UNKNOWN
- `failure_type`: Required if success=False, one of: timeout, nxdomain_zone, invalid_response_range, invalid_response_type

**Preconditions**:
- `zone` exists in `_health_records`
- If `success == False`, then `failure_type` is not None

**Postconditions**:
- Increments `checks_performed` for the zone
- Increments `successful_checks` or `failed_checks` based on success
- If failure, increments `failure_types[failure_type]`

**Invariant Preservation**: Maintains `checks_performed = successful_checks + failed_checks`

#### `get_summary(network_connectivity: NetworkConnectivityResult | None = None) -> HealthSummary`
Generate final health summary.

**Parameters**:
- `network_connectivity`: Optional supplemental DNS check results

**Preconditions**:
- At least one check has been recorded (some `checks_performed > 0`)

**Postconditions**:
- Returns `HealthSummary` with all fields populated
- `network_issue_detected` is True if ≥50% DNSBLs have failure_rate == 1.0 AND network_connectivity shows failures

**Business Logic**:
```python
def get_summary(self, network_connectivity):
    broken_count = sum(1 for r in self._health_records.values() if r.failure_rate == 1.0)
    total_dnsbls = len(self._health_records)
    
    network_issue = False
    if broken_count / total_dnsbls >= 0.5:
        if network_connectivity and network_connectivity.check_enabled:
            # Network issue if both supplemental checks failed
            network_issue = not (network_connectivity.cloudflare_reachable or 
                                network_connectivity.google_reachable)
    
    return HealthSummary(
        timestamp=datetime.now(timezone.utc),
        total_dnsbls=total_dnsbls,
        broken_dnsbls=broken_count,
        network_issue_detected=network_issue,
        # ... other fields
    )
```

---

## Service: HealthReporter

**Purpose**: Generates JSON and YAML output from health data.

### Methods

#### `generate_json_report(summary: HealthSummary) -> str`
Generate JSON-formatted health summary.

**Parameters**:
- `summary`: HealthSummary object

**Returns**: JSON string (pretty-printed, sorted keys for determinism)

**Implementation**:
```python
def generate_json_report(summary: HealthSummary) -> str:
    import json
    return json.dumps(summary.to_json(), indent=2, sort_keys=True)
```

#### `generate_pruned_yaml(health_records: List[DNSBLHealthRecord], original_zones: List[str]) -> str`
Generate YAML-formatted pruned DNSBL list.

**Parameters**:
- `health_records`: List of DNSBLHealthRecord objects
- `original_zones`: Original configured DNSBL zones (for validation)

**Returns**: YAML string with header comments and pruned zone list

**Business Logic**:
```python
def generate_pruned_yaml(health_records, original_zones):
    healthy = [r.zone for r in health_records if r.status == "healthy"]
    broken = [r.zone for r in health_records if r.status == "broken"]
    
    pruned_config = PrunedConfiguration(
        healthy_zones=healthy,
        removed_zones=broken,
        generated_at=datetime.now(timezone.utc)
    )
    
    return pruned_config.to_yaml()
```

---

## Service: NetworkChecker

**Purpose**: Performs supplemental DNS connectivity checks to cloud providers.

### Methods

#### `check_connectivity(timeout: int = 5) -> NetworkConnectivityResult`
Check DNS connectivity to Cloudflare and Google public resolvers.

**Parameters**:
- `timeout`: DNS query timeout in seconds (default: 5)

**Returns**: NetworkConnectivityResult with reachability status

**Implementation Details**:
- Query: DNS A record lookup for `google.com`
- Targets: 1.1.1.1 (Cloudflare), 8.8.8.8 (Google)
- Success criteria: Any valid A record response (no validation of IP address)
- Failure handling: Timeout, SERVFAIL, NXDOMAIN all count as unreachable

**Business Logic**:
```python
def check_connectivity(timeout=5):
    import dns.resolver
    
    def check_resolver(nameserver: str) -> bool:
        resolver = dns.resolver.Resolver()
        resolver.nameservers = [nameserver]
        resolver.timeout = timeout
        resolver.lifetime = timeout
        
        try:
            answers = resolver.resolve("google.com", "A")
            return len(answers) > 0
        except (dns.exception.Timeout, dns.resolver.NXDOMAIN, 
                dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            return False
    
    return NetworkConnectivityResult(
        check_enabled=True,
        cloudflare_reachable=check_resolver("1.1.1.1"),
        google_reachable=check_resolver("8.8.8.8")
    )
```

---

## Integration with Existing Data Model

### Existing Entity: DNSResult (src/models/dns_result.py)

**No changes required.** Existing categorization (LISTED, NOT_LISTED, UNKNOWN) is sufficient.

**Integration Point**: Health tracker consumes DNSResult status to determine success/failure:
- LISTED → success=True
- NOT_LISTED → success=True
- UNKNOWN → success=False (categorize failure_type based on exception)

### Existing Service: DNSChecker (src/services/dns_checker.py)

**Modification Required**: Add health tracking callback after each DNSBL check.

**Example Integration**:
```python
class DNSChecker:
    def __init__(self, zones, timeout, health_tracker=None):
        self.zones = zones
        self.timeout = timeout
        self.health_tracker = health_tracker  # NEW
    
    def check_ip(self, ip):
        results = []
        for zone in self.zones:
            result = self._query_zone(ip, zone)
            results.append(result)
            
            # NEW: Record health data
            if self.health_tracker:
                success = result.status in (DNSResultStatus.LISTED, DNSResultStatus.NOT_LISTED)
                failure_type = self._categorize_failure(result) if not success else None
                self.health_tracker.record_check(zone, success, failure_type)
        
        return results
    
    def _categorize_failure(self, result):
        """Map DNS exception to failure type."""
        if isinstance(result.error, dns.exception.Timeout):
            return "timeout"
        elif isinstance(result.error, dns.resolver.NXDOMAIN):
            # Zone itself doesn't exist
            return "nxdomain_zone"
        elif result.status == DNSResultStatus.UNKNOWN:
            # Invalid response detected by validation
            return "invalid_response_range"  # or invalid_response_type
        else:
            return "unknown_error"
```

---

## Validation Rules Summary

### Data Integrity

1. **Counters are monotonic**: checks_performed, successful_checks, failed_checks only increase
2. **Failure accounting**: `sum(failure_types.values()) == failed_checks`
3. **Partition invariant**: `checks_performed == successful_checks + failed_checks`
4. **Rate bounds**: `0.0 ≤ failure_rate ≤ 1.0`

### Output Determinism

1. **Sorted JSON keys**: Use `sort_keys=True` in `json.dumps()`
2. **Sorted DNSBL lists**: Always sort zones alphabetically in YAML and JSON arrays
3. **Sorted failure_types**: Use `dict(sorted(failure_types.items()))` for JSON output

### Constitution Compliance

1. **No persistence**: All entities are Python objects in memory only
2. **Idempotency**: Identical DNSBL responses → identical JSON/YAML output (excluding timestamps)
3. **Stateless**: No file I/O except stdout (logs), no database writes

---

## Testing Validation

### Contract Tests

Create `tests/contract/test_health_output.py` to validate:

1. **JSON schema validation**: Verify all required fields present, correct types
2. **YAML format validation**: Parse generated YAML, verify structure matches config
3. **Determinism**: Same input data → identical JSON output (stable sort order)

### Unit Tests

Create `tests/unit/test_health_tracker.py` to validate:

1. **Counter invariants**: Verify partition property after record_check()
2. **Failure rate calculation**: Test edge cases (0 checks, all success, all fail)
3. **Network issue detection**: Test 50% threshold with various configurations

### Integration Tests

Create `tests/integration/test_health_tracking.py` to validate:

1. **End-to-end tracking**: Simulate DNS checks, verify final summary accuracy
2. **Supplemental check integration**: Mock network checker, verify network_issue_detected logic
3. **YAML generation**: Verify pruned list excludes broken zones

---

**Status**: Data model design complete. Ready for contract generation.
