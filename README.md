# PitcherWAA

An alternative to starting-pitcher WAR, computed as **WAA (Wins Above Average)**
derived from *start quality* rather than component pitching stats. See
`CLAUDE.md` for the full design writeup.

## Setup

Requires Python 3.11.

```bash
python -m venv .venv
source .venv/bin/activate
pip install MLB-StatsAPI numpy pybaseball matplotlib
```

## `CalculateMatrix.py`

Builds the league-wide `(outs, earned runs) -> win probability` matrix from
real MLB game logs, then writes it as JSON (source of truth) and an aligned
text heatmap.

```bash
# Default: most recent complete season, alpha=0.1
python src/CalculateMatrix.py

# A single season
python src/CalculateMatrix.py 2024

# A multi-year spread -- all starts from every year are pooled into one matrix
python src/CalculateMatrix.py 2020-2025

# Tune alpha (credit/blame for no-decisions; 0 = fully neutral, 0.5 = fully responsible)
python src/CalculateMatrix.py 2024 --alpha 0.25

# Control how many pitchers' game logs are fetched concurrently per season (default 8)
python src/CalculateMatrix.py 2024 --max-threads 16

# Include "opener" starts under 1.0 IP instead of excluding them (default excludes < 3 outs)
python src/CalculateMatrix.py 2024 --min-start-outs 0

# Loosen or disable the starter/replacement split used for replacement_baseline (default 0.5)
python src/CalculateMatrix.py 2024 --min-start-ratio 0.3
python src/CalculateMatrix.py 2024 --min-start-ratio 0

# Logging verbosity: error, info, or debug (default info)
python src/CalculateMatrix.py 2024 --log-level debug
```

`--log-level` uses standard Python logging semantics: each level shows its
own messages plus everything above it in severity (DEBUG < INFO < ERROR), so
lower levels are cumulative supersets of higher ones.

- `debug`: every step as it happens -- each pitcher's game log fetch, each
  cache hit/miss, each start's decision classification, each populated
  bucket's counts, each interpolated cell -- plus everything `info` logs.
- `info` (default): major state transitions and incremental progress only
  (phase changes, "N/M pitchers processed" every 50, isotonic convergence
  deltas) -- plus errors.
- `error`: errors only (e.g. a failed per-pitcher fetch, isotonic regression
  failing to converge).

Each run writes `output/matrix_<years>_a<alpha>.json` and the matching
`.txt` heatmap, e.g. `output/matrix_2024_a0.10.json` /
`output/matrix_2024_a0.10.txt`. A multi-year spread like `2020-2025` produces
`matrix_2020-2025_a0.10.{json,txt}`.

`--min-start-ratio` (default `0.5`) splits the matrix's pooled starts into a
starter pool and a replacement pool by each pitcher's aggregate
`gamesStarted / gamesPlayed` ratio over the matrix's year span -- the
replacement pool's mean WP becomes `replacement_baseline`, an empirical
replacement-level baseline `CalculateValue.py`'s `--metric war` can use.
This only affects that one derived statistic, not which starts get bucketed
into the matrix cells (every start in the league is still pooled regardless
of who threw it). Pass `0` to disable the split (`replacement_baseline` is
left unset).

Raw MLB API responses are cached on disk under `src/Cache/` (keyed by season
and pitcher ID), so re-running the same year(s) — including with a different
`--alpha` — reuses the cache instead of re-fetching. A cold run over a full
season fetches each pitcher's game log concurrently (`--max-threads`, default
8) and finishes in seconds to tens of seconds depending on thread count; a
warm rerun is near-instant.

### Sample output (`matrix_2024_a0.10.txt`, truncated)

```
Matrix years=2024-2024 alpha=0.10 baseline=0.488 replacement_baseline=0.399 replacement_min_start_ratio=0.50 total_starts=4827
          ER=0   ER=1   ER=2   ER=3   ER=4   ER=5   ER=6   ER=7   ER=8   ER=9+
Outs=0     0.488* 0.422* 0.420* 0.351* 0.290* 0.262* 0.262* 0.262* 0.262* 0.262*
...
Outs=18    0.796  0.690  0.569  0.459  0.291  0.291  0.291  0.290  0.290  0.290*
...
Outs=27+   0.835  0.737  0.652  0.538  0.488* 0.488* 0.488* 0.488* 0.488* 0.488*

* = interpolated (n=0; value comes purely from the monotonic fit)
```

