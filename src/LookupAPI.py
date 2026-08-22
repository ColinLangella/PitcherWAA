import logging

import statsapi as mlb


### https://statsapi.mlb.com/api/v1/sports/{sportId}/players (via statsapi.lookup_player)
class PlayerLookupAPI:
    @staticmethod
    def Resolve(identifier: str, season: int) -> tuple[int, str]:
        """Accepts an MLBAM id or a name (fuzzy substring match); returns (id, full_name).
        Raises ValueError on zero or multiple matches."""
        logging.debug(f"Resolving player identifier='{identifier}' season={season}")
        matches = mlb.lookup_player(identifier, season=season)
        if not matches:
            raise ValueError(f"No player found matching '{identifier}' in season {season}.")
        if len(matches) > 1:
            candidates = ", ".join(f"{m['fullName']} (id={m['id']})" for m in matches)
            raise ValueError(f"Ambiguous player '{identifier}': {candidates}")
        match = matches[0]
        logging.debug(f"Resolved player '{identifier}' -> id={match['id']} name='{match['fullName']}'")
        return match["id"], match["fullName"]


### https://statsapi.mlb.com/api/v1/teams (via statsapi.lookup_team)
class TeamLookupAPI:
    @staticmethod
    def Resolve(identifier: str, season: int) -> tuple[int, str]:
        """Accepts an MLBAM team id, abbreviation, or name; returns (id, full_name) where
        full_name matches Start.team (e.g. 'New York Yankees'). Raises ValueError on zero
        or multiple matches."""
        logging.debug(f"Resolving team identifier='{identifier}' season={season}")
        matches = mlb.lookup_team(identifier, season=season)
        if not matches:
            raise ValueError(f"No team found matching '{identifier}' in season {season}.")
        if len(matches) > 1:
            candidates = ", ".join(f"{m['name']} (id={m['id']})" for m in matches)
            raise ValueError(f"Ambiguous team '{identifier}': {candidates}")
        match = matches[0]
        logging.debug(f"Resolved team '{identifier}' -> id={match['id']} name='{match['name']}'")
        return match["id"], match["name"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

    pid, pname = PlayerLookupAPI.Resolve("543037", 2024)
    assert (pid, pname) == (543037, "Gerrit Cole")

    pid, pname = PlayerLookupAPI.Resolve("Gerrit Cole", 2024)
    assert (pid, pname) == (543037, "Gerrit Cole")

    try:
        PlayerLookupAPI.Resolve("Cole", 2024)
        raise AssertionError("expected ValueError for an ambiguous name")
    except ValueError:
        pass

    tid, tname = TeamLookupAPI.Resolve("NYY", 2024)
    assert (tid, tname) == (147, "New York Yankees")

    tid, tname = TeamLookupAPI.Resolve("147", 2024)
    assert (tid, tname) == (147, "New York Yankees")

    print("LookupAPI self-checks passed.")
