#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${SRC:-$SCRIPT_DIR/SKILL.md}"
SCRIPTS_SRC="${SCRIPTS_SRC:-$SCRIPT_DIR/scripts}"
VIEWER_SRC="${VIEWER_SRC:-$SCRIPT_DIR/viewer}"
LOCAL_SHARE="${LOCAL_SHARE:-$HOME/.local/share/grill-flow}"

[ -f "$SRC" ] || { echo "✗ source not found: $SRC" >&2; exit 1; }
[ -d "$SCRIPTS_SRC" ] || { echo "✗ scripts dir not found: $SCRIPTS_SRC" >&2; exit 1; }
[ -d "$VIEWER_SRC" ] || { echo "✗ viewer dir not found: $VIEWER_SRC" >&2; exit 1; }

PRIMARY_ROOTS=("$HOME/.claude" "$HOME/.codex")
OPTIONAL_ROOTS=(
  "$HOME/.agents"
  "$HOME/.config/muse"
  "$HOME/.gemini/config"
  "$HOME/.pi/agent"
  "$HOME/.zcode"
  "$HOME/.kimicode"
)
ROOTS=("${PRIMARY_ROOTS[@]}")
for opt_root in "${OPTIONAL_ROOTS[@]}"; do
  if [ -d "$opt_root" ]; then
    ROOTS+=("$opt_root")
  fi
done

written=""
for root in "${ROOTS[@]}"; do
  skills_dir="$root/skills"
  mkdir -p "$skills_dir"
  canon="$(cd "$skills_dir" && pwd -P)"
  if printf '%s' "$written" | grep -qxF "$canon"; then
    echo "↩ skip    $skills_dir  (symlink → already-synced target; not registering twice)"
    continue
  fi
  written="$written$canon"$'\n'
  skill_dst="$skills_dir/grill-flow"
  mkdir -p "$skill_dst"
  cp "$SRC" "$skill_dst/SKILL.md"
  rm -rf "$skill_dst/scripts"
  cp -R "$SCRIPTS_SRC" "$skill_dst/scripts"
  rm -rf "$skill_dst/scripts/__pycache__"
  rm -f "$skill_dst/scripts"/test_*.py
  chmod +x "$skill_dst/scripts/grill-flow.py"
  rm -rf "$skill_dst/viewer"
  cp -R "$VIEWER_SRC" "$skill_dst/viewer"
  echo "✓ synced  $skill_dst"
done

rm -rf "$LOCAL_SHARE"
mkdir -p "$LOCAL_SHARE"
cp "$SCRIPTS_SRC/grill-flow.py" "$LOCAL_SHARE/grill-flow.py"
for mod in "$SCRIPTS_SRC"/grill_flow_*.py; do
  cp "$mod" "$LOCAL_SHARE/$(basename "$mod")"
done
cp -R "$VIEWER_SRC" "$LOCAL_SHARE/viewer"
chmod +x "$LOCAL_SHARE/grill-flow.py"
echo "✓ synced  $LOCAL_SHARE"

CURSOR_RULES_DIR="${CURSOR_RULES_DIR:-$HOME/.cursor/rules}"
CURSOR="$CURSOR_RULES_DIR/grill-flow.mdc"
mkdir -p "$(dirname "$CURSOR")"
{
  cat <<'CURSOR_FRONTMATTER'
---
description: Use when mapping a file-set or git diff into a component graph and line-to-flow coverage with dual budgets, validators, and a hosted HTML viewer. Maps only — never grades, reviews, or commits. Triggers: "grill-flow", "map this flow", "map the component graph", "run grill-flow on this diff".
globs:
alwaysApply: false
---
CURSOR_FRONTMATTER
  if grep -q '^---$' "$SRC"; then
    awk 'f>=2{print} /^---$/{f++}' "$SRC"
  else
    cat "$SRC"
  fi
} > "$CURSOR"
echo "✓ synced  $CURSOR"

echo "Done — grill-flow synced (SKILL.md + scripts/ + viewer/) to ${#ROOTS[@]} agent skill roots, Cursor (.mdc), and LOCAL_SHARE."
