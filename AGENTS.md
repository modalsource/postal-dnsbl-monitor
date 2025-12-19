# postal-dnsbl-monitor Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-12-17

## Active Technologies
- Python 3.14 + dnspython (DNS lookups), python-json-logger (structured logging), PyYAML (YAML generation) (002-dnsbl-health-report)
- In-memory aggregation only (no persistent storage per Constitution Principle I) (002-dnsbl-health-report)

- Python 3.14 (001-postal-dnsbl-monitor)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.14: Follow standard conventions

## Recent Changes
- 002-dnsbl-health-report: Added Python 3.14 + dnspython (DNS lookups), python-json-logger (structured logging), PyYAML (YAML generation)

- 001-postal-dnsbl-monitor: Added Python 3.14

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
