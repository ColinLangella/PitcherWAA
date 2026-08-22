import dataclasses
import enum


class Decision(enum.Enum):
    W       = "W"
    ND_WON  = "ND_team_won"
    ND_LOST = "ND_team_lost"
    L       = "L"


@dataclasses.dataclass
class Start:
    pitcher_id:  int
    season:      int
    game_pk:     int
    outs:        int
    earned_runs: int
    decision:    Decision
    date:        str | None = None
    team:        str | None = None
    opponent:    str | None = None


if __name__ == "__main__":
    s = Start(
        pitcher_id  = 1,
        season      = 2024,
        game_pk     = 1,
        outs        = 17,
        earned_runs = 2,
        decision    = Decision.W,
    )
    print(s)
