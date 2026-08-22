import dataclasses
import json
import os
import re

from Models.Value import PitcherValue, ValueReport

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "values")


def _Slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", name)


def OutputFileStem(
    eval_years:      list[int],
    matrix_path:     str,
    pitcher_filter:  int | None,
    team_filter:     str | None,
    by_season:       bool = False,
    min_start_ratio: float = 0.5,
) -> str:
    eval_spread = str(eval_years[0]) if len(eval_years) == 1 else f"{eval_years[0]}-{eval_years[-1]}"
    matrix_stem = os.path.splitext(os.path.basename(matrix_path))[0]
    stem = f"value_{eval_spread}_{matrix_stem}"
    if pitcher_filter is not None:
        stem += f"_pitcher{pitcher_filter}"
    if team_filter is not None:
        stem += f"_team{_Slug(team_filter)}"
    if by_season:
        stem += "_byseason"
    if pitcher_filter is None and min_start_ratio != 0.5:
        stem += f"_ratio{min_start_ratio:.2f}"
    return stem


def WriteJSON(report: ValueReport, path: str) -> None:
    with open(path, "w") as f:
        json.dump(dataclasses.asdict(report), f, indent=2)


def ReadJSON(path: str) -> ValueReport:
    """Reads a values JSON written by WriteJSON. Raises if the file is missing or malformed --
    CompareCalculations.py must never silently regenerate values."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Values file not found: {path}")
    with open(path, "r") as f:
        raw = json.load(f)
    pitchers = [PitcherValue(**p) for p in raw.pop("pitchers")]
    return ValueReport(pitchers=pitchers, **raw)


def WriteText(report: ValueReport, path: str) -> None:
    years_spread = f"{report.eval_years[0]}-{report.eval_years[-1]}"

    filters = []
    if report.pitcher_filter is not None:
        filters.append(f"pitcher={report.pitcher_filter}")
    if report.team_filter is not None:
        filters.append(f"team={report.team_filter}")
    filter_str = (" " + " ".join(filters)) if filters else ""

    lines = [
        f"Values eval_years={years_spread} matrix={os.path.basename(report.matrix_path)} "
        f"baseline={report.baseline:.3f} pitchers={len(report.pitchers)} "
        f"min_start_ratio={report.min_start_ratio:.2f}{filter_str}"
        + (" by_season=true" if report.by_season else "")
    ]

    rows = sorted(report.pitchers, key=lambda p: p.waa, reverse=True)

    if report.by_season:
        lines.append(f"{'Pitcher':<24}{'ID':>8}  {'Season':>6}  {'Starts':>6}  {'SumWP':>7}  {'AvgWP':>6}  {'WAA':>7}")
    else:
        lines.append(f"{'Pitcher':<24}{'ID':>8}  {'Starts':>6}  {'SumWP':>7}  {'AvgWP':>6}  {'WAA':>7}")

    for pv in rows:
        if report.by_season:
            lines.append(
                f"{pv.pitcher_name:<24}{pv.pitcher_id:>8}  {pv.season:>6}  {pv.starts:>6}  "
                f"{pv.sum_wp:>7.3f}  {pv.avg_wp:>6.3f}  {pv.waa:>+7.3f}"
            )
        else:
            lines.append(
                f"{pv.pitcher_name:<24}{pv.pitcher_id:>8}  {pv.starts:>6}  "
                f"{pv.sum_wp:>7.3f}  {pv.avg_wp:>6.3f}  {pv.waa:>+7.3f}"
            )

    with open(path, "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    print(f"OUTPUT_DIR = {os.path.abspath(OUTPUT_DIR)}")

    stem = OutputFileStem([2024], "output/matrix_2024_a0.10.json", None, None)
    assert stem == "value_2024_matrix_2024_a0.10", stem

    stem = OutputFileStem([2020, 2021, 2022], "output/matrix_2024_a0.10.json", 543037, None)
    assert stem == "value_2020-2022_matrix_2024_a0.10_pitcher543037", stem

    stem = OutputFileStem([2024], "output/matrix_2024_a0.10.json", None, "New York Yankees")
    assert stem == "value_2024_matrix_2024_a0.10_teamNewYorkYankees", stem

    stem = OutputFileStem([2020, 2021], "output/matrix_2024_a0.10.json", None, None, by_season=True)
    assert stem == "value_2020-2021_matrix_2024_a0.10_byseason", stem

    stem = OutputFileStem([2024], "output/matrix_2024_a0.10.json", None, None, min_start_ratio=0.5)
    assert stem == "value_2024_matrix_2024_a0.10", stem  # default ratio is not encoded in the stem

    stem = OutputFileStem([2024], "output/matrix_2024_a0.10.json", None, None, min_start_ratio=0.3)
    assert stem == "value_2024_matrix_2024_a0.10_ratio0.30", stem

    stem = OutputFileStem([2024], "output/matrix_2024_a0.10.json", 543037, None, min_start_ratio=0.3)
    assert stem == "value_2024_matrix_2024_a0.10_pitcher543037", stem  # ratio irrelevant once a pitcher is named explicitly

    report = ValueReport(
        eval_years   = [2024],
        matrix_path  = "output/matrix_2024_a0.10.json",
        matrix_years = [2024],
        matrix_alpha = 0.1,
        baseline     = 0.488,
        pitchers     = [
            PitcherValue(pitcher_id=543037, pitcher_name="Gerrit Cole", starts=32, sum_wp=19.442, avg_wp=0.608, waa=3.316),
            PitcherValue(pitcher_id=1,      pitcher_name="Nobody",      starts=5,  sum_wp=1.5,    avg_wp=0.3,   waa=-1.14),
        ],
    )
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        json_path = os.path.join(tmp, "report.json")
        text_path = os.path.join(tmp, "report.txt")
        WriteJSON(report, json_path)
        WriteText(report, text_path)
        with open(json_path) as f:
            assert json.load(f)["pitchers"][0]["pitcher_id"] == 543037
        with open(text_path) as f:
            text = f.read()
        assert "Gerrit Cole" in text
        assert text.index("Gerrit Cole") < text.index("Nobody")  # sorted by waa desc
        assert "min_start_ratio=0.50" in text

        round_tripped = ReadJSON(json_path)
        assert round_tripped == report

    try:
        ReadJSON("/nonexistent/values.json")
        raise AssertionError("expected FileNotFoundError for a missing values file")
    except FileNotFoundError:
        pass

    by_season_report = ValueReport(
        eval_years   = [2020, 2021],
        matrix_path  = "output/matrix_2024_a0.10.json",
        matrix_years = [2024],
        matrix_alpha = 0.1,
        baseline     = 0.488,
        by_season    = True,
        pitchers     = [
            PitcherValue(pitcher_id=543037, pitcher_name="Gerrit Cole", starts=12, sum_wp=6.0, avg_wp=0.5, waa=0.3, season=2021),
            PitcherValue(pitcher_id=543037, pitcher_name="Gerrit Cole", starts=10, sum_wp=5.0, avg_wp=0.5, waa=0.2, season=2020),
        ],
    )
    with tempfile.TemporaryDirectory() as tmp:
        json_path = os.path.join(tmp, "report.json")
        text_path = os.path.join(tmp, "report.txt")
        WriteJSON(by_season_report, json_path)
        WriteText(by_season_report, text_path)
        with open(text_path) as f:
            text = f.read()
        assert "Season" in text
        # always sorted by waa desc, even when by_season -- 2021 (waa=0.3) precedes 2020 (waa=0.2)
        rows_text = text.split("\n", 2)[2]  # skip the two header lines
        assert rows_text.index("2021") < rows_text.index("2020")

    print("ValueIO self-checks passed.")
