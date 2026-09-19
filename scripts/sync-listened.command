#!/bin/bash
# Double-click this to publish your current Apple Podcasts listening history.
# It reads the Podcasts database on this Mac, encrypts the result, and pushes it.
cd "$(dirname "$0")/.." || exit 1
echo "Reading Apple Podcasts…"
python3 scripts/export_listened.py --push
echo
echo "Done. This window can be closed."
