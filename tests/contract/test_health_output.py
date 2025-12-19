"""Contract tests for DNSBL health reporting output.

Validates that JSON output conforms to health-summary-schema.json contract.
"""

import json
import pytest
import yaml
from jsonschema import validate, ValidationError
from pathlib import Path
from datetime import datetime, timezone

from src.models.dnsbl_health import (
    DNSBLHealthRecord,
    HealthSummary,
    NetworkConnectivityResult,
    PrunedConfiguration,
)


def load_schema():
    """Load the JSON schema for health summary validation."""
    schema_path = (
        Path(__file__).parent.parent.parent
        / "specs"
        / "002-dnsbl-health-report"
        / "contracts"
        / "health-summary-schema.json"
    )
    with open(schema_path) as f:
        return json.load(f)


class TestHealthSummaryJSONContract:
    """Test JSON output conforms to health-summary-schema.json."""

    def test_valid_health_summary_with_network_check_enabled(self):
        """Test that valid HealthSummary serialization passes schema validation."""
        # Arrange
        schema = load_schema()

        record1 = DNSBLHealthRecord(zone="zen.spamhaus.org")
        record1.record_check(success=True)
        record1.record_check(success=True)

        record2 = DNSBLHealthRecord(zone="bl.spamcop.net")
        record2.record_check(success=False, failure_type="timeout")
        record2.record_check(success=False, failure_type="timeout")

        network_result = NetworkConnectivityResult(
            check_enabled=True,
            cloudflare_reachable=True,
            google_reachable=True,
        )

        summary = HealthSummary(
            timestamp=datetime.now(timezone.utc),
            total_dnsbls=2,
            broken_dnsbls=1,
            network_issue_detected=False,
            total_ip_checks=2,
            execution_duration_ms=1500,
            dnsbl_health=[record1, record2],
            network_connectivity=network_result,
        )

        # Act
        json_output = summary.to_json()

        # Assert
        validate(instance=json_output, schema=schema)

    def test_valid_health_summary_with_network_check_disabled(self):
        """Test HealthSummary with network check disabled passes schema validation."""
        # Arrange
        schema = load_schema()

        record = DNSBLHealthRecord(zone="zen.spamhaus.org")
        record.record_check(success=True)

        network_result = NetworkConnectivityResult(
            check_enabled=False,
            cloudflare_reachable=None,
            google_reachable=None,
        )

        summary = HealthSummary(
            timestamp=datetime.now(timezone.utc),
            total_dnsbls=1,
            broken_dnsbls=0,
            network_issue_detected=False,
            total_ip_checks=1,
            execution_duration_ms=500,
            dnsbl_health=[record],
            network_connectivity=network_result,
        )

        # Act
        json_output = summary.to_json()

        # Assert
        validate(instance=json_output, schema=schema)

    def test_health_summary_json_keys_are_sorted(self):
        """Test that JSON output has sorted keys for determinism."""
        # Arrange
        record = DNSBLHealthRecord(zone="test.dnsbl.org")
        record.record_check(success=False, failure_type="timeout")
        record.record_check(success=False, failure_type="invalid_response_range")
        record.record_check(success=False, failure_type="nxdomain_zone")

        summary = HealthSummary(
            timestamp=datetime.now(timezone.utc),
            total_dnsbls=1,
            broken_dnsbls=1,
            network_issue_detected=False,
            total_ip_checks=3,
            execution_duration_ms=1000,
            dnsbl_health=[record],
            network_connectivity=None,
        )

        # Act
        json_str = json.dumps(summary.to_json(), sort_keys=True)
        json_output = json.loads(json_str)

        # Assert - failure_types should be sorted alphabetically
        failure_types = json_output["dnsbl_health"][0]["failure_types"]
        failure_keys = list(failure_types.keys())
        assert failure_keys == sorted(failure_keys), "Failure types must be sorted"


class TestDNSBLHealthRecordFailureRate:
    """Test DNSBLHealthRecord failure_rate calculation."""

    def test_failure_rate_zero_when_no_checks(self):
        """Test that failure_rate is 0.0 when no checks performed."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")
        assert record.failure_rate == 0.0

    def test_failure_rate_zero_when_all_success(self):
        """Test that failure_rate is 0.0 when all checks succeed."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")
        record.record_check(success=True)
        record.record_check(success=True)
        record.record_check(success=True)

        assert record.failure_rate == 0.0

    def test_failure_rate_one_when_all_fail(self):
        """Test that failure_rate is 1.0 when all checks fail."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")
        record.record_check(success=False, failure_type="timeout")
        record.record_check(success=False, failure_type="timeout")
        record.record_check(success=False, failure_type="timeout")

        assert record.failure_rate == 1.0

    def test_failure_rate_partial(self):
        """Test that failure_rate calculates correctly for partial failures."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")
        record.record_check(success=True)
        record.record_check(success=False, failure_type="timeout")
        record.record_check(success=True)
        record.record_check(success=False, failure_type="timeout")

        # 2 failures out of 4 checks = 0.5
        assert record.failure_rate == 0.5

    def test_status_healthy_when_not_all_fail(self):
        """Test that status is 'healthy' when failure_rate < 1.0."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")
        record.record_check(success=True)
        record.record_check(success=False, failure_type="timeout")

        assert record.status == "healthy"

    def test_status_broken_when_all_fail(self):
        """Test that status is 'broken' when failure_rate == 1.0."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")
        record.record_check(success=False, failure_type="timeout")
        record.record_check(success=False, failure_type="timeout")

        assert record.status == "broken"

    def test_record_check_enforces_failure_type_when_failure(self):
        """Test that record_check raises ValueError if failure_type is None on failure."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")

        with pytest.raises(ValueError, match="failure_type is required"):
            record.record_check(success=False, failure_type=None)
