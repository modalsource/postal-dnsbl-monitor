"""State transition logic for IP records.

Implements the state machine from data-model.md section "State Transition Rules".
"""

from dataclasses import dataclass
from typing import Optional

from src.models.dns_result import DNSResult, DNSStatus
from src.models.ip_record import IPRecord


@dataclass
class StateTransition:
    """Represents a state transition event for an IP.

    Attributes:
        ip: IPv4 address.
        previous_state: State before transition (CLEAN or LISTED).
        new_state: State after transition (CLEAN or LISTED).
        listed_zones: List of zones where IP is currently listed.
        zone_delta: Changes in zone membership.
        requires_update: Whether database update is needed.
    """

    ip: str
    previous_state: str  # "CLEAN" or "LISTED"
    new_state: str  # "CLEAN" or "LISTED"
    listed_zones: list[str]
    zone_delta: dict[str, list[str]]  # {"added": [...], "removed": [...]}
    requires_update: bool


def aggregate_dns_results(results: list[DNSResult]) -> tuple[list[str], list[str]]:
    """Aggregate DNS results to determine listing status.

    Per FR-012: IP is LISTED if ≥1 zone returns LISTED.
    UNKNOWN results are logged but ignored for throttling decision.

    Args:
        results: List of DNS query results for one IP.

    Returns:
        tuple[list[str], list[str]]: (listed_zones, unknown_zones)
    """
    listed_zones = []
    unknown_zones = []

    for result in results:
        if result.status == DNSStatus.LISTED:
            listed_zones.append(result.zone)
        elif result.status == DNSStatus.UNKNOWN:
            unknown_zones.append(result.zone)

    # Return sorted lists for determinism
    return sorted(listed_zones), sorted(unknown_zones)


def determine_state_transition(
    ip_record: IPRecord, dns_results: list[DNSResult]
) -> Optional[StateTransition]:
    """Determine if state transition is required based on DNS results.

    Implements state machine from data-model.md:
    - Clean → Listed: IP becomes listed on ≥1 zone
    - Listed → Clean: All zones return NOT_LISTED or UNKNOWN
    - Listed → Listed (zone change): Set of listing zones changes

    Args:
        ip_record: Current IP record from database.
        dns_results: DNS query results for this IP.

    Returns:
        Optional[StateTransition]: Transition event if state changed, None if no-op.
    """
    listed_zones, unknown_zones = aggregate_dns_results(dns_results)

    current_listed = ip_record.is_currently_listed()
    current_zones = set(ip_record.get_listed_zones())
    new_zones = set(listed_zones)

    # Determine previous and new states
    previous_state = "LISTED" if current_listed else "CLEAN"
    new_state = "LISTED" if listed_zones else "CLEAN"

    # Case 1: No change in state or zones
    if previous_state == new_state and current_zones == new_zones:
        return None  # Idempotent no-op

    # Calculate zone delta
    added_zones = list(new_zones - current_zones)
    removed_zones = list(current_zones - new_zones)
    zone_delta = {"added": sorted(added_zones), "removed": sorted(removed_zones)}

    return StateTransition(
        ip=ip_record.ip,
        previous_state=previous_state,
        new_state=new_state,
        listed_zones=listed_zones,
        zone_delta=zone_delta,
        requires_update=True,
    )


def detect_zone_delta(
    current_zones: list[str], new_zones: list[str]
) -> dict[str, list[str]]:
    """Calculate added/removed zones between current and new zone sets.

    Args:
        current_zones: Currently listed zones.
        new_zones: New listed zones from DNS check.

    Returns:
        dict[str, list[str]]: {"added": [...], "removed": [...]}
    """
    current_set = set(current_zones)
    new_set = set(new_zones)

    added = list(new_set - current_set)
    removed = list(current_set - new_set)

    return {"added": sorted(added), "removed": sorted(removed)}
