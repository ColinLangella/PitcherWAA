from Models.Start import Decision


def ParseOuts(innings_pitched: str) -> int:
    """'5.2' -> 17 outs (5*3 + 2). NEVER float('5.2') -- '.2' means 2 outs, not 0.2 innings."""
    full_str, _, partial_str = innings_pitched.partition(".")
    full    = int(full_str or 0)
    partial = int(partial_str or 0)
    if partial not in (0, 1, 2):
        raise ValueError(f"Unexpected partial-innings digit in inningsPitched='{innings_pitched}'")
    return 3 * full + partial


def ClassifyDecision(stat: dict, split: dict) -> Decision:
    if stat.get("wins", 0) == 1:
        return Decision.W
    if stat.get("losses", 0) == 1:
        return Decision.L
    if split.get("isWin"):
        return Decision.ND_WON
    return Decision.ND_LOST


if __name__ == "__main__":
    assert ParseOuts("5.2") == 17
    assert ParseOuts("5.0") == 15
    assert ParseOuts("5")   == 15
    assert ParseOuts("0.1") == 1
    try:
        ParseOuts("5.3")
        raise AssertionError("expected ValueError for invalid partial-innings digit")
    except ValueError:
        pass

    assert ClassifyDecision({"wins": 1, "losses": 0}, {"isWin": True})  == Decision.W
    assert ClassifyDecision({"wins": 0, "losses": 1}, {"isWin": False}) == Decision.L
    assert ClassifyDecision({"wins": 0, "losses": 0}, {"isWin": True})  == Decision.ND_WON
    assert ClassifyDecision({"wins": 0, "losses": 0}, {"isWin": False}) == Decision.ND_LOST

    print("StartClassifier self-checks passed.")
