# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

An alternative to starting-pitcher WAR, computed as **WAA (Wins Above Average)** derived from *start quality* rather than component pitching stats.

The premise: bucket every start in the league by `(innings pitched, earned runs)`, then empirically measure how often a start in each bucket led to a team win. A pitcher's value is the sum of how much better (or worse) their starts' bucket win probabilities were than a league-average start.

**Win probability per bucket:**

```
WP = (1·W + (0.5 + alpha)·ND_team_won + (0.5 - alpha)·ND_team_lost + 0·L) / total_starts_in_bucket
```

`alpha` (default `0.1`) credits the pitcher for no-decisions their team won and debits for no-decisions their team lost. `alpha = 0` treats all no-decisions as neutral; `alpha = 0.5` treats the pitcher as fully responsible for the team result.

**WAA** for a pitcher is then:

```
WAA = SUM over their starts of ( WP(bucket of start) - baseline )
```

where `baseline` is the mean win probability across every start in the matrix year(s) — see "Settled Design Decisions".

The three-step pipeline below is implemented (`src/CalculateMatrix.py`, `src/CalculateValue.py`, `src/CompareCalculations.py`). Every module also carries an `if __name__ == "__main__":` self-check block that doubles as its test coverage — run `./run_self_checks.sh` after making changes. The sections below remain the source of truth for design intent; don't silently deviate from a "Settled Design Decision" or "Resolved Question" when extending the code.

## Settled Design Decisions

These four were decided explicitly by the project owner. Do not silently change them.

1. **IP axis granularity: thirds of an inning (outs).** Rows are outs recorded, so 5.0 / 5.1 / 5.2 IP are distinct buckets. This is a real distinction in start quality and is worth the sparser cells. ~28 rows × ~10 ER columns ≈ 280 cells against ~4,858 starts/season, so the tails are thin by design and lean on the smoothing step.
2. **WAA baseline: league mean start WP**, computed across every start in the matrix year(s). With symmetric alpha weights this lands at ~0.500 by construction, but it must be *computed*, not hardcoded — a computed baseline self-calibrates to the run environment.
3. **Matrix output: JSON source of truth + rendered text heatmap.** The JSON holds probabilities, raw counts, `alpha`, years, and a per-cell interpolated flag; the `.txt` is the aligned human view. `CalculateValue.py` reads the JSON. Suggested naming: `matrix_2025_a0.10.json` / `.txt`.
4. **Smoothing: sample-size shrinkage, then 2D isotonic regression.** Shrink each cell toward a prior in proportion to its `n` (so an `n=2` all-wins cell does not read `1.000`), then enforce monotonicity along both axes. Nonparametric — no assumed functional form. Empty cells inherit from neighbors via the monotonic fit.

## Three-Step Pipeline

### `CalculateMatrix.py`
Builds the league-wide bucket → win-probability matrix.

| Argument | Default |
|---|---|
| year spread (`2023` or `2020-2025`) | most recent **complete** season |
| `--alpha` | `0.1` |
| `--min-start-outs` (exclude starts with fewer outs; `0` includes every start) | `3` (excludes < 1.0 IP) |
| `--max-threads` (concurrent per-pitcher game-log fetches) | `8` |
| `--log-level` (`error`/`info`/`debug`) | `info` |

Outputs a human-readable value heatmap file (matrix of win probabilities keyed by IP × ER), which is the input to step two.

### `CalculateValue.py`
Consumes a generated matrix file and scores pitchers against it.

| Argument | Default |
|---|---|
| matrix file | required |
| `--pitcher` (MLBAM id or fuzzy name match) | all qualified starters |
| `--team` (MLBAM id, abbreviation, or name; matched as-of each start) | all |
| `--years` (`2023` or `2020-2025`) | current season |
| `--by-season` (one row per pitcher-season instead of totaled) | off (totaled) |
| `--min-start-ratio` (minimum `gamesStarted / gamesPlayed` for the default all-starters pool; `0` disables it) | `0.5` |
| `--max-threads` (concurrent per-pitcher game-log fetches) | `8` |
| `--log-level` (`error`/`info`/`debug`) | `info` |

