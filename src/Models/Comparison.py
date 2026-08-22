import dataclasses


@dataclasses.dataclass
class ComparisonPoint:
    pitcher_id:   int
    pitcher_name: str
    waa:          float
    war:          float
    season:       int | None = None   # set iff the source values report was --by-season


@dataclasses.dataclass
class ComparisonResult:
    war_source: str
    points:     list[ComparisonPoint]
    excluded:   int                # pitchers in the values report with no matching WAR record
    r:          float | None = None   # None when len(points) < 2 -- no fit is meaningful
    r_squared:  float | None = None
    slope:      float | None = None
    intercept:  float | None = None


if __name__ == "__main__":
    cp = ComparisonPoint(pitcher_id=543037, pitcher_name="Gerrit Cole", waa=3.316, war=7.39, season=2023)
    print(cp)

    result = ComparisonResult(
        war_source = "bWAR",
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
