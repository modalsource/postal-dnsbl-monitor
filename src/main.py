"""Main entry point for Postal DNSBL Monitor."""

import logging
import sys
import time

from src.config import Config
from src.models.state_transition import determine_state_transition
from src.services.database import DatabaseService
from src.services.dns_checker import check_ip_concurrent
from src.services.jira_client import JiraClient
from src.services.logger import (
    setup_logging,
    log_job_summary,
    log_ip_check,
    log_dns_failure,
)


logger = logging.getLogger(__name__)


def process_ip(
    ip_record,
    dns_zones: list[str],
    dns_timeout: int,
    dns_concurrency: int,
    db_service: DatabaseService,
    jira_client: JiraClient,
    config: Config,
) -> dict:
    """Process a single IP address.

    Args:
        ip_record: IP record from database.
        dns_zones: List of DNSBL zones to check.
        dns_timeout: DNS query timeout in seconds.
        dns_concurrency: Max concurrent DNS queries.
        db_service: Database service instance.
        jira_client: Jira client instance.
        config: Application configuration.

    Returns:
        dict: Processing statistics (listed, cleaned, unchanged, jira_created, jira_updated).
    """
    ip_start = time.time()
    stats = {
        "listed": 0,
        "cleaned": 0,
        "unchanged": 0,
        "jira_created": 0,
        "jira_updated": 0,
    }

    # Check IP against all DNSBL zones
    dns_results = check_ip_concurrent(
        ip_record.ip, dns_zones, dns_concurrency, dns_timeout
    )

    # Determine if state transition is needed
    transition = determine_state_transition(ip_record, dns_results)

    if transition is None:
        # No change - idempotent no-op
        stats["unchanged"] = 1
        listed_zones = ip_record.get_listed_zones()
        unknown_zones = [r.zone for r in dns_results if r.is_unknown()]

        log_ip_check(
            ip=ip_record.ip,
            listed_zones=listed_zones,
            unknown_zones=unknown_zones,
            decision="LISTED" if ip_record.is_currently_listed() else "CLEAN",
            db_changes=False,
            jira_action="no_action",
            duration_ms=int((time.time() - ip_start) * 1000),
        )
        return stats

    # State transition detected
    db_updated = False
    jira_action = "no_action"

    if not config.dry_run:
        # Execute database update based on transition type
        if transition.previous_state == "CLEAN" and transition.new_state == "LISTED":
            # Clean → Listed
            db_updated = db_service.update_ip_listed(
                ip_record.id,
                ip_record.priority,
                transition.listed_zones,
                config.listed_priority,
            )
            stats["listed"] = 1

            # Create Jira issue if none exists
            existing_issue = jira_client.find_open_issue_for_ip(ip_record.ip)
            if not existing_issue:
                description = f"IP {ip_record.ip} has been listed on {len(transition.listed_zones)} DNSBL zone(s):\n"
                description += "\n".join(
                    f"- {zone}" for zone in transition.listed_zones
                )
                jira_client.create_issue(
                    ip_record.ip, transition.listed_zones, description
                )
                jira_action = "created_issue"
                stats["jira_created"] = 1

        elif transition.previous_state == "LISTED" and transition.new_state == "CLEAN":
            # Listed → Clean
            db_updated = db_service.update_ip_clean(
                ip_record.id, ip_record.old_priority, config.clean_fallback_priority
            )
            stats["cleaned"] = 1

            # Add comment to existing Jira issue
            existing_issue = jira_client.find_open_issue_for_ip(ip_record.ip)
            if existing_issue:
                jira_client.add_comment(
                    existing_issue["key"],
                    f"IP {ip_record.ip} is now clean (no longer listed)",
                )
                jira_action = "updated_issue"
                stats["jira_updated"] = 1

        elif transition.previous_state == "LISTED" and transition.new_state == "LISTED":
            # Listed → Listed (zone change)
            db_updated = db_service.update_ip_zone_change(
                ip_record.id, transition.listed_zones
            )
            stats["listed"] = 1

            # Add comment to existing Jira issue
            existing_issue = jira_client.find_open_issue_for_ip(ip_record.ip)
            if existing_issue:
                comment = f"Zone membership changed:\n"
                if transition.zone_delta["added"]:
                    comment += f"Added: {', '.join(transition.zone_delta['added'])}\n"
                if transition.zone_delta["removed"]:
                    comment += (
                        f"Removed: {', '.join(transition.zone_delta['removed'])}\n"
                    )
                comment += f"Currently listed on: {', '.join(transition.listed_zones)}"
                jira_client.add_comment(existing_issue["key"], comment)
                jira_action = "updated_issue"
                stats["jira_updated"] = 1
    else:
        # DRY_RUN mode - log what would happen
        logger.info(
            f"DRY_RUN: Would update IP {ip_record.ip}: {transition.previous_state} → {transition.new_state}"
        )

    unknown_zones = [r.zone for r in dns_results if r.is_unknown()]
    log_ip_check(
        ip=ip_record.ip,
        listed_zones=transition.listed_zones,
        unknown_zones=unknown_zones,
        decision=transition.new_state,
        db_changes=db_updated,
        jira_action=jira_action,
        duration_ms=int((time.time() - ip_start) * 1000),
    )

    return stats


