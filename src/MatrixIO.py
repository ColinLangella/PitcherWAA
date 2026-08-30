import dataclasses
import json
import os

from Models.Matrix import Cell, Matrix

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")


def OutputFileStem(years: list[int], alpha: float) -> str:
    spread = str(years[0]) if len(years) == 1 else f"{years[0]}-{years[-1]}"
    return f"matrix_{spread}_a{alpha:.2f}"


def WriteJSON(matrix: Matrix, path: str) -> None:
    with open(path, "w") as f:
        json.dump(dataclasses.asdict(matrix), f, indent=2)


def ReadJSON(path: str) -> Matrix:
    """Reads a matrix JSON written by WriteJSON. Raises if the file is missing or malformed --
    CalculateValue.py must never silently rebuild the matrix."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Matrix file not found: {path}")
    with open(path, "r") as f:
        raw = json.load(f)
    cells = [Cell(**c) for c in raw.pop("cells")]
    return Matrix(cells=cells, **raw)


def _ColumnHeader(matrix: Matrix, col_width: int, indent: int = 10) -> str:
    col_labels = [f"ER={col}" + ("+" if col == matrix.er_cap else "") for col in range(matrix.er_cap + 1)]
    return " " * indent + "".join(f"{label:<{col_width}}" for label in col_labels)


def _RowLabel(row: int, outs_cap: int) -> str:
    return f"Outs={row}" if row < outs_cap else f"Outs={row}+"


def _RenderWpGrid(
    matrix:      Matrix,
    by_pos:      dict[tuple[int, int], Cell],
    title:       str,
    explanation: list[str],
    value_fn,
    mark_fn,
) -> list[str]:
    lines = ["", title, *explanation, _ColumnHeader(matrix, col_width=7)]
    for row in range(matrix.outs_cap + 1):
        line = f"{_RowLabel(row, matrix.outs_cap):<10}"
        for col in range(matrix.er_cap + 1):
            cell  = by_pos[(row, col)]
            value = value_fn(cell)
            mark  = mark_fn(cell)
            line += f"{'n/a':>6}{mark}" if value is None else f"{value:6.3f}{mark}"
        lines.append(line)
    return lines


def _RenderCountsGrid(matrix: Matrix, by_pos: dict[tuple[int, int], Cell]) -> list[str]:
    # Each field gets its own globally-computed width so the "|" separators line up vertically
    # across every row and column, not just within a single cell.
    w_width       = max(len(str(c.w))       for c in matrix.cells)
    nd_won_width  = max(len(str(c.nd_won))  for c in matrix.cells)
    nd_lost_width = max(len(str(c.nd_lost)) for c in matrix.cells)
    l_width       = max(len(str(c.l))       for c in matrix.cells)

    def count_str(cell: Cell) -> str:
        return (
            f"{cell.w:>{w_width}}|{cell.nd_won:>{nd_won_width}}|"
            f"{cell.nd_lost:>{nd_lost_width}}|{cell.l:>{l_width}}"
        )

    col_width = w_width + nd_won_width + nd_lost_width + l_width + 3 + 2
    lines = [
        "",
        "Counts (W|ND_won|ND_lost|L)",
        "The raw decision tally behind each cell's Raw WP -- wins, no-decisions the team won,",
        "no-decisions the team lost, and losses, in that order. Summing the four gives n.",
        _ColumnHeader(matrix, col_width=col_width),
    ]
    for row in range(matrix.outs_cap + 1):
        line = f"{_RowLabel(row, matrix.outs_cap):<10}"
        for col in range(matrix.er_cap + 1):
            line += f"{count_str(by_pos[(row, col)]):<{col_width}}"
        lines.append(line)
    lines.append("")
    lines.append("Counts are raw per-cell decision tallies; n = w + nd_won + nd_lost + l")
    return lines


def WriteText(matrix: Matrix, path: str) -> None:
    by_pos = {(c.outs, c.earned_runs): c for c in matrix.cells}

    replacement_str = (
        f" replacement_baseline={matrix.replacement_baseline:.3f} "
        f"replacement_min_start_ratio={matrix.replacement_min_start_ratio:.2f}"
        if matrix.replacement_baseline is not None else ""
    )
    lines = [
        f"Matrix years={matrix.years[0]}-{matrix.years[-1]} alpha={matrix.alpha:.2f} "
        f"baseline={matrix.baseline:.3f}{replacement_str} total_starts={matrix.total_starts}"
    ]

    lines.extend(_RenderWpGrid(
        matrix, by_pos,
        title       = "Smoothed WP",
        explanation = [
            "The final win probability used by CalculateValue.py, after both sample-size shrinkage",
            "and 2D isotonic smoothing. '*' marks cells with zero observed starts, filled in purely",
            "from the monotonic fit.",
        ],
        value_fn = lambda c: c.smoothed_wp,
        mark_fn  = lambda c: '*' if c.interpolated else ' ',
    ))

    lines.extend(_RenderWpGrid(
        matrix, by_pos,
        title       = "Raw WP (empirical, pre-shrinkage)",
        explanation = [
            "The unadjusted observed win probability for starts that actually landed in this bucket,",
            "before any smoothing. Shows what the model corrected away from, but is noisy or",
            "degenerate ('n/a' = zero starts observed) in low-n cells.",
        ],
        value_fn = lambda c: c.raw_wp,
        mark_fn  = lambda c: ' ',
    ))

    lines.extend(_RenderWpGrid(
        matrix, by_pos,
        title       = "Shrunk WP (post-shrinkage, pre-isotonic)",
        explanation = [
            "Raw WP pulled toward the league baseline in proportion to sample size (low-n cells move",
            "most). This is before the isotonic monotonicity pass, so it can still show non-monotonic",
            "bumps that the final Smoothed WP grid above removes.",
        ],
        value_fn = lambda c: c.shrunk_wp,
        mark_fn  = lambda c: '*' if c.interpolated else ' ',
    ))

    lines.append("")
    lines.append("* = interpolated (n=0; value comes purely from the monotonic fit)")

    lines.extend(_RenderCountsGrid(matrix, by_pos))

    with open(path, "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    print(f"OUTPUT_DIR = {os.path.abspath(OUTPUT_DIR)}")
    print(OutputFileStem([2025], 0.1))
    print(OutputFileStem([2020, 2021, 2022, 2023, 2024, 2025], 0.1))

    import tempfile

    cell = Cell(
        outs=0, earned_runs=0, n=100, w=60, nd_won=20, nd_lost=15, l=5,
        raw_wp=0.65, shrunk_wp=0.64, smoothed_wp=0.645, interpolated=False,
    )
    matrix = Matrix(
        years=[2024], alpha=0.1, baseline=0.488, outs_cap=0, er_cap=0,
        cells=[cell], total_starts=4858, min_start_outs=3,
        replacement_baseline=0.401, replacement_min_start_ratio=0.5,
    )
    with tempfile.TemporaryDirectory() as tmp:
        json_path = os.path.join(tmp, "matrix.json")
        text_path = os.path.join(tmp, "matrix.txt")
        WriteJSON(matrix, json_path)
        WriteText(matrix, text_path)
        with open(text_path) as f:
            text = f.read()
        assert "replacement_baseline=0.401" in text
        assert "replacement_min_start_ratio=0.50" in text
        assert ReadJSON(json_path) == matrix

        # All four sections and their explanations are present.
        assert "Smoothed WP" in text
        assert "final win probability used by CalculateValue.py" in text
        assert "Raw WP (empirical, pre-shrinkage)" in text
        assert "unadjusted observed win probability" in text
        assert "Shrunk WP (post-shrinkage, pre-isotonic)" in text
        assert "pulled toward the league baseline" in text
        assert "Counts (W|ND_won|ND_lost|L)" in text
        assert "raw decision tally behind each cell" in text
        assert "60|20|15|5" in text  # w|nd_won|nd_lost|l for `cell`

    matrix_no_replacement = Matrix(
        years=[2024], alpha=0.1, baseline=0.488, outs_cap=0, er_cap=0,
        cells=[cell], total_starts=4858, min_start_outs=3,
    )
    with tempfile.TemporaryDirectory() as tmp:
        text_path = os.path.join(tmp, "matrix.txt")
        WriteText(matrix_no_replacement, text_path)
        with open(text_path) as f:
            text = f.read()
        assert "replacement_baseline" not in text

    # A grid with an interpolated (n=0) cell: raw section shows 'n/a', smoothed/shrunk mark '*'.
    empty_cell = Cell(
        outs=1, earned_runs=0, n=0, w=0, nd_won=0, nd_lost=0, l=0,
        raw_wp=None, shrunk_wp=0.488, smoothed_wp=0.5, interpolated=True,
    )
    matrix_with_gap = Matrix(
        years=[2024], alpha=0.1, baseline=0.488, outs_cap=1, er_cap=0,
        cells=[cell, empty_cell], total_starts=100, min_start_outs=3,
    )
    with tempfile.TemporaryDirectory() as tmp:
        text_path = os.path.join(tmp, "matrix.txt")
        WriteText(matrix_with_gap, text_path)
        with open(text_path) as f:
            text = f.read()
        assert "n/a" in text
        assert "*" in text
        assert " 0| 0| 0|0" in text  # empty cell's counts, right-aligned to match `cell`'s 2-digit fields
        assert "60|20|15|5" in text  # `cell`'s counts -- "|" positions line up with empty_cell's

    print("MatrixIO self-checks passed.")
