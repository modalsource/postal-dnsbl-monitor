"""Unit tests for state transition logic."""

from datetime import datetime


from src.models.dns_result import DNSResult, DNSStatus
from src.models.ip_record import IPRecord
from src.models.state_transition import (
    aggregate_dns_results,
    determine_state_transition,
    detect_zone_delta,
)


def test_aggregate_dns_results_all_clean():
    """Test aggregation when all zones return NOT_LISTED."""
    results = [
        DNSResult(
            "203.0.113.45",
            "zen.spamhaus.org",
            DNSStatus.NOT_LISTED,
            "",
            datetime.utcnow(),
        ),
        DNSResult(
            "203.0.113.45",
            "bl.spamcop.net",
            DNSStatus.NOT_LISTED,
            "",
            datetime.utcnow(),
        ),
    ]

    listed_zones, unknown_zones = aggregate_dns_results(results)

    assert listed_zones == []
    assert unknown_zones == []


def test_aggregate_dns_results_some_listed():
    """Test aggregation when some zones return LISTED."""
    results = [
        DNSResult(
            "203.0.113.45",
            "zen.spamhaus.org",
            DNSStatus.LISTED,
            "127.0.0.2",
            datetime.utcnow(),
        ),
        DNSResult(
            "203.0.113.45",
            "bl.spamcop.net",
            DNSStatus.NOT_LISTED,
            "",
            datetime.utcnow(),
        ),
        DNSResult(
            "203.0.113.45",
            "dnsbl.sorbs.net",
            DNSStatus.LISTED,
            "127.0.0.3",
            datetime.utcnow(),
        ),
    ]

    listed_zones, unknown_zones = aggregate_dns_results(results)

    assert sorted(listed_zones) == ["dnsbl.sorbs.net", "zen.spamhaus.org"]
    assert unknown_zones == []


def test_aggregate_dns_results_with_unknown():
    """Test aggregation when some zones return UNKNOWN."""
    results = [
        DNSResult(
            "203.0.113.45",
            "zen.spamhaus.org",
            DNSStatus.LISTED,
            "127.0.0.2",
            datetime.utcnow(),
        ),
        DNSResult(
            "203.0.113.45",
            "bl.spamcop.net",
            DNSStatus.UNKNOWN,
            "Timeout",
            datetime.utcnow(),
        ),
    ]

    listed_zones, unknown_zones = aggregate_dns_results(results)

    assert listed_zones == ["zen.spamhaus.org"]
    assert unknown_zones == ["bl.spamcop.net"]


def test_determine_state_transition_clean_to_listed():
    """Test clean -> listed transition detection."""
    ip_record = IPRecord(
        id=1,
        ip="203.0.113.45",
        priority=50,
        old_priority=None,
        blocking_lists="",
        last_event=None,
    )

    dns_results = [
        DNSResult(
            "203.0.113.45",
            "zen.spamhaus.org",
            DNSStatus.LISTED,
            "127.0.0.2",
            datetime.utcnow(),
        ),
        DNSResult(
            "203.0.113.45",
            "bl.spamcop.net",
            DNSStatus.NOT_LISTED,
            "",
            datetime.utcnow(),
        ),
    ]

    transition = determine_state_transition(ip_record, dns_results)

    assert transition is not None
    assert transition.previous_state == "CLEAN"
    assert transition.new_state == "LISTED"
    assert transition.listed_zones == ["zen.spamhaus.org"]
    assert transition.requires_update is True


def test_determine_state_transition_listed_to_clean():
    """Test listed -> clean transition detection."""
    ip_record = IPRecord(
        id=1,
        ip="203.0.113.45",
        priority=0,
        old_priority=50,
        blocking_lists="zen.spamhaus.org",
        last_event="new block from list(s) zen.spamhaus.org",
    )

    dns_results = [
        DNSResult(
            "203.0.113.45",
            "zen.spamhaus.org",
            DNSStatus.NOT_LISTED,
            "",
            datetime.utcnow(),
        ),
    ]

    transition = determine_state_transition(ip_record, dns_results)

    assert transition is not None
    assert transition.previous_state == "LISTED"
    assert transition.new_state == "CLEAN"
    assert transition.listed_zones == []
    assert transition.requires_update is True


def test_determine_state_transition_zone_change():
    """Test listed -> listed (zone change) transition detection."""
    ip_record = IPRecord(
        id=1,
        ip="203.0.113.45",
        priority=0,
        old_priority=50,
        blocking_lists="zen.spamhaus.org",
        last_event="new block from list(s) zen.spamhaus.org",
    )

    dns_results = [
        DNSResult(
            "203.0.113.45",
            "zen.spamhaus.org",
            DNSStatus.NOT_LISTED,
            "",
            datetime.utcnow(),
        ),
        DNSResult(
            "203.0.113.45",
            "bl.spamcop.net",
            DNSStatus.LISTED,
            "127.0.0.2",
            datetime.utcnow(),
        ),
    ]

    transition = determine_state_transition(ip_record, dns_results)

    assert transition is not None
    assert transition.previous_state == "LISTED"
    assert transition.new_state == "LISTED"
    assert transition.listed_zones == ["bl.spamcop.net"]
    assert transition.zone_delta["added"] == ["bl.spamcop.net"]
    assert transition.zone_delta["removed"] == ["zen.spamhaus.org"]


def test_determine_state_transition_no_change():
    """Test idempotent no-op when state unchanged."""
    ip_record = IPRecord(
        id=1,
        ip="203.0.113.45",
        priority=0,
        old_priority=50,
        blocking_lists="zen.spamhaus.org",
        last_event="new block from list(s) zen.spamhaus.org",
    )

    dns_results = [
        DNSResult(
            "203.0.113.45",
            "zen.spamhaus.org",
            DNSStatus.LISTED,
            "127.0.0.2",
            datetime.utcnow(),
        ),
    ]

    transition = determine_state_transition(ip_record, dns_results)

    assert transition is None  # No change, idempotent no-op


def test_detect_zone_delta():
    """Test zone delta calculation."""
    current_zones = ["zen.spamhaus.org", "bl.spamcop.net"]
    new_zones = ["bl.spamcop.net", "dnsbl.sorbs.net"]

    delta = detect_zone_delta(current_zones, new_zones)

    assert delta["added"] == ["dnsbl.sorbs.net"]
    assert delta["removed"] == ["zen.spamhaus.org"]


def test_detect_zone_delta_all_new():
    """Test zone delta when all zones are new."""
    current_zones = []
    new_zones = ["zen.spamhaus.org", "bl.spamcop.net"]

    delta = detect_zone_delta(current_zones, new_zones)

    assert sorted(delta["added"]) == ["bl.spamcop.net", "zen.spamhaus.org"]
    assert delta["removed"] == []


def test_detect_zone_delta_all_removed():
    """Test zone delta when all zones are removed."""
    current_zones = ["zen.spamhaus.org", "bl.spamcop.net"]
    new_zones = []

    delta = detect_zone_delta(current_zones, new_zones)

    assert delta["added"] == []
    assert sorted(delta["removed"]) == ["bl.spamcop.net", "zen.spamhaus.org"]
