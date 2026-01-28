#!/bin/bash
# Prepare prefect.yaml for local deployment by interpolating current git branch
# This script creates a prefect.yaml from a template with the current branch

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE_FILE="$SCRIPT_DIR/prefect.yaml.local.in"
OUTPUT_FILE="$PROJECT_ROOT/prefect.yaml.local"

# Get current git branch
BRANCH=$(git branch --show-current 2>/dev/null || echo "main")

# Get git remote URL (prefer origin, fallback to first remote)
REMOTE=$(git remote | head -n1 || echo "origin")
GIT_REPO=$(git remote get-url "$REMOTE" 2>/dev/null | sed 's#git@github.com:#https://github.com/#; s#\.git$#.git#' || echo "https://github.com/mediacloud/sous-chef-kitchen.git")

echo "Preparing local deployment configuration..."
echo "  Branch: $BRANCH"
echo "  Repository: $GIT_REPO"
echo "  Template: $TEMPLATE_FILE"
echo "  Output: $OUTPUT_FILE"

if [ ! -f "$TEMPLATE_FILE" ]; then
    echo "Error: Template file not found: $TEMPLATE_FILE" >&2
    exit 1
fi

# Interpolate template
sed -e "s|GIT_REPO|$GIT_REPO|g" \
    -e "s|GIT_BRANCH|$BRANCH|g" \
    "$TEMPLATE_FILE" > "$OUTPUT_FILE"

echo "✅ Created $OUTPUT_FILE"
echo ""
echo "To deploy:"
echo "  1. Review the generated prefect.yaml.local"
echo "  2. Run: make local-deploy"
