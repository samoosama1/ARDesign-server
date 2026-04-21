#!/usr/bin/env bash
# Apply Hunyuan3D-2 patches to a target clone.
# Usage: bash patches/apply.sh [path-to-Hunyuan3D-2-clone]
# Default target: ~/Hunyuan3D-2

set -euo pipefail

TARGET="${1:-$HOME/Hunyuan3D-2}"
PATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$TARGET/.git" ]; then
    echo "error: $TARGET is not a git repo. Clone Hunyuan3D-2 first." >&2
    exit 1
fi

cd "$TARGET"

# Dry-run every patch so we fail before touching files on any conflict.
for patch in "$PATCH_DIR"/*.patch; do
    [ -f "$patch" ] || continue
    echo "checking: $(basename "$patch")"
    git apply --check "$patch"
done

# All good — apply for real.
for patch in "$PATCH_DIR"/*.patch; do
    [ -f "$patch" ] || continue
    echo "applying: $(basename "$patch")"
    git apply "$patch"
done

echo ""
echo "done. 'git diff' to review changes in $TARGET."