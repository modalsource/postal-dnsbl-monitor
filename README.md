# Postal DNSBL Monitor

A stateless, containerized Python 3.14 application that runs as a Kubernetes CronJob to periodically check IPv4 addresses against DNSBL (DNS-based Blackhole List) providers. It automatically throttles blacklisted IPs in the Postal mail server database and creates Jira tracking tickets.

## Features

- **Automatic DNSBL Monitoring**: Checks IP addresses against configurable DNSBL zones
- **Smart Throttling**: Automatically updates MySQL database to throttle listed IPs
- **Jira Integration**: Creates and updates tickets with JQL-based deduplication
- **Fault Tolerant**: Handles DNS failures gracefully, alerts on systemic issues
- **Idempotent**: Safe to re-run without creating duplicates
- **Observable**: Structured JSON logging for Kubernetes log aggregation

## Quick Start

See the comprehensive quickstart guide at:
[specs/001-postal-dnsbl-monitor/quickstart.md](specs/001-postal-dnsbl-monitor/quickstart.md)

## Project Structure

```
src/                  # Python source code
tests/                # Test suite (unit, integration, contract)
kubernetes/           # Kubernetes manifests (CronJob, ConfigMap, Secret)
specs/                # Feature specifications and documentation
```

## Documentation

- **Specification**: [specs/001-postal-dnsbl-monitor/spec.md](specs/001-postal-dnsbl-monitor/spec.md)
- **Implementation Plan**: [specs/001-postal-dnsbl-monitor/plan.md](specs/001-postal-dnsbl-monitor/plan.md)
- **Data Model**: [specs/001-postal-dnsbl-monitor/data-model.md](specs/001-postal-dnsbl-monitor/data-model.md)
- **Technical Research**: [specs/001-postal-dnsbl-monitor/research.md](specs/001-postal-dnsbl-monitor/research.md)

## Requirements

- Python 3.14+
- MySQL 5.7+ (or MariaDB 10.2+) with Postal mail server database
- Jira Cloud/Server instance
- Kubernetes cluster (for production deployment)

## Development

```bash
# Install dependencies
uv sync

# Run tests
pytest tests/ -v --cov=src

# Run locally (dry-run mode)
export DRY_RUN=true
python src/main.py
```

