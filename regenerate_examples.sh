#!/usr/bin/env bash
# Regenerates every example file under output/, values/, and reports/ by
# running the exact commands documented in EXAMPLES.md. Update both files
# together -- this script's commands must stay in lockstep with that doc.
# Requires the venv from README's Setup section to be active.
set -euo pipefail
cd "$(dirname "$0")"

echo "== Matrices (output/) =="
python src/CalculateMatrix.py 2024
python src/CalculateMatrix.py 2000-2025 --min-start-outs 0

echo "== Values (values/) =="
python src/CalculateValue.py output/matrix_2000-2025_a0.10.json
python src/CalculateValue.py output/matrix_2000-2025_a0.10.json --years 2000-2026
python src/CalculateValue.py output/matrix_2000-2025_a0.10.json --years 1950-2026
python src/CalculateValue.py output/matrix_2000-2025_a0.10.json --pitcher 136880 --years 2000-2026 --by-season

echo "== Reports (reports/) =="
python src/CompareCalculations.py values/value_2026_matrix_2000-2025_a0.10.json
python src/CompareCalculations.py values/value_2000-2026_matrix_2000-2025_a0.10.json
python src/CompareCalculations.py values/value_1950-2026_matrix_2000-2025_a0.10.json
python src/CompareCalculations.py values/value_2000-2026_matrix_2000-2025_a0.10_pitcher136880_byseason.json

echo "All examples regenerated."
