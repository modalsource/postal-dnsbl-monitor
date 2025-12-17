# Technical Research: Postal DNSBL Monitor

**Date**: 2025-12-17  
**Purpose**: Document technical decisions and best practices for implementing the DNSBL monitoring CronJob

---

## 1. DNS Library: dnspython for Concurrent DNSBL Lookups

### Decision

Use **dnspython with threading** (via `concurrent.futures.ThreadPoolExecutor`) for concurrent DNSBL lookups with configurable timeout and concurrency limit.

### Rationale

- **Performance**: Threading is sufficient for I/O-bound DNS queries. Python's GIL doesn't block I/O operations.
- **Simplicity**: dnspython synchronous API is simpler than async alternatives, no event loop management needed for CronJob.
- **Constitutional Compliance**: dnspython is mandated by constitution v1.2.0
- **Timeout Control**: dnspython's resolver supports per-query timeouts via `lifetime` parameter
- **Scale**: ThreadPoolExecutor with 10 workers can handle 1000 IPs × 10 zones (~10k queries) well within 5-minute requirement

### Code Example

```python
import dns.resolver
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple
from enum import Enum

class DNSStatus(Enum):
    LISTED = "LISTED"
    NOT_LISTED = "NOT_LISTED"
    UNKNOWN = "UNKNOWN"

def reverse_ip(ip: str) -> str:
    """Convert 203.0.113.45 to 45.113.0.203"""
    octets = ip.split('.')
    return '.'.join(reversed(octets))

def check_dnsbl(ip: str, zone: str, timeout: int = 5) -> Tuple[str, DNSStatus, str]:
    """
    Check single IP against single DNSBL zone.
    
    Returns: (zone, status, response_data)
    """
    query_hostname = f"{reverse_ip(ip)}.{zone}"
    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout  # Total timeout for query
    
    try:
        answers = resolver.resolve(query_hostname, 'A')
        # DNSBL typically returns 127.0.0.x for listings
        response = str(answers[0])
        return (zone, DNSStatus.LISTED, response)
    
    except dns.resolver.NXDOMAIN:
        # Definitive "not listed" response
        return (zone, DNSStatus.NOT_LISTED, "")
    
    except (dns.resolver.NoAnswer, dns.resolver.Timeout, 
            dns.resolver.NoNameservers, dns.exception.DNSException) as e:
        # Transient failures - cannot determine status
        return (zone, DNSStatus.UNKNOWN, str(type(e).__name__))

def check_ip_concurrent(ip: str, zones: List[str], 
                        concurrency: int = 10, timeout: int = 5) -> List[Tuple[str, DNSStatus, str]]:
    """
    Check single IP against multiple DNSBL zones concurrently.
    
    Args:
        ip: IPv4 address (e.g., "203.0.113.45")
        zones: List of DNSBL zone domains
        concurrency: Max concurrent DNS queries
        timeout: Per-query timeout in seconds
        
    Returns: List of (zone, status, response_data) tuples
    """
    results = []
    
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # Submit all zone checks for this IP
        futures = {
            executor.submit(check_dnsbl, ip, zone, timeout): zone 
            for zone in zones
        }
        
        # Collect results as they complete
        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                # Unexpected error - treat as UNKNOWN
                zone = futures[future]
                results.append((zone, DNSStatus.UNKNOWN, f"Exception: {e}"))
    
    return results
```

### Alternatives Considered

- **asyncio with aiodns**: More complex for CronJob use case, no significant benefit over threading for I/O-bound DNS
- **Serial queries**: Too slow - 10k queries at 5s timeout each = 50k seconds worst case
- **multiprocessing**: Overkill for I/O-bound task, higher overhead than threading

---

## 2. Jira API Client: jira-python with Exponential Backoff

### Decision

Use **jira library (pycontribs)** with custom exponential backoff decorator (2s, 4s, 8s intervals) and JQL-based deduplication.

### Rationale

- **Constitutional Mandate**: `jira` library specified in constitution v1.2.0
- **Retry Strategy**: Custom decorator provides precise 2s/4s/8s backoff per clarification (vs generic retry libraries)
- **JQL Flexibility**: Supports configurable JIRA_EXCLUDED_STATUSES for different workflows
- **Rate Limit Handling**: Detect 429 responses and apply backoff automatically

### Code Example

