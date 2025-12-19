"""Network connectivity verification utility.

Performs supplemental DNS checks to cloud providers to detect network-wide
DNS issues vs. DNSBL-specific failures.
"""

import dns.resolver
import dns.exception
from src.models.dnsbl_health import NetworkConnectivityResult


class NetworkChecker:
    """Performs supplemental DNS connectivity checks.

    Uses public DNS resolvers (Cloudflare and Google) to determine if DNS
    failures are network-wide or specific to DNSBL endpoints.
    """

    @staticmethod
    def check_connectivity(timeout: int = 5) -> NetworkConnectivityResult:
        """Check DNS connectivity to Cloudflare and Google public resolvers.

        Performs DNS A record lookups for 'google.com' using:
        - 1.1.1.1 (Cloudflare)
        - 8.8.8.8 (Google)

        Args:
            timeout: DNS query timeout in seconds (default: 5).

        Returns:
            NetworkConnectivityResult: Reachability status for both providers.

        Example:
            >>> result = NetworkChecker.check_connectivity()
            >>> if result.cloudflare_reachable and result.google_reachable:
            ...     print("Network connectivity OK")
        """

        def check_resolver(nameserver: str) -> bool:
            """Check if a specific DNS resolver is reachable.

            Args:
                nameserver: IP address of DNS resolver to test.

            Returns:
                bool: True if resolver responded with valid A records, False otherwise.
            """
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [nameserver]
            resolver.timeout = timeout
            resolver.lifetime = timeout

            try:
                answers = resolver.resolve("google.com", "A")
                return len(answers) > 0
            except (
                dns.exception.Timeout,
                dns.resolver.NXDOMAIN,
                dns.resolver.NoAnswer,
                dns.resolver.NoNameservers,
            ):
                return False
            except Exception:
                # Catch any other DNS exceptions (SERVFAIL, network errors, etc.)
                return False

        return NetworkConnectivityResult(
            check_enabled=True,
            cloudflare_reachable=check_resolver("1.1.1.1"),
            google_reachable=check_resolver("8.8.8.8"),
        )
