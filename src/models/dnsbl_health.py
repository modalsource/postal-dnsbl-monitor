"""DNSBL health tracking data models.

This module provides data structures for tracking DNSBL endpoint health
and generating health reports at the end of execution.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List
import yaml


@dataclass
class DNSBLHealthRecord:
    """Tracks health metrics for a single DNSBL zone.

    Attributes:
        zone: DNSBL zone name (e.g., "zen.spamhaus.org").
        checks_performed: Total number of IP checks attempted.
        successful_checks: Number of successful responses (LISTED or NOT_LISTED).
        failed_checks: Number of failed checks (timeouts, invalid responses).
        failure_types: Count of each failure type encountered.

    Computed Properties:
        failure_rate: Ratio of failed_checks / checks_performed (0.0 to 1.0).
        status: "healthy" if failure_rate < 1.0, else "broken".

    Invariants:
        - checks_performed = successful_checks + failed_checks
        - sum(failure_types.values()) = failed_checks
    """

    zone: str
    checks_performed: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    failure_types: Dict[str, int] = field(default_factory=dict)

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate as failed_checks / checks_performed.

        Returns:
            float: Failure rate between 0.0 and 1.0, or 0.0 if no checks performed.
        """
        if self.checks_performed == 0:
            return 0.0
        return self.failed_checks / self.checks_performed

    @property
    def status(self) -> str:
        """Determine DNSBL health status.

        Returns:
            str: "broken" if failure_rate == 1.0, else "healthy".
        """
        return "broken" if self.failure_rate == 1.0 else "healthy"

    def record_check(self, success: bool, failure_type: str | None = None) -> None:
        """Record a single DNS check result.

        Args:
            success: True if LISTED or NOT_LISTED, False if UNKNOWN.
            failure_type: Required if success=False, one of: timeout, nxdomain_zone,
                         invalid_response_range, invalid_response_type, unknown_error.

        Raises:
            ValueError: If success=False but failure_type is None.
        """
        self.checks_performed += 1

        if success:
            self.successful_checks += 1
        else:
            if failure_type is None:
                raise ValueError("failure_type is required when success=False")

            self.failed_checks += 1
            self.failure_types[failure_type] = (
                self.failure_types.get(failure_type, 0) + 1
            )


@dataclass
class NetworkConnectivityResult:
    """Results of supplemental DNS connectivity checks to cloud providers.

    Attributes:
        check_enabled: Whether supplemental checks were performed.
        cloudflare_reachable: True if 1.1.1.1 responded to DNS query.
        google_reachable: True if 8.8.8.8 responded to DNS query.

    Invariants:
        - If check_enabled=False, both reachability fields must be None.
        - If check_enabled=True, both reachability fields must be bool.
    """

    check_enabled: bool
    cloudflare_reachable: bool | None = None
    google_reachable: bool | None = None

    def to_json(self) -> dict:
        """Serialize to JSON-compatible dict.

        Returns:
            dict: JSON-serializable representation.
        """
        return {
            "check_enabled": self.check_enabled,
            "cloudflare_reachable": self.cloudflare_reachable,
            "google_reachable": self.google_reachable,
        }


@dataclass
class HealthSummary:
    """Aggregated DNSBL health data for JSON output.

    Attributes:
        timestamp: Execution end timestamp (UTC).
        total_dnsbls: Total number of configured DNSBL zones.
        broken_dnsbls: Count of zones with failure_rate == 1.0.
        network_issue_detected: True if >=50% DNSBLs failed AND supplemental checks failed.
        total_ip_checks: Total IP addresses checked across all DNSBLs.
        execution_duration_ms: Time from first check to summary generation (milliseconds).
        dnsbl_health: Per-DNSBL health records.
        network_connectivity: Supplemental DNS check results (optional).

    Invariants:
        - len(dnsbl_health) == total_dnsbls
        - broken_dnsbls == count(r for r in dnsbl_health if r.status == "broken")
        - dnsbl_health list is sorted by zone name (alphabetical)
    """

    timestamp: datetime
    total_dnsbls: int
    broken_dnsbls: int
    network_issue_detected: bool
    total_ip_checks: int
    execution_duration_ms: int
    dnsbl_health: List[DNSBLHealthRecord]
    network_connectivity: NetworkConnectivityResult | None = None

    def to_json(self) -> dict:
        """Serialize to JSON-compatible dict with sorted keys.

        Returns:
            dict: JSON-serializable representation matching health-summary-schema.json.
        """
        return {
            "execution_summary": {
                "timestamp": self.timestamp.isoformat(),
                "total_dnsbls": self.total_dnsbls,
                "broken_dnsbls": self.broken_dnsbls,
                "network_issue_detected": self.network_issue_detected,
                "total_ip_checks": self.total_ip_checks,
                "execution_duration_ms": self.execution_duration_ms,
            },
            "dnsbl_health": [
                {
                    "zone": r.zone,
                    "status": r.status,
                    "checks_performed": r.checks_performed,
                    "successful_checks": r.successful_checks,
                    "failed_checks": r.failed_checks,
                    "failure_rate": r.failure_rate,
                    "failure_types": dict(sorted(r.failure_types.items())),
                }
                for r in sorted(self.dnsbl_health, key=lambda x: x.zone)
            ],
            "network_connectivity": (
                self.network_connectivity.to_json()
                if self.network_connectivity
                else None
            ),
        }


@dataclass
class PrunedConfiguration:
    """YAML-formatted suggested DNSBL list with broken endpoints removed.

    Attributes:
        healthy_zones: DNSBL zones with failure_rate < 1.0.
        removed_zones: DNSBL zones with failure_rate == 1.0.
        generated_at: Timestamp of pruned list generation.

    Invariants:
        - healthy_zones and removed_zones are disjoint sets.
        - Both lists are sorted alphabetically for deterministic output.
    """

    healthy_zones: List[str]
    removed_zones: List[str]
    generated_at: datetime

    def to_yaml(self) -> str:
        """Generate YAML-formatted pruned configuration.

        Returns:
            str: YAML string with header comments and pruned zone list.
        """
        removed_str = (
            ", ".join(sorted(self.removed_zones)) if self.removed_zones else "None"
        )

        header = [
            "# Suggested DNSBL Configuration (Broken endpoints removed)",
            f"# Generated: {self.generated_at.isoformat()}",
            f"# Removed: {removed_str}",
        ]

        yaml_dict = {"dnsbl_zones": sorted(self.healthy_zones)}
        yaml_output = yaml.safe_dump(
            yaml_dict, default_flow_style=False, sort_keys=False
        )

        return "\n".join(header) + "\n" + yaml_output
