"""Unit tests for NetworkChecker utility."""

import pytest
from unittest.mock import patch, MagicMock
import dns.resolver
import dns.exception

from src.utils.network_check import NetworkChecker
from src.models.dnsbl_health import NetworkConnectivityResult


class TestNetworkChecker:
    """Test NetworkChecker.check_connectivity() method."""

    @patch("src.utils.network_check.dns.resolver.Resolver")
    def test_check_connectivity_both_reachable(self, mock_resolver_class):
        """Test when both Cloudflare and Google are reachable."""
        # Mock resolver to return successful answers
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [MagicMock()]  # Non-empty answers
        mock_resolver_class.return_value = mock_resolver

        result = NetworkChecker.check_connectivity(timeout=5)

        assert result.check_enabled is True
        assert result.cloudflare_reachable is True
        assert result.google_reachable is True

    @patch("src.utils.network_check.dns.resolver.Resolver")
    def test_check_connectivity_both_unreachable(self, mock_resolver_class):
        """Test when both providers are unreachable."""
        # Mock resolver to raise Timeout
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = dns.exception.Timeout()
        mock_resolver_class.return_value = mock_resolver

        result = NetworkChecker.check_connectivity(timeout=5)

        assert result.check_enabled is True
        assert result.cloudflare_reachable is False
        assert result.google_reachable is False

    @patch("src.utils.network_check.dns.resolver.Resolver")
    def test_check_connectivity_cloudflare_only(self, mock_resolver_class):
        """Test when only Cloudflare is reachable."""
        mock_resolver = MagicMock()

        # First call (Cloudflare) succeeds, second call (Google) fails
        mock_resolver.resolve.side_effect = [
            [MagicMock()],  # Cloudflare success
            dns.exception.Timeout(),  # Google timeout
        ]
        mock_resolver_class.return_value = mock_resolver

        result = NetworkChecker.check_connectivity(timeout=5)

        assert result.check_enabled is True
        assert result.cloudflare_reachable is True
        assert result.google_reachable is False

    @patch("src.utils.network_check.dns.resolver.Resolver")
    def test_check_connectivity_google_only(self, mock_resolver_class):
        """Test when only Google is reachable."""
        mock_resolver = MagicMock()

        # First call (Cloudflare) fails, second call (Google) succeeds
        mock_resolver.resolve.side_effect = [
            dns.exception.Timeout(),  # Cloudflare timeout
            [MagicMock()],  # Google success
        ]
        mock_resolver_class.return_value = mock_resolver

        result = NetworkChecker.check_connectivity(timeout=5)

        assert result.check_enabled is True
        assert result.cloudflare_reachable is False
        assert result.google_reachable is True

    @patch("src.utils.network_check.dns.resolver.Resolver")
    def test_check_connectivity_handles_nxdomain(self, mock_resolver_class):
        """Test handling of NXDOMAIN response."""
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = dns.resolver.NXDOMAIN()
        mock_resolver_class.return_value = mock_resolver

        result = NetworkChecker.check_connectivity(timeout=5)

        assert result.cloudflare_reachable is False
        assert result.google_reachable is False

    @patch("src.utils.network_check.dns.resolver.Resolver")
    def test_check_connectivity_handles_no_answer(self, mock_resolver_class):
        """Test handling of NoAnswer response."""
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = dns.resolver.NoAnswer()
        mock_resolver_class.return_value = mock_resolver

        result = NetworkChecker.check_connectivity(timeout=5)

        assert result.cloudflare_reachable is False
        assert result.google_reachable is False

    @patch("src.utils.network_check.dns.resolver.Resolver")
    def test_check_connectivity_handles_no_nameservers(self, mock_resolver_class):
        """Test handling of NoNameservers response."""
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = dns.resolver.NoNameservers()
        mock_resolver_class.return_value = mock_resolver

        result = NetworkChecker.check_connectivity(timeout=5)

        assert result.cloudflare_reachable is False
        assert result.google_reachable is False

    @patch("src.utils.network_check.dns.resolver.Resolver")
    def test_check_connectivity_handles_generic_exception(self, mock_resolver_class):
        """Test handling of generic exceptions."""
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = Exception("Network error")
        mock_resolver_class.return_value = mock_resolver

        result = NetworkChecker.check_connectivity(timeout=5)

        assert result.cloudflare_reachable is False
        assert result.google_reachable is False

    @patch("src.utils.network_check.dns.resolver.Resolver")
    def test_check_connectivity_sets_timeout(self, mock_resolver_class):
        """Test that timeout is properly configured on resolver."""
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [MagicMock()]
        mock_resolver_class.return_value = mock_resolver

        NetworkChecker.check_connectivity(timeout=10)

        # Verify timeout was set
        assert mock_resolver.timeout == 10
        assert mock_resolver.lifetime == 10

    @patch("src.utils.network_check.dns.resolver.Resolver")
    def test_check_connectivity_queries_google_com(self, mock_resolver_class):
        """Test that queries are made for google.com A record."""
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [MagicMock()]
        mock_resolver_class.return_value = mock_resolver

        NetworkChecker.check_connectivity()

        # Should have been called twice (Cloudflare + Google)
        assert mock_resolver.resolve.call_count == 2

        # Both calls should be for "google.com" A record
        for call in mock_resolver.resolve.call_args_list:
            args, kwargs = call
            assert args[0] == "google.com"
            assert args[1] == "A"
