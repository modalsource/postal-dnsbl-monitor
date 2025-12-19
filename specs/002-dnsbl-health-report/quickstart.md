# Quickstart: DNSBL Health Report

**Feature**: 002-dnsbl-health-report  
**Date**: 2025-12-19  
**Audience**: Developers implementing this feature

## Overview

This quickstart provides step-by-step guidance for implementing DNSBL health tracking and reporting. Follow the phases in order to ensure all components integrate correctly.

---

## Prerequisites

1. **Existing codebase**: postal-dnsbl-monitor (feature 001) is functional
2. **Python 3.14** with uv dependency manager
3. **Development dependencies**: pytest, pytest-cov installed
4. **Familiarity**: Understanding of existing DNS checking flow in `src/services/dns_checker.py`

---

## Phase 1: Data Models (Estimated: 1-2 hours)

### Step 1.1: Create `src/models/dnsbl_health.py`

Implement the core health tracking models:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List

@dataclass
class DNSBLHealthRecord:
    """Tracks health metrics for a single DNSBL zone."""
    zone: str
    checks_performed: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    failure_types: Dict[str, int] = field(default_factory=lambda: {
        "timeout": 0,
        "nxdomain_zone": 0,
        "invalid_response_range": 0,
        "invalid_response_type": 0,
        "unknown_error": 0
    })
    
    @property
    def failure_rate(self) -> float:
        """Compute failure rate (0.0 to 1.0)."""
        if self.checks_performed == 0:
            return 0.0
        return self.failed_checks / self.checks_performed
    
    @property
    def status(self) -> str:
        """Compute status: 'healthy' or 'broken'."""
        return "broken" if self.failure_rate == 1.0 else "healthy"

@dataclass
class NetworkConnectivityResult:
    """Supplemental DNS connectivity check results."""
    check_enabled: bool
    cloudflare_reachable: bool | None = None
    google_reachable: bool | None = None
    
    def to_json(self) -> dict:
        return {
            "check_enabled": self.check_enabled,
            "cloudflare_reachable": self.cloudflare_reachable,
            "google_reachable": self.google_reachable
        }

@dataclass
class HealthSummary:
    """Aggregated health summary for all DNSBLs."""
    timestamp: datetime
    total_dnsbls: int
    broken_dnsbls: int
    network_issue_detected: bool
    total_ip_checks: int
    execution_duration_ms: int
    dnsbl_health: List[DNSBLHealthRecord]
    network_connectivity: NetworkConnectivityResult | None
    
    def to_json(self) -> dict:
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

@dataclass
class PrunedConfiguration:
    """YAML-formatted suggested DNSBL list."""
    healthy_zones: List[str]
    removed_zones: List[str]
    generated_at: datetime
    
    def to_yaml(self) -> str:
        import yaml
        header = [
            "# Suggested DNSBL Configuration (Broken endpoints removed)",
            f"# Generated: {self.generated_at.isoformat()}",
            f"# Removed: {', '.join(sorted(self.removed_zones)) if self.removed_zones else 'None'}",
        ]
        yaml_dict = {"dnsbl_zones": sorted(self.healthy_zones)}
        yaml_output = yaml.safe_dump(yaml_dict, default_flow_style=False, sort_keys=False)
        return "\n".join(header) + "\n" + yaml_output
```

### Step 1.2: Write unit tests

Create `tests/unit/test_dnsbl_health.py`:

```python
from src.models.dnsbl_health import DNSBLHealthRecord

def test_failure_rate_calculation():
    record = DNSBLHealthRecord(zone="test.dnsbl.org")
    record.checks_performed = 100
    record.successful_checks = 90
    record.failed_checks = 10
    
    assert record.failure_rate == 0.1
    assert record.status == "healthy"

def test_broken_status():
    record = DNSBLHealthRecord(zone="broken.dnsbl.org")
    record.checks_performed = 50
    record.failed_checks = 50
    
    assert record.failure_rate == 1.0
    assert record.status == "broken"

# Add more tests for edge cases...
```

**Validation**: Run `pytest tests/unit/test_dnsbl_health.py` - all tests pass.

---

## Phase 2: Health Tracking Service (Estimated: 2-3 hours)

### Step 2.1: Create `src/services/health_tracker.py`

Implement the in-memory health aggregator:

```python
from typing import Dict, List
from datetime import datetime, timezone
from src.models.dnsbl_health import DNSBLHealthRecord, HealthSummary, NetworkConnectivityResult

