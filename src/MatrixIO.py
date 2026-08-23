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

    col_labels = [f"ER={col}" + ("+" if col == matrix.er_cap else "") for col in range(matrix.er_cap + 1)]
    header = "          " + "".join(f"{label:<7}" for label in col_labels)
    lines.append(header)

    for row in range(matrix.outs_cap + 1):
        label = f"Outs={row}" if row < matrix.outs_cap else f"Outs={row}+"
        line = f"{label:<10}"
        for col in range(matrix.er_cap + 1):
            cell  = by_pos[(row, col)]
            line += f"{cell.smoothed_wp:6.3f}{'*' if cell.interpolated else ' '}"
        lines.append(line)

    lines.append("")
    lines.append("* = interpolated (n=0; value comes purely from the monotonic fit)")

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

    print("MatrixIO self-checks passed.")
