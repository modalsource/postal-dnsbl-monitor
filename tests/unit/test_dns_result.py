"""Unit tests for DNS result classification (T031).

Tests the DNSResult model and DNSStatus enum classification logic.
"""

from datetime import UTC, datetime

from src.models.dns_result import DNSResult, DNSStatus


def test_dns_status_enum_values():
    """Test DNSStatus enum has correct values."""
    assert DNSStatus.LISTED.value == "LISTED"
    assert DNSStatus.NOT_LISTED.value == "NOT_LISTED"
    assert DNSStatus.UNKNOWN.value == "UNKNOWN"


def test_dns_result_is_listed_true():
    """Test is_listed() returns True for LISTED status."""
    result = DNSResult(
        ip="192.0.2.1",
        zone="zen.spamhaus.org",
        status=DNSStatus.LISTED,
        response_data="127.0.0.2",
        timestamp=datetime.now(UTC),
    )
    assert result.is_listed() is True


def test_dns_result_is_listed_false_not_listed():
    """Test is_listed() returns False for NOT_LISTED status."""
    result = DNSResult(
        ip="192.0.2.1",
        zone="zen.spamhaus.org",
        status=DNSStatus.NOT_LISTED,
        response_data="NXDOMAIN",
        timestamp=datetime.now(UTC),
    )
    assert result.is_listed() is False


def test_dns_result_is_listed_false_unknown():
    """Test is_listed() returns False for UNKNOWN status."""
    result = DNSResult(
        ip="192.0.2.1",
        zone="zen.spamhaus.org",
        status=DNSStatus.UNKNOWN,
        response_data="Timeout after 5.0s",
        timestamp=datetime.now(UTC),
    )
    assert result.is_listed() is False


def test_dns_result_is_unknown_true():
    """Test is_unknown() returns True for UNKNOWN status."""
    result = DNSResult(
        ip="192.0.2.1",
        zone="zen.spamhaus.org",
        status=DNSStatus.UNKNOWN,
        response_data="SERVFAIL",
        timestamp=datetime.now(UTC),
    )
    assert result.is_unknown() is True


def test_dns_result_is_unknown_false_listed():
    """Test is_unknown() returns False for LISTED status."""
    result = DNSResult(
        ip="192.0.2.1",
        zone="zen.spamhaus.org",
        status=DNSStatus.LISTED,
        response_data="127.0.0.2",
        timestamp=datetime.now(UTC),
    )
    assert result.is_unknown() is False


def test_dns_result_is_unknown_false_not_listed():
    """Test is_unknown() returns False for NOT_LISTED status."""
    result = DNSResult(
        ip="192.0.2.1",
        zone="zen.spamhaus.org",
        status=DNSStatus.NOT_LISTED,
        response_data="NXDOMAIN",
        timestamp=datetime.now(UTC),
    )
    assert result.is_unknown() is False


def test_dns_result_dataclass_attributes():
    """Test DNSResult dataclass has correct attributes."""
    timestamp = datetime.now(UTC)
    result = DNSResult(
        ip="198.51.100.42",
        zone="b.barracudacentral.org",
        status=DNSStatus.LISTED,
        response_data="127.0.0.2",
        timestamp=timestamp,
    )

    assert result.ip == "198.51.100.42"
    assert result.zone == "b.barracudacentral.org"
    assert result.status == DNSStatus.LISTED
    assert result.response_data == "127.0.0.2"
    assert result.timestamp == timestamp


def test_dns_result_all_statuses_coverage():
    """Test DNSResult with all possible DNSStatus values."""
    timestamp = datetime.now(UTC)

    # LISTED status
    listed = DNSResult(
        ip="192.0.2.1",
        zone="test.dnsbl.org",
        status=DNSStatus.LISTED,
        response_data="127.0.0.2",
        timestamp=timestamp,
    )
    assert listed.status == DNSStatus.LISTED
    assert listed.is_listed() is True
    assert listed.is_unknown() is False

    # NOT_LISTED status
    not_listed = DNSResult(
        ip="192.0.2.1",
        zone="test.dnsbl.org",
        status=DNSStatus.NOT_LISTED,
        response_data="NXDOMAIN",
        timestamp=timestamp,
    )
    assert not_listed.status == DNSStatus.NOT_LISTED
    assert not_listed.is_listed() is False
    assert not_listed.is_unknown() is False

    # UNKNOWN status
    unknown = DNSResult(
        ip="192.0.2.1",
        zone="test.dnsbl.org",
        status=DNSStatus.UNKNOWN,
        response_data="Timeout",
        timestamp=timestamp,
    )
    assert unknown.status == DNSStatus.UNKNOWN
    assert unknown.is_listed() is False
    assert unknown.is_unknown() is True
