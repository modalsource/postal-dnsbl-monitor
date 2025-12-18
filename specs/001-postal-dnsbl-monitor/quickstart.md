# Quickstart Guide: Postal DNSBL Monitor

**Feature ID**: 001-postal-dnsbl-monitor  
**Last Updated**: 2025-12-17  
**Target Audience**: Developers, DevOps Engineers

This guide provides step-by-step instructions for local development, testing, building, and deploying the Postal DNSBL Monitor application.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [Running the Application Locally](#running-the-application-locally)
4. [Testing](#testing)
5. [Docker Build](#docker-build)
6. [Kubernetes Deployment](#kubernetes-deployment)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Tools

- **Python 3.14+**: The application requires Python 3.14 or later
- **uv**: Modern Python package manager ([installation guide](https://github.com/astral-sh/uv))
- **MySQL 13+**: Database with existing `postal.ip_addresses` table
- **Jira Cloud/Server**: Configured project with API access
- **Docker**: For containerized builds (optional for local dev)
- **Kubernetes**: For production deployment (kubectl configured)
- **Git**: For version control

### System Requirements

- **Memory**: Minimum 512Mi available for container
- **CPU**: Minimum 500m available
- **Network**: Outbound DNS (UDP/53), HTTPS (443) to Jira API

### Access Requirements

- MySQL credentials with `SELECT` and `UPDATE` permissions on `postal.ip_addresses`
- Jira API token with permissions to create/update issues in target project
- Network access to all configured DNSBL zones (e.g., `zen.spamhaus.org`)

---

## Local Development Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd postal-dnsbl-monitor
git checkout 001-postal-dnsbl-monitor
```

### 2. Install uv Package Manager

```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify installation
uv --version
```

### 3. Create Virtual Environment and Install Dependencies

```bash
# Create Python 3.14 virtual environment
uv venv --python 3.14

# Activate virtual environment
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install application dependencies
uv pip install -e .

# Install development dependencies
uv pip install -e ".[dev]"
```

**Expected dependencies** (from `pyproject.toml`):
- `dnspython>=2.4.0` - DNS queries
- `jira>=3.5.0` - Jira API client
- `mysql-connector-python>=8.0.0` - MySQL adapter
- `python-json-logger>=2.0.0` - Structured logging
- `pytest>=7.4.0` - Testing framework (dev)
- `testcontainers>=3.7.0` - Integration tests (dev)

### 4. Configure Environment Variables

Create `.env` file in project root:

```bash
# Database Configuration
DB_HOST=localhost
DB_PORT=3306
DB_NAME=postal
DB_USER=postal_user
DB_PASSWORD=secure_password_here

# DNSBL Configuration
DNSBL_ZONES=zen.spamhaus.org,bl.spamcop.net,b.barracudacentral.org
DNSBL_TIMEOUT_SECONDS=5.0
DNSBL_MAX_WORKERS=10

# Priority Configuration
PRIORITY_CLEAN=0
PRIORITY_LISTED=50
PRIORITY_UNKNOWN_THRESHOLD=0.5

# Jira Configuration
JIRA_URL=https://your-instance.atlassian.net
JIRA_USERNAME=api-user@example.com
JIRA_API_TOKEN=your_jira_api_token_here
JIRA_PROJECT=OPS
JIRA_ISSUE_TYPE=Task
JIRA_EXCLUDED_STATUSES=Done,Closed,Resolved

# Jira Retry Configuration
JIRA_RETRY_COUNT=3
JIRA_RETRY_DELAY_SECONDS=2.0
JIRA_RETRY_BACKOFF_FACTOR=2.0

# Operational Configuration
DRY_RUN=false
LOG_LEVEL=INFO
MAX_EXECUTION_TIME_SECONDS=300
JOB_RUN_ID_PREFIX=postal-dnsbl-
```

**See**: `specs/001-postal-dnsbl-monitor/contracts/config-schema.yaml` for full schema and validation rules.

### 5. Prepare MySQL Database

Ensure the `postal.ip_addresses` table exists with required schema:

```sql
-- Expected schema (DO NOT run if table exists)
CREATE SCHEMA IF NOT EXISTS postal;

CREATE TABLE IF NOT EXISTS postal.ip_addresses (
    id SERIAL PRIMARY KEY,
    ip VARCHAR(45) NOT NULL UNIQUE,
    priority INTEGER NOT NULL DEFAULT 0,
    old_priority INTEGER,
    blocking_lists TEXT,
    last_event TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Verify table structure
\d postal.ip_addresses
```

**Note**: The application assumes this table already exists (managed by Postal application).

---

## Running the Application Locally

### 1. Load Environment Variables

```bash
# Export variables from .env file
export $(grep -v '^#' .env | xargs)

# Verify critical variables
echo $DB_HOST
echo $JIRA_URL
echo $DNSBL_ZONES
```

### 2. Run in Dry-Run Mode (Recommended First Run)

```bash
# Enable dry-run to verify configuration without database writes
export DRY_RUN=true

# Run the application
python main.py
```

**Expected output** (see `contracts/log-format.json`):
```json
{"timestamp": "2025-12-17T10:30:00Z", "level": "INFO", "message": "Starting DNSBL monitor", "job_run_id": "postal-dnsbl-abc123", "dry_run": true}
{"timestamp": "2025-12-17T10:30:01Z", "level": "INFO", "ip": "203.0.113.5", "listed_zones": ["zen.spamhaus.org"], "unknown_zones": [], "decision": "THROTTLE", "db_changes": "priority: 0->50, oldPriority: null->0, blockingLists: ''->'zen.spamhaus.org'", "jira_action": "CREATE OPS-123: IP 203.0.113.5 listed on 1 DNSBL(s)", "duration_ms": 145}
{"timestamp": "2025-12-17T10:30:05Z", "level": "INFO", "message": "Job completed", "job_run_id": "postal-dnsbl-abc123", "total_ips": 42, "clean": 38, "listed": 3, "unknown": 1, "db_updates": 0, "jira_created": 0, "jira_updated": 0, "duration_ms": 4820}
```

### 3. Run in Production Mode

```bash
# Disable dry-run for actual database/Jira updates
export DRY_RUN=false

# Run the application
python main.py
```

**Validation**:
- Check MySQL: `SELECT ip, priority, blocking_lists FROM postal.ip_addresses WHERE priority > 0;`
- Check Jira: Search for issues in configured project with `DNSBL` label

---

## Testing

### Unit Tests

```bash
# Run all unit tests with coverage
pytest tests/unit -v --cov=src --cov-report=term-missing

# Run specific test module
pytest tests/unit/test_dns_resolver.py -v
```

**Key test modules**:
- `tests/unit/test_dns_resolver.py` - DNS query logic with mocked dnspython
- `tests/unit/test_state_machine.py` - State transition validation (CLEAN ↔ LISTED)
- `tests/unit/test_jira_client.py` - Retry logic, deduplication, exponential backoff
- `tests/unit/test_config.py` - Environment variable parsing and validation

### Integration Tests

```bash
# Run integration tests with testcontainers (requires Docker)
pytest tests/integration -v --tb=short

# Run specific integration test
pytest tests/integration/test_database_integration.py -v
```

**Integration test coverage**:
- MySQL transactions with READ COMMITTED isolation
- Concurrent update scenarios ("last committed wins")
- DNS queries against real DNSBL zones (using test IPs)
- Jira API roundtrip (create, search, update, close)

### Contract Tests

```bash
# Validate contracts against implementation
pytest tests/contract -v

# Specific contract validations
pytest tests/contract/test_config_contract.py -v  # config-schema.yaml
pytest tests/contract/test_log_contract.py -v     # log-format.json
```

**Contract validation**:
- `config-schema.yaml`: All required env vars present, types match, defaults applied
- `log-format.json`: JSON logs match schema, required fields present

### End-to-End Test

```bash
# Full workflow test (requires MySQL + Jira access)
pytest tests/e2e/test_full_workflow.py -v --log-cli-level=INFO
```

**E2E test scenario**:
1. Insert test IP with priority=0
2. Mock DNS responses (1 listed zone)
3. Run application
4. Verify DB: priority=50, oldPriority=0, blockingLists populated
5. Verify Jira: Issue created with correct summary/description
6. Re-run with same state -> Verify idempotency (no duplicate writes)

---

## Docker Build

### 1. Build Multi-Stage Image

```bash
# Build using Docker (references research.md multi-stage pattern)
docker build -t postal-dnsbl-monitor:latest .

# Verify image size (should be <150MB with distroless base)
docker images postal-dnsbl-monitor:latest
```

**Expected `Dockerfile` structure** (from `research.md`):
```dockerfile
# Stage 1: Builder with uv
FROM python:3.14-slim AS builder
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv pip install --system --compile-bytecode .

# Stage 2: Runtime with distroless
FROM gcr.io/distroless/python3-debian12:latest
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY src/ /app/src/
COPY main.py /app/
WORKDIR /app
CMD ["python", "main.py"]
```

### 2. Test Container Locally

```bash
# Run container with environment variables
docker run --rm \
  --env-file .env \
  -e DRY_RUN=true \
  postal-dnsbl-monitor:latest

# Expected: JSON logs to stdout, exit code 0
```

### 3. Push to Registry (Optional)

```bash
# Tag for your registry
docker tag postal-dnsbl-monitor:latest registry.example.com/postal-dnsbl-monitor:v1.0.0

# Push to registry
docker push registry.example.com/postal-dnsbl-monitor:v1.0.0
```

---

## Kubernetes Deployment

### 1. Create ConfigMap

```bash
# Apply ConfigMap from contracts/config-schema.yaml template
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: postal-dnsbl-config
  namespace: postal
data:
  DNSBL_ZONES: "zen.spamhaus.org,bl.spamcop.net,b.barracudacentral.org"
  DNSBL_TIMEOUT_SECONDS: "5.0"
  DNSBL_MAX_WORKERS: "10"
  PRIORITY_CLEAN: "0"
  PRIORITY_LISTED: "50"
  PRIORITY_UNKNOWN_THRESHOLD: "0.5"
  JIRA_URL: "https://your-instance.atlassian.net"
  JIRA_PROJECT: "OPS"
  JIRA_ISSUE_TYPE: "Task"
  JIRA_EXCLUDED_STATUSES: "Done,Closed,Resolved"
  JIRA_RETRY_COUNT: "3"
  JIRA_RETRY_DELAY_SECONDS: "2.0"
  JIRA_RETRY_BACKOFF_FACTOR: "2.0"
  DRY_RUN: "false"
  LOG_LEVEL: "INFO"
  MAX_EXECUTION_TIME_SECONDS: "300"
EOF
```

### 2. Create Secret

```bash
# Apply Secret with sensitive credentials
kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: postal-dnsbl-secrets
  namespace: postal
type: Opaque
stringData:
  DB_HOST: "mysql.postal.svc.cluster.local"
  DB_PORT: "3306"
  DB_NAME: "postal"
  DB_USER: "postal_user"
  DB_PASSWORD: "secure_password_here"
  JIRA_USERNAME: "api-user@example.com"
  JIRA_API_TOKEN: "your_jira_api_token_here"
EOF
```

### 3. Deploy CronJob

```bash
# Apply CronJob manifest
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postal-dnsbl-monitor
  namespace: postal
spec:
  schedule: "*/15 * * * *"  # Every 15 minutes
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 5
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      backoffLimit: 0  # No retries (FR-007: stateless, fail-fast)
      template:
        metadata:
          labels:
            app: postal-dnsbl-monitor
        spec:
          restartPolicy: Never
          containers:
          - name: monitor
            image: registry.example.com/postal-dnsbl-monitor:v1.0.0
            imagePullPolicy: IfNotPresent
            envFrom:
            - configMapRef:
                name: postal-dnsbl-config
            - secretRef:
                name: postal-dnsbl-secrets
            resources:
              requests:
                memory: "256Mi"
                cpu: "250m"
              limits:
                memory: "512Mi"
                cpu: "500m"
            securityContext:
              runAsNonRoot: true
              runAsUser: 65532
              allowPrivilegeEscalation: false
              readOnlyRootFilesystem: true
              capabilities:
                drop: ["ALL"]
EOF
```

### 4. Verify Deployment

```bash
# Check CronJob status
kubectl get cronjob postal-dnsbl-monitor -n postal

# Trigger manual job run
kubectl create job --from=cronjob/postal-dnsbl-monitor postal-dnsbl-manual-test -n postal

# View logs
kubectl logs -n postal -l app=postal-dnsbl-monitor --tail=100 -f

# Check job completion
kubectl get jobs -n postal -l app=postal-dnsbl-monitor
```

---

## Troubleshooting

### Issue: DNS Queries Timing Out

**Symptoms**: High percentage of `unknown_zones` in logs, DNS timeout errors

**Solutions**:
1. Increase `DNSBL_TIMEOUT_SECONDS` (default: 5.0 -> try 10.0)
2. Check network egress rules allow UDP/53 to DNSBL zones
3. Verify DNS resolver configuration in cluster (`kubectl get svc -n kube-system kube-dns`)
4. Test DNS from pod: `kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup zen.spamhaus.org`

### Issue: Jira API Rate Limiting

**Symptoms**: Jira 429 errors, `jira_action: FAILED` in logs

**Solutions**:
1. Increase `JIRA_RETRY_DELAY_SECONDS` and `JIRA_RETRY_BACKOFF_FACTOR`
2. Reduce CronJob frequency (e.g., `*/15 * * * *` -> `*/30 * * * *`)
3. Check Jira Cloud rate limits: 10 requests/second per user
4. Use dedicated service account with higher rate limits

### Issue: Duplicate Jira Issues Created

**Symptoms**: Multiple issues for same IP despite JQL deduplication

**Solutions**:
1. Verify `JIRA_EXCLUDED_STATUSES` includes all terminal states (Done, Closed, Resolved)
2. Check JQL search accuracy: Run query in Jira UI: `project = OPS AND summary ~ "IP 203.0.113.5" AND status NOT IN (Done,Closed)`
3. Enable idempotency verification: Check `lastEvent` not updated on no-op runs
4. Review logs for JQL search results: `grep "jira_search" logs.json`

### Issue: Database Connection Failures

**Symptoms**: `FATAL: database connection failed` errors, exit code 1

**Solutions**:
1. Verify Secret credentials: `kubectl get secret postal-dnsbl-secrets -n postal -o yaml`
2. Test connectivity from pod: `kubectl run -it --rm mysql-test --image=mysql:8.0 --restart=Never -- mysql -h mysql.postal.svc.cluster.local -u postal_user -p -D postal`
3. Check MySQL NetworkPolicy allows ingress from `postal` namespace
4. Verify READ COMMITTED isolation level: `SELECT @@transaction_isolation;` (should be `READ-COMMITTED`)

### Issue: Container OOMKilled

**Symptoms**: Pod restarts with `OOMKilled` status, memory limit exceeded

**Solutions**:
1. Increase memory limits in CronJob: `limits.memory: 512Mi -> 1Gi`
2. Reduce concurrent DNS workers: `DNSBL_MAX_WORKERS: 10 -> 5`
3. Check for memory leaks: Run locally with memory profiler (`pytest tests/performance/test_memory.py`)
4. Verify batch processing logic (should process IPs in streaming fashion, not load all into memory)

### Issue: Job Exceeds MAX_EXECUTION_TIME

**Symptoms**: Job self-terminates with `MAX_EXECUTION_TIME_SECONDS exceeded` error

**Solutions**:
1. Increase timeout: `MAX_EXECUTION_TIME_SECONDS: 300 -> 600`
2. Optimize DNS concurrency: `DNSBL_MAX_WORKERS: 10 -> 20` (if network/CPU allows)
3. Check database query performance: Ensure index on `postal.ip_addresses(id)` exists
4. Profile execution: Enable `LOG_LEVEL=DEBUG` to see per-IP processing times

### Debugging with DRY_RUN Mode

```bash
# Enable dry-run to test configuration without side effects
kubectl set env cronjob/postal-dnsbl-monitor -n postal DRY_RUN=true

# Trigger manual job
kubectl create job --from=cronjob/postal-dnsbl-monitor postal-dnsbl-debug -n postal

# View logs to verify logic without DB/Jira changes
kubectl logs -n postal -l job-name=postal-dnsbl-debug --tail=200

# Re-enable production mode
kubectl set env cronjob/postal-dnsbl-monitor -n postal DRY_RUN=false
```

### Viewing Structured Logs

```bash
# Pretty-print JSON logs with jq
kubectl logs -n postal -l app=postal-dnsbl-monitor --tail=100 | jq '.'

# Filter logs by decision type
kubectl logs -n postal -l app=postal-dnsbl-monitor --tail=500 | jq 'select(.decision == "THROTTLE")'

# Calculate average processing time per IP
kubectl logs -n postal -l app=postal-dnsbl-monitor --tail=1000 | jq -s '[.[] | select(.duration_ms) | .duration_ms] | add / length'

# Find DNS failures
kubectl logs -n postal -l app=postal-dnsbl-monitor --tail=500 | jq 'select(.unknown_zones | length > 0)'
```

### Verifying Idempotency

```bash
# Run job twice with same database state
kubectl create job --from=cronjob/postal-dnsbl-monitor postal-dnsbl-run1 -n postal
# Wait for completion
kubectl wait --for=condition=complete job/postal-dnsbl-run1 -n postal --timeout=300s

# Capture first run summary
kubectl logs -n postal -l job-name=postal-dnsbl-run1 | jq 'select(.message == "Job completed")' > run1.json

# Run again immediately
kubectl create job --from=cronjob/postal-dnsbl-monitor postal-dnsbl-run2 -n postal
kubectl wait --for=condition=complete job/postal-dnsbl-run2 -n postal --timeout=300s

# Capture second run summary
kubectl logs -n postal -l job-name=postal-dnsbl-run2 | jq 'select(.message == "Job completed")' > run2.json

# Verify idempotency: db_updates and jira_created should be 0 on run2
cat run2.json | jq '{db_updates, jira_created, jira_updated}'
# Expected: {"db_updates": 0, "jira_created": 0, "jira_updated": 0}
```

---

## Next Steps

After successful deployment:

1. **Monitor Initial Runs**: Watch first 3-5 CronJob executions, verify no errors
2. **Tune Configuration**: Adjust `DNSBL_ZONES`, timeouts, retry policies based on actual performance
3. **Set Up Alerts**: Configure Kubernetes alerts for failed jobs (e.g., Prometheus AlertManager)
4. **Validate Idempotency**: Run verification script after 24 hours to confirm no duplicate Jira issues
5. **Performance Tuning**: Review execution times, optimize if exceeding 5-minute SLA (FR-002)
6. **Documentation**: Update team runbooks with Jira ticket management procedures

---

## Additional Resources

- **Specification**: `specs/001-postal-dnsbl-monitor/spec.md` - Full requirements and success criteria
- **Data Model**: `specs/001-postal-dnsbl-monitor/data-model.md` - Entity definitions and state machine
- **Research**: `specs/001-postal-dnsbl-monitor/research.md` - Technical library decisions and patterns
- **Config Schema**: `specs/001-postal-dnsbl-monitor/contracts/config-schema.yaml` - Environment variable reference
- **Log Format**: `specs/001-postal-dnsbl-monitor/contracts/log-format.json` - Structured logging schema
- **Constitution**: `.specify/memory/constitution.md` - Design principles and constraints

---

**Document Version**: 1.0.0  
**Last Reviewed**: 2025-12-17  
**Maintained By**: Development Team
