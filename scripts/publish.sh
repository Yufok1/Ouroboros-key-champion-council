#!/bin/bash
# Champion Council — VS Code Marketplace Publish Script
# Publishes a pre-built .vsix to the VS Code Marketplace.
# The vsix is built manually by the developer and placed in /app/vsix/
# Requires VSCE_PAT environment variable (set as HF Space Secret)

set -e

echo "=== Champion Council Publish ==="
echo "Timestamp: $(date -u)"

# Check for PAT
if [ -z "$VSCE_PAT" ]; then
    echo "ERROR: VSCE_PAT not set. Add it as a Space Secret."
    exit 1
fi

VSIX_DIR="/app/vsix"

# Find the latest .vsix file
VSIX_FILE=$(ls -t "$VSIX_DIR"/*.vsix 2>/dev/null | head -1)

if [ -z "$VSIX_FILE" ]; then
    echo "ERROR: No .vsix file found in $VSIX_DIR"
    echo "Place your pre-built .vsix in the vsix/ directory and push."
    exit 1
fi

echo "Found: $VSIX_FILE"
echo "Size: $(du -h "$VSIX_FILE" | cut -f1)"

# Publish to VS Code Marketplace
echo "--- Publishing to VS Code Marketplace ---"
npx @vscode/vsce publish --packagePath "$VSIX_FILE" --pat "$VSCE_PAT" --no-dependencies

echo "=== Published successfully ==="
echo "Timestamp: $(date -u)"
