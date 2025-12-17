"""IP address utilities for DNSBL queries."""

import ipaddress
import re


def is_valid_ipv4(ip: str) -> bool:
    """Validate if string is a valid IPv4 address.

    Args:
        ip: IP address string to validate.

    Returns:
        bool: True if valid IPv4, False otherwise.

    Examples:
        >>> is_valid_ipv4("203.0.113.45")
        True
        >>> is_valid_ipv4("256.0.0.1")
        False
        >>> is_valid_ipv4("::1")
        False
    """
    try:
        addr = ipaddress.ip_address(ip)
        return isinstance(addr, ipaddress.IPv4Address)
    except ValueError:
        return False


def reverse_ip(ip: str) -> str:
    """Convert IPv4 address to reverse DNS format for DNSBL queries.

    DNSBL queries require reversed octets. For example:
    203.0.113.45 becomes 45.113.0.203

    Args:
        ip: IPv4 address in dotted-quad format.

    Returns:
        str: Reversed IP address.

    Raises:
        ValueError: If IP is not a valid IPv4 address.

    Examples:
        >>> reverse_ip("203.0.113.45")
        '45.113.0.203'
        >>> reverse_ip("192.168.1.1")
        '1.1.168.192'
    """
    if not is_valid_ipv4(ip):
        raise ValueError(f"Invalid IPv4 address: {ip}")

    octets = ip.split(".")
    return ".".join(reversed(octets))


def build_dnsbl_query(ip: str, zone: str) -> str:
    """Build DNSBL query hostname for DNS lookup.

    Args:
        ip: IPv4 address to check.
        zone: DNSBL zone domain (e.g., "zen.spamhaus.org").

    Returns:
        str: DNSBL query hostname (e.g., "45.113.0.203.zen.spamhaus.org").

    Raises:
        ValueError: If IP is invalid or zone is empty.

    Examples:
        >>> build_dnsbl_query("203.0.113.45", "zen.spamhaus.org")
        '45.113.0.203.zen.spamhaus.org'
    """
    if not zone:
        raise ValueError("DNSBL zone cannot be empty")

    reversed_ip = reverse_ip(ip)
    return f"{reversed_ip}.{zone}"
