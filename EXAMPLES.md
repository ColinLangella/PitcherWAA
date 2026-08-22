# Example Data Provenance

The example files checked into `output/`, `values/`, and `reports/` are real
pipeline output, not hand-written fixtures. This documents the exact command
that produced each one, so they can be regenerated or extended consistently.
Update this file whenever an example is added, replaced, or removed.

## Matrices (`output/`)

| File | Command |
|---|---|
| `matrix_2024_a0.10.json` / `.txt` | `python src/CalculateMatrix.py 2024` |
| `matrix_2000-2025_a0.10.json` / `.txt` | `python src/CalculateMatrix.py 2000-2025 --min-start-outs 0` |

The 2000-2025 matrix was built with `--min-start-outs 0` (include every
start, openers included) rather than the default `3` -- note this if you
diff it against a freshly built default-settings matrix for the same years.

## Values (`values/`)

All four evaluate against `output/matrix_2000-2025_a0.10.json`.

| File | Command |
|---|---|
| `value_2026_matrix_2000-2025_a0.10.json` / `.txt` | `python src/CalculateValue.py output/matrix_2000-2025_a0.10.json` |
| `value_2000-2026_matrix_2000-2025_a0.10.json` / `.txt` | `python src/CalculateValue.py output/matrix_2000-2025_a0.10.json --years 2000-2026` |
| `value_1950-2026_matrix_2000-2025_a0.10.json` / `.txt` | `python src/CalculateValue.py output/matrix_2000-2025_a0.10.json --years 1950-2026` |
| `value_2000-2026_matrix_2000-2025_a0.10_pitcher136880_byseason.json` / `.txt` | `python src/CalculateValue.py output/matrix_2000-2025_a0.10.json --pitcher 136880 --years 2000-2026 --by-season` |

The first has no `--years` flag, so it evaluates the actual current season
(2026 as of this writing) via `CalculateValue.py`'s default. Pitcher `136880`
is Roy Halladay.

## Reports (`reports/`)

Each report is `CompareCalculations.py` run against its matching values file
above -- no other flags:

```bash
python src/CompareCalculations.py values/value_2026_matrix_2000-2025_a0.10.json
python src/CompareCalculations.py values/value_2000-2026_matrix_2000-2025_a0.10.json
python src/CompareCalculations.py values/value_1950-2026_matrix_2000-2025_a0.10.json
python src/CompareCalculations.py values/value_2000-2026_matrix_2000-2025_a0.10_pitcher136880_byseason.json
```
