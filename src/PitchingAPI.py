import logging

import statsapi as mlb

from Cache.Cache import GetOrFetch
from Models.Start import Start
from StartClassifier import ClassifyDecision, ParseOuts
from Utils.Retry import WithRetry


### https://statsapi.mlb.com/api/v1/stats?stats=season&group=pitching&sportId=1
class SeasonPitchingAPI:
    @staticmethod
    def GetQualifiedStarters(season: int) -> list[int]:
        """Every MLBAM pitcher id with gamesStarted > 0 in `season` (regular season only)."""
        logging.info(f"Fetching season pitching stats for season={season}")
        raw = GetOrFetch(
            file_name = f"season_{season}.json",
            fetch_fn  = lambda: WithRetry(lambda: mlb.get("stats", {
                "stats":      "season",
                "group":      "pitching",
                "season":     season,
                "gameType":   "R",
                "sportId":    1,
                "playerPool": "All",
                "limit":      1000,
            })),
        )
        splits = raw.get("stats", [{}])[0].get("splits", [])
        ids = [s["player"]["id"] for s in splits if s.get("stat", {}).get("gamesStarted", 0) > 0]
        logging.info(f"season={season}: {len(splits)} pitchers total, {len(ids)} with GS > 0")
        return ids


### https://statsapi.mlb.com/api/v1/people?hydrate=stats(group=[pitching],type=[gameLog],...)
class PitcherGameLogAPI:
    @staticmethod
    def GetStarts(pitcher_id: int, season: int, min_outs: int) -> tuple[list[Start], int]:
        """Returns (classified starts, count of starts excluded for outs < min_outs)."""
        logging.debug(f"Fetching game log: pitcher_id={pitcher_id} season={season}")
        raw = GetOrFetch(
            file_name = f"pitcher_{season}_{pitcher_id}.json",
            fetch_fn  = lambda: WithRetry(lambda: mlb.get("people", {
                "personIds": pitcher_id,
                "hydrate":   f"stats(group=[pitching],type=[gameLog],season={season},gameType=R)",
            })),
        )
        people_stats = raw.get("people", [{}])[0].get("stats", [{}])
        splits = people_stats[0].get("splits", []) if people_stats else []

        starts, excluded = [], 0
        for split in splits:
            stat = split.get("stat", {})
            if stat.get("gamesStarted", 0) != 1:
                continue

            outs    = ParseOuts(stat.get("inningsPitched", "0.0"))
            game_pk = split.get("game", {}).get("gamePk")

            if outs < min_outs:
                excluded += 1
                logging.debug(f"Excluding short start: pitcher={pitcher_id} game={game_pk} outs={outs}")
                continue

            decision = ClassifyDecision(stat, split)
            logging.debug(
                f"Classified start: pitcher={pitcher_id} game={game_pk} "
                f"outs={outs} er={stat.get('earnedRuns', 0)} decision={decision.value}"
            )

            starts.append(Start(
                pitcher_id  = pitcher_id,
                season      = season,
                game_pk     = game_pk,
                outs        = outs,
                earned_runs = stat.get("earnedRuns", 0),
                decision    = decision,
                date        = split.get("date"),
                team        = split.get("team", {}).get("name"),
                opponent    = split.get("opponent", {}).get("name"),
            ))

        logging.debug(f"pitcher_id={pitcher_id} season={season}: {len(starts)} starts, {excluded} excluded")
        return starts, excluded

    @staticmethod
    def GetName(pitcher_id: int, season: int) -> str:
        """Reads the pitcher's fullName from the same cached people/gameLog response GetStarts()
        uses -- free after GetStarts has already populated the cache for (pitcher_id, season)."""
        raw = GetOrFetch(
            file_name = f"pitcher_{season}_{pitcher_id}.json",
            fetch_fn  = lambda: WithRetry(lambda: mlb.get("people", {
                "personIds": pitcher_id,
                "hydrate":   f"stats(group=[pitching],type=[gameLog],season={season},gameType=R)",
            })),
        )
        people = raw.get("people", [{}])
        return people[0].get("fullName", str(pitcher_id)) if people else str(pitcher_id)


if __name__ == "__main__":
    import sys

    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

    pitcher_ids = SeasonPitchingAPI.GetQualifiedStarters(season)
    print(f"{season}: {len(pitcher_ids)} qualified starters")

    if pitcher_ids:
        starts, excluded = PitcherGameLogAPI.GetStarts(pitcher_ids[0], season, min_outs=3)
        print(f"pitcher_id={pitcher_ids[0]}: {len(starts)} starts, {excluded} excluded as short starts")

        name = PitcherGameLogAPI.GetName(pitcher_ids[0], season)
        print(f"pitcher_id={pitcher_ids[0]}: name='{name}'")
