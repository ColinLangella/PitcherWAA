#!/usr/bin/env bash
# Runs every module's `if __name__ == "__main__":` self-check block -- this is
# the project's test suite (plain asserts, no pytest dependency; see CLAUDE.md
# "Code Style"). Requires the venv from README's Setup section to be active.
#
# PitchingAPI.py, LookupAPI.py, and WarAPI.py are intentionally excluded: their
# self-checks make live MLB-StatsAPI / Baseball-Reference calls, so they're
# network-dependent smoke tests, not fast/deterministic unit checks. Run them
# individually (e.g. `python src/LookupAPI.py`) if you want to exercise them.
set -euo pipefail
cd "$(dirname "$0")"

checks=(
  src/Cache/Cache.py
  src/StartClassifier.py
  src/MatrixBuilder.py
  src/Smoothing.py
  src/MatrixIO.py
  src/ValueIO.py
  src/ReportIO.py
  src/Utils/Retry.py
  src/Utils/YearSpread.py
  src/Models/Start.py
  src/Models/Matrix.py
  src/Models/Value.py
  src/Models/Comparison.py
)

for check in "${checks[@]}"; do
  echo "== $check =="
  python "$check"
done

echo "All self-checks passed."