def main() -> int:
    """Main execution function.

    Returns:
        int: Exit code (0 for success, 1 for fatal error).
    """
    start_time = time.time()

    # Setup logging
    setup_logging()
    logger.info("Starting Postal DNSBL Monitor")

    try:
        # Load configuration (FR-002)
        config = Config.from_env()
        logger.info(
            f"Configuration loaded: {len(config.dnsbl_zones)} DNSBL zones configured"
        )

        if config.dry_run:
            logger.info(
                "DRY_RUN mode enabled - no database writes or Jira actions will occur"
            )

        # Initialize services
        dsn = config.get_db_connection_string()
        db_service = DatabaseService(dsn)
        jira_client = JiraClient(
            server=config.jira_server,
            user=config.jira_user,
            token=config.jira_api_token,
            project=config.jira_project,
            issue_type=config.jira_issue_type,
            dns_failure_issue_type=config.jira_dns_failure_issue_type,
            excluded_statuses=config.jira_excluded_statuses,
        )

        # Fetch all IPs from database (FR-006)
        ip_records = db_service.get_all_ips()
        logger.info(f"Loaded {len(ip_records)} IP addresses from database")

        # Process each IP (FR-001: stateless execution)
        total_stats = {
            "listed": 0,
            "cleaned": 0,
            "unchanged": 0,
            "jira_created": 0,
            "jira_updated": 0,
        }
        total_dns_failures = 0

        for ip_record in ip_records:
            stats = process_ip(
                ip_record=ip_record,
                dns_zones=config.dnsbl_zones,
                dns_timeout=config.dns_timeout,
                dns_concurrency=config.dns_concurrency,
                db_service=db_service,
                jira_client=jira_client,
                config=config,
            )

            # Aggregate statistics
            for key in total_stats:
                total_stats[key] += stats.get(key, 0)

        # Check for DNS infrastructure failure (FR-013a)
        # TODO: Implement DNS failure detection in Phase 5 (User Story 3)

        # Log job summary (FR-031)
        duration_sec = time.time() - start_time
        log_job_summary(
            total_ips=len(ip_records),
            listed=total_stats["listed"],
            cleaned=total_stats["cleaned"],
            unchanged=total_stats["unchanged"],
            jira_created=total_stats["jira_created"],
            jira_updated=total_stats["jira_updated"],
            dns_failures=total_dns_failures,
            duration_sec=duration_sec,
        )

        logger.info(f"Job completed successfully in {duration_sec:.2f} seconds")
        return 0

    except Exception as e:
        # Fatal error handling (FR-004, FR-030)
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
