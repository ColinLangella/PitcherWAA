import os

from Models.Comparison import ComparisonResult
from Models.Value import ValueReport

_BLUE      = "#2a78d6"
_GRAY      = "#52514e"
_GRIDLINE  = "#e1e0d9"
_BASELINE  = "#c3c2b7"
_INK       = "#0b0b0b"
_SURFACE   = "#fcfcfb"

_OUTLIER_ROWS  = 10
_EXTREME_ROWS  = 5


def PlotScatter(result: ComparisonResult, path: str) -> None:
    """Scatter of WAR (x) vs WAA (y) for one WAR source, with a best-fit line when the
    result has one (>=2 points). Styled per the project's dataviz palette: a single blue
    series for observed pitchers, a muted dashed line for the fit -- not a second hue,
    since it's a derived quantity rather than another category."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    xs = [p.war for p in result.points]
    ys = [p.waa for p in result.points]

    fig, ax = plt.subplots(figsize=(7, 5.5), facecolor=_SURFACE)
    ax.set_facecolor(_SURFACE)

    ax.scatter(xs, ys, s=42, color=_BLUE, alpha=0.75, edgecolors="none", label="Pitcher-seasons" if result.slope is not None else None)

    if result.slope is not None:
        x_line = np.array([min(xs), max(xs)])
        y_line = result.slope * x_line + result.intercept
        ax.plot(x_line, y_line, color=_GRAY, linewidth=2, linestyle="--", label="Best fit")
        ax.legend(frameon=False, labelcolor=_GRAY, fontsize=9, loc="best")

    ax.set_xlabel(result.war_source, color=_GRAY, fontsize=11)
    ax.set_ylabel("WAA", color=_GRAY, fontsize=11)
    title = f"WAA vs {result.war_source} (n={len(result.points)})"
    if result.r_squared is not None:
        title += f", R²={result.r_squared:.3f}"
    ax.set_title(title, color=_INK, fontsize=13, pad=12)

    ax.grid(True, color=_GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(_BASELINE)
    ax.tick_params(colors=_GRAY, labelsize=9)

    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=_SURFACE)
    plt.close(fig)


def _ExtremeTableLines(points, metric_label: str, metric_fn, war_source: str) -> list[str]:
    """Top/bottom _EXTREME_ROWS points by metric_fn (either WAA or the WAR source), each as
    its own small table -- lets a reader see each metric's own extremes, not just where the
    two metrics disagree most (that's the separate largest-residual table)."""
    lines = [f"### Top/bottom {_EXTREME_ROWS} by {metric_label}", ""]

    ranked = sorted(points, key=metric_fn, reverse=True)
    top    = ranked[:_EXTREME_ROWS]
    bottom = list(reversed(ranked[-_EXTREME_ROWS:]))

    for heading, rows in (("Top", top), ("Bottom", bottom)):
        lines.append(f"**{heading} {len(rows)}:**")
        lines.append("")
        lines.append(f"| Pitcher | Season | WAA | {war_source} |")
        lines.append("|---|---|---|---|")
        for p in rows:
            season_str = str(p.season) if p.season is not None else "-"
            lines.append(f"| {p.pitcher_name} | {season_str} | {p.waa:+.3f} | {p.war:+.2f} |")
        lines.append("")

    return lines


def _ScopeLabel(value_report: ValueReport) -> str:
    """A human-readable description of which pitchers this report covers, so a reader
    doesn't have to infer it from a raw id/name in a bullet list."""
    if value_report.pitcher_filter is not None:
        name = next(
            (p.pitcher_name for p in value_report.pitchers if p.pitcher_id == value_report.pitcher_filter),
            None,
        )
        return f"{name} (MLBAM id {value_report.pitcher_filter})" if name else f"pitcher MLBAM id {value_report.pitcher_filter}"
    if value_report.team_filter is not None:
        return value_report.team_filter
    return "All qualified starters"


def WriteMarkdown(
    value_report: ValueReport,
    results:      list[ComparisonResult],
    image_names:  dict[str, str],
    values_path:  str,
    path:         str,
) -> None:
    years = value_report.eval_years
    years_label = str(years[0]) if len(years) == 1 else f"{years[0]}–{years[-1]}"
    granularity = "one row per pitcher-season" if value_report.by_season else "pooled across the full span"
    scope_label = _ScopeLabel(value_report)

    lines = [
        f"# WAA vs. Accepted WAR: {scope_label}, {years_label}",
        "",
        f"- **Scope:** {scope_label}",
        f"- **Years evaluated:** {years_label} ({granularity})",
        f"- Source values file: `{os.path.basename(values_path)}`",
        f"- Matrix: `{os.path.basename(value_report.matrix_path)}` "
        f"(years={value_report.matrix_years[0]}-{value_report.matrix_years[-1]}, "
        f"alpha={value_report.matrix_alpha:.2f}, baseline={value_report.baseline:.3f})",
    ]

    for result in results:
        lines.append("")
        lines.append(f"## WAA vs {result.war_source}")
        lines.append("")
        lines.append(f"![WAA vs {result.war_source}]({image_names[result.war_source]})")
        lines.append("")
        lines.append(f"- n = {len(result.points)} (excluded {result.excluded}: no {result.war_source} match)")
        if result.r is None:
            lines.append("- Fewer than 2 points -- no correlation/fit computed.")
        else:
            lines.append(f"- Pearson r = {result.r:.3f}, R² = {result.r_squared:.3f}")
            intercept_sign = "-" if result.intercept < 0 else "+"
            lines.append(
                f"- Best fit: WAA = {result.slope:.3f} × {result.war_source} {intercept_sign} {abs(result.intercept):.3f}"
            )

        if result.points:
            lines.append("")
            lines.extend(_ExtremeTableLines(result.points, "WAA", lambda p: p.waa, result.war_source))
            lines.extend(_ExtremeTableLines(result.points, result.war_source, lambda p: p.war, result.war_source))

        if result.r is not None:
            lines.append("### Largest disagreements (by fit residual)")
            lines.append("")
            lines.append(f"| Pitcher | Season | WAA | {result.war_source} | Residual |")
            lines.append("|---|---|---|---|---|")

            def _residual(p):
                return p.waa - (result.slope * p.war + result.intercept)

            top = sorted(result.points, key=lambda p: abs(_residual(p)), reverse=True)[:_OUTLIER_ROWS]
            for p in top:
                season_str = str(p.season) if p.season is not None else "-"
                lines.append(f"| {p.pitcher_name} | {season_str} | {p.waa:+.3f} | {p.war:+.2f} | {_residual(p):+.3f} |")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    from Models.Comparison import ComparisonPoint

    result = ComparisonResult(
        war_source = "bWAR",
        points     = [
            ComparisonPoint(pitcher_id=543037, pitcher_name="Gerrit Cole", waa=3.316, war=7.39, season=2023),
            ComparisonPoint(pitcher_id=519242, pitcher_name="Chris Sale",  waa=4.383, war=6.10, season=2024),
            ComparisonPoint(pitcher_id=1,      pitcher_name="Nobody",      waa=-1.14, war=-0.5, season=2022),
        ],
        excluded  = 1,
        r         = 0.9,
        r_squared = 0.81,
        slope     = 0.6,
        intercept = 0.1,
    )

    report = ValueReport(
        eval_years   = [2022, 2023, 2024],
        matrix_path  = "output/matrix_2024_a0.10.json",
        matrix_years = [2024],
        matrix_alpha = 0.1,
        baseline     = 0.488,
        by_season    = True,
        pitchers     = [],
    )

    import dataclasses
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "scatter_bwar.png")
        md_path  = os.path.join(tmp, "report.md")
        PlotScatter(result, img_path)
        assert os.path.isfile(img_path) and os.path.getsize(img_path) > 0
        WriteMarkdown(report, [result], {"bWAR": "scatter_bwar.png"}, "values/value_2022-2024.json", md_path)
        with open(md_path) as f:
            text = f.read()
        assert "Gerrit Cole" in text
        assert "scatter_bwar.png" in text
        assert "R² = 0.810" in text
        assert "Top/bottom 5 by WAA" in text
        assert "Top/bottom 5 by bWAR" in text
        # only 3 points exist, so "bottom 5" degrades gracefully to all 3, not a crash
        assert text.count("Gerrit Cole") >= 2
        assert "All qualified starters" in text        # no --pitcher/--team filter on this report
        assert "value_2022-2024.json" in text          # source values file, not the matrix's name
        assert "2022–2024" in text                     # years shown as a real span, not raw booleans

    single = ComparisonResult(war_source="bWAR", points=[result.points[0]], excluded=0)
    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "scatter_bwar.png")
        md_path  = os.path.join(tmp, "report.md")
        PlotScatter(single, img_path)  # must not crash with no fit line
        assert os.path.isfile(img_path)
        WriteMarkdown(report, [single], {"bWAR": "scatter_bwar.png"}, "values/value_2022-2024.json", md_path)
        with open(md_path) as f:
            text = f.read()
        assert "Fewer than 2 points" in text
        assert "Top/bottom 5 by WAA" in text  # extremes tables don't need a fit

    # a --pitcher-filtered report's own `pitchers` list carries the resolved name; simulate that here
    from Models.Value import PitcherValue
    pitcher_report = dataclasses.replace(
        report,
        pitcher_filter = 543037,
        pitchers       = [PitcherValue(pitcher_id=543037, pitcher_name="Gerrit Cole", starts=32, sum_wp=19.4, avg_wp=0.6, waa=3.3)],
    )
    with tempfile.TemporaryDirectory() as tmp:
        md_path = os.path.join(tmp, "report.md")
        WriteMarkdown(pitcher_report, [result], {"bWAR": "scatter_bwar.png"}, "values/value_pitcher543037.json", md_path)
        with open(md_path) as f:
            text = f.read()
        assert "Gerrit Cole (MLBAM id 543037)" in text

    team_report = dataclasses.replace(report, team_filter="New York Yankees")
    with tempfile.TemporaryDirectory() as tmp:
        md_path = os.path.join(tmp, "report.md")
        WriteMarkdown(team_report, [result], {"bWAR": "scatter_bwar.png"}, "values/value_teamNYY.json", md_path)
        with open(md_path) as f:
            text = f.read()
        assert "New York Yankees" in text

    print("ReportIO self-checks passed.")