Outputs per-pitcher totals (starts, sum WP, avg WP, WAA) as JSON (source of truth) + an aligned text table, written under `values/` — see "Resolved Questions".

**The matrix year and the evaluation year are independent** — building on 2020-2025 and evaluating 2026 is a normal use case. `CalculateValue.py` must never silently rebuild the matrix; a missing or malformed matrix file is an error.

### `CompareCalculations.py`
Consumes a generated values file and checks WAA against Baseball-Reference's bWAR for the same pitchers/seasons.

| Argument | Default |
|---|---|
| values file | required |
| `--log-level` (`error`/`info`/`debug`) | `info` |

It derives everything it needs — matrix, alpha, eval years, `--by-season` vs. pooled, any `--pitcher`/`--team` filter — from the values JSON itself; it never re-derives settings some other way. Outputs `reports/<values-file-stem>/report.md` plus a `scatter_bwar.png` scatterplot (bWAR on x, WAA on y, with a best-fit line when there are ≥2 points). `CompareCalculations.py` must never silently regenerate the values file; a missing or malformed values file is an error.

### Logging
All three scripts always emit simple progress logging; `--log-level debug` enables detailed logging (per-start decisions, cache hits/misses, bucket counts, interpolation choices, unmatched WAR comparisons). Use the `logging` module, not bare `print`, for anything that respects the log level.

## Data Acquisition

Uses the `statsapi` (MLB-StatsAPI) Python package. **The efficient path is per-pitcher game logs, not per-game boxscores** — this was measured, not assumed:

```python
# 1. One call -> every pitcher in the league for a season (855 pitchers, 370 with GS > 0)
mlb.get("stats", {"stats": "season", "group": "pitching", "season": 2024,
                  "gameType": "R", "sportId": 1, "playerPool": "All", "limit": 1000})

# 2. One call per starter -> every one of their starts
mlb.get("people", {"personIds": pid,
                   "hydrate": "stats(group=[pitching],type=[gameLog],season=2024,gameType=R)"})
```

~370 calls covers all ~4,858 starts in a season and runs in **under a minute uncached**. The naive `mlb.boxscore_data(game_id)` route needs 2,430 calls and still requires a separate join to get the team result — avoid it.

A league-wide `stats=gameLog` query returns an empty `stats` list. It does not work; do not retry it.

### Fields on each game-log split

Each split in `people[0]["stats"][0]["splits"]` carries everything a bucket needs:

- `stat.gamesStarted == 1` — **this is how you identify a start.** Relief appearances are `0`.
- `stat.inningsPitched` — string like `"5.2"`, meaning 5 innings + 2 outs. Parse as `3 * full + part` to get outs. **Never parse as a float** — `5.2` is not 5.2 innings.
- `stat.earnedRuns` — bucket's ER axis.
- `stat.wins` / `stat.losses` — the pitcher's decision for that game (`1`/`0`).
- `isWin` — whether the pitcher's **team** won. This is what separates `ND_team_won` from `ND_team_lost`, and it removes any need to join against the schedule.
- `game.gamePk`, `date`, `team`, `opponent` — for dedup, filtering, and verbose logging.

Decision classification is exact and needs no name matching:

```
wins == 1   -> W
losses == 1 -> L
isWin       -> ND_team_won
otherwise   -> ND_team_lost
```

### Caching
Cache raw API responses to disk (keyed by season and pitcher ID) so re-runs and multi-year spreads don't re-fetch. Follow the `StaticData.GetFile()` pattern from `~/code/baseball/main`: check for the cached file, fetch and write it if absent, then read from disk. Cache the *raw* JSON, not the parsed buckets — bucket definitions and `alpha` will change during tuning, and the expensive part is the network, not the arithmetic.

`alpha` must **not** be part of the cache key for raw data. It is applied at matrix-build time.

## Sparse Buckets and Interpolation

The tails are thin and are exactly where the model is most fragile. Two distinct problems:

1. **Empty / low-count cells** — no starts ever landed there, or too few to trust.
2. **Outlier performances that still didn't lose** — e.g. a 9 IP / 0 ER start where the sample is small and all-wins, producing a degenerate `WP = 1.0`.