class HealthTracker:
    """Aggregates DNSBL health data in real-time."""
    
    def __init__(self, dnsbl_zones: List[str]):
        self._health_records: Dict[str, DNSBLHealthRecord] = {
            zone: DNSBLHealthRecord(zone=zone)
            for zone in dnsbl_zones
        }
        self._start_time = datetime.now(timezone.utc)
        self._total_ip_checks = 0
    
    def record_check(self, zone: str, success: bool, failure_type: str | None = None):
        """Record a single DNS check result."""
        if zone not in self._health_records:
            raise ValueError(f"Unknown DNSBL zone: {zone}")
        
        record = self._health_records[zone]
        record.checks_performed += 1
        
        if success:
            record.successful_checks += 1
        else:
            record.failed_checks += 1
            if failure_type:
                if failure_type in record.failure_types:
                    record.failure_types[failure_type] += 1
                else:
                    record.failure_types["unknown_error"] += 1
    
    def record_ip_check_start(self):
        """Increment total IP check counter."""
        self._total_ip_checks += 1
    
    def get_summary(self, network_connectivity: NetworkConnectivityResult | None = None) -> HealthSummary:
        """Generate final health summary."""
        health_records = list(self._health_records.values())
        broken_count = sum(1 for r in health_records if r.status == "broken")
        total_dnsbls = len(health_records)
        
        # Network issue detection (50% threshold + supplemental checks)
        network_issue = False
        if total_dnsbls > 0 and broken_count / total_dnsbls >= 0.5:
            if network_connectivity and network_connectivity.check_enabled:
                # Both targets failed = network issue
                network_issue = not (network_connectivity.cloudflare_reachable or 
                                    network_connectivity.google_reachable)
        
        execution_duration = int((datetime.now(timezone.utc) - self._start_time).total_seconds() * 1000)
        
        return HealthSummary(
            timestamp=datetime.now(timezone.utc),
            total_dnsbls=total_dnsbls,
            broken_dnsbls=broken_count,
            network_issue_detected=network_issue,
            total_ip_checks=self._total_ip_checks,
            execution_duration_ms=execution_duration,
            dnsbl_health=health_records,
            network_connectivity=network_connectivity
        )
```

### Step 2.2: Write unit tests

Create `tests/unit/test_health_tracker.py`:

```python
from src.services.health_tracker import HealthTracker

def test_record_check_success():
    tracker = HealthTracker(["zen.spamhaus.org", "bl.spamcop.net"])
    
    tracker.record_check("zen.spamhaus.org", success=True)
    tracker.record_check("bl.spamcop.net", success=True)
    
    summary = tracker.get_summary()
    assert summary.total_dnsbls == 2
    assert summary.broken_dnsbls == 0

def test_network_issue_detection():
    from src.models.dnsbl_health import NetworkConnectivityResult
    
    tracker = HealthTracker(["zone1.org", "zone2.org"])
    
    # 100% failure on both zones
    tracker.record_check("zone1.org", success=False, failure_type="timeout")
    tracker.record_check("zone2.org", success=False, failure_type="timeout")
    
    # Supplemental checks also failed
    net_result = NetworkConnectivityResult(
        check_enabled=True,
        cloudflare_reachable=False,
        google_reachable=False
    )
    
    summary = tracker.get_summary(network_connectivity=net_result)
    assert summary.network_issue_detected is True

# Add more tests...
```

**Validation**: Run `pytest tests/unit/test_health_tracker.py` - all tests pass.

---

## Phase 3: Network Connectivity Checker (Estimated: 1 hour)

### Step 3.1: Create `src/utils/network_check.py`

```python
import dns.resolver
from src.models.dnsbl_health import NetworkConnectivityResult

class NetworkChecker:
    """Performs supplemental DNS connectivity checks."""
    
    CLOUDFLARE_DNS = "1.1.1.1"
    GOOGLE_DNS = "8.8.8.8"
    TEST_DOMAIN = "google.com"
    
    @staticmethod
    def check_connectivity(timeout: int = 5) -> NetworkConnectivityResult:
        """Check DNS connectivity to cloud providers."""
        
        def check_resolver(nameserver: str) -> bool:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [nameserver]
            resolver.timeout = timeout
            resolver.lifetime = timeout
            
            try:
                answers = resolver.resolve(NetworkChecker.TEST_DOMAIN, "A")
                return len(answers) > 0
            except (dns.exception.Timeout, dns.resolver.NXDOMAIN, 
                    dns.resolver.NoAnswer, dns.resolver.NoNameservers):
                return False
            except Exception:
                # Catch-all for unexpected DNS errors
                return False
        
        return NetworkConnectivityResult(
            check_enabled=True,
            cloudflare_reachable=check_resolver(NetworkChecker.CLOUDFLARE_DNS),
            google_reachable=check_resolver(NetworkChecker.GOOGLE_DNS)
        )
