#!/usr/bin/env bash
# Scaffolder: copies the memory/ knowledge base + scripts/ into a target repo
# as a subfolder. Safe to run from a CI/pipeline action or interactively.
#
# Usage:
#   scripts/scaffold.sh /path/to/target-repo [subfolder-name]
#
# Defaults subfolder-name to "memory". Never overwrites an existing subfolder.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="${1:?usage: scaffold.sh /path/to/target-repo [subfolder-name]}"
SUBFOLDER="${2:-memory}"

if [ ! -d "$TARGET_REPO" ]; then
  echo "target repo does not exist: $TARGET_REPO" >&2
  exit 1
fi

DEST="$TARGET_REPO/$SUBFOLDER"
if [ -e "$DEST" ]; then
  echo "refusing to overwrite existing path: $DEST" >&2
  exit 1
fi

mkdir -p "$DEST"
cp -R "$SELF_DIR/memory/." "$DEST/"

SCRIPTS_DEST="$TARGET_REPO/scripts"
mkdir -p "$SCRIPTS_DEST"
cp "$SELF_DIR/scripts/kb.py" "$SCRIPTS_DEST/kb.py"
cp "$SELF_DIR/scripts/visualize.py" "$SCRIPTS_DEST/visualize.py"

WORKFLOW_DEST="$TARGET_REPO/.github/workflows"
mkdir -p "$WORKFLOW_DEST"
cp "$SELF_DIR/.github/workflows/kb-lint.yml" "$WORKFLOW_DEST/kb-lint.yml"

echo "scaffolded knowledge base into $DEST"
echo "scripts copied into $SCRIPTS_DEST"
echo "CI workflow copied into $WORKFLOW_DEST"
echo "next: read $DEST/AGENT.md"
