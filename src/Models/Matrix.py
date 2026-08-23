import dataclasses


@dataclasses.dataclass
class Cell:
    outs:         int            # row, 0-27 (27 absorbs 27+ outs)
    earned_runs:  int            # col, 0-9  (9 absorbs 9+ ER)
    n:            int            # raw starts landing here
    w:            int
    nd_won:       int
    nd_lost:      int
    l:            int
    raw_wp:       float | None   # None when n == 0
    shrunk_wp:    float          # after sample-size shrinkage
    smoothed_wp:  float          # final value after 2D isotonic fit
    interpolated: bool           # True iff n == 0


@dataclasses.dataclass
class Matrix:
    years:                        list[int]
    alpha:                        float
    baseline:                     float
    outs_cap:                     int
    er_cap:                       int
    cells:                        list[Cell]
    total_starts:                 int
    min_start_outs:               int
    excluded_openers:             int | None = None
    replacement_baseline:         float | None = None   # mean WP of the non-qualifying (replacement) pool; None if never computed
    replacement_min_start_ratio:  float | None = None   # gamesStarted/gamesPlayed threshold used to split the replacement pool


if __name__ == "__main__":
    cell = Cell(
        outs         = 15,
        earned_runs  = 2,
        n            = 100,
        w            = 60,
        nd_won       = 20,
        nd_lost      = 15,
        l            = 5,
        raw_wp       = 0.65,
        shrunk_wp    = 0.64,
        smoothed_wp  = 0.645,
        interpolated = False,
    )
    print(cell)

    matrix = Matrix(
        years                       = [2024],
        alpha                       = 0.1,
        baseline                    = 0.488,
        outs_cap                    = 27,
        er_cap                      = 9,
        cells                       = [cell],
        total_starts                = 4858,
        min_start_outs              = 3,
        replacement_baseline        = 0.401,
        replacement_min_start_ratio = 0.5,
    )
    raw = dataclasses.asdict(matrix)
    round_tripped = Matrix(cells=[Cell(**c) for c in raw.pop("cells")], **raw)
    assert round_tripped == matrix
    assert round_tripped.replacement_baseline == 0.401
    assert round_tripped.replacement_min_start_ratio == 0.5

    old_style_matrix = Matrix(
        years          = [2024],
        alpha          = 0.1,
        baseline       = 0.488,
        outs_cap       = 27,
        er_cap         = 9,
        cells          = [cell],
        total_starts   = 4858,
        min_start_outs = 3,
    )
    assert old_style_matrix.replacement_baseline is None
    assert old_style_matrix.replacement_min_start_ratio is None
    print("Matrix self-checks passed.")
