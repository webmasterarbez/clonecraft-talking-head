#!/bin/sh
# Check the Operator docs: no real names or home paths, and every relative link resolves.
# Run from the repo root: sh .claude/skills/operator-docs-authoring/scripts/check-docs.sh [file ...]
files="${*:-README.md docs/operator-guide.md docs/setup-and-maintenance.md}"
status=0
for f in $files; do
  if grep -nE '/home/|@[A-Za-z][A-Za-z0-9_]*' "$f" | grep -v '@example'; then
    echo "LEAK: possible real name or home path in $f"
    status=1
  fi
  dir=$(dirname "$f")
  for p in $(grep -oE '\]\([^) #:]+' "$f" | sed 's/^](//' | grep -v '^http'); do
    if [ ! -e "$dir/$p" ]; then
      echo "BROKEN link in $f: $p"
      status=1
    fi
  done
done
if [ "$status" -eq 0 ]; then echo "docs ok"; fi
exit $status
