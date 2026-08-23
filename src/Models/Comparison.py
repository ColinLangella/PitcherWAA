import dataclasses


@dataclasses.dataclass
class ComparisonPoint:
    pitcher_id:      int
    pitcher_name:    str
    our_value:       float   # this project's own metric for the pitcher -- WAA or WAR, per ComparisonResult.our_metric
    reference_value: float   # the external figure being compared against (e.g. bWAR), per ComparisonResult.war_source
    season:          int | None = None   # set iff the source values report was --by-season


@dataclasses.dataclass
class ComparisonResult:
    war_source: str        # label for the external reference, e.g. "bWAR"
    our_metric: str        # "waa" or "war" -- which of this project's own metrics these points use (from the source ValueReport.metric)
    points:     list[ComparisonPoint]
    excluded:   int                # pitchers in the values report with no matching WAR record
    r:          float | None = None   # None when len(points) < 2 -- no fit is meaningful
    r_squared:  float | None = None
    slope:      float | None = None
    intercept:  float | None = None


if __name__ == "__main__":
    cp = ComparisonPoint(pitcher_id=543037, pitcher_name="Gerrit Cole", our_value=3.316, reference_value=7.39, season=2023)
    print(cp)

    result = ComparisonResult(
        war_source = "bWAR",
        our_metric = "waa",
        points     = [cp],
        excluded   = 2,
        r          = None,
        r_squared  = None,
        slope      = None,
        intercept  = None,
    )
    print(result)
    assert result.r is None  # a single point has no meaningful fit

    print("Comparison self-checks passed.")