Rows are outs recorded (0-27, with `27+` absorbing extra-inning complete
games); columns are earned runs allowed (0-9, with `9+` absorbing blowouts).
Cells marked `*` had zero observed starts and are filled purely by the 2D
isotonic fit, not raw counts.

## `CalculateValue.py`

Consumes a matrix file produced above and scores real pitchers' starts
against it: WAA = sum over their starts of `(matrix cell's smoothed_wp -
matrix baseline)`. It never rebuilds the matrix -- a missing or malformed
matrix file is an error.

`--metric war` computes a second, opt-in metric alongside WAA: WAR = sum
over their starts of `(matrix cell's smoothed_wp - replacement_baseline)`,
where `replacement_baseline` is below the league-average baseline (see
`CalculateMatrix.py`'s `--min-start-ratio` above). Subtracting a
replacement-level baseline instead of a league-average one means an
average-or-better start is worth something, and more of them is worth
more -- closer to how real-world WAR rewards durable, average-or-better
volume rather than punishing it. Default output (`--metric waa`, the
default) is unaffected either way.

```bash
# Every qualified starter, evaluated against the 2024 matrix, for the 2024 season
python src/CalculateValue.py output/matrix_2024_a0.10.json --years 2024

# A single pitcher, by MLBAM id or by name (fuzzy match)
python src/CalculateValue.py output/matrix_2024_a0.10.json --pitcher 543037 --years 2024
python src/CalculateValue.py output/matrix_2024_a0.10.json --pitcher "Gerrit Cole" --years 2024

# A single team's starts, as-of each start (mid-season trades split correctly across teams)
python src/CalculateValue.py output/matrix_2024_a0.10.json --team NYY --years 2024

# Evaluate a season different from the matrix's -- matrix and evaluation years are independent
python src/CalculateValue.py output/matrix_2020-2025_a0.10.json --years 2026

# Split a multi-year span into one row per pitcher-season instead of one totaled row
python src/CalculateValue.py output/matrix_2020-2025_a0.10.json --pitcher "Gerrit Cole" --years 2020-2025 --by-season

# Loosen or disable the starter-role filter (default 0.5) for the default all-pitchers pool
python src/CalculateValue.py output/matrix_2024_a0.10.json --min-start-ratio 0.3
python src/CalculateValue.py output/matrix_2024_a0.10.json --min-start-ratio 0

# Compute WAR (replacement-level baseline) alongside WAA -- requires a matrix built with
# CalculateMatrix.py --min-start-ratio > 0
python src/CalculateValue.py output/matrix_2024_a0.10.json --years 2024 --metric war

# Override the replacement baseline instead of using the matrix's computed one
python src/CalculateValue.py output/matrix_2024_a0.10.json --years 2024 --metric war --replacement-level 0.40

# Control concurrent per-pitcher fetches (default 8) and logging verbosity (default info)
python src/CalculateValue.py output/matrix_2024_a0.10.json --max-threads 16 --log-level debug
```

`--pitcher`/`--team` accept either an MLBAM numeric id or a name/abbreviation
(resolved via `statsapi.lookup_player`/`lookup_team`); an ambiguous name
raises an error listing every candidate. Name resolution for `--pitcher` is
tried against each evaluated season, most recent first, so a pitcher who
didn't appear at all in the last `--years` season (e.g. hurt the whole year)
still resolves via an earlier season's roster snapshot. With no
`--pitcher`/`--team`, the default pool is every pitcher whose
`gamesStarted / gamesPlayed` ratio is at least `--min-start-ratio` (default
`0.5`) -- this keeps relievers who make an occasional spot start out of a
report meant to score starters. Pass `--min-start-ratio 0` to restore the
old "any start counts" behavior. This filter is skipped entirely when
`--pitcher` is given -- an explicitly named pitcher is always evaluated
regardless of role. Once a pitcher is in the pool (or named explicitly),
there's still no minimum start *count* applied.

The ratio window matches how the report groups starts: a `--by-season`
report qualifies each season on its own (each season is scored
independently anyway), but a pooled multi-year report qualifies on the
pitcher's *aggregate* ratio summed across the whole `--years` span --
otherwise a career reliever with one qualifying rookie season (e.g. Mariano
Rivera going 10 GS / 19 GP in 1995) would land in a career-span report on
that one season's strength, while every start counted against their bWAR
comes from relief years. `CalculateMatrix.py` is unaffected either way -- it
always fetches every pitcher who started a game that season, since the
matrix buckets every start in the league regardless of who threw it.

`--years` defaults to the
actual current season (unlike `CalculateMatrix.py`'s default of the most
recent *complete* season), and accepts the same `2024` / `2020-2025` spread
syntax. `--log-level` has the same `error`/`info`/`debug` semantics as
`CalculateMatrix.py`, with `debug` additionally logging each start's bucket
lookup and WAA contribution.

By default, a multi-year `--years` span is totaled into one row per pitcher.
`--by-season` splits that into one row per pitcher *per season* instead --
each season's starts are scored independently, so you can see a pitcher's
year-by-year trend rather than a single career-span number. The `.json`/`.txt`
filenames get a `_byseason` suffix, and each pitcher entry carries a `season`
field (`null` when not split).

Fetches reuse the same per-pitcher game-log cache under `src/Cache/`, and
exclude short starts using the matrix's own `min_start_outs` (not a separate
flag) so evaluation stays consistent with how the matrix's buckets were
built.

