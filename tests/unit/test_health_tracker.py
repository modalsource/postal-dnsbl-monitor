"""Unit tests for HealthTracker service."""

import pytest
from time import sleep

from src.services.health_tracker import HealthTracker
from src.models.dnsbl_health import NetworkConnectivityResult


class TestHealthTrackerInitialization:
    """Test HealthTracker initialization."""

    def test_init_with_zones(self):
        """Test initialization with DNSBL zones."""
        zones = ["zen.spamhaus.org", "bl.spamcop.net"]
        tracker = HealthTracker(zones)

        assert tracker._total_ip_checks == 0
        assert tracker._start_time is None
        assert len(tracker._health_records) == 2
        assert "zen.spamhaus.org" in tracker._health_records
        assert "bl.spamcop.net" in tracker._health_records

    def test_init_with_empty_zones_raises_error(self):
        """Test that empty zone list raises ValueError."""
        with pytest.raises(ValueError, match="must contain at least one zone"):
            HealthTracker([])


class TestHealthTrackerRecordCheck:
    """Test HealthTracker.record_check() method."""

    def test_record_check_success(self):
        """Test recording successful check."""
        tracker = HealthTracker(["test.dnsbl.org"])
        tracker.record_check("test.dnsbl.org", success=True)

        record = tracker._health_records["test.dnsbl.org"]
        assert record.checks_performed == 1
        assert record.successful_checks == 1
        assert record.failed_checks == 0

    def test_record_check_failure_with_type(self):
        """Test recording failed check with failure type."""
        tracker = HealthTracker(["test.dnsbl.org"])
        tracker.record_check("test.dnsbl.org", success=False, failure_type="timeout")

        record = tracker._health_records["test.dnsbl.org"]
        assert record.checks_performed == 1
        assert record.successful_checks == 0
        assert record.failed_checks == 1
        assert record.failure_types["timeout"] == 1

    def test_record_check_unknown_zone_raises_error(self):
        """Test that unknown zone raises ValueError."""
        tracker = HealthTracker(["test.dnsbl.org"])

        with pytest.raises(ValueError, match="Unknown DNSBL zone"):
            tracker.record_check("unknown.dnsbl.org", success=True)

    def test_record_check_failure_without_type_raises_error(self):
        """Test that failure without type raises ValueError."""
        tracker = HealthTracker(["test.dnsbl.org"])

        with pytest.raises(ValueError, match="failure_type is required"):
            tracker.record_check("test.dnsbl.org", success=False, failure_type=None)

    def test_record_check_maintains_invariants(self):
        """Test that counter invariants are maintained."""
        tracker = HealthTracker(["test.dnsbl.org"])

        tracker.record_check("test.dnsbl.org", success=True)
        tracker.record_check("test.dnsbl.org", success=False, failure_type="timeout")
        tracker.record_check("test.dnsbl.org", success=True)
        tracker.record_check(
            "test.dnsbl.org", success=False, failure_type="nxdomain_zone"
        )

        record = tracker._health_records["test.dnsbl.org"]
        # Invariant: checks_performed = successful_checks + failed_checks
        assert (
            record.checks_performed == record.successful_checks + record.failed_checks
        )
        assert record.checks_performed == 4
        assert record.successful_checks == 2
        assert record.failed_checks == 2


class TestHealthTrackerIPChecks:
    """Test IP check tracking."""

    def test_record_ip_check_start_increments_counter(self):
        """Test that IP check counter increments."""
        tracker = HealthTracker(["test.dnsbl.org"])

        tracker.record_ip_check_start()
        assert tracker._total_ip_checks == 1

        tracker.record_ip_check_start()
        assert tracker._total_ip_checks == 2

    def test_record_ip_check_start_sets_start_time(self):
        """Test that first IP check sets start time."""
        tracker = HealthTracker(["test.dnsbl.org"])

        assert tracker._start_time is None
        tracker.record_ip_check_start()
        assert tracker._start_time is not None


