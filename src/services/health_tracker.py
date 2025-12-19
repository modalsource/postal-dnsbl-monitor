"""Health tracking service for DNSBL endpoint monitoring.

Aggregates health data in real-time during execution and generates
summary reports at the end.
"""

from datetime import datetime, timezone
from typing import List, Dict
from time import time

from src.models.dnsbl_health import (
    DNSBLHealthRecord,
    HealthSummary,
    NetworkConnectivityResult,
)


class HealthTracker:
    """Tracks DNSBL health metrics during execution.

    Aggregates real-time DNS check results to generate end-of-execution
    health summaries showing which DNSBLs are broken and why.

    Attributes:
        _health_records: Dict mapping zone name to DNSBLHealthRecord.
        _start_time: Timestamp of first check (for duration tracking).
        _total_ip_checks: Total number of unique IP addresses checked.

    Example:
        >>> tracker = HealthTracker(["zen.spamhaus.org", "bl.spamcop.net"])
        >>> tracker.record_ip_check_start()
        >>> tracker.record_check("zen.spamhaus.org", success=True)
        >>> tracker.record_check("bl.spamcop.net", success=False, failure_type="timeout")
        >>> summary = tracker.get_summary()
        >>> print(summary.broken_dnsbls)
        0
    """

    def __init__(self, dnsbl_zones: List[str]):
        """Initialize health tracker with configured DNSBL zones.

        Args:
            dnsbl_zones: List of DNSBL zone names to track.

        Raises:
            ValueError: If dnsbl_zones is empty.
        """
        if not dnsbl_zones:
            raise ValueError("dnsbl_zones must contain at least one zone")

        self._health_records: Dict[str, DNSBLHealthRecord] = {
            zone: DNSBLHealthRecord(zone=zone) for zone in dnsbl_zones
        }
        self._start_time: float | None = None
        self._total_ip_checks: int = 0

    def record_ip_check_start(self) -> None:
        """Record the start of a new IP address check.

        Increments the total IP check counter and sets start time on first call.
        """
        if self._start_time is None:
            self._start_time = time()

        self._total_ip_checks += 1

    def record_check(
        self, zone: str, success: bool, failure_type: str | None = None
    ) -> None:
        """Record a single DNS check result for a DNSBL zone.

        Args:
            zone: DNSBL zone name (must exist in initialized zones).
            success: True if LISTED or NOT_LISTED, False if UNKNOWN.
            failure_type: Required if success=False, one of: timeout, nxdomain_zone,
                         invalid_response_range, invalid_response_type, unknown_error.

        Raises:
            ValueError: If zone is not recognized or if success=False but failure_type is None.
        """
        if zone not in self._health_records:
            raise ValueError(f"Unknown DNSBL zone: {zone}")

        self._health_records[zone].record_check(
            success=success, failure_type=failure_type
        )

    def get_summary(
        self, network_connectivity: NetworkConnectivityResult | None = None
    ) -> HealthSummary:
        """Generate final health summary.

        Calculates broken DNSBL count and determines if network-wide issues
        are detected based on 50% threshold logic.

        Args:
            network_connectivity: Optional supplemental DNS check results.

        Returns:
            HealthSummary: Aggregated health data ready for JSON output.

        Network Issue Detection Logic:
            - If >=50% of DNSBLs have failure_rate == 1.0:
              - AND network_connectivity.check_enabled == True:
                - AND both Cloudflare and Google are unreachable:
                  - Set network_issue_detected = True
        """
        total_dnsbls = len(self._health_records)
        broken_dnsbls = sum(
            1 for record in self._health_records.values() if record.status == "broken"
        )

        # Network issue detection: >=50% DNSBLs failed + supplemental checks failed
        network_issue_detected = False
        if broken_dnsbls / total_dnsbls >= 0.5:
            if network_connectivity and network_connectivity.check_enabled:
                # Network issue if BOTH supplemental checks failed
                network_issue_detected = not (
                    network_connectivity.cloudflare_reachable
                    or network_connectivity.google_reachable
                )

        # Calculate execution duration
        execution_duration_ms = 0
        if self._start_time is not None:
            execution_duration_ms = int((time() - self._start_time) * 1000)

        return HealthSummary(
            timestamp=datetime.now(timezone.utc),
            total_dnsbls=total_dnsbls,
            broken_dnsbls=broken_dnsbls,
            network_issue_detected=network_issue_detected,
            total_ip_checks=self._total_ip_checks,
            execution_duration_ms=execution_duration_ms,
            dnsbl_health=list(self._health_records.values()),
            network_connectivity=network_connectivity,
        )
