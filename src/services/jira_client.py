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
    def transition_issue_to_done(self, issue_key: str) -> None:
        """Transition issue to Done status when IP is cleared.

        Args:
            issue_key: Jira issue key to close.
        """
        try:
            # Get available transitions for this issue
            transitions = self.jira.transitions(issue_key)

            # Find the "Done" transition ID (case-insensitive)
            done_transition_id = None
            for transition in transitions:
                if transition["name"].lower() == "done":
                    done_transition_id = transition["id"]
                    break

            if not done_transition_id:
                logger.warning(
                    f"No 'Done' transition found for {issue_key}, available: {[t['name'] for t in transitions]}"
                )
                return

            # Transition the issue
            self.jira.transition_issue(issue_key, done_transition_id)
            logger.info(f"Transitioned {issue_key} to Done")
        except JIRAError as e:
            logger.error(f"Failed to transition {issue_key} to Done: {e}")
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

    @exponential_backoff_retry()
    def find_run_report_issue(self) -> Optional[dict]:
        """Search for open 'Run Report' issue.

        Returns:
            Optional[dict]: Issue dict if found, None otherwise.
        """
        status_list = ",".join(f'"{s}"' for s in self.excluded_statuses)
        jql = f'project = "{self.project}" AND status NOT IN ({status_list}) AND summary ~ "Run Report"'

        try:
            issues = self.jira.search_issues(jql, maxResults=10)
        except JIRAError as e:
            logger.error(f"JQL search failed for Run Report: {e}")
            raise

        if not issues:
            return None

        if len(issues) > 1:
            logger.warning("Multiple open Run Report issues, using most recent")
            issues = sorted(issues, key=lambda i: i.fields.created, reverse=True)

        issue = issues[0]
        return {
            "key": issue.key,
            "summary": issue.fields.summary,
            "status": issue.fields.status.name,
        }

    @exponential_backoff_retry()
    def create_or_update_run_report(
        self, json_report: str, yaml_report: str | None, execution_timestamp: str
    ) -> str:
        """Create or update Run Report issue with health diagnostics.

        If an open 'Run Report' issue exists, adds a comment with the new report.
        Otherwise, creates a new issue.

        Args:
            json_report: JSON health summary report.
            yaml_report: YAML pruned configuration (None if no broken DNSBLs).
            execution_timestamp: ISO 8601 timestamp of execution.

        Returns:
            str: Issue key (created or updated).
        """
        # Build report content
        report_content = f"*Execution completed at:* {execution_timestamp}\n\n"
        report_content += "h3. DNSBL Health Summary\n\n"
        report_content += "{code:json}\n"
        report_content += json_report
        report_content += "\n{code}\n\n"

        if yaml_report:
            report_content += "h3. Suggested DNSBL Configuration (Pruned)\n\n"
            report_content += "{code:yaml}\n"
            report_content += yaml_report
            report_content += "\n{code}\n\n"
            report_content += "⚠️ *Action Required:* Review the pruned configuration above and update DNSBL_ZONES environment variable if broken endpoints should be removed.\n"
        else:
            report_content += (
                "✅ *All DNSBLs healthy* - No configuration changes needed.\n"
            )

        # Check if Run Report issue already exists
        existing_issue = self.find_run_report_issue()

        if existing_issue:
            # Update existing issue with comment
            issue_key = existing_issue["key"]
            logger.info(f"Updating existing Run Report issue {issue_key}")
            self.add_comment(issue_key, report_content)
            return issue_key
        else:
            # Create new Run Report issue
            summary = "Run Report"
            description = (
                "This issue tracks DNSBL health monitoring diagnostics and configuration recommendations.\n\n"
                "Each execution appends a new report as a comment.\n\n" + report_content
            )

            issue_dict = {
                "project": {"key": self.project},
                "summary": summary,
                "description": description,
                "issuetype": {"name": self.issue_type},
                "labels": ["run-report", "dnsbl-health"],
            }

            try:
                new_issue = self.jira.create_issue(fields=issue_dict)
                logger.info(f"Created new Run Report issue {new_issue.key}")
                return new_issue.key
            except JIRAError as e:
                logger.error(f"Failed to create Run Report issue: {e}")
                raise
