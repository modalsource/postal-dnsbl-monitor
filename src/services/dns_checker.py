"""DNS checker service for DNSBL queries."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Tuple, Optional

import dns.resolver
import dns.exception

from src.models.dns_result import DNSResult, DNSStatus
from src.utils.ip_utils import build_dnsbl_query


logger = logging.getLogger(__name__)


def categorize_failure(exception: Exception, response_data: str) -> str:
    """Categorize DNS failure into specific failure type.

    Maps DNS exceptions to failure types for health tracking.

    Args:
        exception: The DNS exception that occurred.
        response_data: Response data string (may contain error info).

    Returns:
        str: One of: timeout, nxdomain_zone, invalid_response_range,
             invalid_response_type, unknown_error.
    """
    if isinstance(exception, dns.exception.Timeout):
        return "timeout"
    elif isinstance(exception, dns.resolver.NXDOMAIN):
        # NXDOMAIN for the query itself means zone doesn't exist
        # (Different from NXDOMAIN for IP query which means NOT_LISTED)
        return "nxdomain_zone"
    elif isinstance(exception, dns.resolver.NoAnswer):
        return "invalid_response_type"
    elif isinstance(exception, dns.resolver.NoNameservers):
        return "unknown_error"
    else:
        return "unknown_error"


def validate_dnsbl_response(response: str) -> bool:
    """Validate that DNSBL response is in valid 127.0.0.0/8 range.

    Args:
        response: IP address string from DNSBL response.

    Returns:
        bool: True if response is valid (starts with 127.), False otherwise.
    """
    return response.startswith("127.")


def check_dnsbl(
    ip: str,
    zone: str,
    timeout: int = 5,
    health_tracker: Optional[object] = None,
) -> Tuple[str, DNSStatus, str]:
    """Check single IP against single DNSBL zone.

    Args:
        ip: IPv4 address to check.
        zone: DNSBL zone domain.
        timeout: Query timeout in seconds.
        health_tracker: Optional HealthTracker instance for recording check results.

    Returns:
        Tuple[str, DNSStatus, str]: (zone, status, response_data)
    """
    query_hostname = build_dnsbl_query(ip, zone)
    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout  # Total timeout for query

    caught_exception = None
    status = DNSStatus.UNKNOWN
    response_data = ""

    try:
        answers = resolver.resolve(query_hostname, "A")
        # DNSBL typically returns 127.0.0.x for listings
        response = str(answers[0])

        # Validate response is in 127.0.0.0/8 range
        if not validate_dnsbl_response(response):
            status = DNSStatus.UNKNOWN
            response_data = f"invalid_response_range:{response}"
            if health_tracker:
                health_tracker.record_check(
                    zone, success=False, failure_type="invalid_response_range"
                )
        else:
            status = DNSStatus.LISTED
            response_data = response
            if health_tracker:
                health_tracker.record_check(zone, success=True)

        return (zone, status, response_data)

    except dns.resolver.NXDOMAIN:
        # Definitive "not listed" response
        if health_tracker:
            health_tracker.record_check(zone, success=True)
        return (zone, DNSStatus.NOT_LISTED, "")

    except (
        dns.resolver.NoAnswer,
        dns.resolver.Timeout,
        dns.resolver.NoNameservers,
        dns.exception.DNSException,
    ) as e:
        # Transient failures - cannot determine status
        caught_exception = e
        response_data = str(type(e).__name__)

        if health_tracker:
            failure_type = categorize_failure(e, response_data)
            health_tracker.record_check(zone, success=False, failure_type=failure_type)

        return (zone, DNSStatus.UNKNOWN, response_data)


def check_ip_concurrent(
    ip: str,
    zones: list[str],
    concurrency: int = 10,
    timeout: int = 5,
    health_tracker: Optional[object] = None,
) -> list[DNSResult]:
    """Check single IP against multiple DNSBL zones concurrently.

    Uses ThreadPoolExecutor for concurrent DNS queries per research.md section 1.

    Args:
        ip: IPv4 address to check.
        zones: List of DNSBL zone domains.
        concurrency: Max concurrent DNS queries.
        timeout: Per-query timeout in seconds.
        health_tracker: Optional HealthTracker instance for recording check results.

    Returns:
        list[DNSResult]: List of DNS query results.
    """
    results: list[DNSResult] = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # Submit all zone checks for this IP
        futures = {
            executor.submit(check_dnsbl, ip, zone, timeout, health_tracker): zone
            for zone in zones
        }

        # Collect results as they complete
        for future in as_completed(futures):
            try:
                zone, status, response_data = future.result()
                result = DNSResult(
                    ip=ip,
                    zone=zone,
                    status=status,
                    response_data=response_data,
                    timestamp=datetime.utcnow(),
                )
                results.append(result)
            except Exception as e:
                # Unexpected error - treat as UNKNOWN
                zone = futures[future]
                logger.error(f"Unexpected error checking {ip} against {zone}: {e}")

                if health_tracker:
                    health_tracker.record_check(
                        zone, success=False, failure_type="unknown_error"
                    )

                result = DNSResult(
                    ip=ip,
                    zone=zone,
                    status=DNSStatus.UNKNOWN,
                    response_data=f"Exception: {e}",
                    timestamp=datetime.utcnow(),
                )
                results.append(result)

    return results
