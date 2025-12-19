"""Unit tests for HealthReporter service."""

import json
import yaml
from datetime import datetime, timezone

from src.services.health_reporter import HealthReporter
from src.models.dnsbl_health import (
    DNSBLHealthRecord,
    HealthSummary,
    NetworkConnectivityResult,
)


class TestHealthReporterGenerateJSONReport:
    """Test HealthReporter.generate_json_report() method."""

    def test_generate_json_report_returns_valid_json(self):
        """Test that JSON report is valid and parseable."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")
        record.record_check(success=True)

        summary = HealthSummary(
            timestamp=datetime(2025, 12, 19, 10, 30, 0, tzinfo=timezone.utc),
            total_dnsbls=1,
            broken_dnsbls=0,
            network_issue_detected=False,
            total_ip_checks=1,
            execution_duration_ms=1000,
            dnsbl_health=[record],
            network_connectivity=None,
        )

        json_report = HealthReporter.generate_json_report(summary)

        # Should be valid JSON
        parsed = json.loads(json_report)
        assert "execution_summary" in parsed
        assert "dnsbl_health" in parsed

    def test_generate_json_report_keys_are_sorted(self):
        """Test that JSON keys are sorted for determinism."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")
        record.record_check(success=False, failure_type="timeout")
        record.record_check(success=False, failure_type="nxdomain_zone")

        summary = HealthSummary(
            timestamp=datetime.now(timezone.utc),
            total_dnsbls=1,
            broken_dnsbls=1,
            network_issue_detected=False,
            total_ip_checks=2,
            execution_duration_ms=500,
            dnsbl_health=[record],
            network_connectivity=None,
        )

        json_report = HealthReporter.generate_json_report(summary)

        # Check that JSON is sorted by comparing with re-parsed sorted version
        parsed = json.loads(json_report)
        resorted_json = json.dumps(parsed, indent=2, sort_keys=True)

        assert json_report == resorted_json

    def test_generate_json_report_pretty_printed(self):
        """Test that JSON report is pretty-printed with indentation."""
        record = DNSBLHealthRecord(zone="test.dnsbl.org")
        record.record_check(success=True)

        summary = HealthSummary(
            timestamp=datetime.now(timezone.utc),
            total_dnsbls=1,
            broken_dnsbls=0,
            network_issue_detected=False,
            total_ip_checks=1,
            execution_duration_ms=1000,
            dnsbl_health=[record],
            network_connectivity=None,
        )

        json_report = HealthReporter.generate_json_report(summary)

        # Pretty-printed JSON should contain newlines and indentation
        assert "\n" in json_report
        assert "  " in json_report  # 2-space indentation