```python
import time
from functools import wraps
from jira import JIRA
from jira.exceptions import JIRAError
from typing import Optional, List

def exponential_backoff_retry(max_retries=3, delays=[2, 4, 8]):
    """
    Decorator for exponential backoff retry (2s, 4s, 8s).
    Retries on rate limits (429) and transient errors (5xx).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except JIRAError as e:
                    # Retry on rate limit or server errors
                    if e.status_code in (429, 500, 502, 503, 504):
                        if attempt < max_retries:
                            delay = delays[attempt]
                            print(f"Jira error {e.status_code}, retrying in {delay}s...")
                            time.sleep(delay)
                            continue
                    # Non-retryable error or retries exhausted
                    raise
            raise Exception(f"Max retries ({max_retries}) exhausted")
        return wrapper
    return decorator

class JiraClient:
    def __init__(self, server: str, user: str, token: str, 
                 project: str, issue_type: str, 
                 excluded_statuses: str = "Done,Closed,Resolved"):
        self.jira = JIRA(server=server, basic_auth=(user, token))
        self.project = project
        self.issue_type = issue_type
        self.excluded_statuses = [s.strip() for s in excluded_statuses.split(',')]
    
    @exponential_backoff_retry()
    def find_open_issue_for_ip(self, ip: str) -> Optional[dict]:
        """
        Search for open Jira issue associated with IP using JQL.
        
        Returns: Issue dict if found, None otherwise
        """
        # Construct JQL with configurable excluded statuses
        status_list = ','.join(f'"{s}"' for s in self.excluded_statuses)
        jql = f'project = "{self.project}" AND status NOT IN ({status_list}) AND summary ~ "IP {ip}"'
        
        issues = self.jira.search_issues(jql, maxResults=10)
        
        if not issues:
            return None
        
        if len(issues) > 1:
            # Edge case: multiple open issues (manual intervention occurred)
            print(f"WARNING: Multiple open issues for IP {ip}, using most recent")
            # Sort by created date descending
            issues = sorted(issues, key=lambda i: i.fields.created, reverse=True)
        
        return issues[0]
    
    @exponential_backoff_retry()
    def create_issue(self, ip: str, zones: List[str], description: str) -> str:
        """
        Create new Jira issue for blacklisted IP.
        
        Returns: Issue key (e.g., "OPS-123")
        """
        sorted_zones = ','.join(sorted(zones))
        summary = f"IP {ip} blacklisted by {sorted_zones}"
        
        issue_dict = {
            'project': {'key': self.project},
            'summary': summary,
            'description': description,
            'issuetype': {'name': self.issue_type}
        }
        
        new_issue = self.jira.create_issue(fields=issue_dict)
        return new_issue.key
    
    @exponential_backoff_retry()
    def add_comment(self, issue_key: str, comment: str):
        """Add comment to existing issue."""
        self.jira.add_comment(issue_key, comment)
```

### Alternatives Considered

- **requests + manual API calls**: More control but loses jira library's abstractions and error handling
- **tenacity library for retry**: Generic but requires custom delay config, less explicit than custom decorator
- **DB-only deduplication**: Violates constitution principle IV (Jira is source of truth)

---

## 3. PostgreSQL Transactions: psycopg2 with READ COMMITTED

### Decision

Use **psycopg2** with READ COMMITTED isolation (PostgreSQL default), context managers for transaction boundaries, and batch UPDATE statements for idempotent updates.

### Rationale

- **Constitutional Mandate**: psycopg2 specified in constitution v1.2.0
- **Isolation Level**: READ COMMITTED sufficient for "last committed wins" semantics per clarification
- **Idempotency**: Conditional UPDATE with WHERE clause ensures no-op when state unchanged
- **Simplicity**: No connection pooling needed for CronJob (single execution, then exit)

### Code Example

