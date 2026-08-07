# Multi-stage build for Luminari Sage API
FROM python:3.13-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64 AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gcc \
    g++ \
    python3-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements-core.txt .
# Install to a specific location that we can copy later
RUN pip install --no-cache-dir --target=/opt/python-packages -r requirements-core.txt && \
    # Graphiti makes anonymous PostHog telemetry opt-out. Sage does not ship the
    # telemetry client; functionality is unaffected when telemetry is disabled.
    rm -rf /opt/python-packages/posthog /opt/python-packages/posthog-*.dist-info && \
    # Clean up build artifacts to reduce layer size
    find /opt/python-packages -name "*.pyc" -delete && \
    find /opt/python-packages -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true && \
    rm -rf /tmp/* /var/tmp/*

# Development images add test/lint tooling without bloating production builds.
ARG INSTALL_DEV=false
COPY requirements-dev.txt .
RUN mkdir -p /opt/dev-tools && \
    if [ "$INSTALL_DEV" = "true" ]; then \
      pip install --no-cache-dir --target=/opt/python-packages -r requirements-dev.txt && \
      pip install --no-cache-dir --prefix=/opt/dev-tools ruff==0.16.0; \
    fi

# Install the compatible spaCy model from its immutable release asset and verify
# the publisher-provided SHA-256 before pip sees the wheel.
ARG SPACY_MODEL_VERSION=3.8.0
ARG SPACY_MODEL_SHA256=1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85
RUN model="/tmp/en_core_web_sm-${SPACY_MODEL_VERSION}-py3-none-any.whl" && \
    curl --fail --silent --show-error --location \
      --proto '=https' --tlsv1.2 \
      "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-${SPACY_MODEL_VERSION}/en_core_web_sm-${SPACY_MODEL_VERSION}-py3-none-any.whl" \
      --output "${model}" && \
    printf '%s  %s\n' "${SPACY_MODEL_SHA256}" "${model}" | sha256sum --check --strict && \
    pip install --no-cache-dir --no-deps --target=/opt/python-packages "${model}" && \
    rm -f "${model}"

# Production stage
FROM python:3.13-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64

# Create non-root user with same uid as luminari on host (1013)
RUN useradd -m -u 1013 sage && \
    mkdir -p /app/logs /var/run && \
    chown -R sage:sage /app && \
    chown sage:sage /var/run

# Copy Python packages from builder
COPY --from=builder --chown=sage:sage /opt/python-packages /opt/python-packages
COPY --from=builder --chown=sage:sage /opt/dev-tools /opt/dev-tools

# Debug: List what was actually installed
RUN ls -la /opt/python-packages/ | head -20 || echo "No packages directory" && \
    find /opt/python-packages -name "uvicorn*" -type d | head -5 || echo "No uvicorn found"

# Pre-download the embedding model at an immutable revision as root (before
# switching to sage). Runtime network downloads are disabled below.
ARG SENTENCE_TRANSFORMERS_MODEL_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41
ENV HF_HOME=/opt/hf_cache
ENV SENTENCE_TRANSFORMERS_HOME=/opt/sentence_transformers_cache
ENV PYTHONPATH=/opt/python-packages
ENV SAGE_SENTENCE_TRANSFORMERS_REVISION=${SENTENCE_TRANSFORMERS_MODEL_REVISION}
RUN mkdir -p $HF_HOME $SENTENCE_TRANSFORMERS_HOME && \
    python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', revision=os.environ['SAGE_SENTENCE_TRANSFORMERS_REVISION'])" && \
    chown -R sage:sage $HF_HOME $SENTENCE_TRANSFORMERS_HOME && \
    # Clean up pip cache and temporary files to reduce image size
    pip cache purge && \
    find /opt/python-packages -name "*.pyc" -delete && \
    find /opt/python-packages -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Keep runtime model loading deterministic and prevent an unexpected model name
# from downloading executable/model artifacts into a running service.
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

# Set working directory
WORKDIR /app

# Cache busting for code changes
ARG CACHE_BUST=unknown
RUN echo "Cache bust: $CACHE_BUST"

# Copy application code
COPY --chown=sage:sage src/ ./src/
COPY --chown=sage:sage schemas/ ./schemas/
COPY --chown=sage:sage benchmarks/ ./benchmarks/

# Make scripts executable
RUN chmod +x ./src/scripts/entrypoint.sh && \
    chmod +x ./src/scripts/run_services.sh && \
    chmod +x ./src/scripts/debug_startup.sh

# Set Python path
ENV PYTHONPATH=/app:/opt/python-packages
ENV PATH=/opt/dev-tools/bin:/opt/python-packages/bin:$PATH

# LangSmith Configuration (non-secret values)
# Tracing is opt-in: with it on and no LANGSMITH_API_KEY, every LLM step emits a
# 401 from api.smith.langchain.com. Enable per-environment (see docker-compose files).
ENV LANGCHAIN_TRACING_V2=false
ENV LANGSMITH_ENDPOINT=https://api.smith.langchain.com
ENV LANGCHAIN_PROJECT=luminari-sage
ENV GRAPHITI_TELEMETRY_ENABLED=false
ENV HF_HUB_DISABLE_TELEMETRY=1

# Switch to non-root user
USER sage

# Health check (will use API_PORT environment variable at runtime)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c 'import os, urllib.request; urllib.request.urlopen("http://127.0.0.1:%s/api/v1/health" % os.getenv("API_PORT", "8003"), timeout=5).read()' || exit 1

# Expose ports for both API (8003) and MCP (8004)
EXPOSE 8003 8004

# Set entrypoint and default command
ENTRYPOINT ["./src/scripts/entrypoint.sh"]
CMD ["./src/scripts/run_services.sh"]