Each run writes `values/value_<eval-years>_<matrix-file-stem>[_pitcher<id>][_team<name>].json`
and the matching `.txt` table -- a directory separate from `output/`, since
`output/` holds matrices and `values/` holds evaluations against them.

### Sample output (`value_2024_matrix_2024_a0.10.txt`, truncated)

```
Values eval_years=2024-2024 matrix=matrix_2024_a0.10.json baseline=0.488 pitchers=259 min_start_ratio=0.50 metric=waa
Pitcher                       ID  Starts    SumWP   AvgWP      WAA
Zack Wheeler              554430      32   20.349   0.636   +4.743
Chris Sale                519242      29   18.526   0.639   +4.383
Tarik Skubal              669373      31   19.449   0.627   +4.331
...
Taijuan Walker            592836      15    5.657   0.377   -1.658
```

Rows are sorted by WAA descending. `SumWP`/`AvgWP` are the sum/average of
each start's `smoothed_wp` looked up from the matrix; `WAA` is the sum of
`(smoothed_wp - baseline)` across the pitcher's starts.

With `--metric war`, the header line additionally shows
`replacement_baseline=`, a `WAR` column appears after `WAA`, and rows sort
by `WAR` descending instead.

## `CompareCalculations.py`

Takes a `values/*.json` file produced above and checks it against
Baseball-Reference's bWAR for the same pitchers/seasons, via
[`pybaseball`](https://github.com/jldbc/pybaseball) (`bwar_pitch()`, one bulk
data file covering every season/pitcher, joined directly on its `mlb_ID`
column -- no scraping, no id crosswalk needed). It figures out everything it
needs (matrix, alpha, eval years, `--by-season` vs. pooled, `--metric`, any
`--pitcher`/`--team` filter) from the values JSON itself -- including which of
this project's own metrics to compare. A values file built with `--metric war`
gets compared, plotted, and written up as WAR vs. bWAR throughout (titles,
axis labels, column headers, and the prose analysis all say "WAR", and the
scope bullets explain the replacement-level baseline that mode uses); a
default `--metric waa` values file is unaffected and reads exactly as before.

```bash
python src/CompareCalculations.py values/value_2024_matrix_2024_a0.10.json

python src/CompareCalculations.py values/value_2000-2026_matrix_2000-2025_a0.10_byseason.json --log-level debug

# Same detection applies to a --metric war values file -- no extra flag needed here
python src/CompareCalculations.py values/value_2026_matrix_2000-2025_a0.10_war.json
```

`--log-level` has the same `error`/`info`/`debug` semantics as the other two
scripts, with `debug` additionally logging every pitcher/season that has no
matching bWAR record.

A **pooled** (non-`--by-season`) values report is compared against each
pitcher's bWAR *summed across every season in the report's `eval_years`*, so
a career-span WAA lines up with a career-span WAR. A **`--by-season`** report
joins each pitcher-season exactly. Either shape works with `--pitcher`- or
`--team`-filtered values files too; a single-pitcher, single-season report
(one point) still plots, it just skips the correlation/fit stats that need
`>= 2` points.

