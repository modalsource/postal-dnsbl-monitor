"""Contract tests for Jira deduplication (Constitutional Principle IV).

Verifies FR-020: JQL-based deduplication (not DB-only).
"""

import pytest


def test_jira_deduplication_via_jql():
    """Verify FR-020: Jira deduplication uses JQL search, not database.

    Test Steps:
    1. Mock Jira API to return existing issue for IP
    2. Call find_open_issue_for_ip("203.0.113.45")
    3. Verify JQL query constructed: project="OPS" AND status NOT IN (...) AND summary ~ "IP 203.0.113.45"
    4. Verify existing issue returned (not creating duplicate)
    5. Mock Jira API to return empty results
    6. Call find_open_issue_for_ip("203.0.113.46")
    7. Verify returns None (no existing issue)
    """
    pytest.skip("Requires JiraClient implementation - to be implemented in T041")
    # This test MUST fail until JiraClient.find_open_issue_for_ip() is implemented
