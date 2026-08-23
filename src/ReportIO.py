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
    """Scatter of the WAR source (x) vs this project's own metric (y, WAA or WAR per
    result.our_metric) for one WAR source, with a best-fit line when the result has one
    (>=2 points). Styled per the project's dataviz palette: a single blue series for
    observed pitchers, a muted dashed line for the fit -- not a second hue, since it's a
    derived quantity rather than another category."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    our_metric_label = result.our_metric.upper()

    xs = [p.reference_value for p in result.points]
    ys = [p.our_value for p in result.points]

    fig, ax = plt.subplots(figsize=(7, 5.5), facecolor=_SURFACE)
    ax.set_facecolor(_SURFACE)

    ax.scatter(xs, ys, s=42, color=_BLUE, alpha=0.75, edgecolors="none", label="Pitcher-seasons" if result.slope is not None else None)

    if result.slope is not None:
        x_line = np.array([min(xs), max(xs)])
        y_line = result.slope * x_line + result.intercept
        ax.plot(x_line, y_line, color=_GRAY, linewidth=2, linestyle="--", label="Best fit")
        ax.legend(frameon=False, labelcolor=_GRAY, fontsize=9, loc="best")

    ax.set_xlabel(result.war_source, color=_GRAY, fontsize=11)
    ax.set_ylabel(our_metric_label, color=_GRAY, fontsize=11)
    title = f"{our_metric_label} vs {result.war_source} (n={len(result.points)})"
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


def _ExtremeTableLines(points, heading_label: str, metric_fn, our_metric_label: str, war_source: str) -> list[str]:
    """Top/bottom _EXTREME_ROWS points by metric_fn (either this project's own metric or the
    WAR source), each as its own small table -- lets a reader see each metric's own extremes,
    not just where the two metrics disagree most (that's the separate largest-residual table)."""
    lines = [f"### Top/bottom {_EXTREME_ROWS} by {heading_label}", ""]

    ranked = sorted(points, key=metric_fn, reverse=True)
    top    = ranked[:_EXTREME_ROWS]
    bottom = list(reversed(ranked[-_EXTREME_ROWS:]))

    for heading, rows in (("Top", top), ("Bottom", bottom)):
        lines.append(f"**{heading} {len(rows)}:**")
        lines.append("")
        lines.append(f"| Pitcher | Season | {our_metric_label} | {war_source} |")
        lines.append("|---|---|---|---|")
        for p in rows:
            season_str = str(p.season) if p.season is not None else "-"
            lines.append(f"| {p.pitcher_name} | {season_str} | {p.our_value:+.3f} | {p.reference_value:+.2f} |")
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
    is_war = value_report.metric == "war"
    metric_label = value_report.metric.upper()

    metric_bullet = (
        f"- **Metric:** WAR (replacement-level baseline={value_report.replacement_baseline:.3f}, "
        f"vs. league-average baseline={value_report.baseline:.3f}) -- an average-or-better start, "
        f"and more of them, accumulates real value here instead of netting ~0 the way WAA does."
        if is_war else
        f"- **Metric:** WAA (league-average baseline={value_report.baseline:.3f})"
    )

    lines = [
        f"# {metric_label} vs. Accepted WAR: {scope_label}, {years_label}",
        "",
        f"- **Scope:** {scope_label}",
        f"- **Years evaluated:** {years_label} ({granularity})",
        metric_bullet,
        f"- Source values file: `{os.path.basename(values_path)}`",
        f"- Matrix: `{os.path.basename(value_report.matrix_path)}` "
        f"(years={value_report.matrix_years[0]}-{value_report.matrix_years[-1]}, "
        f"alpha={value_report.matrix_alpha:.2f})",
    ]

    for result in results:
        our_metric_label = result.our_metric.upper()
        lines.append("")
        lines.append(f"## {our_metric_label} vs {result.war_source}")
        lines.append("")
        lines.append(f"![{our_metric_label} vs {result.war_source}]({image_names[result.war_source]})")
        lines.append("")
        lines.append(f"- n = {len(result.points)} (excluded {result.excluded}: no {result.war_source} match)")
        if result.r is None:
            lines.append("- Fewer than 2 points -- no correlation/fit computed.")
        else:
            lines.append(f"- Pearson r = {result.r:.3f}, R² = {result.r_squared:.3f}")
            intercept_sign = "-" if result.intercept < 0 else "+"
            lines.append(
                f"- Best fit: {our_metric_label} = {result.slope:.3f} × {result.war_source} "
                f"{intercept_sign} {abs(result.intercept):.3f}"
            )
            if is_war:
                lines.append(
                    f"- A slope near 1.0 with a small positive intercept would mean this project's "
                    f"replacement-level WAR tracks {result.war_source} on close to a 1:1 scale; "
                    f"compare against the WAA report for the same pitchers to see how much the "
                    f"replacement-level baseline changes that relationship."
                )

        if result.points:
            lines.append("")
            lines.extend(_ExtremeTableLines(result.points, our_metric_label, lambda p: p.our_value, our_metric_label, result.war_source))
            lines.extend(_ExtremeTableLines(result.points, result.war_source, lambda p: p.reference_value, our_metric_label, result.war_source))

        if result.r is not None:
            lines.append("### Largest disagreements (by fit residual)")
            lines.append("")
            lines.append(f"| Pitcher | Season | {our_metric_label} | {result.war_source} | Residual |")
            lines.append("|---|---|---|---|---|")

            def _residual(p):
                return p.our_value - (result.slope * p.reference_value + result.intercept)

            top = sorted(result.points, key=lambda p: abs(_residual(p)), reverse=True)[:_OUTLIER_ROWS]
            for p in top:
                season_str = str(p.season) if p.season is not None else "-"
                lines.append(f"| {p.pitcher_name} | {season_str} | {p.our_value:+.3f} | {p.reference_value:+.2f} | {_residual(p):+.3f} |")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    from Models.Comparison import ComparisonPoint

    result = ComparisonResult(
        war_source = "bWAR",
        our_metric = "waa",
        points     = [
            ComparisonPoint(pitcher_id=543037, pitcher_name="Gerrit Cole", our_value=3.316, reference_value=7.39, season=2023),
            ComparisonPoint(pitcher_id=519242, pitcher_name="Chris Sale",  our_value=4.383, reference_value=6.10, season=2024),
            ComparisonPoint(pitcher_id=1,      pitcher_name="Nobody",      our_value=-1.14, reference_value=-0.5, season=2022),
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
        assert "**Metric:** WAA" in text

    single = ComparisonResult(war_source="bWAR", our_metric="waa", points=[result.points[0]], excluded=0)
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

    # A --metric war values report should drive war-flavored labels/analysis throughout,
    # not silently reuse "WAA" text.
    war_result = ComparisonResult(
        war_source = "bWAR",
        our_metric = "war",
        points     = [
            ComparisonPoint(pitcher_id=543037, pitcher_name="Gerrit Cole", our_value=6.5, reference_value=7.39, season=2023),
            ComparisonPoint(pitcher_id=519242, pitcher_name="Chris Sale",  our_value=7.0, reference_value=6.10, season=2024),
            ComparisonPoint(pitcher_id=1,      pitcher_name="Nobody",      our_value=1.2, reference_value=-0.5, season=2022),
        ],
        excluded  = 1,
        r         = 0.9,
        r_squared = 0.81,
        slope     = 0.6,
        intercept = 0.1,
    )
    war_report = dataclasses.replace(
        report, metric="war", replacement_baseline=0.401,
    )
    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "scatter_bwar.png")
        md_path  = os.path.join(tmp, "report.md")
        PlotScatter(war_result, img_path)
        assert os.path.isfile(img_path) and os.path.getsize(img_path) > 0
        WriteMarkdown(war_report, [war_result], {"bWAR": "scatter_bwar.png"}, "values/value_2022-2024_war.json", md_path)
        with open(md_path) as f:
            text = f.read()
        assert "# WAR vs. Accepted WAR" in text
        assert "## WAR vs bWAR" in text
        assert "**Metric:** WAR (replacement-level baseline=0.401" in text
        assert "Best fit: WAR = 0.600 × bWAR" in text
        assert "Top/bottom 5 by WAR" in text
        assert "| Pitcher | Season | WAR | bWAR |" in text
        assert "| Pitcher | Season | WAR | bWAR | Residual |" in text
        assert "netting ~0 the way WAA does" in text

    print("ReportIO self-checks passed.")
