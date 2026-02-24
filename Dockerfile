# Champion Council — HuggingFace Space
# Full system: capsule backend + web control panel + marketplace publish webhook

FROM python:3.10-slim

# Install Node.js 18 + system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (HF Spaces requirement)
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"
ENV HOME="/home/user"

WORKDIR /app

# Install Python dependencies
COPY --chown=user ./requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Install vsce for marketplace publishing
RUN npm install -g @vscode/vsce

# Copy application files
COPY --chown=user . /app

# Make scripts executable
RUN chmod +x scripts/*.sh 2>/dev/null || true

# Ensure vsix directory exists for publish workflow
RUN mkdir -p vsix

# Expose port 7860 (HF Spaces default)
EXPOSE 7860

# Start both the capsule MCP server and the web frontend
CMD ["python", "server.py"]