```

### Step 3.2: Write unit tests

Create `tests/unit/test_network_check.py` (use mocking for DNS queries).

---

## Phase 4: Health Reporter (Estimated: 1 hour)

### Step 4.1: Create `src/services/health_reporter.py`

```python
import json
from typing import List
from datetime import datetime, timezone
from src.models.dnsbl_health import HealthSummary, DNSBLHealthRecord, PrunedConfiguration

class HealthReporter:
    """Generates JSON and YAML output from health data."""
    
    @staticmethod
    def generate_json_report(summary: HealthSummary) -> str:
        """Generate JSON-formatted health summary."""
        return json.dumps(summary.to_json(), indent=2, sort_keys=True)
    
    @staticmethod
    def generate_pruned_yaml(health_records: List[DNSBLHealthRecord]) -> str:
        """Generate YAML-formatted pruned DNSBL list."""
        healthy = [r.zone for r in health_records if r.status == "healthy"]
        broken = [r.zone for r in health_records if r.status == "broken"]
        
        pruned_config = PrunedConfiguration(
            healthy_zones=healthy,
            removed_zones=broken,
            generated_at=datetime.now(timezone.utc)
        )
        
        return pruned_config.to_yaml()
```

### Step 4.2: Write unit tests

Create `tests/unit/test_health_reporter.py`.

---

## Phase 5: Integration with Main Flow (Estimated: 2 hours)

### Step 5.1: Update `src/config.py`

Add new configuration field:

```python
@dataclass
class Config:
    # ... existing fields ...
    
    # Health Reporting
    enable_network_connectivity_check: bool = True
    
    @classmethod
    def from_env(cls):
        # ... existing parsing ...
        
        enable_network_connectivity_check = os.getenv(
            "ENABLE_NETWORK_CONNECTIVITY_CHECK", "true"
        ).lower() in ("true", "1", "yes")
        
        return cls(
            # ... existing args ...
            enable_network_connectivity_check=enable_network_connectivity_check
        )
```

### Step 5.2: Update `src/services/dns_checker.py`

Add health tracking hooks:

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
            return "nxdomain_zone"
        elif result.status == DNSResultStatus.UNKNOWN:
            # Determine if invalid_response_range or invalid_response_type
            # based on validation logic
            return "invalid_response_range"  # Simplified
        else:
            return "unknown_error"
```

### Step 5.3: Update `src/main.py`

Integrate health tracking into main execution flow:

```python
from src.services.health_tracker import HealthTracker
from src.services.health_reporter import HealthReporter
from src.utils.network_check import NetworkChecker

def main():
    config = Config.from_env()
    
    # Initialize health tracker
    health_tracker = HealthTracker(config.dnsbl_zones)
    
    # Initialize DNS checker with health tracker
    dns_checker = DNSChecker(
        zones=config.dnsbl_zones,
        timeout=config.dns_timeout,
        health_tracker=health_tracker
    )
    
    # Existing IP checking loop
    for ip_record in fetch_ips_to_check():
        health_tracker.record_ip_check_start()
        results = dns_checker.check_ip(ip_record.ip)
        # ... existing processing ...
    
    # NEW: Generate health report
    network_result = None
    if config.enable_network_connectivity_check:
        network_result = NetworkChecker.check_connectivity()
    
    summary = health_tracker.get_summary(network_connectivity=network_result)
    
    # Output JSON health summary
    json_report = HealthReporter.generate_json_report(summary)
    logger.info("DNSBL Health Summary", extra={"health_summary": json.loads(json_report)})
    
    # Output YAML pruned list
    yaml_report = HealthReporter.generate_pruned_yaml(summary.dnsbl_health)
    logger.info("Suggested Pruned DNSBL Configuration:\\n" + yaml_report)
```

---

## Phase 6: Contract Testing (Estimated: 1 hour)

### Step 6.1: Create `tests/contract/test_health_output.py`

Validate JSON schema compliance:

```python
import json
import jsonschema
from pathlib import Path

def test_json_schema_validation():
    # Load schema
    schema_path = Path("specs/002-dnsbl-health-report/contracts/health-summary-schema.json")
    with open(schema_path) as f:
        schema = json.load(f)
    
    # Generate sample health summary
    from src.services.health_tracker import HealthTracker
    tracker = HealthTracker(["zen.spamhaus.org"])
    tracker.record_check("zen.spamhaus.org", success=True)
    summary = tracker.get_summary()
    
    # Validate against schema
    json_output = summary.to_json()
    jsonschema.validate(instance=json_output, schema=schema)  # Raises if invalid

def test_yaml_format_parseable():
    import yaml
    from src.services.health_reporter import HealthReporter
    from src.models.dnsbl_health import DNSBLHealthRecord
    
    records = [DNSBLHealthRecord(zone="test.org")]
    yaml_output = HealthReporter.generate_pruned_yaml(records)
    
    # Verify YAML is parseable
    parsed = yaml.safe_load(yaml_output)
    assert "dnsbl_zones" in parsed
    assert "test.org" in parsed["dnsbl_zones"]
```

