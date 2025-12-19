"""Unit tests for configuration validation."""

import os
import pytest

from src.config import Config


def test_config_from_env_valid(monkeypatch):
    """Test loading valid configuration from environment variables."""
    # Set all required environment variables
    env_vars = {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "postal",
        "DB_USER": "test_user",
        "DB_PASSWORD": "test_pass",
        "DNSBL_ZONES": "zen.spamhaus.org,bl.spamcop.net",
        "JIRA_SERVER": "https://test.atlassian.net",
        "JIRA_USER": "test@example.com",
        "JIRA_API_TOKEN": "test_token",
        "JIRA_PROJECT": "OPS",
        "JIRA_ISSUE_TYPE": "Incident",
        "JIRA_DNS_FAILURE_ISSUE_TYPE": "Alert",
    }

    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    config = Config.from_env()

    assert config.db_host == "localhost"
    assert config.db_port == 5432
    assert config.db_name == "postal"
    assert config.dnsbl_zones == ["zen.spamhaus.org", "bl.spamcop.net"]
    assert config.dns_timeout == 5  # Default
    assert config.dns_concurrency == 10  # Default
    assert config.listed_priority == 0  # Default
    assert config.clean_fallback_priority == 50  # Default
    assert config.jira_server == "https://test.atlassian.net"
    assert config.dry_run is False  # Default


def test_config_missing_required_var(monkeypatch):
    """Test that missing required variable raises ValueError."""
    # Clear all env vars
    for key in os.environ.keys():
        if key.startswith("DB_") or key.startswith("JIRA_") or key.startswith("DNSBL_"):
            monkeypatch.delenv(key, raising=False)

    with pytest.raises(
        ValueError, match="Required environment variable DB_HOST is not set"
    ):
        Config.from_env()


def test_config_invalid_jira_server(monkeypatch):
    """Test that non-HTTPS Jira server raises ValueError."""
    env_vars = {
        "DB_HOST": "localhost",
        "DB_NAME": "postal",
        "DB_USER": "test_user",
        "DB_PASSWORD": "test_pass",
        "DNSBL_ZONES": "zen.spamhaus.org",
        "JIRA_SERVER": "http://test.atlassian.net",  # Invalid: HTTP not HTTPS
        "JIRA_USER": "test@example.com",
        "JIRA_API_TOKEN": "test_token",
        "JIRA_PROJECT": "OPS",
        "JIRA_ISSUE_TYPE": "Incident",
        "JIRA_DNS_FAILURE_ISSUE_TYPE": "Alert",
    }

    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(ValueError, match="JIRA_SERVER must be an HTTPS URL"):
        Config.from_env()


def test_config_priority_validation(monkeypatch):
    """Test that LISTED_PRIORITY must be < CLEAN_FALLBACK_PRIORITY."""
    env_vars = {
        "DB_HOST": "localhost",
        "DB_NAME": "postal",
        "DB_USER": "test_user",
        "DB_PASSWORD": "test_pass",
        "DNSBL_ZONES": "zen.spamhaus.org",
        "LISTED_PRIORITY": "60",  # Invalid: greater than CLEAN_FALLBACK_PRIORITY
        "CLEAN_FALLBACK_PRIORITY": "50",
        "JIRA_SERVER": "https://test.atlassian.net",
        "JIRA_USER": "test@example.com",
        "JIRA_API_TOKEN": "test_token",
        "JIRA_PROJECT": "OPS",
        "JIRA_ISSUE_TYPE": "Incident",
        "JIRA_DNS_FAILURE_ISSUE_TYPE": "Alert",
    }

    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(
        ValueError, match="LISTED_PRIORITY.*must be < CLEAN_FALLBACK_PRIORITY"
    ):
        Config.from_env()


def test_config_dry_run_parsing(monkeypatch):
    """Test that DRY_RUN boolean parsing works correctly."""
    base_env = {
        "DB_HOST": "localhost",
        "DB_NAME": "postal",
        "DB_USER": "test_user",
        "DB_PASSWORD": "test_pass",
        "DNSBL_ZONES": "zen.spamhaus.org",
        "JIRA_SERVER": "https://test.atlassian.net",
        "JIRA_USER": "test@example.com",
        "JIRA_API_TOKEN": "test_token",
        "JIRA_PROJECT": "OPS",
        "JIRA_ISSUE_TYPE": "Incident",
        "JIRA_DNS_FAILURE_ISSUE_TYPE": "Alert",
    }

    # Test true values
    for dry_run_value in ["true", "True", "TRUE", "1", "yes"]:
        for key, value in base_env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("DRY_RUN", dry_run_value)

        config = Config.from_env()
        assert config.dry_run is True, f"Expected True for DRY_RUN={dry_run_value}"

    # Test false values
    for dry_run_value in ["false", "False", "FALSE", "0", "no", ""]:
        for key, value in base_env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("DRY_RUN", dry_run_value)

        config = Config.from_env()
        assert config.dry_run is False, f"Expected False for DRY_RUN={dry_run_value}"


def test_config_verbose_parsing(monkeypatch):
    """Test that VERBOSE boolean parsing works correctly."""
    base_env = {
        "DB_HOST": "localhost",
        "DB_NAME": "postal",
        "DB_USER": "test_user",
        "DB_PASSWORD": "test_pass",
        "DNSBL_ZONES": "zen.spamhaus.org",
        "JIRA_SERVER": "https://test.atlassian.net",
        "JIRA_USER": "test@example.com",
        "JIRA_API_TOKEN": "test_token",
        "JIRA_PROJECT": "OPS",
        "JIRA_ISSUE_TYPE": "Incident",
        "JIRA_DNS_FAILURE_ISSUE_TYPE": "Alert",
    }

    # Test true values
    for verbose_value in ["true", "True", "TRUE", "1", "yes"]:
        for key, value in base_env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("VERBOSE", verbose_value)

        config = Config.from_env()
        assert config.verbose is True, f"Expected True for VERBOSE={verbose_value}"

    # Test false values (default)
    for key, value in base_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("VERBOSE", raising=False)

    config = Config.from_env()
    assert config.verbose is False, "Expected False for VERBOSE not set (default)"


def test_config_enable_network_connectivity_check_default(monkeypatch):
    """Test that ENABLE_NETWORK_CONNECTIVITY_CHECK defaults to true."""
    base_env = {
        "DB_HOST": "localhost",
        "DB_NAME": "postal",
        "DB_USER": "test_user",
        "DB_PASSWORD": "test_pass",
        "DNSBL_ZONES": "zen.spamhaus.org",
        "JIRA_SERVER": "https://test.atlassian.net",
        "JIRA_USER": "test@example.com",
        "JIRA_API_TOKEN": "test_token",
        "JIRA_PROJECT": "OPS",
        "JIRA_ISSUE_TYPE": "Incident",
        "JIRA_DNS_FAILURE_ISSUE_TYPE": "Alert",
    }

    for key, value in base_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("ENABLE_NETWORK_CONNECTIVITY_CHECK", raising=False)

    config = Config.from_env()
    assert config.enable_network_connectivity_check is True, "Expected True by default"
