"""Unit tests for IP utility functions."""

import pytest

from src.utils.ip_utils import is_valid_ipv4, reverse_ip, build_dnsbl_query


def test_is_valid_ipv4_valid():
    """Test validation of valid IPv4 addresses."""
    assert is_valid_ipv4("203.0.113.45") is True
    assert is_valid_ipv4("192.168.1.1") is True
    assert is_valid_ipv4("0.0.0.0") is True
    assert is_valid_ipv4("255.255.255.255") is True


def test_is_valid_ipv4_invalid():
    """Test validation rejects invalid IPv4 addresses."""
    assert is_valid_ipv4("256.0.0.1") is False  # Out of range
    assert is_valid_ipv4("192.168.1") is False  # Incomplete
    assert is_valid_ipv4("::1") is False  # IPv6
    assert is_valid_ipv4("not an ip") is False  # Invalid format
    assert is_valid_ipv4("") is False  # Empty string


def test_reverse_ip():
    """Test IP reversal for DNSBL queries."""
    assert reverse_ip("203.0.113.45") == "45.113.0.203"
    assert reverse_ip("192.168.1.1") == "1.1.168.192"
    assert reverse_ip("8.8.8.8") == "8.8.8.8"  # Palindrome


def test_reverse_ip_invalid():
    """Test reverse_ip raises ValueError for invalid IPs."""
    with pytest.raises(ValueError, match="Invalid IPv4 address"):
        reverse_ip("256.0.0.1")

    with pytest.raises(ValueError, match="Invalid IPv4 address"):
        reverse_ip("not an ip")


def test_build_dnsbl_query():
    """Test DNSBL query hostname construction."""
    assert (
        build_dnsbl_query("203.0.113.45", "zen.spamhaus.org")
        == "45.113.0.203.zen.spamhaus.org"
    )
    assert (
        build_dnsbl_query("192.168.1.1", "bl.spamcop.net")
        == "1.1.168.192.bl.spamcop.net"
    )


def test_build_dnsbl_query_invalid_ip():
    """Test build_dnsbl_query raises ValueError for invalid IP."""
    with pytest.raises(ValueError, match="Invalid IPv4 address"):
        build_dnsbl_query("invalid", "zen.spamhaus.org")


def test_build_dnsbl_query_empty_zone():
    """Test build_dnsbl_query raises ValueError for empty zone."""
    with pytest.raises(ValueError, match="DNSBL zone cannot be empty"):
        build_dnsbl_query("203.0.113.45", "")
