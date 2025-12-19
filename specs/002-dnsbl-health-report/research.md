# Research: DNSBL Health Report

**Feature**: 002-dnsbl-health-report  
**Date**: 2025-12-19  
**Status**: Complete

## Overview

This research document addresses technical decisions for implementing DNSBL health tracking and reporting. All unknowns from the Technical Context have been resolved through analysis of existing codebase, Python ecosystem best practices, and DNSBL monitoring patterns.

---

## Decision 1: JSON Output Structure

**Context**: FR-003 requires structured JSON output for DNSBL health metrics.

**Decision**: Use nested JSON structure with top-level metadata and per-DNSBL detail arrays.

**Rationale**:
- Enables machine parsing for monitoring/alerting systems
- Supports progressive disclosure (summary stats + detailed breakdowns)
- Compatible with existing `python-json-logger` infrastructure
- Allows future extension without breaking schema

**Schema Design**:
```json
{
  "execution_summary": {
    "timestamp": "2025-12-19T10:30:00Z",
    "total_dnsbls": 15,
    "broken_dnsbls": 2,
    "network_issue_detected": false,
    "total_ip_checks": 150,
    "execution_duration_ms": 4523
  },
  "dnsbl_health": [
    {
      "zone": "zen.spamhaus.org",
      "status": "healthy",
      "checks_performed": 150,
      "successful_checks": 150,
      "failed_checks": 0,
      "failure_rate": 0.0,
      "failure_types": {}
    },
    {
      "zone": "dead.example.com",
      "status": "broken",
      "checks_performed": 150,
      "successful_checks": 0,
      "failed_checks": 150,
      "failure_rate": 1.0,
      "failure_types": {
        "timeout": 120,
        "nxdomain_zone": 30
      }
    }
  ],
  "network_connectivity": {
    "check_enabled": true,
    "cloudflare_reachable": true,
    "google_reachable": true
  }
}
```

**Alternatives Considered**:
- **Flat structure**: Rejected - harder to extend, poor separation of concerns
- **CSV format**: Rejected - loses type information, poor for nested data (failure_types)
- **Plain text tables**: Rejected - not machine-parseable

---

## Decision 2: YAML Pruned List Format

**Context**: FR-006 requires YAML output matching DNSBL_LISTS configuration structure.

**Decision**: Generate YAML list matching the existing `config.py` DNSBL_ZONES format.

**Rationale**:
- Existing config uses `DNSBL_ZONES` environment variable (comma-separated string)
- YAML output should match list format for clarity
- PyYAML library already available (transitive dependency via Jira SDK)
- Human-readable for manual verification before applying

**Output Format**:
```yaml
# Suggested DNSBL Configuration (Broken endpoints removed)
# Generated: 2025-12-19T10:30:00Z
# Removed: dead.example.com, broken.dnsbl.org
dnsbl_zones:
  - zen.spamhaus.org
  - bl.spamcop.net
  - dnsbl.sorbs.net
  # ... (all healthy DNSBLs)
```

**Implementation Note**: Use `yaml.safe_dump()` with `default_flow_style=False` for readable list format.

**Alternatives Considered**:
- **JSON array**: Rejected - doesn't match YAML config file format
- **Comma-separated string**: Rejected - less readable, harder to verify changes
- **ENV file format**: Rejected - DNSBL_ZONES is set via ConfigMap, not .env file

---

## Decision 3: Network Issue Detection Strategy

**Context**: FR-007/FR-007a require 50% threshold + supplemental DNS checks to cloud providers.

**Decision**: Two-phase detection:
1. Calculate DNSBL failure rate across all zones
2. If ≥50% fail, perform supplemental checks to Cloudflare (1.1.1.1) and Google (8.8.8.8)
3. If supplemental checks also fail, classify as network issue