---

## Phase 7: Integration Testing (Estimated: 2 hours)

### Step 7.1: Create `tests/integration/test_health_tracking.py`

End-to-end test with mocked DNS responses:

```python
import pytest
from unittest.mock import Mock, patch
from src.main import main

def test_end_to_end_health_tracking(monkeypatch):
    # Mock configuration
    monkeypatch.setenv("DNSBL_ZONES", "zen.spamhaus.org,broken.dnsbl.org")
    monkeypatch.setenv("ENABLE_NETWORK_CONNECTIVITY_CHECK", "true")
    
    # Mock DNS responses (zen healthy, broken fails)
    with patch("src.services.dns_checker.DNSChecker._query_zone") as mock_query:
        def side_effect(ip, zone):
            if zone == "broken.dnsbl.org":
                return DNSResult(status=DNSResultStatus.UNKNOWN, error=dns.exception.Timeout())
            else:
                return DNSResult(status=DNSResultStatus.NOT_LISTED)
        
        mock_query.side_effect = side_effect
        
        # Run main (capture logs)
        with pytest.raises(SystemExit):  # main() calls sys.exit()
            main()
        
        # Verify health summary was logged
        # (Use log capture fixture to assert JSON output structure)
```

---

## Phase 8: Dependencies and Documentation (Estimated: 30 min)

### Step 8.1: Update `pyproject.toml`

Add PyYAML dependency:

```toml
[project]
dependencies = [
    "dnspython>=2.4.0",
    "jira>=3.5.0",
    "mysql-connector-python>=8.0.0",
    "python-json-logger>=2.0.0",
    "pyyaml>=6.0.1",  # NEW
]
```

### Step 8.2: Add jsonschema to dev dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "testcontainers>=3.7.0",
    "responses>=0.23.0",
    "ruff>=0.8.0",
    "jsonschema>=4.17.0",  # NEW - for contract tests
]
```

### Step 8.3: Run dependency sync

```bash
uv sync
```

---

## Validation Checklist

Before considering the implementation complete:

- [ ] All unit tests pass (`pytest tests/unit/`)
- [ ] All contract tests pass (`pytest tests/contract/`)
- [ ] Integration test passes (`pytest tests/integration/`)
- [ ] JSON output validates against schema
- [ ] YAML output is parseable and matches config format
- [ ] Health tracking adds <10% execution overhead (benchmark)
- [ ] Health summary generates in <2 seconds (benchmark)
- [ ] Network issue detection works with 50% threshold
- [ ] Supplemental DNS checks can be disabled via env var
- [ ] Code passes ruff linting (`ruff check .`)
- [ ] Constitution compliance verified (no violations)

---

## Expected Deliverables

1. **New files**:
   - `src/models/dnsbl_health.py`
   - `src/services/health_tracker.py`
   - `src/services/health_reporter.py`
   - `src/utils/network_check.py`
   - `tests/unit/test_dnsbl_health.py`
   - `tests/unit/test_health_tracker.py`
   - `tests/unit/test_health_reporter.py`
   - `tests/unit/test_network_check.py`
   - `tests/contract/test_health_output.py`
   - `tests/integration/test_health_tracking.py`

2. **Modified files**:
   - `src/config.py` (add ENABLE_NETWORK_CONNECTIVITY_CHECK)
   - `src/services/dns_checker.py` (add health tracking hooks)
   - `src/main.py` (integrate health reporting)
   - `pyproject.toml` (add pyyaml, jsonschema dependencies)

3. **Test coverage**: ≥90% for new modules

---

## Troubleshooting

### Issue: Health summary not appearing in logs

**Solution**: Verify `logger.info()` calls are using structured logging. Check that `python-json-logger` is configured correctly.

### Issue: YAML output malformed

**Solution**: Ensure `yaml.safe_dump()` uses `default_flow_style=False` and `sort_keys=False` for list format.

### Issue: Network connectivity checks timing out

**Solution**: Increase timeout in `NetworkChecker.check_connectivity()` or disable via `ENABLE_NETWORK_CONNECTIVITY_CHECK=false`.

### Issue: JSON schema validation fails

**Solution**: Check that all required fields are present in `HealthSummary.to_json()`. Verify `sorted()` is used for deterministic ordering.

---

## Next Steps

After completing implementation:

1. Run full test suite: `pytest --cov=src tests/`
2. Review coverage report: Ensure ≥90% for new modules
3. Manual testing: Run against production-like DNSBL configuration
4. Update RUNBOOK.md with health report interpretation guide
5. Create /speckit.tasks breakdown (Phase 2 command - separate from this plan)

**Estimated Total Time**: 10-12 hours for full implementation and testing.
