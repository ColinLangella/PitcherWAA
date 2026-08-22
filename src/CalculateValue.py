import collections
import logging
import os

import MatrixIO
import ValueIO
from LookupAPI import PlayerLookupAPI, TeamLookupAPI
from Models.Start import Start
from Models.Value import PitcherValue, ValueReport
from PitchingAPI import PitcherGameLogAPI, SeasonPitchingAPI
from Utils.YearSpread import ParseYearSpread


def _CurrentSeason() -> int:
    from datetime import datetime
    return datetime.now().year


def _ResolvePlayerAcrossYears(identifier: str, years: list[int]) -> tuple[int, str]:
    """Tries PlayerLookupAPI.Resolve against each evaluated season, most recent first, so a
    pitcher who didn't appear at all in the final --years season (e.g. hurt all year) still
    resolves via an earlier season's roster snapshot. Re-raises the last season's error if
    every season fails."""
    last_error: ValueError | None = None
    for season in reversed(years):
        try:
            return PlayerLookupAPI.Resolve(identifier, season)
        except ValueError as e:
            logging.debug(f"'{identifier}' did not resolve in season={season}: {e}")
            last_error = e
    raise last_error


def _FetchStarts(pitcher_ids: list[int], season: int, min_start_outs: int, max_threads: int) -> list[Start]:
    """Fetches starts for a caller-supplied set of pitcher ids concurrently (same thread-safety
    rationale as CalculateMatrix._FetchSeasonStarts: each pitcher writes to its own uniquely-keyed
    cache file, and all aggregation happens back on the calling thread once futures resolve)."""
    import concurrent.futures

    starts:  list[Start] = []
    excluded = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {
            executor.submit(PitcherGameLogAPI.GetStarts, pid, season, min_start_outs): pid
            for pid in pitcher_ids
        }
        for future in concurrent.futures.as_completed(futures):
            pid = futures[future]
            try:
                pitcher_starts, pitcher_excluded = future.result()
            except Exception:
                logging.error(f"Failed to fetch game log for pitcher_id={pid} season={season}")
                raise
            starts.extend(pitcher_starts)
            excluded += pitcher_excluded

    logging.info(f"season={season}: fetched {len(starts)} starts for {len(pitcher_ids)} pitchers ({excluded} excluded)")
    return starts


