import collections
import logging

import statsapi as mlb

from Cache.Cache import GetOrFetch
from Models.Start import Start
from StartClassifier import ClassifyDecision, ParseOuts
from Utils.Retry import WithRetry


### https://statsapi.mlb.com/api/v1/stats?stats=season&group=pitching&sportId=1
class SeasonPitchingAPI:
    @staticmethod
    def _GetSeasonStats(season: int) -> dict[int, tuple[int, int]]:
        """Returns {pitcher_id: (gamesStarted, gamesPlayed)} for every pitcher who appeared in
        `season` (regular season only), straight off the cached season-stats response."""
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
        return {
            s["player"]["id"]: (s.get("stat", {}).get("gamesStarted", 0), s.get("stat", {}).get("gamesPlayed", 0))
            for s in splits
        }

    @staticmethod
    def GetQualifiedStarters(season: int, min_start_ratio: float = 0.5) -> list[int]:
        """Every MLBAM pitcher id in `season` (regular season only) with gamesStarted > 0 AND
        gamesStarted / gamesPlayed >= min_start_ratio, both computed from that single season alone
        -- this excludes relievers who picked up a spot start or two but whose primary role wasn't
        starting. min_start_ratio=0 disables the ratio filter and keeps the old "any start counts"
        behavior. Appropriate for a single-season evaluation or a --by-season report, where each
        season is scored independently; a pooled multi-season report should use
        GetQualifiedStartersAcrossSeasons instead, so a pitcher's role is judged over the whole
        span rather than by whichever one season they happened to clear the ratio in."""
        stats = SeasonPitchingAPI._GetSeasonStats(season)

        ids, excluded = [], 0
        for pid, (games_started, games_played) in stats.items():
            if games_started <= 0:
                continue
            if games_played > 0 and (games_started / games_played) < min_start_ratio:
                excluded += 1
                logging.debug(
                    f"Excluding pitcher_id={pid} season={season}: "
                    f"gamesStarted={games_started} gamesPlayed={games_played} "
                    f"ratio={games_started / games_played:.3f} < min_start_ratio={min_start_ratio}"
                )
                continue
            ids.append(pid)

        logging.info(
            f"season={season}: {len(stats)} pitchers total, {len(ids)} with GS > 0 and "
            f"start_ratio >= {min_start_ratio} ({excluded} excluded as non-primary starters)"
        )
        return ids

    @staticmethod
    def GetQualifiedStartersAcrossSeasons(seasons: list[int], min_start_ratio: float = 0.5) -> dict[int, list[int]]:
        """Qualifies pitchers by their aggregate gamesStarted/gamesPlayed ratio summed across every
        season in `seasons`, not by any single season in isolation -- this is the pool a pooled
        (non-by-season) multi-year CalculateValue.py report should use, so a career reliever who
        had one qualifying rookie season (e.g. Mariano Rivera going 10 GS / 19 GP in 1995) isn't
        included on the strength of that one season while every start counted against their bWAR
        comes from relief years. Returns, for each season, the subset of that season's actual
        roster which clears the *aggregate* ratio -- callers still fetch one season's game logs at
        a time, just against this narrower per-season list."""
        per_season: dict[int, dict[int, tuple[int, int]]] = {season: SeasonPitchingAPI._GetSeasonStats(season) for season in seasons}

        totals: dict[int, list[int]] = collections.defaultdict(lambda: [0, 0])
        for stats in per_season.values():
            for pid, (games_started, games_played) in stats.items():
                totals[pid][0] += games_started
                totals[pid][1] += games_played

        qualified = {
            pid for pid, (games_started, games_played) in totals.items()
            if games_started > 0 and (games_played == 0 or games_started / games_played >= min_start_ratio)
        }

        logging.info(
            f"seasons={seasons}: {len(totals)} pitchers total, {len(qualified)} with aggregate "
            f"GS > 0 and start_ratio >= {min_start_ratio} ({len(totals) - len(qualified)} excluded "
            f"as non-primary starters over the full span)"
        )

        return {season: [pid for pid in stats if pid in qualified] for season, stats in per_season.items()}


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

    all_starters = SeasonPitchingAPI.GetQualifiedStarters(season, min_start_ratio=0.0)
    assert len(all_starters) >= len(pitcher_ids), "raising min_start_ratio should never grow the pool"
    print(f"{season}: {len(all_starters)} pitchers with any start (min_start_ratio=0.0)")

    # Mariano Rivera (121250) went 10 GS / 19 GP as a rookie in 1995 (ratio 0.526, clears 0.5
    # per season alone) but started 0 of 61 games in 1996 -- a career reliever whose one qualifying
    # season shouldn't earn him a spot in a pooled multi-season starter pool.
    rivera_id = 121250
    assert rivera_id in SeasonPitchingAPI.GetQualifiedStarters(1995, min_start_ratio=0.5)
    assert rivera_id not in SeasonPitchingAPI.GetQualifiedStarters(1996, min_start_ratio=0.5)

    pooled = SeasonPitchingAPI.GetQualifiedStartersAcrossSeasons([1995, 1996], min_start_ratio=0.5)
    assert rivera_id not in pooled[1995], "aggregate ratio across 1995-1996 should exclude Rivera"
    assert rivera_id not in pooled[1996]
    print("Mariano Rivera correctly excluded from the 1995-1996 pooled starter pool")

    if pitcher_ids:
        starts, excluded = PitcherGameLogAPI.GetStarts(pitcher_ids[0], season, min_outs=3)
        print(f"pitcher_id={pitcher_ids[0]}: {len(starts)} starts, {excluded} excluded as short starts")

        name = PitcherGameLogAPI.GetName(pitcher_ids[0], season)
        print(f"pitcher_id={pitcher_ids[0]}: name='{name}'")
