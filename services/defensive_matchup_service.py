from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from services.nflverse_usage_service import PLAYER_STATS_URL, _normalize_team


SUPPORTED_POSITIONS = {"QB", "RB", "WR", "TE"}


@dataclass(frozen=True)
class DefensiveMatchupResult:
    ratings: pd.DataFrame
    source_rows: int
    weeks_used: list[int]
    source_url: str


@dataclass(frozen=True)
class MatchupEnrichmentResult:
    player_pool: pd.DataFrame
    match_report: pd.DataFrame
    unmatched_players: pd.DataFrame


class DefensiveMatchupService:
    """Build leak-free fantasy-points-allowed ratings by defense and position."""

    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = int(timeout_seconds)

    def fetch_player_stats(self, season: int) -> pd.DataFrame:
        url = PLAYER_STATS_URL.format(season=int(season))
        request = Request(url, headers={"User-Agent": "dfs-football-optimizer/2.2"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise ValueError(
                    f"nflverse does not currently have player stats for {season}."
                ) from exc
            raise RuntimeError(
                f"nflverse returned HTTP {exc.code} while downloading {season}."
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                "Could not connect to nflverse. Check your internet connection."
            ) from exc

        try:
            return pd.read_csv(BytesIO(payload), low_memory=False)
        except Exception as exc:
            raise RuntimeError("The nflverse player-stat file could not be read.") from exc

    def summarize_for_week(
        self,
        season: int,
        week: int,
        lookback_weeks: int = 6,
    ) -> DefensiveMatchupResult:
        if int(week) < 1:
            raise ValueError("NFL week must be at least 1.")
        if int(lookback_weeks) < 1:
            raise ValueError("Matchup lookback must be at least one week.")

        source = self.fetch_player_stats(int(season))
        required = {"week", "position", "opponent_team", "fantasy_points_ppr"}
        missing = required - set(source.columns)
        if missing:
            raise ValueError(
                "The nflverse file is missing required matchup fields: "
                f"{sorted(missing)}"
            )

        working = source.copy()
        if "season_type" in working.columns:
            working = working.loc[
                working["season_type"].astype(str).str.upper().eq("REG")
            ].copy()

        working["week"] = pd.to_numeric(working["week"], errors="coerce")
        working = working.loc[working["week"].lt(int(week))].copy()
        available_weeks = sorted(
            int(value) for value in working["week"].dropna().unique()
        )
        weeks_used = available_weeks[-int(lookback_weeks):]
        working = working.loc[working["week"].isin(weeks_used)].copy()

        if working.empty:
            return DefensiveMatchupResult(
                ratings=pd.DataFrame(),
                source_rows=0,
                weeks_used=[],
                source_url=PLAYER_STATS_URL.format(season=int(season)),
            )

        working["position"] = (
            working["position"].fillna("").astype(str).str.upper().str.strip()
        )
        working = working.loc[working["position"].isin(SUPPORTED_POSITIONS)].copy()
        working["defense"] = working["opponent_team"].map(_normalize_team)
        working["fantasy_points_allowed"] = pd.to_numeric(
            working["fantasy_points_ppr"], errors="coerce"
        ).fillna(0.0)

        weekly = (
            working.groupby(["week", "defense", "position"], as_index=False)
            .agg(fantasy_points_allowed=("fantasy_points_allowed", "sum"))
        )
        ratings = (
            weekly.groupby(["defense", "position"], as_index=False)
            .agg(
                matchup_games=("week", "nunique"),
                fantasy_points_allowed=("fantasy_points_allowed", "mean"),
            )
        )
        ratings["matchup_rating"] = (
            ratings.groupby("position")["fantasy_points_allowed"]
            .rank(method="average", pct=True)
            .mul(100.0)
        )
        ratings["matchup_label"] = pd.cut(
            ratings["matchup_rating"],
            bins=[-0.1, 20, 40, 60, 80, 100.1],
            labels=["Very tough", "Tough", "Neutral", "Favorable", "Elite"],
        ).astype(str)
        ratings[["fantasy_points_allowed", "matchup_rating"]] = ratings[
            ["fantasy_points_allowed", "matchup_rating"]
        ].round(2)
        ratings = ratings.sort_values(
            ["position", "matchup_rating"], ascending=[True, False]
        ).reset_index(drop=True)

        return DefensiveMatchupResult(
            ratings=ratings,
            source_rows=len(working),
            weeks_used=weeks_used,
            source_url=PLAYER_STATS_URL.format(season=int(season)),
        )


def enrich_player_pool_with_matchups(
    players: pd.DataFrame,
    ratings: pd.DataFrame,
) -> MatchupEnrichmentResult:
    """Attach opponent/position matchup ratings to a weekly player pool."""

    output = players.copy().reset_index(drop=True)
    output["position"] = output["position"].astype(str).str.upper().str.strip()
    output["opponent_key"] = output.get(
        "opponent", pd.Series("", index=output.index)
    ).map(_normalize_team)

    if ratings.empty:
        output["matchup_matched"] = False
        output = output.drop(columns=["opponent_key"])
        unmatched = output.loc[
            output["position"].isin(SUPPORTED_POSITIONS),
            ["name", "position", "team", "opponent"],
        ].copy()
        return MatchupEnrichmentResult(
            player_pool=output,
            match_report=pd.DataFrame(
                [{"Eligible players": len(unmatched), "Matched": 0, "Match rate": 0.0}]
            ),
            unmatched_players=unmatched,
        )

    rating_copy = ratings.rename(columns={"defense": "opponent_key"}).copy()
    output = output.merge(
        rating_copy,
        how="left",
        on=["opponent_key", "position"],
        validate="many_to_one",
    )
    eligible = output["position"].isin(SUPPORTED_POSITIONS)
    output["matchup_matched"] = eligible & output["matchup_rating"].notna()
    matched = int(output["matchup_matched"].sum())
    eligible_count = int(eligible.sum())
    match_rate = round(matched / eligible_count * 100.0, 1) if eligible_count else 0.0
    unmatched = output.loc[
        eligible & ~output["matchup_matched"],
        ["name", "position", "team", "opponent"],
    ].copy()
    output = output.drop(columns=["opponent_key"])

    return MatchupEnrichmentResult(
        player_pool=output,
        match_report=pd.DataFrame(
            [{"Eligible players": eligible_count, "Matched": matched, "Match rate": match_rate}]
        ),
        unmatched_players=unmatched,
    )