def main(
    matrix_path:  str,
    pitcher:      str | None,
    team:         str | None,
    year_spread:  str | None,
    by_season:    bool,
    max_threads:  int,
    log_level:    str,
) -> None:
    logging.basicConfig(
        level  = getattr(logging, log_level),
        format = "%(asctime)s [%(levelname)s] %(message)s",
    )

    years = ParseYearSpread(year_spread) if year_spread else [_CurrentSeason()]
    logging.info(
        f"Evaluating years={years} against matrix={matrix_path} pitcher={pitcher} team={team} "
        f"by_season={by_season}"
    )

    matrix = MatrixIO.ReadJSON(matrix_path)
    logging.info(
        f"Loaded matrix years={matrix.years} alpha={matrix.alpha} baseline={matrix.baseline:.4f} "
        f"min_start_outs={matrix.min_start_outs}"
    )
    by_pos = {(c.outs, c.earned_runs): c for c in matrix.cells}

    pitcher_id, pitcher_name = (
        _ResolvePlayerAcrossYears(pitcher, years) if pitcher else (None, None)
    )
    team_id, team_name = (
        TeamLookupAPI.Resolve(team, years[-1]) if team else (None, None)
    )
    if pitcher_id is not None:
        logging.info(f"Resolved --pitcher '{pitcher}' -> id={pitcher_id} name='{pitcher_name}'")
    if team_id is not None:
        logging.info(f"Resolved --team '{team}' -> id={team_id} name='{team_name}'")

    all_starts: list[Start] = []
    for season in years:
        if pitcher_id is not None:
            pitcher_ids = [pitcher_id]
        else:
            pitcher_ids = SeasonPitchingAPI.GetQualifiedStarters(season)
        logging.info(f"season={season}: evaluating {len(pitcher_ids)} pitcher(s)")
        all_starts.extend(_FetchStarts(pitcher_ids, season, matrix.min_start_outs, max_threads))

    logging.info(f"Pooled {len(all_starts)} starts across {years}")

    if team_name is not None:
        before = len(all_starts)
        all_starts = [s for s in all_starts if s.team == team_name]
        logging.info(f"Filtered to team='{team_name}': {before} -> {len(all_starts)} starts")

    by_pitcher: dict[tuple[int, int | None], list[Start]] = collections.defaultdict(list)
    for s in all_starts:
        by_pitcher[(s.pitcher_id, s.season if by_season else None)].append(s)

    pitchers: list[PitcherValue] = []
    for (pid, season_key), starts in by_pitcher.items():
        sum_wp = 0.0
        waa    = 0.0
        for s in starts:
            cell = by_pos[(min(s.outs, matrix.outs_cap), min(s.earned_runs, matrix.er_cap))]
            wp   = cell.smoothed_wp
            sum_wp += wp
            waa    += wp - matrix.baseline
            logging.debug(
                f"pitcher_id={pid} season={s.season} game={s.game_pk} outs={s.outs} er={s.earned_runs} "
                f"wp={wp:.4f} waa_contribution={wp - matrix.baseline:.4f}"
            )

        name = pitcher_name if pid == pitcher_id else PitcherGameLogAPI.GetName(pid, starts[0].season)
        pitchers.append(PitcherValue(
            pitcher_id   = pid,
            pitcher_name = name,
            starts       = len(starts),
            sum_wp       = sum_wp,
            avg_wp       = sum_wp / len(starts),
            waa          = waa,
            season       = season_key,
        ))

    logging.info(f"Scored {len(pitchers)} pitcher(s)")

    report = ValueReport(
        eval_years     = years,
        matrix_path    = matrix_path,
        matrix_years   = matrix.years,
        matrix_alpha   = matrix.alpha,
        baseline       = matrix.baseline,
        pitchers       = pitchers,
        pitcher_filter = pitcher_id,
        team_filter    = team_name,
        by_season      = by_season,
    )

    stem = ValueIO.OutputFileStem(years, matrix_path, pitcher_id, team_name, by_season)
    os.makedirs(ValueIO.OUTPUT_DIR, exist_ok=True)
    json_path = os.path.join(ValueIO.OUTPUT_DIR, f"{stem}.json")
    text_path = os.path.join(ValueIO.OUTPUT_DIR, f"{stem}.txt")
    ValueIO.WriteJSON(report, json_path)
    ValueIO.WriteText(report, text_path)
    logging.info(f"Wrote {json_path} and {text_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Score pitchers' starts against a prebuilt start-quality WP matrix.")
    parser.add_argument("matrix_file", help="Path to a matrix JSON file produced by CalculateMatrix.py")
    parser.add_argument("--pitcher", default=None, help="MLBAM id or name (fuzzy match); default: all qualified starters")
    parser.add_argument("--team", default=None, help="MLBAM team id, abbreviation, or name; default: no team filter")
    parser.add_argument("--years", default=None, help="e.g. 2024 or 2020-2025 (default: current season)")
    parser.add_argument(
        "--by-season", action="store_true",
        help="Report each pitcher's stats separately per season instead of totaling them across "
             "the full --years span (default: totaled).",
    )
    parser.add_argument(
        "--max-threads", type=int, default=8,
        help="Max concurrent threads fetching per-pitcher game logs within a season (default 8).",
    )
    parser.add_argument(
        "--log-level", type=str.upper, choices=["ERROR", "INFO", "DEBUG"], default="INFO",
        help=(
            "Logging verbosity (default INFO). DEBUG: every start's bucket lookup and WAA "
            "contribution, cache hits/misses, plus everything INFO logs. INFO: major state "
            "transitions and incremental progress. ERROR: errors only."
        ),
    )
    args = parser.parse_args()

    if args.max_threads < 1:
        parser.error("--max-threads must be at least 1")

    main(args.matrix_file, args.pitcher, args.team, args.years, args.by_season, args.max_threads, args.log_level)
