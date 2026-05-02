# Champion Council — HuggingFace Space
# Full system: capsule backend + web control panel + marketplace publish webhook

FROM python:3.11-slim

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    openssh-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (HF Spaces requirement), but keep dependency install as
# root so packages land in system site-packages for the capsule subprocess.
RUN useradd -m -u 1000 user

WORKDIR /app

# Install Python dependencies into the system site-packages. The capsule is
# launched with PYTHONNOUSERSITE=1, so user-site packages are intentionally
# hidden from it.
COPY --chown=user ./requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt
RUN mkdir -p /usr/local/lib/python3.11/site-packages/lattice/observations \
    && chown -R user:user /usr/local/lib/python3.11/site-packages/lattice

# Copy application files
COPY --chown=user . /app
COPY --chown=user ./scripts /app/scripts
COPY --chown=user ./static/assets/packs/index.json /app/static/assets/packs/index.json
RUN mkdir -p /app/.infinity_cache \
    && test -f /app/scripts/text_theater.py \
    && test -f /app/static/assets/packs/index.json \
    && chown -R user:user /app

USER user
ENV PATH="/home/user/.local/bin:$PATH"
ENV HOME="/home/user"

# Expose port 7860 (HF Spaces default)
EXPOSE 7860

# Start both the capsule MCP server and the web frontend
CMD ["python", "server.py"]
