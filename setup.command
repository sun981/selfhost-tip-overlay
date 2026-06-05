#!/usr/bin/env bash
# Double-click this on macOS to run the first-time setup wizard.
# (Finder runs .command files in Terminal.) It just launches scripts/setup.sh.
cd "$(dirname "$0")" || exit 1
bash scripts/setup.sh