class TestHealthReporterGeneratePrunedYAML:
    """Test HealthReporter.generate_pruned_yaml() method."""

    def test_generate_pruned_yaml_returns_valid_yaml(self):
        """Test that YAML report is valid and parseable."""
        record1 = DNSBLHealthRecord(zone="healthy.dnsbl.org")
        record1.record_check(success=True)

        record2 = DNSBLHealthRecord(zone="broken.dnsbl.org")
        record2.record_check(success=False, failure_type="timeout")

        yaml_report = HealthReporter.generate_pruned_yaml([record1, record2])

        # Extract YAML content (skip comment lines)
        yaml_lines = [
            line for line in yaml_report.split("\n") if not line.startswith("#")
        ]
        yaml_content = "\n".join(yaml_lines)

        # Should be valid YAML
        parsed = yaml.safe_load(yaml_content)
        assert "dnsbl_zones" in parsed
        assert isinstance(parsed["dnsbl_zones"], list)

    def test_generate_pruned_yaml_excludes_broken_zones(self):
        """Test that broken zones are excluded from pruned list."""
        record1 = DNSBLHealthRecord(zone="healthy.dnsbl.org")
        record1.record_check(success=True)

        record2 = DNSBLHealthRecord(zone="broken.dnsbl.org")
        record2.record_check(success=False, failure_type="timeout")

        yaml_report = HealthReporter.generate_pruned_yaml([record1, record2])

        # Extract YAML content
        yaml_lines = [
            line for line in yaml_report.split("\n") if not line.startswith("#")
        ]
        yaml_content = "\n".join(yaml_lines)
        parsed = yaml.safe_load(yaml_content)

        # Only healthy zone should be included
        assert parsed["dnsbl_zones"] == ["healthy.dnsbl.org"]

    def test_generate_pruned_yaml_includes_header_comments(self):
        """Test that YAML includes header comments."""
        record = DNSBLHealthRecord(zone="healthy.dnsbl.org")
        record.record_check(success=True)

        yaml_report = HealthReporter.generate_pruned_yaml([record])

        # Should contain header comments
        assert "# Suggested DNSBL Configuration" in yaml_report
        assert "# Generated:" in yaml_report
        assert "# Removed:" in yaml_report

    def test_generate_pruned_yaml_shows_removed_zones_in_header(self):
        """Test that removed zones are listed in header comment."""
        record1 = DNSBLHealthRecord(zone="healthy.dnsbl.org")
        record1.record_check(success=True)

        record2 = DNSBLHealthRecord(zone="broken.dnsbl.org")
        record2.record_check(success=False, failure_type="timeout")

        yaml_report = HealthReporter.generate_pruned_yaml([record1, record2])

        # Removed zone should be in header comment
        assert "# Removed: broken.dnsbl.org" in yaml_report

    def test_generate_pruned_yaml_shows_none_when_all_healthy(self):
        """Test that 'None' is shown when no zones are removed."""
        record = DNSBLHealthRecord(zone="healthy.dnsbl.org")
        record.record_check(success=True)

        yaml_report = HealthReporter.generate_pruned_yaml([record])

        # Should show "None" for removed zones
        assert "# Removed: None" in yaml_report

    def test_generate_pruned_yaml_zones_are_sorted(self):
        """Test that healthy zones are sorted alphabetically."""
        record1 = DNSBLHealthRecord(zone="zen.spamhaus.org")
        record1.record_check(success=True)

        record2 = DNSBLHealthRecord(zone="bl.spamcop.net")
        record2.record_check(success=True)

        record3 = DNSBLHealthRecord(zone="dnsbl.sorbs.net")
        record3.record_check(success=True)

        yaml_report = HealthReporter.generate_pruned_yaml([record1, record2, record3])

        # Extract YAML content
        yaml_lines = [
            line for line in yaml_report.split("\n") if not line.startswith("#")
        ]
        yaml_content = "\n".join(yaml_lines)
        parsed = yaml.safe_load(yaml_content)

        zones = parsed["dnsbl_zones"]
        # Should be sorted: bl.spamcop.net, dnsbl.sorbs.net, zen.spamhaus.org
        assert zones == sorted(zones)

    def test_generate_pruned_yaml_with_healthy_and_broken_separation(self):
        """Test that healthy and broken zones are properly separated."""
        records = [
            DNSBLHealthRecord(zone="zone1.org"),
            DNSBLHealthRecord(zone="zone2.org"),
            DNSBLHealthRecord(zone="zone3.org"),
        ]

        # zone1: healthy
        records[0].record_check(success=True)

        # zone2: broken
        records[1].record_check(success=False, failure_type="timeout")

        # zone3: healthy
        records[2].record_check(success=True)

        yaml_report = HealthReporter.generate_pruned_yaml(records)

        # Extract YAML content
        yaml_lines = [
            line for line in yaml_report.split("\n") if not line.startswith("#")
        ]
        yaml_content = "\n".join(yaml_lines)
        parsed = yaml.safe_load(yaml_content)

        # Should include only zone1 and zone3
        assert set(parsed["dnsbl_zones"]) == {"zone1.org", "zone3.org"}
        assert "# Removed: zone2.org" in yaml_report
