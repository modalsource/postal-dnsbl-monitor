"""Unit tests for DNSBL health data models."""

import pytest
from datetime import datetime, timezone

from src.models.dnsbl_health import (
    DNSBLHealthRecord,
    HealthSummary,
    NetworkConnectivityResult,
    PrunedConfiguration,
)


class TestDNSBLHealthRecord:
    """Test DNSBLHealthRecord model behavior."""

    def test_initial_state(self):
        """Test that new record starts with zero counters."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")

        assert record.zone == "test.dnsbl.org"
        assert record.checks_performed == 0
        assert record.successful_checks == 0
        assert record.failed_checks == 0
        assert record.failure_types == {}
        assert record.failure_rate == 0.0
        assert record.status == "healthy"  # No failures yet

    def test_record_check_success_increments_counters(self):
        """Test that successful check increments correct counters."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")
        record.record_check(success=True)

        assert record.checks_performed == 1
        assert record.successful_checks == 1
        assert record.failed_checks == 0
        assert record.failure_rate == 0.0

    def test_record_check_failure_increments_counters(self):
        """Test that failed check increments correct counters."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")
        record.record_check(success=False, failure_type="timeout")

        assert record.checks_performed == 1
        assert record.successful_checks == 0
        assert record.failed_checks == 1
        assert record.failure_types["timeout"] == 1
        assert record.failure_rate == 1.0

    def test_counter_invariant_maintained(self):
        """Test that checks_performed = successful_checks + failed_checks."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")

        record.record_check(success=True)
        record.record_check(success=False, failure_type="timeout")
        record.record_check(success=True)
        record.record_check(success=False, failure_type="nxdomain_zone")

        assert (
            record.checks_performed == record.successful_checks + record.failed_checks
        )
        assert record.checks_performed == 4
        assert record.successful_checks == 2
        assert record.failed_checks == 2

    def test_failure_types_accounting(self):
        """Test that sum(failure_types.values()) == failed_checks."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")

        record.record_check(success=False, failure_type="timeout")
        record.record_check(success=False, failure_type="timeout")
        record.record_check(success=False, failure_type="nxdomain_zone")
        record.record_check(success=False, failure_type="invalid_response_range")

        assert sum(record.failure_types.values()) == record.failed_checks
        assert record.failure_types["timeout"] == 2
        assert record.failure_types["nxdomain_zone"] == 1
        assert record.failure_types["invalid_response_range"] == 1


class TestNetworkConnectivityResult:
    """Test NetworkConnectivityResult model."""

    def test_to_json_with_check_enabled(self):
        """Test JSON serialization when checks are enabled."""
        result = NetworkConnectivityResult(
            check_enabled=True,
            cloudflare_reachable=True,
            google_reachable=False,
        )

        json_output = result.to_json()

        assert json_output["check_enabled"] is True
        assert json_output["cloudflare_reachable"] is True
        assert json_output["google_reachable"] is False

    def test_to_json_with_check_disabled(self):
        """Test JSON serialization when checks are disabled."""
        result = NetworkConnectivityResult(
            check_enabled=False,
            cloudflare_reachable=None,
            google_reachable=None,
        )

        json_output = result.to_json()

        assert json_output["check_enabled"] is False
        assert json_output["cloudflare_reachable"] is None
        assert json_output["google_reachable"] is None


class TestHealthSummary:
    """Test HealthSummary model."""

    def test_to_json_structure(self):
        """Test that to_json returns expected structure."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")
        record.record_check(success=True)

        network_result = NetworkConnectivityResult(
            check_enabled=True,
            cloudflare_reachable=True,
            google_reachable=True,
        )

        summary = HealthSummary(
            timestamp=datetime(2025, 12, 19, 10, 30, 0, tzinfo=timezone.utc),
            total_dnsbls=1,
            broken_dnsbls=0,
            network_issue_detected=False,
            total_ip_checks=1,
            execution_duration_ms=1000,
            dnsbl_health=[record],
            network_connectivity=network_result,
        )

        json_output = summary.to_json()

        assert "execution_summary" in json_output
        assert "dnsbl_health" in json_output
        assert "network_connectivity" in json_output
        assert json_output["execution_summary"]["total_dnsbls"] == 1
        assert json_output["execution_summary"]["broken_dnsbls"] == 0

    def test_dnsbl_health_sorted_by_zone(self):
        """Test that dnsbl_health array is sorted alphabetically by zone."""
        record1 = DNSBLHealthRecord(zone="zen.spamhaus.org")
        record2 = DNSBLHealthRecord(zone="bl.spamcop.net")
        record3 = DNSBLHealthRecord(zone="dnsbl.sorbs.net")

        # Add in unsorted order
        summary = HealthSummary(
            timestamp=datetime.now(timezone.utc),
            total_dnsbls=3,
            broken_dnsbls=0,
            network_issue_detected=False,
            total_ip_checks=0,
            execution_duration_ms=1000,
            dnsbl_health=[record1, record2, record3],
            network_connectivity=None,
        )

        json_output = summary.to_json()
        zones = [r["zone"] for r in json_output["dnsbl_health"]]

        # Should be sorted: bl.spamcop.net, dnsbl.sorbs.net, zen.spamhaus.org
        assert zones == sorted(zones)


class TestPrunedConfiguration:
    """Test PrunedConfiguration model."""

    def test_to_yaml_format(self):
        """Test that to_yaml generates valid YAML with header comments."""
        pruned = PrunedConfiguration(
            healthy_zones=["bl.spamcop.net", "zen.spamhaus.org"],
            removed_zones=["broken.dnsbl.org"],
            generated_at=datetime(2025, 12, 19, 10, 30, 0, tzinfo=timezone.utc),
        )

        yaml_output = pruned.to_yaml()

        # Check header comments exist
        assert "# Suggested DNSBL Configuration" in yaml_output
        assert "# Generated: 2025-12-19T10:30:00+00:00" in yaml_output
        assert "# Removed: broken.dnsbl.org" in yaml_output

        # Parse YAML to verify structure
        import yaml

        yaml_lines = yaml_output.split("\n")
        yaml_content = "\n".join(
            [line for line in yaml_lines if not line.startswith("#")]
        )
        parsed = yaml.safe_load(yaml_content)

        assert "dnsbl_zones" in parsed
        assert parsed["dnsbl_zones"] == ["bl.spamcop.net", "zen.spamhaus.org"]

    def test_to_yaml_with_no_removed_zones(self):
        """Test YAML generation when all zones are healthy."""
        pruned = PrunedConfiguration(
            healthy_zones=["bl.spamcop.net", "zen.spamhaus.org"],
            removed_zones=[],
            generated_at=datetime(2025, 12, 19, 10, 30, 0, tzinfo=timezone.utc),
        )

        yaml_output = pruned.to_yaml()

        # Should show "None" for removed zones
        assert "# Removed: None" in yaml_output

    def test_to_yaml_zones_are_sorted(self):
        """Test that healthy_zones are sorted in YAML output."""
        pruned = PrunedConfiguration(
            healthy_zones=["zen.spamhaus.org", "bl.spamcop.net", "dnsbl.sorbs.net"],
            removed_zones=[],
            generated_at=datetime.now(timezone.utc),
        )

        yaml_output = pruned.to_yaml()

        import yaml

        yaml_lines = yaml_output.split("\n")
        yaml_content = "\n".join(
            [line for line in yaml_lines if not line.startswith("#")]
        )
        parsed = yaml.safe_load(yaml_content)

        zones = parsed["dnsbl_zones"]
        assert zones == sorted(zones)
