"""Jira client service for issue management."""

import logging
from typing import Optional

from jira import JIRA
from jira.exceptions import JIRAError

from src.utils.retry import exponential_backoff_retry


logger = logging.getLogger(__name__)


class JiraClient:
    """Jira API client with JQL-based deduplication and retry logic."""

    def __init__(
        self,
        server: str,
        user: str,
        token: str,
        project: str,
        issue_type: str,
        dns_failure_issue_type: str,
        excluded_statuses: list[str],
    ):
        """Initialize Jira client.

        Args:
            server: Jira server URL.
            user: Jira username or email.
            token: Jira API token.
            project: Jira project key.
            issue_type: Issue type for blacklist issues.
            dns_failure_issue_type: Issue type for DNS failures.
            excluded_statuses: Status names to exclude from JQL searches.
        """
        self.jira = JIRA(server=server, basic_auth=(user, token))
        self.project = project
        self.issue_type = issue_type
        self.dns_failure_issue_type = dns_failure_issue_type
        self.excluded_statuses = excluded_statuses

    @exponential_backoff_retry()
    def find_open_issue_for_ip(self, ip: str) -> Optional[dict]:
        """Search for open Jira issue associated with IP using JQL (FR-021).

        Args:
            ip: IPv4 address to search for.

        Returns:
            Optional[dict]: Issue dict if found, None otherwise.
        """
        # Construct JQL with configurable excluded statuses
        status_list = ",".join(f'"{s}"' for s in self.excluded_statuses)
        jql = f'project = "{self.project}" AND status NOT IN ({status_list}) AND summary ~ "IP {ip}"'

        try:
            issues = self.jira.search_issues(jql, maxResults=10)
        except JIRAError as e:
            logger.error(f"JQL search failed for IP {ip}: {e}")
            raise

        if not issues:
            return None

        if len(issues) > 1:
            # Edge case: multiple open issues (manual intervention occurred)
            logger.warning(f"Multiple open issues for IP {ip}, using most recent")
            # Sort by created date descending
            issues = sorted(issues, key=lambda i: i.fields.created, reverse=True)

        # Return issue as dict
        issue = issues[0]
        return {
            "key": issue.key,
            "summary": issue.fields.summary,
            "status": issue.fields.status.name,
        }

    @exponential_backoff_retry()
    def create_issue(self, ip: str, zones: list[str], description: str) -> str:
        """Create new Jira issue for blacklisted IP (FR-022).

        Args:
            ip: IPv4 address.
            zones: List of DNSBL zones where IP is listed.
            description: Detailed issue description.

        Returns:
            str: Issue key (e.g., "OPS-123").
        """
        sorted_zones = ",".join(sorted(zones))
        summary = f"IP {ip} blacklisted by {sorted_zones}"

        issue_dict = {
            "project": {"key": self.project},
            "summary": summary,
            "description": description,
            "issuetype": {"name": self.issue_type},
        }

        try:
            new_issue = self.jira.create_issue(fields=issue_dict)
            logger.info(f"Created Jira issue {new_issue.key} for IP {ip}")
            return new_issue.key
        except JIRAError as e:
            logger.error(f"Failed to create Jira issue for IP {ip}: {e}")
            raise

    @exponential_backoff_retry()
    def add_comment(self, issue_key: str, comment: str) -> None:
        """Add comment to existing Jira issue (FR-024).

        Args:
            issue_key: Jira issue key.
            comment: Comment text.
        """
        try:
            self.jira.add_comment(issue_key, comment)
            logger.info(f"Added comment to {issue_key}")
        except JIRAError as e:
            logger.error(f"Failed to add comment to {issue_key}: {e}")
            raise

    @exponential_backoff_retry()
    def create_dns_failure_issue(
        self, unknown_percentage: float, failed_zones: list[str]
    ) -> str:
        """Create MAJOR MALFUNCTION issue for DNS failures (FR-013a).

        Args:
            unknown_percentage: Percentage of zones returning UNKNOWN.
            failed_zones: List of zones that failed.

        Returns:
            str: Issue key.
        """
        summary = f"DNS Infrastructure Failure Detected - {unknown_percentage:.1f}% zones unreachable"
        description = (
            f"MAJOR MALFUNCTION: {unknown_percentage:.1f}% of DNSBL zones returned UNKNOWN.\n\n"
            f"Failed zones:\n" + "\n".join(f"- {zone}" for zone in failed_zones)
        )

        issue_dict = {
            "project": {"key": self.project},
            "summary": summary,
            "description": description,
            "issuetype": {"name": self.dns_failure_issue_type},
            "labels": ["MAJOR MALFUNCTION"],
        }

        try:
            new_issue = self.jira.create_issue(fields=issue_dict)
            logger.info(f"Created DNS failure issue {new_issue.key}")
            return new_issue.key
        except JIRAError as e:
            logger.error(f"Failed to create DNS failure issue: {e}")
            raise
