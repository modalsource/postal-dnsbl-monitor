"""DNS checker service for DNSBL queries."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Tuple

import dns.resolver

from src.models.dns_result import DNSResult, DNSStatus
from src.utils.ip_utils import build_dnsbl_query


logger = logging.getLogger(__name__)


def check_dnsbl(ip: str, zone: str, timeout: int = 5) -> Tuple[str, DNSStatus, str]:
    """Check single IP against single DNSBL zone.

    Args:
        ip: IPv4 address to check.
        zone: DNSBL zone domain.
        timeout: Query timeout in seconds.

    Returns:
        Tuple[str, DNSStatus, str]: (zone, status, response_data)
    """
    query_hostname = build_dnsbl_query(ip, zone)
    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout  # Total timeout for query

    try:
        answers = resolver.resolve(query_hostname, "A")
        # DNSBL typically returns 127.0.0.x for listings
        response = str(answers[0])
        return (zone, DNSStatus.LISTED, response)

    except dns.resolver.NXDOMAIN:
        # Definitive "not listed" response
        return (zone, DNSStatus.NOT_LISTED, "")

    except (
        dns.resolver.NoAnswer,
        dns.resolver.Timeout,
        dns.resolver.NoNameservers,
        dns.exception.DNSException,
    ) as e:
        # Transient failures - cannot determine status
        return (zone, DNSStatus.UNKNOWN, str(type(e).__name__))


def check_ip_concurrent(
    ip: str, zones: list[str], concurrency: int = 10, timeout: int = 5
) -> list[DNSResult]:
    """Check single IP against multiple DNSBL zones concurrently.

    Uses ThreadPoolExecutor for concurrent DNS queries per research.md section 1.

    Args:
        ip: IPv4 address to check.
        zones: List of DNSBL zone domains.
        concurrency: Max concurrent DNS queries.
        timeout: Per-query timeout in seconds.

    Returns:
        list[DNSResult]: List of DNS query results.
    """
    results: list[DNSResult] = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # Submit all zone checks for this IP
        futures = {
            executor.submit(check_dnsbl, ip, zone, timeout): zone for zone in zones
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
                result = DNSResult(
                    ip=ip,
                    zone=zone,
                    status=DNSStatus.UNKNOWN,
                    response_data=f"Exception: {e}",
                    timestamp=datetime.utcnow(),
                )
                results.append(result)

    return results
