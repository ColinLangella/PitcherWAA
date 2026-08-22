import logging
import math

from Cache.Cache import GetOrFetch
from Utils.Retry import WithRetry


### https://www.baseball-reference.com/data/war_daily_pitch.txt (via pybaseball.bwar_pitch)
class BaseballReferenceWarAPI:
    @staticmethod
    def GetAllWar() -> dict[int, dict[int, float]]:
        """Every pitcher-season's bWAR, keyed by MLBAM id -> {season: bWAR}. This is one bulk
        file covering every season/pitcher at once (not per-page scraping), fetched through
        WithRetry to ride out transient network errors, and cached raw so re-runs don't refetch.
        Rows with no MLBAM id (pre-integration-era players) are skipped -- our own pitcher ids
        always come from statsapi, so they always have one. A pitcher traded mid-season gets one
        row per team/stint for that year_ID (distinct stint_ID); those are summed rather than the
        last one winning, so a mid-season trade doesn't silently drop most of the season's WAR."""
        import pybaseball as pb

        raw = GetOrFetch(
            file_name = "bbref_war_pitch.json",
            fetch_fn  = lambda: {"rows": WithRetry(lambda: pb.bwar_pitch().to_dict(orient="records"))},
        )

        by_mlbam: dict[int, dict[int, float]] = {}
        skipped = 0
        for row in raw["rows"]:
            mlb_id = row.get("mlb_ID")
            war    = row.get("WAR")
            if mlb_id is None or math.isnan(mlb_id) or war is None or math.isnan(war):
                skipped += 1
                continue
            season = int(row["year_ID"])
            seasons = by_mlbam.setdefault(int(mlb_id), {})
            seasons[season] = seasons.get(season, 0.0) + float(war)

        logging.info(f"Loaded bWAR for {len(by_mlbam)} MLBAM-mapped pitchers ({skipped} rows skipped, no MLBAM id)")
        return by_mlbam


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    by_mlbam = BaseballReferenceWarAPI.GetAllWar()
    assert 543037 in by_mlbam, "Gerrit Cole (543037) should have bWAR rows"
    assert by_mlbam[543037][2023] > 5.0, "Cole's 2023 bWAR should reflect his Cy Young season"

    # David Price was traded DET -> TOR mid-2015 (two stints, one row each); the season total
    # must be their sum (3.75 + 2.58 = 6.33), not just whichever stint's row is read last.
    price_2015 = by_mlbam[456034][2015]
    assert abs(price_2015 - 6.33) < 0.01, f"David Price's 2015 bWAR should sum both stints, got {price_2015}"

    print("WarAPI self-checks passed.")
