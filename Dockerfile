# Multi-stage Dockerfile for Postal DNSBL Monitor
# Per research.md section 6: Multi-stage build with uv

# Stage 1: Builder with uv
FROM python:3.14-slim AS builder

# Install uv
RUN pip install --no-cache-dir uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies to system (not venv for multi-stage)
RUN uv pip install --system --no-cache --compile-bytecode .

# Copy source code
COPY src/ ./src/

# Stage 2: Runtime environment
FROM python:3.14-slim

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /app/src /app/src

# Create non-root user for security (UID 1000)
RUN useradd -m -u 1000 monitor && \
    chown -R monitor:monitor /app

# Switch to non-root user
USER monitor

# Entry point
CMD ["python", "-m", "src.main"]
