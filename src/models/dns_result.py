"""DNS query result models."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DNSStatus(Enum):
    """DNS query result classification per FR-009."""

    LISTED = "LISTED"  # A record response (IP is on DNSBL)
    NOT_LISTED = "NOT_LISTED"  # NXDOMAIN response (IP is clean)
    UNKNOWN = "UNKNOWN"  # Timeout, SERVFAIL, or other non-definitive response


@dataclass
class DNSResult:
    """Result of a single DNSBL zone query.

    Attributes:
        ip: IPv4 address that was checked.
        zone: DNSBL zone domain that was queried.
        status: Classification of the query result.
        response_data: DNS response data or error description.
        timestamp: When the query completed.
    """

    ip: str
    zone: str
    status: DNSStatus
    response_data: str
    timestamp: datetime

    def is_listed(self) -> bool:
        """Check if IP is listed on this zone.

        Returns:
            bool: True if status is LISTED, False otherwise.
        """
        return self.status == DNSStatus.LISTED

    def is_unknown(self) -> bool:
        """Check if query result is unknown (transient failure).

        Returns:
            bool: True if status is UNKNOWN, False otherwise.
        """
        return self.status == DNSStatus.UNKNOWN
