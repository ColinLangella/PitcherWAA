import logging
import os

import ReportIO
import ValueIO
from Models.Comparison import ComparisonPoint, ComparisonResult
from Models.Value import ValueReport
from WarAPI import BaseballReferenceWarAPI

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")


def _BuildPoints(value_report: ValueReport, by_mlbam: dict[int, dict[int, float]]) -> tuple[list[ComparisonPoint], int]:
    """Joins each PitcherValue row to a bWAR figure. by_season reports join on the exact
    (pitcher, season) pair; pooled reports sum bWAR across every eval_years season the
    pitcher has a record for (missing individual seasons within the span contribute
    nothing, matching a career-span total). Compares against pv.war instead of pv.waa
    when the source values report was built with --metric war, so a WAR-mode report is
    checked against bWAR on its own terms rather than silently falling back to WAA."""
    is_war = value_report.metric == "war"
    points:   list[ComparisonPoint] = []
    excluded = 0

    for pv in value_report.pitchers:
        bwar_by_season = by_mlbam.get(pv.pitcher_id)

        if value_report.by_season:
            bwar = bwar_by_season.get(pv.season) if bwar_by_season else None
            if bwar is None:
                logging.debug(f"No bWAR match for pitcher_id={pv.pitcher_id} season={pv.season}")
                excluded += 1
                continue
        else:
            matching_years = [y for y in value_report.eval_years if bwar_by_season and y in bwar_by_season]
            if not matching_years:
                logging.debug(f"No bWAR match for pitcher_id={pv.pitcher_id} eval_years={value_report.eval_years}")
                excluded += 1
                continue
            bwar = sum(bwar_by_season[y] for y in matching_years)

        points.append(ComparisonPoint(
            pitcher_id      = pv.pitcher_id,
            pitcher_name    = pv.pitcher_name,
            our_value       = pv.war if is_war else pv.waa,
            reference_value = bwar,
            season          = pv.season,
        ))

    return points, excluded


def _FitStats(points: list[ComparisonPoint]) -> tuple[float | None, float | None, float | None, float | None]:
    """Pearson r, R-squared, and best-fit slope/intercept. None for all four when there
    are fewer than 2 points, or when either axis has zero variance -- no fit is meaningful."""
    if len(points) < 2:
        return None, None, None, None

    import numpy as np
    xs = np.array([p.reference_value for p in points])
    ys = np.array([p.our_value for p in points])
    if np.std(xs) == 0 or np.std(ys) == 0:
        return None, None, None, None

    r               = float(np.corrcoef(xs, ys)[0, 1])
    slope, intercept = (float(v) for v in np.polyfit(xs, ys, 1))
    return r, r * r, slope, intercept


def main(values_path: str, log_level: str) -> None:
    logging.basicConfig(
        level  = getattr(logging, log_level),
        format = "%(asctime)s [%(levelname)s] %(message)s",
    )

    logging.info(f"Loading values report from {values_path}")
    value_report = ValueIO.ReadJSON(values_path)
    logging.info(
        f"Loaded {len(value_report.pitchers)} pitcher row(s), metric={value_report.metric}, "
        f"by_season={value_report.by_season}, eval_years={value_report.eval_years}"
    )

    logging.info("Fetching bWAR data (Baseball-Reference, via pybaseball)")
    by_mlbam = BaseballReferenceWarAPI.GetAllWar()

    points, excluded = _BuildPoints(value_report, by_mlbam)
    r, r_squared, slope, intercept = _FitStats(points)
    result = ComparisonResult(
        war_source = "bWAR",
        our_metric = value_report.metric,
        points     = points,
        excluded   = excluded,
        r          = r,
        r_squared  = r_squared,
        slope      = slope,
        intercept  = intercept,
    )
    logging.info(
        f"Matched {len(points)} pitcher(s) to bWAR ({excluded} excluded, no match), "
        f"comparing bWAR against this project's {value_report.metric.upper()}"
    )

    stem       = os.path.splitext(os.path.basename(values_path))[0]
    report_dir = os.path.join(REPORTS_DIR, stem)
    os.makedirs(report_dir, exist_ok=True)

    image_name = "scatter_bwar.png"
    ReportIO.PlotScatter(result, os.path.join(report_dir, image_name))
    ReportIO.WriteMarkdown(
        value_report, [result], {"bWAR": image_name}, values_path, os.path.join(report_dir, "report.md")
    )
    logging.info(f"Wrote report to {report_dir}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Compare WAA or WAR values (whichever the values file was built with) against "
                     "Baseball-Reference's bWAR."
    )
    parser.add_argument("values_file", help="Path to a values JSON file produced by CalculateValue.py")
    parser.add_argument(
        "--log-level", type=str.upper, choices=["ERROR", "INFO", "DEBUG"], default="INFO",
        help=(
            "Logging verbosity (default INFO). DEBUG: every unmatched pitcher/season, plus "
            "everything INFO logs. INFO: major state transitions and incremental progress. "
            "ERROR: errors only."
        ),
    )
    args = parser.parse_args()

    main(args.values_file, args.log_level)