```python
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_READ_COMMITTED
from contextlib import contextmanager
from typing import List, Dict, Optional

@contextmanager
def get_db_connection(dsn: str):
    """
    Context manager for PostgreSQL connection with READ COMMITTED isolation.
    Ensures connection is properly closed even on errors.
    """
    conn = psycopg2.connect(dsn)
    conn.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
    try:
        yield conn
        conn.commit()  # Commit on successful context exit
    except Exception:
        conn.rollback()  # Rollback on any exception
        raise
    finally:
        conn.close()

class DatabaseService:
    def __init__(self, dsn: str):
        self.dsn = dsn
    
    def get_all_ips(self) -> List[Dict]:
        """
        Fetch all IP records from postal.ip_addresses.
        
        Returns: List of dicts with id, ip, priority, oldPriority, blockingLists, lastEvent
        """
        with get_db_connection(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, ip, priority, "oldPriority", "blockingLists", "lastEvent"
                    FROM postal.ip_addresses
                """)
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
    
    def update_ip_listed(self, ip_id: int, current_priority: int, 
                         zones: List[str], listed_priority: int) -> bool:
        """
        Idempotent update for clean → listed transition.
        
        Returns: True if update occurred, False if no-op (already in this state)
        """
        sorted_zones = ','.join(sorted(zones))
        last_event = f"new block from list(s) {sorted_zones}"
        
        with get_db_connection(self.dsn) as conn:
            with conn.cursor() as cur:
                # Only update if blockingLists differs (idempotency check)
                cur.execute("""
                    UPDATE postal.ip_addresses
                    SET priority = %s,
                        "oldPriority" = CASE 
                            WHEN "oldPriority" IS NULL THEN %s 
                            ELSE "oldPriority"  -- Preserve existing oldPriority
                        END,
                        "blockingLists" = %s,
                        "lastEvent" = %s
                    WHERE id = %s 
                      AND "blockingLists" != %s  -- Only update if changed
                """, (listed_priority, current_priority, sorted_zones, last_event, ip_id, sorted_zones))
                
                return cur.rowcount > 0  # True if row was updated
    
    def update_ip_clean(self, ip_id: int, old_priority: Optional[int], 
                        clean_fallback: int) -> bool:
        """
        Idempotent update for listed → clean transition.
        
        Returns: True if update occurred, False if no-op
        """
        restore_priority = old_priority if old_priority is not None else clean_fallback
        
        with get_db_connection(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE postal.ip_addresses
                    SET priority = %s,
                        "oldPriority" = NULL,
                        "blockingLists" = '',
                        "lastEvent" = 'block removed'
                    WHERE id = %s 
                      AND "blockingLists" != ''  -- Only update if currently listed
                """, (restore_priority, ip_id))
                
                return cur.rowcount > 0
```

### Alternatives Considered

- **SERIALIZABLE isolation**: Unnecessary strictness, causes serialization failures on concurrent updates
- **Connection pooling (e.g., pgbouncer)**: Not needed for stateless CronJob (single execution lifecycle)
- **ORM (SQLAlchemy)**: Adds complexity for simple CRUD operations, harder to enforce constitutional invariants

---

## 4. Structured Logging: Python logging with JSON formatter

### Decision

Use **python-json-logger** library with Python's built-in `logging` module for structured JSON output, with per-IP structured records and job-level correlation ID.

### Rationale

