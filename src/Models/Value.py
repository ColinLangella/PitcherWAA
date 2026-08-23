import dataclasses


@dataclasses.dataclass
class PitcherValue:
    pitcher_id:   int
    pitcher_name: str
    starts:       int
    sum_wp:       float
    avg_wp:       float
    waa:          float
    season:       int | None = None   # set iff the report is split by_season; None means pooled across eval_years
    war:          float | None = None   # sum(wp - replacement_baseline); set only when metric == "war"


@dataclasses.dataclass
class ValueReport:
    eval_years:           list[int]
    matrix_path:          str
    matrix_years:         list[int]
    matrix_alpha:         float
    baseline:             float
    pitchers:             list[PitcherValue]
    pitcher_filter:       int | None = None
    team_filter:          str | None = None
    by_season:            bool = False
    min_start_ratio:      float = 0.5   # gamesStarted/gamesPlayed cutoff used to build the default starter pool; irrelevant when pitcher_filter is set
    metric:               str = "waa"   # "waa" (default) or "war"; selects which PitcherValue field drives sorting/display
    replacement_baseline: float | None = None   # replacement-level WP actually used for war (matrix's, or --replacement-level override); None unless metric == "war"


if __name__ == "__main__":
    pv = PitcherValue(
        pitcher_id   = 543037,
        pitcher_name = "Gerrit Cole",
        starts       = 32,
        sum_wp       = 19.442,
        avg_wp       = 0.608,
        waa          = 3.316,
        season       = 2024,
    )
    print(pv)

    report = ValueReport(
        eval_years   = [2024],
        matrix_path  = "output/matrix_2024_a0.10.json",
        matrix_years = [2024],
        matrix_alpha = 0.1,
        baseline     = 0.488,
        pitchers     = [pv],
        by_season    = True,
    )
    print(report)