The chosen approach is **shrinkage then 2D isotonic regression** (decision 4 above):

- **Shrink** each cell toward a prior in proportion to its sample size, so low-`n` cells are pulled away from degenerate `0.000`/`1.000` values and high-`n` cells stay essentially as observed.
- **Isotonic fit** across both axes to enforce monotonicity: win probability must not decrease as outs rise at fixed ER, and must not increase as ER rises at fixed outs. Raw empirical cells *will* violate this in the tails.

Cells with zero observations are filled by the monotonic fit rather than by a separate interpolation rule. Record `n` and an `interpolated` flag per cell in the JSON, mark interpolated cells in the text heatmap (e.g. a trailing `*`), and log every interpolated cell under `--log-level debug`. Keeping the observed counts visible alongside the smoothed probabilities is required, not optional — it is the only way to tell a trustworthy cell from a reconstructed one.

## Environment

Python 3.11. The sibling project `~/code/baseball/main` has a working `.venv` with `statsapi` (mlb-statsapi 1.9.0), `pandas`, `numpy`, and `requests` — this project needs its own venv with at least `statsapi`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install MLB-StatsAPI numpy pybaseball matplotlib
```

`pybaseball` and `matplotlib` back `CompareCalculations.py` — `pybaseball.bwar_pitch()` for Baseball-Reference's bulk WAR data file, `matplotlib` for the scatterplot PNGs.

`saved-logs/` holds full run logs saved off for debugging (e.g. `> saved-logs/run_<timestamp>.log`), separate from the raw API cache (`src/Cache/`) and the matrix outputs (`output/`). Not read by any script — purely a human/debugging artifact.

## Code Style

Inherited from `~/code/baseball/main` (see its `CLAUDE.md` for the full set). The conventions that matter most here:

- **Alignment.** Align `=` across multi-line keyword arguments and `:` across dataclass fields, padding with spaces so values line up. This is pervasive in the sibling project and is expected here.
- `import dataclasses` then `@dataclasses.dataclass` — never `from dataclasses import dataclass`.
- Every module gets an `if __name__ == "__main__":` block, which doubles as its test — plain `assert`s, no pytest dependency. Run `./run_self_checks.sh` to execute the fast/offline ones after making changes; `PitchingAPI.py`, `LookupAPI.py`, and `WarAPI.py` are excluded from that script because their self-checks make live network calls, and are run individually instead.
- API-wrapper classes use an `XxxAPI` suffix with `@staticmethod` methods only — no `__init__`, no instance state.
- Optional dataclass fields (`= None`) come last.
- `### https://...` comments above API classes linking the relevant MLB endpoint.
- Casing is per-file and consistent within a file; PascalCase function names are normal in this codebase (`GetFile`, `GetActiveGames`).

## Git Workflow

`master` has GitHub branch protection requiring every change to land through
a pull request, enforced even for the repo admin — a direct push to `master`
will be rejected. For any non-trivial change:

1. Create a branch (`feat/<short-description>` or `fix/<short-description>`).
2. Commit there, following this file's commit-message conventions.
3. Push the branch and open a PR with `gh pr create` (summary + test plan).
4. Report the PR URL back and stop. **Never merge or approve a PR yourself**
   — the project owner reviews the diff and merges it themselves.

Because `master` requires a PR either way, there's no "small enough to skip
this" exception — even a one-line fix needs a branch + PR to land.

## Data Gotchas

- Total starts in 2024 came to 4,858, not the expected 4,860 (2,430 games × 2). Small discrepancies are normal — don't treat a count mismatch as a bug without investigating the specific games.
- Filter `gameType="R"` for regular season. Spring training and postseason will otherwise contaminate the matrix.
- Openers (a 1-inning "start") are legitimate `gamesStarted == 1` rows and will pile up in the low-IP buckets. They are real starts by the data's definition but represent a different tactical intent than a short outing by a failed starter. `--min-start-outs` (default `3`, i.e. under 1.0 IP) is the tunable cutoff — the default keeps true 1-inning openers in the matrix and only drops sub-inning outings.
- Doubleheaders produce two splits for the same pitcher on the same date; they are distinct games (`game.gamePk` differs) and both count.
- Today is in the 2026 season, so "most recent complete season" currently resolves to **2025**.

