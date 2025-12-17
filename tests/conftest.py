"""pytest fixtures for testing."""

import pytest
from unittest.mock import Mock


@pytest.fixture
def mock_jira():
    """Mock Jira client for unit tests."""
    mock = Mock()
    mock.search_issues.return_value = []
    mock.create_issue.return_value = Mock(key="OPS-123")
    return mock


@pytest.fixture
def sample_ip_record():
    """Sample IP record for testing."""
    from src.models.ip_record import IPRecord

    return IPRecord(
        id=1,
        ip="203.0.113.45",
        priority=50,
        old_priority=None,
        blocking_lists="",
        last_event=None,
    )