class TestHealthTrackerGetSummary:
    """Test HealthTracker.get_summary() method."""

    def test_get_summary_basic(self):
        """Test basic summary generation."""
        tracker = HealthTracker(["zen.spamhaus.org", "bl.spamcop.net"])

        tracker.record_ip_check_start()
        tracker.record_check("zen.spamhaus.org", success=True)
        tracker.record_check("bl.spamcop.net", success=True)

        summary = tracker.get_summary()

        assert summary.total_dnsbls == 2
        assert summary.broken_dnsbls == 0
        assert summary.network_issue_detected is False
        assert summary.total_ip_checks == 1

    def test_get_summary_with_broken_dnsbl(self):
        """Test summary with one broken DNSBL."""
        tracker = HealthTracker(["zen.spamhaus.org", "bl.spamcop.net"])

        tracker.record_ip_check_start()
        tracker.record_check("zen.spamhaus.org", success=True)
        tracker.record_check("bl.spamcop.net", success=False, failure_type="timeout")

        tracker.record_ip_check_start()
        tracker.record_check("zen.spamhaus.org", success=True)
        tracker.record_check("bl.spamcop.net", success=False, failure_type="timeout")

        summary = tracker.get_summary()

        assert summary.total_dnsbls == 2
        assert summary.broken_dnsbls == 1
        assert summary.total_ip_checks == 2

    def test_get_summary_network_issue_detection_below_threshold(self):
        """Test network issue not detected when below 50% threshold."""
        tracker = HealthTracker(["zone1.org", "zone2.org", "zone3.org"])

        # Only 1 out of 3 broken (33% < 50%)
        tracker.record_check("zone1.org", success=False, failure_type="timeout")
        tracker.record_check("zone2.org", success=True)
        tracker.record_check("zone3.org", success=True)

        network_result = NetworkConnectivityResult(
            check_enabled=True,
            cloudflare_reachable=False,
            google_reachable=False,
        )

        summary = tracker.get_summary(network_result)

        # Network issue should NOT be detected (below 50% threshold)
        assert summary.network_issue_detected is False

    def test_get_summary_network_issue_detection_at_threshold(self):
        """Test network issue detected at exactly 50% threshold."""
        tracker = HealthTracker(["zone1.org", "zone2.org"])

        # 1 out of 2 broken (50% threshold)
        tracker.record_check("zone1.org", success=False, failure_type="timeout")
        tracker.record_check("zone2.org", success=True)

        tracker.record_check("zone1.org", success=False, failure_type="timeout")
        tracker.record_check("zone2.org", success=True)

        network_result = NetworkConnectivityResult(
            check_enabled=True,
            cloudflare_reachable=False,
            google_reachable=False,
        )

        summary = tracker.get_summary(network_result)

        # Network issue should be detected (50% threshold + both checks failed)
        assert summary.network_issue_detected is True

    def test_get_summary_network_issue_not_detected_if_one_check_succeeds(self):
        """Test network issue not detected if one supplemental check succeeds."""
        tracker = HealthTracker(["zone1.org", "zone2.org"])

        # Both DNSBLs broken (100%)
        tracker.record_check("zone1.org", success=False, failure_type="timeout")
        tracker.record_check("zone2.org", success=False, failure_type="timeout")

        tracker.record_check("zone1.org", success=False, failure_type="timeout")
        tracker.record_check("zone2.org", success=False, failure_type="timeout")

        network_result = NetworkConnectivityResult(
            check_enabled=True,
            cloudflare_reachable=True,  # One check succeeded
            google_reachable=False,
        )

        summary = tracker.get_summary(network_result)

        # Network issue should NOT be detected (one supplemental check succeeded)
        assert summary.network_issue_detected is False

    def test_get_summary_network_issue_not_detected_if_check_disabled(self):
        """Test network issue not detected if supplemental check disabled."""
        tracker = HealthTracker(["zone1.org", "zone2.org"])

        # Both DNSBLs broken (100%)
        tracker.record_check("zone1.org", success=False, failure_type="timeout")
        tracker.record_check("zone2.org", success=False, failure_type="timeout")

        tracker.record_check("zone1.org", success=False, failure_type="timeout")
        tracker.record_check("zone2.org", success=False, failure_type="timeout")

        network_result = NetworkConnectivityResult(
            check_enabled=False,
            cloudflare_reachable=None,
            google_reachable=None,
        )

        summary = tracker.get_summary(network_result)

        # Network issue should NOT be detected (check disabled)
        assert summary.network_issue_detected is False

    def test_get_summary_execution_duration(self):
        """Test that execution duration is tracked."""
        tracker = HealthTracker(["test.dnsbl.org"])

        tracker.record_ip_check_start()
        sleep(0.1)  # Sleep 100ms

        summary = tracker.get_summary()

        # Duration should be >= 100ms
        assert summary.execution_duration_ms >= 100
