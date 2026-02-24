#!/bin/bash
# Champion Council — VS Code Marketplace Publish Script
# Called by webhook or manual trigger
# Requires VSCE_PAT environment variable

set -e

echo "=== Champion Council Publish Pipeline ==="
echo "Timestamp: $(date -u)"

# Check for PAT
if [ -z "$VSCE_PAT" ]; then
    echo "ERROR: VSCE_PAT not set"
    exit 1
fi

EXTENSION_DIR="/app/extension"

# Check if extension source exists
if [ ! -d "$EXTENSION_DIR" ]; then
    echo "ERROR: Extension directory not found at $EXTENSION_DIR"
    exit 1
fi

cd "$EXTENSION_DIR"

# Install dependencies
echo "--- Installing dependencies ---"
npm ci --ignore-scripts 2>/dev/null || npm install --ignore-scripts

# Compile TypeScript
echo "--- Compiling TypeScript ---"
npm run compile

# Package vsix
echo "--- Packaging vsix ---"
npx @vscode/vsce package --no-dependencies

# Find the built vsix
VSIX_FILE=$(ls -t *.vsix 2>/dev/null | head -1)
if [ -z "$VSIX_FILE" ]; then
    echo "ERROR: No vsix file found after packaging"
    exit 1
fi

echo "Built: $VSIX_FILE"
echo "Size: $(du -h "$VSIX_FILE" | cut -f1)"

# Publish to VS Code Marketplace
echo "--- Publishing to VS Code Marketplace ---"
npx @vscode/vsce publish --pat "$VSCE_PAT" --no-dependencies

echo "=== Published successfully ==="
echo "Timestamp: $(date -u)"
