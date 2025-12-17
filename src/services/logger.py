"""Structured JSON logging for Kubernetes."""

import logging
import sys
import uuid
from datetime import datetime
from typing import Any, Dict

from pythonjsonlogger import jsonlogger


# Global job run ID for correlation across log entries
JOB_RUN_ID = str(uuid.uuid4())


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter that adds job_run_id and standardized fields."""

    def add_fields(
        self,
        log_record: Dict[str, Any],
        record: logging.LogRecord,
        message_dict: Dict[str, Any],
    ) -> None:
        """Add custom fields to log record.

        Args:
            log_record: The log record to modify.
            record: The original logging.LogRecord.
            message_dict: Additional fields from the logging call.
        """
        super().add_fields(log_record, record, message_dict)

        # Add timestamp in ISO 8601 format
        log_record["timestamp"] = datetime.utcnow().isoformat() + "Z"

        # Add job run ID for correlation
        log_record["job_run_id"] = JOB_RUN_ID

        # Add log level
        log_record["level"] = record.levelname

        # Add logger name
        log_record["logger"] = record.name


def setup_logging() -> logging.Logger:
    """Configure structured JSON logging for the application.

    Returns:
        logging.Logger: Configured root logger.
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # JSON handler for stdout (Kubernetes logs)
    json_handler = logging.StreamHandler(sys.stdout)
    formatter = CustomJsonFormatter(
        "%(message)s",  # Message field
        timestamp=True,
    )
    json_handler.setFormatter(formatter)
    logger.addHandler(json_handler)

    return logger


def log_ip_check(
    ip: str,
    listed_zones: list[str],
    unknown_zones: list[str],
    decision: str,
    db_changes: bool,
    jira_action: str,
    duration_ms: int,
) -> None:
    """Log structured per-IP check result (FR-028).

    Args:
        ip: IPv4 address checked.
        listed_zones: DNSBL zones where IP is LISTED.
        unknown_zones: DNSBL zones that returned UNKNOWN.
        decision: Final listing decision (LISTED or CLEAN).
        db_changes: Whether database was updated.
        jira_action: Jira action taken (created_issue, updated_issue, no_action).
        duration_ms: Processing time in milliseconds.
    """
    logger = logging.getLogger(__name__)
    logger.info(
        "IP check completed",
        extra={
            "ip": ip,
            "listed_zones": listed_zones,
            "unknown_zones": unknown_zones,
            "decision": decision,
            "db_changes": db_changes,
            "jira_action": jira_action,
            "duration_ms": duration_ms,
        },
    )


def log_job_summary(
    total_ips: int,
    listed: int,
    cleaned: int,
    unchanged: int,
    jira_created: int,
    jira_updated: int,
    dns_failures: int,
    duration_sec: float,
) -> None:
    """Log job completion summary (FR-031).

    Args:
        total_ips: Total number of IPs checked.
        listed: Number of IPs newly listed.
        cleaned: Number of IPs cleaned.
        unchanged: Number of IPs with no state change.
        jira_created: Number of Jira issues created.
        jira_updated: Number of Jira issues updated.
        dns_failures: Number of DNS failures encountered.
        duration_sec: Total job execution time in seconds.
    """
    logger = logging.getLogger(__name__)
    logger.info(
        "Job completed",
        extra={
            "total_ips": total_ips,
            "listed": listed,
            "cleaned": cleaned,
            "unchanged": unchanged,
            "jira_created": jira_created,
            "jira_updated": jira_updated,
            "dns_failures": dns_failures,
            "duration_sec": duration_sec,
        },
    )


def log_dns_failure(unknown_percentage: float, failed_zones: list[str]) -> None:
    """Log DNS infrastructure failure when >50% zones return UNKNOWN.

    Args:
        unknown_percentage: Percentage of zones returning UNKNOWN.
        failed_zones: List of zones that returned UNKNOWN.
    """
    logger = logging.getLogger(__name__)
    logger.error(
        "DNS infrastructure failure detected",
        extra={
            "unknown_percentage": unknown_percentage,
            "failed_zones": failed_zones,
            "severity": "MAJOR MALFUNCTION",
        },
    )