Each run writes `reports/<values-file-stem>/`:

```
reports/value_2000-2026_matrix_2000-2025_a0.10_byseason/
  report.md          # correlation stats, best-fit line, largest-residual pitchers
  scatter_bwar.png    # WAA (y) vs bWAR (x), with a best-fit line
```

### Sample report (truncated)

```
# WAA vs. Accepted WAR: All qualified starters, 2000–2026

- **Scope:** All qualified starters
- **Years evaluated:** 2000–2026 (one row per pitcher-season)
- **Metric:** WAA (league-average baseline=0.495)
- Source values file: `value_2000-2026_matrix_2000-2025_a0.10_byseason.json`
- Matrix: `matrix_2000-2025_a0.10.json` (years=2000-2025, alpha=0.10)

## WAA vs bWAR

![WAA vs bWAR](scatter_bwar.png)

- n = 8578 (excluded 0: no bWAR match)
- Pearson r = 0.847, R² = 0.717
- Best fit: WAA = 0.633 × bWAR - 0.526

### Top/bottom 5 by WAA
...

### Top/bottom 5 by bWAR
...

### Largest disagreements (by fit residual)

| Pitcher | Season | WAA | bWAR | Residual |
|---|---|---|---|---|
| Kenny Rogers | 2000 | -1.209 | +4.99 | -3.841 |
...
```

The header's **Scope** line reflects any `--pitcher`/`--team` filter baked into the
source values file (a pitcher name + MLBAM id, a team name, or "All qualified
starters"), so it's always clear at a glance what a given report actually covers.
The **Metric** line reflects the values file's own `--metric`: for a `--metric
war` file it instead reads `**Metric:** WAR (replacement-level baseline=...,
vs. league-average baseline=...)`, every `WAA` label in the sections below
becomes `WAR`, and an extra sentence explains how to read the fit against the
paired WAA report for the same pitchers. See
`reports/value_2026_matrix_2000-2025_a0.10_war/report.md` for a full example.

**fWAR (FanGraphs) is not yet supported.** FanGraphs' leaderboard endpoint
sits behind an active Cloudflare bot challenge that blocks `pybaseball` (and
plain `requests`) outright -- see "Open Questions" in `CLAUDE.md`.

## Development

Every module under `src/` carries an `if __name__ == "__main__":` block with
plain `assert`s -- that's this project's test suite, no `pytest` dependency.
Run them all with:

```bash
./run_self_checks.sh
```

`PitchingAPI.py`, `LookupAPI.py`, and `WarAPI.py` are excluded from that
script because their self-checks make live MLB-StatsAPI / Baseball-Reference
calls; run those individually (e.g. `python src/LookupAPI.py`) if you want to
smoke-test live API behavior.

`output/`, `reports/`, and `values/` in this repo hold a few small example
runs, checked in as a demonstration -- they're otherwise gitignored, so
regenerating them locally won't clutter `git status`. See `EXAMPLES.md` for
the exact command that produced each one.

## Future Improvements

- **fWAR support** -- see "Open Questions" in `CLAUDE.md` for why this is
  blocked and what would unblock it (a `pybaseball` fix, another FanGraphs
  access path, or a manual `--fwar-csv` import flow).
- **A formal test suite.** The `if __name__ == "__main__":` self-checks catch
  regressions but don't integrate with test runners, coverage tooling, or CI.
  Porting them to `pytest` (or adding a GitHub Actions workflow that runs
  `run_self_checks.sh` on push) would make regressions visible without a
  manual step.
- **Configurable axis caps.** `_OUTS_CAP`/`_ER_CAP` in `CalculateMatrix.py`
  are hardcoded at 27 outs / 9 ER (see "Resolved Questions" in `CLAUDE.md`).
  Exposing them as flags would let someone experiment with tighter or looser
  tails without editing source.
- **Per-season matrix averaging as an alternative to pooling.** Pooling
  (the current, simpler default) weights seasons by start count; an
  `--average-seasons` mode could compare against equal per-season weighting.

## License

[MIT](LICENSE)
