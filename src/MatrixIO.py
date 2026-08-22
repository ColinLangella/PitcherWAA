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

    lines = [
        f"Matrix years={matrix.years[0]}-{matrix.years[-1]} alpha={matrix.alpha:.2f} "
        f"baseline={matrix.baseline:.3f} total_starts={matrix.total_starts}"
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