- **Kubernetes Integration**: JSON logs parse easily in ELK, Splunk, CloudWatch
- **Performance**: Minimal overhead (logging doesn't block DNS/DB operations)
- **Correlation**: Job run ID ties all log entries together for debugging
- **Constitutional Compliance**: FR-028 requires machine-parseable JSON logs

### Code Example

```python
import logging
import uuid
import time
from pythonjsonlogger import jsonlogger

# Global job run ID for correlation
JOB_RUN_ID = str(uuid.uuid4())

def setup_logging():
    """Configure JSON logging for Kubernetes."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # JSON formatter
    log_handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s',
        timestamp=True
    )
    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)
    
    return logger

def log_ip_check(ip: str, listed_zones: list, unknown_zones: list, 
                 decision: str, db_changes: bool, jira_action: str, duration_ms: int):
    """
    Log structured per-IP check result (FR-028).
    """
    logger = logging.getLogger(__name__)
    logger.info(
        "IP check completed",
        extra={
            "job_run_id": JOB_RUN_ID,
            "ip": ip,
            "listed_zones": listed_zones,
            "unknown_zones": unknown_zones,
            "decision": decision,
            "db_changes": db_changes,
            "jira_action": jira_action,
            "duration_ms": duration_ms
        }
    )

def log_job_summary(total_ips: int, listed: int, cleaned: int, unchanged: int,
                    jira_created: int, jira_updated: int, dns_failures: int, 
                    duration_sec: float):
    """
    Log job completion summary (FR-031).
    """
    logger = logging.getLogger(__name__)
    logger.info(
        "Job completed",
        extra={
            "job_run_id": JOB_RUN_ID,
            "total_ips": total_ips,
            "listed": listed,
            "cleaned": cleaned,
            "unchanged": unchanged,
            "jira_created": jira_created,
            "jira_updated": jira_updated,
            "dns_failures": dns_failures,
            "duration_sec": duration_sec
        }
    )

# Example usage
setup_logging()
start = time.time()
log_ip_check(
    ip="203.0.113.45",
    listed_zones=["zen.spamhaus.org"],
    unknown_zones=[],
    decision="LISTED",
    db_changes=True,
    jira_action="created_issue",
    duration_ms=1234
)
# Output (JSON): {"asctime": "2025-12-17T...", "levelname": "INFO", "job_run_id": "...", "ip": "203.0.113.45", ...}
```

### Alternatives Considered

- **structlog**: More features but overkill for CronJob needs
- **Plain print(json.dumps(...))**: Works but loses log levels, harder to filter in Kubernetes
- **Custom logging to file**: Violates stateless principle (no local files)

---

## 5. Kubernetes CronJob Configuration

### Decision

Use **native Kubernetes CronJob** with ConfigMap for non-sensitive config (DNSBL zones, priorities), Secret for credentials (DB password, Jira token), and resource limits from clarification (250m CPU/256Mi requests, 500m CPU/512Mi limits).

### Rationale

- **GitOps Friendly**: ConfigMap/Secret separation allows versioning config separately from secrets
- **Resource Limits**: Clarification specified 250m/256Mi requests, 500m/512Mi limits (SC-008a)
- **Restart Policy**: `OnFailure` allows Kubernetes to retry fatal errors (DB/Jira unreachable)
- **Concurrency Policy**: `Forbid` prevents overlapping executions (though idempotency handles it)

### Code Example

**File: `kubernetes/cronjob.yaml`**

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postal-dnsbl-monitor
  namespace: postal
spec:
  # Run every 15 minutes
  schedule: "*/15 * * * *"
  
  # Don't allow overlapping jobs
  concurrencyPolicy: Forbid
  
  # Keep last 3 successful and 1 failed job for debugging
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 1
  
  jobTemplate:
    spec:
      template:
        metadata:
          labels:
            app: postal-dnsbl-monitor
        spec:
          restartPolicy: OnFailure  # Retry on fatal errors
          
          containers:
          - name: monitor
            image: postal-dnsbl-monitor:latest
            imagePullPolicy: IfNotPresent
            
            # Resource limits from clarification
            resources:
              requests:
                cpu: 250m
                memory: 256Mi
              limits:
                cpu: 500m
                memory: 512Mi
            
            # Environment from ConfigMap (non-sensitive)
            envFrom:
            - configMapRef:
                name: dnsbl-config
            
            # Environment from Secret (sensitive)
            env:
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: dnsbl-secrets
                  key: db-password
            - name: JIRA_API_TOKEN
              valueFrom:
                secretKeyRef:
                  name: dnsbl-secrets
                  key: jira-api-token
```

**File: `kubernetes/configmap-template.yaml`**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: dnsbl-config
  namespace: postal
data:
  # Database (non-sensitive)
  DB_HOST: "postgresql.postal.svc.cluster.local"
  DB_PORT: "5432"
  DB_NAME: "postal"
  DB_USER: "dnsbl_monitor"
  
  # DNSBL zones (comma-separated)
  DNSBL_ZONES: "zen.spamhaus.org,bl.spamcop.net,dnsbl.sorbs.net"
  DNS_TIMEOUT: "5"
  DNS_CONCURRENCY: "10"
  
  # Priorities
  LISTED_PRIORITY: "0"
  CLEAN_FALLBACK_PRIORITY: "50"
  
  # Jira (non-sensitive)
  JIRA_SERVER: "https://company.atlassian.net"
  JIRA_USER: "dnsbl-bot@company.com"
  JIRA_PROJECT: "OPS"
  JIRA_ISSUE_TYPE: "Incident"
  JIRA_DNS_FAILURE_ISSUE_TYPE: "Alert"
  JIRA_EXCLUDED_STATUSES: "Done,Closed,Resolved"
  
  # Operational
  DRY_RUN: "false"
```

**File: `kubernetes/secret-template.yaml`**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: dnsbl-secrets
  namespace: postal
type: Opaque
stringData:
  # Base64 encode these values before applying
  db-password: "CHANGEME"
  jira-api-token: "CHANGEME"
```

### Alternatives Considered

- **Helm chart**: Overkill for single CronJob, adds complexity
- **Hardcoded config in Docker image**: Violates constitutional principle VII (config as code)
- **restartPolicy: Never**: Prevents Kubernetes from retrying fatal errors

---

## 6. Docker Multi-Stage Build with uv

### Decision

Use **multi-stage Dockerfile** with official Python 3.14 image, uv for dependency management, and slim runtime image to minimize size.

### Rationale

- **Constitutional Mandate**: uv required by constitution v1.2.0
- **Reproducibility**: `uv sync --frozen` ensures deterministic builds from uv.lock
- **Image Size**: Multi-stage build reduces final image (~200MB vs ~1GB with build tools)
- **Security**: Slim runtime image has fewer CVEs than full Python image

### Code Example

**File: `Dockerfile`**

```dockerfile
# Stage 1: Build environment
FROM python:3.14-slim AS builder

# Install uv
RUN pip install --no-cache-dir uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies to virtual environment
RUN uv venv /app/.venv && \
    uv sync --frozen --no-dev

# Stage 2: Runtime environment
FROM python:3.14-slim

# Install runtime dependencies only
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source
COPY src/ ./src/

# Use virtual environment Python
ENV PATH="/app/.venv/bin:$PATH"

# Run as non-root user for security
RUN useradd -m -u 1000 monitor && \
    chown -R monitor:monitor /app
USER monitor

# Entry point
CMD ["python", "src/main.py"]
```

**File: `pyproject.toml`**

```toml
[project]
name = "postal-dnsbl-monitor"
version = "1.0.0"
description = "Stateless DNSBL monitoring CronJob for Postal mail server"
requires-python = ">=3.14"
dependencies = [
    "dnspython>=2.4.0",
    "jira>=3.5.0",
    "psycopg2-binary>=2.9.0",
    "python-json-logger>=2.0.0"
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "testcontainers>=3.7.0",
    "responses>=0.23.0"
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### Alternatives Considered

- **Alpine-based image**: Smaller but musl libc incompatibilities with some Python packages
- **Poetry instead of uv**: Slower, not mandated by constitution
- **Single-stage build**: Larger image (~1GB), includes unnecessary build tools in runtime

---

## 7. Testing Strategy: pytest with Testcontainers

### Decision

Use **pytest** with fixtures for PostgreSQL (via testcontainers), Jira API mocking (via responses), and DNS mocking (via unittest.mock), with dedicated contract tests for constitutional compliance.

### Rationale

- **Testcontainers**: Real PostgreSQL in Docker ensures transaction semantics match production
- **Responses Library**: HTTP mocking for Jira API without external dependencies
- **Contract Tests**: Verify FR-014, FR-032, FR-020 invariants explicitly
- **Fast Unit Tests**: Mock all I/O for speed, use integration tests selectively

### Code Example

**File: `tests/conftest.py`**

```python
import pytest
import psycopg2
from testcontainers.postgres import PostgresContainer
from unittest.mock import Mock

@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL container for integration tests."""
    with PostgresContainer("postgres:15") as postgres:
        yield postgres

@pytest.fixture
def db_connection(postgres_container):
    """Provide database connection with postal.ip_addresses table."""
    conn = psycopg2.connect(postgres_container.get_connection_url())
    
    # Create schema
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS postal.ip_addresses (
                id SERIAL PRIMARY KEY,
                ip VARCHAR(15) NOT NULL,
                priority INTEGER NOT NULL,
                "oldPriority" INTEGER,
                "blockingLists" TEXT DEFAULT '',
                "lastEvent" TEXT
            )
        """)
    conn.commit()
    
    yield conn
    conn.close()

@pytest.fixture
def mock_jira():
    """Mock Jira client for unit tests."""
    mock = Mock()
    mock.search_issues.return_value = []
    mock.create_issue.return_value = Mock(key="OPS-123")
    return mock
```

**File: `tests/contract/test_invariants.py`**

```python
import pytest
from src.services.database import DatabaseService

def test_old_priority_single_write_invariant(db_connection):
    """
    Verify FR-014: oldPriority written exactly once on clean→listed transition.
    """
    db = DatabaseService(db_connection)
    
    # Insert clean IP with priority=50
    with db_connection.cursor() as cur:
        cur.execute("""
            INSERT INTO postal.ip_addresses (ip, priority, "oldPriority", "blockingLists")
            VALUES ('203.0.113.45', 50, NULL, '')
            RETURNING id
        """)
        ip_id = cur.fetchone()[0]
    db_connection.commit()
    
    # First update: clean → listed (should set oldPriority=50)
    db.update_ip_listed(ip_id, current_priority=50, zones=["zen.spamhaus.org"], listed_priority=0)
    
    with db_connection.cursor() as cur:
        cur.execute('SELECT priority, "oldPriority" FROM postal.ip_addresses WHERE id = %s', (ip_id,))
        priority, old_priority = cur.fetchone()
    
    assert priority == 0, "Priority should be LISTED_PRIORITY"
    assert old_priority == 50, "oldPriority should be set to previous priority"
    
    # Second update: listed → listed with different zones (should NOT change oldPriority)
    db.update_ip_listed(ip_id, current_priority=0, zones=["bl.spamcop.net"], listed_priority=0)
    
    with db_connection.cursor() as cur:
        cur.execute('SELECT "oldPriority" FROM postal.ip_addresses WHERE id = %s', (ip_id,))
        old_priority_after = cur.fetchone()[0]
    
    assert old_priority_after == 50, "oldPriority MUST NOT change on subsequent updates"

def test_blocking_lists_deterministic_sort(db_connection):
    """
    Verify FR-014: blockingLists stored as sorted, comma-separated (no spaces).
    """
    db = DatabaseService(db_connection)
    
    zones_unsorted = ["zen.spamhaus.org", "bl.spamcop.net", "dnsbl.sorbs.net"]
    expected_sorted = "bl.spamcop.net,dnsbl.sorbs.net,zen.spamhaus.org"
    
    with db_connection.cursor() as cur:
        cur.execute("""
            INSERT INTO postal.ip_addresses (ip, priority, "blockingLists")
            VALUES ('203.0.113.45', 50, '')
            RETURNING id
        """)
        ip_id = cur.fetchone()[0]
    db_connection.commit()
    
    db.update_ip_listed(ip_id, current_priority=50, zones=zones_unsorted, listed_priority=0)
    
    with db_connection.cursor() as cur:
        cur.execute('SELECT "blockingLists" FROM postal.ip_addresses WHERE id = %s', (ip_id,))
        blocking_lists = cur.fetchone()[0]
    
    assert blocking_lists == expected_sorted, "blockingLists must be sorted with no spaces"

def test_idempotent_updates(db_connection):
    """
    Verify FR-032: Re-running with same state produces zero DB writes.
    """
    db = DatabaseService(db_connection)
    
    with db_connection.cursor() as cur:
        cur.execute("""
            INSERT INTO postal.ip_addresses (ip, priority, "oldPriority", "blockingLists")
            VALUES ('203.0.113.45', 0, 50, 'zen.spamhaus.org')
            RETURNING id
        """)
        ip_id = cur.fetchone()[0]
    db_connection.commit()
    
    # First call: should be no-op (already in this state)
    result1 = db.update_ip_listed(ip_id, current_priority=0, zones=["zen.spamhaus.org"], listed_priority=0)
    assert result1 is False, "Should return False (no update) when state unchanged"
    
    # Second call: also no-op
    result2 = db.update_ip_listed(ip_id, current_priority=0, zones=["zen.spamhaus.org"], listed_priority=0)
    assert result2 is False, "Repeated calls with same state must be no-ops"
```

### Alternatives Considered

- **Mock database**: Faster but doesn't verify transaction isolation or SQL correctness
- **Jira test instance**: Requires external service, slower, harder to test edge cases
- **Real DNS queries in tests**: Flaky (external dependency), violates test isolation

---

## Summary of Decisions

| Area | Decision | Key Benefit |
|------|----------|-------------|
| **DNS** | dnspython + ThreadPoolExecutor | Constitutional compliance, 10k queries < 5min |
| **Jira** | jira-python + custom exponential backoff | Precise 2s/4s/8s retry, JQL flexibility |
| **Database** | psycopg2 + READ COMMITTED + context managers | Idempotent updates, "last committed wins" |
| **Logging** | python-json-logger | Kubernetes-native JSON, minimal overhead |
| **Deployment** | CronJob + ConfigMap/Secret | GitOps-friendly, resource limits enforced |
| **Docker** | Multi-stage + uv sync --frozen | Small image (~200MB), reproducible builds |
| **Testing** | pytest + testcontainers + responses | Real DB semantics, fast unit tests, contract verification |

---

## Next Steps

1. Create `data-model.md` with entity definitions and state transition diagram
2. Generate `contracts/config-schema.yaml` and `contracts/log-format.json`
3. Write `quickstart.md` with setup instructions using patterns from this research
4. Implement source code in `src/` following the patterns documented above
5. Write tests in `tests/` verifying constitutional compliance
