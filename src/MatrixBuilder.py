import collections
import logging

from Models.Matrix import Cell
from Models.Start import Decision, Start


def _DecisionValue(decision: Decision, alpha: float) -> float:
    return {
        Decision.W:       1.0,
        Decision.ND_WON:  0.5 + alpha,
        Decision.ND_LOST: 0.5 - alpha,
        Decision.L:       0.0,
    }[decision]


def ComputeBaseline(starts: list[Start], alpha: float) -> float:
    """League mean start WP across every (pooled) start in the matrix year(s)."""
    if not starts:
        raise ValueError("Cannot compute baseline from zero starts.")
    return sum(_DecisionValue(s.decision, alpha) for s in starts) / len(starts)


def BucketStarts(starts: list[Start], outs_cap: int, er_cap: int) -> dict[tuple[int, int], list[Start]]:
    """Groups starts by (outs, ER), clamping outs > outs_cap and ER > er_cap into the last row/col."""
    logging.info(f"Bucketing {len(starts)} starts (outs_cap={outs_cap} er_cap={er_cap})")
    buckets: dict[tuple[int, int], list[Start]] = collections.defaultdict(list)
    for s in starts:
        buckets[(min(s.outs, outs_cap), min(s.earned_runs, er_cap))].append(s)
    return buckets


def BuildRawCells(buckets: dict[tuple[int, int], list[Start]], outs_cap: int, er_cap: int, alpha: float) -> list[Cell]:
    """One Cell per (outs, ER) grid position 0..outs_cap x 0..er_cap, including empty cells."""
    logging.info(f"Building raw cells for {outs_cap+1}x{er_cap+1} grid (alpha={alpha})")
    cells = []
    for row in range(outs_cap + 1):
        for col in range(er_cap + 1):
            bucket  = buckets.get((row, col), [])
            w       = sum(1 for s in bucket if s.decision == Decision.W)
            nd_won  = sum(1 for s in bucket if s.decision == Decision.ND_WON)
            nd_lost = sum(1 for s in bucket if s.decision == Decision.ND_LOST)
            l       = sum(1 for s in bucket if s.decision == Decision.L)
            n = w + nd_won + nd_lost + l
            raw_wp = (
                (1.0*w + (0.5+alpha)*nd_won + (0.5-alpha)*nd_lost) / n
                if n > 0 else None
            )
            if n > 0:
                logging.debug(f"bucket outs={row} er={col}: n={n} w={w} nd_won={nd_won} nd_lost={nd_lost} l={l} raw_wp={raw_wp:.4f}")
            cells.append(Cell(
                outs         = row,
                earned_runs  = col,
                n            = n,
                w            = w,
                nd_won       = nd_won,
                nd_lost      = nd_lost,
                l            = l,
                raw_wp       = raw_wp,
                shrunk_wp    = 0.0,
                smoothed_wp  = 0.0,
                interpolated = (n == 0),
            ))
    return cells


if __name__ == "__main__":
    starts = [
        Start(pitcher_id=1, season=2024, game_pk=1, outs=18, earned_runs=2, decision=Decision.W),
        Start(pitcher_id=1, season=2024, game_pk=2, outs=15, earned_runs=4, decision=Decision.L),
        Start(pitcher_id=1, season=2024, game_pk=3, outs=30, earned_runs=1, decision=Decision.ND_WON),
    ]
    baseline = ComputeBaseline(starts, alpha=0.1)
    print(f"baseline={baseline:.4f}")

    buckets = BucketStarts(starts, outs_cap=27, er_cap=9)
    assert (27, 1) in buckets, "outs=30 should clamp to outs_cap=27"

    cells = BuildRawCells(buckets, outs_cap=27, er_cap=9, alpha=0.1)
    assert len(cells) == 28 * 10
    populated = [c for c in cells if c.n > 0]
    assert len(populated) == 3
    print("MatrixBuilder self-checks passed.")
