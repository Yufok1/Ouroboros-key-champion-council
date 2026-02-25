# Champion Council self_deploy - Full single-container image
# Includes proxy + capsule dependencies.

FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps — git required for huggingface_hub model downloads via git-lfs
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (full stack)
COPY requirements-server.txt requirements-capsule.txt requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# App files
COPY backend/ backend/
COPY frontend/ frontend/
COPY config/ config/
COPY entrypoint.sh /app/entrypoint.sh

# Non-root user for security
RUN useradd --create-home --uid 1000 council

# Runtime dirs (owned by council user)
RUN mkdir -p /app/data/brain /app/data/bag /app/data/workflows /app/data/slots /app/data/config /app/capsule \
    && chown -R council:council /app/data /app/capsule

EXPOSE 7866 8766

# Defaults for single-container local mode.
ENV APP_ENV=production \
    APP_PORT=7866 \
    MCP_PORT=8766 \
    MANAGE_LOCAL_CAPSULE=1 \
    PERSISTENCE_MODE=local \
    CAPSULE_PATH=/app/capsule/champion_gen8.py \
    CAPSULE_GZ_PATH=/app/capsule/capsule.gz \
    DATA_DIR=/app/data

RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
