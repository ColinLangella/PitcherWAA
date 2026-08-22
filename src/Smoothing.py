"""Sample-size shrinkage, then 2D isotonic regression, per CLAUDE.md decision 4.

The 2D isotonic step is implemented as alternating weighted 1D PAVA passes
(rows then columns, repeated to convergence). This is a standard block-relaxation
heuristic for bivariate isotonic fitting -- it is NOT a proven-optimal projection
onto the 2D isotonic cone, but it always converges to a surface that is monotonic
along both axes simultaneously, which is what decision 4 requires. No dependency
beyond numpy is needed.
"""
import logging

import numpy as np

from Models.Matrix import Cell

_SHRINKAGE_PSEUDOCOUNT = 10.0
_MAX_ISOTONIC_ITER      = 50
_ISOTONIC_TOL           = 1e-6


def ShrinkCells(cells: list[Cell], baseline: float, pseudo_count: float = _SHRINKAGE_PSEUDOCOUNT) -> None:
    """shrunk_wp = (n*observed + k*baseline) / (n+k); n=0 cells collapse to exactly baseline."""
    logging.info(f"Shrinking {len(cells)} cells toward baseline={baseline:.4f} (pseudo_count={pseudo_count})")
    for cell in cells:
        observed        = cell.raw_wp if cell.raw_wp is not None else baseline
        cell.shrunk_wp = (cell.n * observed + pseudo_count * baseline) / (cell.n + pseudo_count)
        logging.debug(
            f"shrink outs={cell.outs} er={cell.earned_runs} n={cell.n} "
            f"raw={cell.raw_wp} -> shrunk={cell.shrunk_wp:.4f}"
        )


def _Violates(prev_v: float, curr_v: float, increasing: bool) -> bool:
    return prev_v > curr_v if increasing else prev_v < curr_v


def _Pava1D(values: np.ndarray, weights: np.ndarray, increasing: bool) -> np.ndarray:
    """O(n) weighted pool-adjacent-violators over a single row/column."""
    block_values:  list[float] = []
    block_weights: list[float] = []
    block_sizes:   list[int]   = []

    for v, w in zip(values, weights):
        block_values.append(float(v))
        block_weights.append(float(w))
        block_sizes.append(1)
        while len(block_values) > 1 and _Violates(block_values[-2], block_values[-1], increasing):
            v2, w2, n2 = block_values.pop(), block_weights.pop(), block_sizes.pop()
            v1, w1, n1 = block_values.pop(), block_weights.pop(), block_sizes.pop()
            merged_w = w1 + w2
            merged_v = (v1*w1 + v2*w2) / merged_w if merged_w > 0 else (v1 + v2) / 2.0
            block_values.append(merged_v)
            block_weights.append(merged_w)
            block_sizes.append(n1 + n2)

    result = np.empty(len(values))
    i = 0
    for v, size in zip(block_values, block_sizes):
        result[i:i+size] = v
        i += size
    return result


def Isotonic2D(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """values, weights: shape (outs_cap+1, er_cap+1).

    Axis 0 (rows, outs):    enforce non-decreasing as outs rises, at fixed ER.
    Axis 1 (columns, ER):   enforce non-increasing as ER rises, at fixed outs.
    """
    current = values.copy()
    for iteration in range(_MAX_ISOTONIC_ITER):
        previous = current.copy()

        for r in range(current.shape[0]):
            current[r, :] = _Pava1D(current[r, :], weights[r, :], increasing=False)

        for c in range(current.shape[1]):
            current[:, c] = _Pava1D(current[:, c], weights[:, c], increasing=True)

        delta = float(np.max(np.abs(current - previous)))
        logging.info(f"isotonic iter={iteration} max_delta={delta:.6f}")
        if delta < _ISOTONIC_TOL:
            break
    else:
        logging.error(f"Isotonic regression did not converge within {_MAX_ISOTONIC_ITER} iterations")

    return current


def ApplyShrinkageAndIsotonic(cells: list[Cell], baseline: float, outs_cap: int, er_cap: int) -> list[Cell]:
    logging.info(f"Applying shrinkage + 2D isotonic regression to {len(cells)} cells")
    ShrinkCells(cells, baseline)

    rows, cols = outs_cap + 1, er_cap + 1
    grid    = np.zeros((rows, cols))
    weights = np.zeros((rows, cols))
    by_pos  = {(c.outs, c.earned_runs): c for c in cells}

    for r in range(rows):
        for col in range(cols):
            cell            = by_pos[(r, col)]
            grid[r, col]    = cell.shrunk_wp
            weights[r, col] = cell.n

    smoothed = Isotonic2D(grid, weights)

    for r in range(rows):
        for col in range(cols):
            by_pos[(r, col)].smoothed_wp = float(smoothed[r, col])

    logging.info("Shrinkage + isotonic smoothing complete")
    return cells


if __name__ == "__main__":
    # Weighted PAVA should merge a single violating point into its neighbors.
    vals = np.array([0.1, 0.5, 0.3, 0.6])
    wts  = np.array([10.0, 10.0, 10.0, 10.0])
    fitted = _Pava1D(vals, wts, increasing=True)
    assert all(fitted[i] <= fitted[i+1] + 1e-12 for i in range(len(fitted)-1)), fitted

    # 2D isotonic on a small synthetic grid with violations and an empty cell (weight 0).
    grid    = np.array([[0.9, 0.6, 0.7], [0.2, 0.5, 0.0], [0.4, 0.8, 0.9]])
    weights = np.array([[5.0, 5.0, 5.0], [5.0, 5.0, 0.0], [5.0, 5.0, 5.0]])
    fitted = Isotonic2D(grid, weights)
    monotonic_tol = 10 * _ISOTONIC_TOL  # accumulated float noise from alternating passes, not a real violation
    for r in range(fitted.shape[0] - 1):
        assert np.all(fitted[r, :] <= fitted[r+1, :] + monotonic_tol), "WP should not decrease as outs rise, fixed ER"
    for c in range(fitted.shape[1] - 1):
        assert np.all(fitted[:, c] >= fitted[:, c+1] - monotonic_tol), "WP should not increase as ER rises, fixed outs"
    print("Smoothing self-checks passed.")