## Open Questions

Not yet decided by the project owner. Ask before hardcoding an answer.

- **fWAR (FanGraphs) support in `CompareCalculations.py`.** FanGraphs' leaderboard endpoint (`pitching_stats`, which `pybaseball` hits) sits behind an active Cloudflare bot challenge — a plain `requests` call gets a 403 "Just a moment..." JS-challenge page, not just a parsing failure. Bypassing that would mean building browser-automation-style evasion of a site's active anti-bot measures, which wasn't done here. Revisit only if `pybaseball` ships a working fix, FanGraphs exposes another legitimate access path, or the project owner wants a manual-CSV-import flow instead (`--fwar-csv <path>`, parsed locally from a leaderboard export the user makes through their own browser session).

## Resolved Questions

Decided explicitly by the project owner when `CalculateMatrix.py` was implemented. Do not silently change them.

- **Multi-year matrices** (`2020-2025`) **pool**, not average: every start from every year in the spread is pooled into one matrix before bucketing/baseline/smoothing, so a season with more starts (or a short season like 2020) is weighted by its actual start count rather than counted equally. See `CalculateMatrix.main()`'s `all_starts` accumulation.
- **Axis caps:** outs capped at `_OUTS_CAP = 27`, earned runs capped at `_ER_CAP = 9` (both in `CalculateMatrix.py`). A start beyond either cap clamps into the last row/column (`27+` outs, `9+` ER) rather than getting its own sparse cell.
- **Openers:** included by default, not excluded or specially flagged. `--min-start-outs` (default `3`, i.e. under 1.0 IP) is the tunable cutoff a caller can raise or lower; it is not a hardcoded opener-detection rule.

Decided explicitly by the project owner when `CalculateValue.py` was implemented. Do not silently change them.

- **`CalculateValue.py` output shape:** per-pitcher totals only (no per-start rows), written as JSON (source of truth, `src/ValueIO.py`) + a rendered text table — the same JSON+text convention as the matrix, but under a separate `values/` directory, not mixed into `output/`.
- **Filter semantics:** `--team` matches a pitcher's team as of each individual start (splits a mid-season trade correctly across both teams), not their season-end team. `--pitcher` and `--team` both accept either an MLBAM numeric id or a fuzzy name/abbreviation match, resolved via `statsapi.lookup_player`/`lookup_team` (`src/LookupAPI.py`); an ambiguous name raises an error listing every candidate.
- **Qualification threshold:** the default "all qualified starters" pool requires `gamesStarted / gamesPlayed >= --min-start-ratio` (default `0.5`), so a reliever who picked up a spot start doesn't get scored as a starter. This ratio filter only applies to that default pool — an explicit `--pitcher` is always evaluated regardless of role, and `--team` only filters starts *after* the pool is built. `--min-start-ratio 0` restores the old "any start counts" behavior. Once in the pool (or named via `--pitcher`), there is still no minimum start *count* — a pitcher with one start (that clears the ratio) is reported like any other.

Decided explicitly by the project owner when `CompareCalculations.py` was implemented. Do not silently change them.

- **Data source:** `pybaseball`, not a hand-rolled scraper — `bwar_pitch()` for Baseball-Reference's bulk WAR file (one fetch, covers every season/pitcher, joined directly on its own `mlb_ID` column) and, if fWAR support returns, `playerid_reverse_lookup`/`pitching_stats` for FanGraphs. Avoids owning HTML parsing against sites we don't control.
- **Pooled (non-`--by-season`) values reports:** compared against each pitcher's bWAR *summed across every season in the report's `eval_years`*, so a career-span WAA lines up with a career-span WAR sum.
- **Few-point reports never error:** every point is always plotted; the best-fit line and correlation stats are skipped only when there are `< 2` points (this covers the single-pitcher case naturally — a `--pitcher --by-season` report with several seasons still gets a real fit).
- **Report depth:** for each WAR version compared — n, Pearson r, R², best-fit slope/intercept, and a table of the largest-residual pitchers, not just the scatterplot image.