**Rationale**:
- Cloudflare and Google are geographically distributed, highly available
- Using public resolvers avoids dependency on external services
- 50% threshold balances sensitivity (catches widespread issues) vs. specificity (doesn't trigger on 1-2 broken DNSBLs)
- Two-phase approach minimizes unnecessary supplemental checks when DNSBLs are healthy

**Implementation Details**:
- Supplemental check: DNS query for `google.com` A record to each resolver
- Timeout: 5 seconds (higher than DNSBL timeout to account for global latency)
- Success criteria: Valid A record response (any IP in 142.250.0.0/16 range for Google)
- Use `dnspython.resolver.Resolver` with explicit nameservers

**Edge Case Handling**:
- Exactly 50% failure: Perform supplemental checks (inclusive threshold)
- Both supplemental targets fail: Network issue confirmed
- Only one supplemental target fails: Still classify as network issue (conservative approach)

**Alternatives Considered**:
- **Ping-based checks**: Rejected - requires ICMP permissions, not available in all container environments
- **HTTP requests**: Rejected - adds HTTP library dependency, slower than DNS
- **Single supplemental target**: Rejected - less reliable, single point of failure

---

## Decision 4: Invalid Response Detection

**Context**: FR-009 requires validation of DNSBL responses (only A records in 127.x.x.x or NXDOMAIN).

**Decision**: Extend existing DNS result categorization in `dns_checker.py` with stricter validation.

**Rationale**:
- Existing code already handles NXDOMAIN (NOT_LISTED) and timeouts (UNKNOWN)
- Need to add validation for A record responses outside 127.0.0.0/8 range
- Aligns with RFC 5782 (DNSBL expected response format)

**Validation Logic**:
```python
def validate_dnsbl_response(answer):
    """Validate DNSBL response per RFC 5782."""
    if not answer:  # NXDOMAIN
        return "NOT_LISTED"
    
    for rdata in answer:
        if rdata.rdtype == dns.rdatatype.A:
            ip = ipaddress.IPv4Address(rdata.address)
            if ip in ipaddress.IPv4Network("127.0.0.0/8"):
                return "LISTED"
            else:
                # Invalid response - A record outside 127.x.x.x
                return "UNKNOWN"  # Treat as failure
    
    # Non-A record response (e.g., CNAME, TXT)
    return "UNKNOWN"
```

**Failure Categorization**:
- A record outside 127.0.0.0/8: `invalid_response_range`
- Non-A record (CNAME, TXT, etc.): `invalid_response_type`
- Both counted as failures for health tracking

**Alternatives Considered**:
- **Accept any A record**: Rejected - violates RFC 5782, could mask DNSBL misconfigurations
- **Only check for NXDOMAIN**: Rejected - doesn't catch format changes or misconfigured zones

---

## Decision 5: Health Tracking Data Collection

**Context**: FR-001 requires real-time tracking for each individual IP check.

**Decision**: Use in-memory aggregator class that receives callbacks from DNS checker.

**Rationale**:
- Minimal performance overhead (simple counter increments)
- Decoupled from DNS checking logic (single responsibility)
- Enables accurate per-DNSBL failure rate calculation
- No persistent storage required (stateless per Constitution)

**Architecture**:
```python
class HealthTracker:
    def __init__(self, dnsbl_zones: List[str]):
        self._health_records: Dict[str, DNSBLHealthRecord] = {
            zone: DNSBLHealthRecord(zone=zone)
            for zone in dnsbl_zones
        }
    
    def record_check(self, zone: str, success: bool, failure_type: str | None):
        """Record a single DNS check result."""
        record = self._health_records[zone]
        record.checks_performed += 1
        if success:
            record.successful_checks += 1
        else:
            record.failed_checks += 1
            if failure_type:
                record.failure_types[failure_type] += 1
    
    def get_summary(self) -> HealthSummary:
        """Generate final health summary."""
        # Calculate failure rates, detect network issues, etc.
```

**Integration Point**: Modify `dns_checker.check_ip()` to call `tracker.record_check()` after each DNSBL query.

**Alternatives Considered**:
- **Batch collection**: Rejected - can't calculate accurate failure rates if some checks are missed
- **Log parsing**: Rejected - brittle, depends on log format stability
- **Database storage**: Rejected - violates Constitution Principle I (stateless execution)

---

## Decision 6: PyYAML Dependency

**Context**: FR-006 requires YAML output for pruned list.

**Decision**: Add `pyyaml>=6.0.1` to `pyproject.toml` dependencies.

**Rationale**:
- Standard Python library for YAML parsing/generation
- Actively maintained, secure (CVE-free in 6.0.1+)
- Zero additional transitive dependencies
- Small footprint (~200KB)

**Version Selection**: 6.0.1 minimum for CVE-2020-14343 fix (arbitrary code execution in unsafe YAML loading - not used here, but good hygiene).

**Alternatives Considered**:
- **Manual YAML generation**: Rejected - error-prone, doesn't handle edge cases (special characters, escaping)
- **ruamel.yaml**: Rejected - heavier dependency, overkill for simple list generation

---

## Decision 7: Performance Optimization

**Context**: SC-003 requires <10% execution overhead, SC-006 requires summary generation <2 seconds.

**Decision**: Use efficient data structures and minimize allocations.

**Rationale**:
- Health tracking adds ~O(n) space overhead (n = number of DNSBLs × number of IPs)
- For 30 DNSBLs × 1000 IPs = 30,000 check records
- Each record: ~100 bytes → 3MB total (negligible)
- JSON serialization: `orjson` for fast serialization (optional optimization if needed)

**Optimization Strategies**:
1. **Reuse DNSBLHealthRecord objects** (don't create per-check)
2. **Lazy evaluation**: Only calculate failure rates when generating summary
3. **Avoid string concatenation**: Use f-strings, join() for lists
4. **Batch JSON writes**: Single `json.dumps()` call at end

**Measurement Plan**: Add duration tracking to health summary generation, fail tests if >2s.

**Alternatives Considered**:
- **Streaming JSON**: Rejected - overkill for ~30 DNSBL entries, adds complexity
- **Compressed output**: Rejected - Kubernetes logs are already compressed, adds CPU overhead

---

## Decision 8: Configuration Environment Variables

**Context**: FR-007a requires configurable supplemental DNS checks.

**Decision**: Add `ENABLE_NETWORK_CONNECTIVITY_CHECK` (default: "true").

**Rationale**:
- Allows disabling supplemental checks in environments with restricted outbound DNS
- Follows existing configuration pattern (all-caps, boolean via string parsing)
- Default enabled maintains desired behavior from spec

**Configuration Schema**:
```python
@dataclass
class Config:
    # ... existing fields ...
    
    # Health Reporting (new)
    enable_network_connectivity_check: bool = True
    
    @classmethod
    def from_env(cls):
        # ... existing parsing ...
        enable_network_connectivity_check = os.getenv(
            "ENABLE_NETWORK_CONNECTIVITY_CHECK", "true"
        ).lower() in ("true", "1", "yes")
```

**Alternatives Considered**:
- **Hardcoded enabled**: Rejected - reduces flexibility for restricted environments
- **Multiple env vars for each target**: Rejected - over-engineered, unlikely to need per-target control

---

## Summary of Resolved Unknowns

| Unknown | Resolution |
|---------|------------|
| JSON structure | Nested object with execution_summary + dnsbl_health array |
| YAML format | List matching DNSBL_ZONES config structure |
| Network detection | 50% threshold + supplemental DNS to Cloudflare/Google |
| Invalid response handling | Validate A records in 127.0.0.0/8, treat others as failures |
| Health tracking timing | Real-time per-check with in-memory aggregator |
| PyYAML dependency | Add pyyaml>=6.0.1 to dependencies |
| Performance approach | Efficient data structures, lazy evaluation, <10% overhead target |
| Configuration | Add ENABLE_NETWORK_CONNECTIVITY_CHECK env var |

All research complete. Ready for Phase 1: Design & Contracts.
