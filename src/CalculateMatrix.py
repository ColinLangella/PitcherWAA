import logging
import os

import MatrixIO
from MatrixBuilder import BucketStarts, BuildRawCells, ComputeBaseline
from Models.Matrix import Matrix
from Models.Start import Start
from PitchingAPI import PitcherGameLogAPI, SeasonPitchingAPI
from Smoothing import ApplyShrinkageAndIsotonic
from Utils.YearSpread import ParseYearSpread

_OUTS_CAP = 27
_ER_CAP   = 9


def _DefaultSeason() -> int:
    from datetime import datetime
    now = datetime.now()
    return now.year - 1 if now.month <= 10 else now.year


def _FetchSeasonStarts(season: int, min_start_outs: int, max_threads: int) -> tuple[list[Start], int]:
    """Fetches every pitcher's starts for `season` concurrently (statsapi.get() is stateless per
    call, and each pitcher writes to its own uniquely-keyed cache file, so no locking is needed).
    All aggregation happens back on the calling thread once futures resolve, so `season_starts`/
    `season_excluded` are never touched from more than one thread at a time."""
    import concurrent.futures

    # min_start_ratio=0: the matrix buckets every start in the league regardless of who threw it,
    # so a reliever's one spot start belongs in the matrix same as any starter's -- the starter-role
    # ratio filter is a CalculateValue.py pitcher-pool concept, not a matrix-input concept.
    pitcher_ids = SeasonPitchingAPI.GetQualifiedStarters(season, min_start_ratio=0)
    logging.info(f"season={season}: fetching game logs for {len(pitcher_ids)} pitchers (max_threads={max_threads})")

    season_starts:   list[Start] = []
    season_excluded = 0
    completed        = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {
            executor.submit(PitcherGameLogAPI.GetStarts, pid, season, min_start_outs): pid
            for pid in pitcher_ids
        }
        for future in concurrent.futures.as_completed(futures):
            pid = futures[future]
            try:
                starts, excluded = future.result()
            except Exception:
                logging.error(f"Failed to fetch game log for pitcher_id={pid} season={season}")
                raise
            season_starts.extend(starts)
            season_excluded  += excluded
            completed         += 1
            if completed % 50 == 0:
                logging.info(f"season={season}: {completed}/{len(pitcher_ids)} pitchers processed")

    logging.info(f"season={season}: finished fetching, {len(season_starts)} starts, {season_excluded} excluded")
    return season_starts, season_excluded


def main(year_spread: str | None, alpha: float, min_start_outs: int, max_threads: int, log_level: str) -> None:
    logging.basicConfig(
        level  = getattr(logging, log_level),
        format = "%(asctime)s [%(levelname)s] %(message)s",
    )

    years = ParseYearSpread(year_spread) if year_spread else [_DefaultSeason()]
    logging.info(f"Building matrix for years={years} alpha={alpha} min_start_outs={min_start_outs} max_threads={max_threads}")

    all_starts: list[Start] = []
    excluded_openers = 0

    for season in years:
        logging.info(f"Entering fetch phase for season={season}")
        season_starts, season_excluded = _FetchSeasonStarts(season, min_start_outs, max_threads)
        all_starts.extend(season_starts)
        excluded_openers += season_excluded

    logging.info(f"Pooled {len(all_starts)} starts ({excluded_openers} excluded) across {years}")

    baseline = ComputeBaseline(all_starts, alpha)
    logging.info(f"Baseline WP = {baseline:.4f}")

    buckets = BucketStarts(all_starts, outs_cap=_OUTS_CAP, er_cap=_ER_CAP)
    cells   = BuildRawCells(buckets, outs_cap=_OUTS_CAP, er_cap=_ER_CAP, alpha=alpha)
    cells   = ApplyShrinkageAndIsotonic(cells, baseline=baseline, outs_cap=_OUTS_CAP, er_cap=_ER_CAP)

    for cell in cells:
        if cell.interpolated:
            logging.debug(f"Interpolated cell outs={cell.outs} er={cell.earned_runs} -> {cell.smoothed_wp:.4f}")

    matrix = Matrix(
        years            = years,
        alpha            = alpha,
        baseline         = baseline,
        outs_cap         = _OUTS_CAP,
        er_cap           = _ER_CAP,
        cells            = cells,
        total_starts     = len(all_starts),
        min_start_outs   = min_start_outs,
        excluded_openers = excluded_openers,
    )

    stem = MatrixIO.OutputFileStem(years, alpha)
    os.makedirs(MatrixIO.OUTPUT_DIR, exist_ok=True)
    json_path = os.path.join(MatrixIO.OUTPUT_DIR, f"{stem}.json")
    text_path = os.path.join(MatrixIO.OUTPUT_DIR, f"{stem}.txt")
    MatrixIO.WriteJSON(matrix, json_path)
    MatrixIO.WriteText(matrix, text_path)
    logging.info(f"Wrote {json_path} and {text_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build the league-wide start-quality WP matrix.")
    parser.add_argument("year_spread", nargs="?", default=None, help="e.g. 2023 or 2020-2025")
    parser.add_argument("--alpha", type=float, default=0.1)
    parser.add_argument(
        "--min-start-outs", type=int, default=3,
        help="Exclude starts with fewer than this many outs (default 3, i.e. < 1.0 IP). Use 0 to include all starts.",
    )
    parser.add_argument(
        "--max-threads", type=int, default=8,
        help="Max concurrent threads fetching per-pitcher game logs within a season (default 8).",
    )
    parser.add_argument(
        "--log-level", type=str.upper, choices=["ERROR", "INFO", "DEBUG"], default="INFO",
        help=(
            "Logging verbosity (default INFO). DEBUG: every step as it happens (per-start "
            "decisions, cache hits/misses, bucket counts, interpolated cells) plus everything "
            "INFO logs. INFO: major state transitions and incremental progress. ERROR: errors only."
        ),
    )
    args = parser.parse_args()

    if args.max_threads < 1:
        parser.error("--max-threads must be at least 1")

    main(args.year_spread, args.alpha, args.min_start_outs, args.max_threads, args.log_level)
