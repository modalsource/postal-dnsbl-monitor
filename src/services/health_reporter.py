"""Health reporting service for generating JSON and YAML outputs.

Converts health tracking data into formatted reports for consumption
by administrators and configuration management tools.
"""

import json
from typing import List

from src.models.dnsbl_health import (
    HealthSummary,
    DNSBLHealthRecord,
    PrunedConfiguration,
)
from datetime import datetime, timezone


class HealthReporter:
    """Generates formatted health reports from tracking data.

    Provides static methods for generating JSON health summaries and
    YAML pruned configuration lists.
    """

    @staticmethod
    def generate_json_report(summary: HealthSummary) -> str:
        """Generate JSON-formatted health summary.

        Args:
            summary: HealthSummary object with aggregated data.

        Returns:
            str: Pretty-printed JSON string with sorted keys for determinism.

        Example:
            >>> summary = HealthSummary(...)
            >>> json_report = HealthReporter.generate_json_report(summary)
            >>> print(json_report)
            {
              "dnsbl_health": [...],
              "execution_summary": {...},
              "network_connectivity": {...}
            }
        """
        return json.dumps(summary.to_json(), indent=2, sort_keys=True)

    @staticmethod
    def generate_pruned_yaml(health_records: List[DNSBLHealthRecord]) -> str:
        """Generate YAML-formatted pruned DNSBL list.

        Creates a suggested configuration with broken DNSBLs removed,
        ready for copy-paste into config files.

        Args:
            health_records: List of DNSBLHealthRecord objects.

        Returns:
            str: YAML string with header comments and pruned zone list.

        Example:
            >>> records = [DNSBLHealthRecord(...), ...]
            >>> yaml_report = HealthReporter.generate_pruned_yaml(records)
            >>> print(yaml_report)
            # Suggested DNSBL Configuration (Broken endpoints removed)
            # Generated: 2025-12-19T10:30:00Z
            # Removed: broken.dnsbl.org
            dnsbl_zones:
            - bl.spamcop.net
            - zen.spamhaus.org
        """
        healthy_zones = [r.zone for r in health_records if r.status == "healthy"]
        broken_zones = [r.zone for r in health_records if r.status == "broken"]

        pruned_config = PrunedConfiguration(
            healthy_zones=healthy_zones,
            removed_zones=broken_zones,
            generated_at=datetime.now(timezone.utc),
        )

        return pruned_config.to_yaml()
