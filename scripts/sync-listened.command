#!/bin/bash
# Double-click this to publish your current Apple Podcasts listening history.
# It reads the Podcasts database on this Mac, writes data/listened.json (unencrypted unless
# export_listened.py is given --encrypt) and pushes it, along with any earlier commit still waiting.
# Output also goes to .claude/logs/sync-<date>.log in the repository folder (not tracked by git).
cd "$(dirname "$0")/.." || exit 1
mkdir -p .claude/logs
LOG=".claude/logs/sync-$(date +%F).log"
{
  echo "=== $(date '+%F %T')"
  echo "Reading Apple Podcasts…"
  python3 scripts/export_listened.py --push
  echo "exit=$?"
} 2>&1 | tee -a "$LOG"
echo
echo "Done. This window can be closed."
