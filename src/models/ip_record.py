"""IP Address Record model from MySQL."""

from dataclasses import dataclass


@dataclass
class IPRecord:
    """IP Address Record from postal.ip_addresses table.

    Represents the current state of an IP address in the database.

    Attributes:
        id: Database primary key.
        ip: IPv4 address in dotted-quad format.
        priority: Current throttling priority (0-100, lower = more throttled).
        old_priority: Backup priority for restoration (NULL when clean).
        blocking_lists: Comma-separated sorted DNSBL zones where IP is listed.
        last_event: Human-readable description of last state transition.
    """

    id: int
    ip: str
    priority: int
    old_priority: int | None
    blocking_lists: str
    last_event: str | None

    def is_currently_listed(self) -> bool:
        """Check if IP is currently listed on any DNSBL.

        Returns:
            bool: True if blocking_lists is non-empty, False otherwise.
        """
        return bool(self.blocking_lists)

    def get_listed_zones(self) -> list[str]:
        """Get list of zones where IP is currently listed.

        Returns:
            list[str]: List of DNSBL zone names (empty if clean).
        """
        if not self.blocking_lists:
            return []
        return self.blocking_lists.split(",")
