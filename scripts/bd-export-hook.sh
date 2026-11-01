#!/usr/bin/env sh
# prek pre-commit hook: keep the tracked beads snapshot current.
#
# `bd init --skip-hooks` (the way every repo here is initialized, so prek and
# entire keep their git hooks) installs no export hook, and `export.auto` writes
# nothing without one (verified 2026-09-08). This hook is the replacement: it
# exports the issues table to .beads/issues.jsonl and stages it, so every commit
# carries the backlog. Shared-server mode keeps the Dolt data under
# ~/.beads/shared-server/, outside the repo, so this file is the only copy that
# leaves the laptop. Restore on a fresh clone: `bd bootstrap --yes`.
#
# Exits 0 without doing anything when the repo has no beads workspace, when bd
# is not installed, or when the export fails: a missing snapshot must never
# block a commit on a branch that predates beads.
set -u
root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -f "$root/.beads/metadata.json" ] || exit 0
command -v bd >/dev/null 2>&1 || exit 0
if bd -C "$root" export -q -o "$root/.beads/issues.jsonl" 2>/dev/null; then
  git -C "$root" add .beads/issues.jsonl
else
  echo "bd-export-hook: bd export failed, commit continues without a fresh snapshot" >&2
fi
exit 0
