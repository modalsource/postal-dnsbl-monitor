"""Configuration module for Postal DNSBL Monitor.

Loads and validates environment variables per contracts/config-schema.yaml.
"""

import os
from dataclasses import dataclass
from typing import List


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    # Database Configuration
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    db_dsn: str | None

    # DNSBL Configuration
    dnsbl_zones: List[str]
    dns_timeout: int
    dns_concurrency: int

    # Priority Configuration
    listed_priority: int
    clean_fallback_priority: int

    # Jira Configuration
    jira_server: str
    jira_user: str
    jira_api_token: str
    jira_project: str
    jira_issue_type: str
    jira_dns_failure_issue_type: str
    jira_excluded_statuses: List[str]

    # Operational Configuration
    dry_run: bool
    enable_network_connectivity_check: bool
    verbose: bool

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables.

        Raises:
            ValueError: If required variables are missing or invalid.

        Returns:
            Config: Validated configuration instance.
        """
        # Database Configuration
        db_dsn = os.getenv("DB_DSN")
        if db_dsn:
            # DSN provided - extract individual components for validation
            db_host = db_dsn.split("@")[-1].split(":")[0] if "@" in db_dsn else ""
            db_port = 3306
            db_name = ""
            db_user = ""
            db_password = ""
        else:
            # Individual parameters required
            db_host = cls._get_required_env("DB_HOST")
            db_port = int(os.getenv("DB_PORT", "3306"))
            db_name = cls._get_required_env("DB_NAME")
            db_user = cls._get_required_env("DB_USER")
            db_password = cls._get_required_env("DB_PASSWORD")

        # DNSBL Configuration
        dnsbl_zones_str = cls._get_required_env("DNSBL_ZONES")
        dnsbl_zones = [
            zone.strip() for zone in dnsbl_zones_str.split(",") if zone.strip()
        ]
        if not dnsbl_zones:
            raise ValueError("DNSBL_ZONES must contain at least one zone")

        dns_timeout = int(os.getenv("DNS_TIMEOUT", "5"))
        if not 1 <= dns_timeout <= 60:
            raise ValueError("DNS_TIMEOUT must be between 1 and 60 seconds")

        dns_concurrency = int(os.getenv("DNS_CONCURRENCY", "10"))
        if not 1 <= dns_concurrency <= 100:
            raise ValueError("DNS_CONCURRENCY must be between 1 and 100")

        # Priority Configuration
        listed_priority = int(os.getenv("LISTED_PRIORITY", "0"))
        clean_fallback_priority = int(os.getenv("CLEAN_FALLBACK_PRIORITY", "50"))

        if not 0 <= listed_priority <= 100:
            raise ValueError("LISTED_PRIORITY must be between 0 and 100")
        if not 0 <= clean_fallback_priority <= 100:
            raise ValueError("CLEAN_FALLBACK_PRIORITY must be between 0 and 100")
        if listed_priority >= clean_fallback_priority:
            raise ValueError(
                f"LISTED_PRIORITY ({listed_priority}) must be < CLEAN_FALLBACK_PRIORITY ({clean_fallback_priority})"
            )

        # Jira Configuration
        jira_server = cls._get_required_env("JIRA_SERVER")
        if not jira_server.startswith("https://"):
            raise ValueError("JIRA_SERVER must be an HTTPS URL")

        jira_user = cls._get_required_env("JIRA_USER")
        jira_api_token = cls._get_required_env("JIRA_API_TOKEN")
        jira_project = cls._get_required_env("JIRA_PROJECT")
        jira_issue_type = cls._get_required_env("JIRA_ISSUE_TYPE")
        jira_dns_failure_issue_type = cls._get_required_env(
            "JIRA_DNS_FAILURE_ISSUE_TYPE"
        )

        jira_excluded_statuses_str = os.getenv(
            "JIRA_EXCLUDED_STATUSES", "Done,Closed,Resolved"
        )
        jira_excluded_statuses = [
            status.strip()
            for status in jira_excluded_statuses_str.split(",")
            if status.strip()
        ]

        # Operational Configuration
        dry_run_str = os.getenv("DRY_RUN", "false").lower()
        dry_run = dry_run_str in ("true", "1", "yes")

        enable_network_connectivity_check_str = os.getenv(
            "ENABLE_NETWORK_CONNECTIVITY_CHECK", "true"
        ).lower()
        enable_network_connectivity_check = enable_network_connectivity_check_str in (
            "true",
            "1",
            "yes",
        )

        verbose_str = os.getenv("VERBOSE", "false").lower()
        verbose = verbose_str in ("true", "1", "yes")

        return cls(
            db_host=db_host,
            db_port=db_port,
            db_name=db_name,
            db_user=db_user,
            db_password=db_password,
            db_dsn=db_dsn,
            dnsbl_zones=dnsbl_zones,
            dns_timeout=dns_timeout,
            dns_concurrency=dns_concurrency,
            listed_priority=listed_priority,
            clean_fallback_priority=clean_fallback_priority,
            jira_server=jira_server,
            jira_user=jira_user,
            jira_api_token=jira_api_token,
            jira_project=jira_project,
            jira_issue_type=jira_issue_type,
            jira_dns_failure_issue_type=jira_dns_failure_issue_type,
            jira_excluded_statuses=jira_excluded_statuses,
            dry_run=dry_run,
            enable_network_connectivity_check=enable_network_connectivity_check,
            verbose=verbose,
        )

    @staticmethod
    def _get_required_env(key: str) -> str:
        """Get required environment variable or raise ValueError.

        Args:
            key: Environment variable name.

        Returns:
            str: Environment variable value.

        Raises:
            ValueError: If environment variable is not set or empty.
        """
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value

    def get_db_connection_string(self) -> str:
        """Build MySQL connection string.

        Returns:
            str: MySQL DSN connection string.
        """
        if self.db_dsn:
            return self.db_dsn

        return (
            f"mysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
