from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd


PLAYER_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "player_stats/stats_player_week_{season}.csv"
)

TEAM_ALIASES = {
    "ARZ": "ARI",
    "BLT": "BAL",
    "CLV": "CLE",
    "HST": "HOU",
    "JAC": "JAX",
    "KAN": "KC",
    "LAR": "LA",
    "LVR": "LV",
    "NWE": "NE",
    "NOR": "NO",
    "OAK": "LV",
    "SD": "LAC",
    "SDG": "LAC",
    "SFO": "SF",
    "STL": "LA",
    "TAM": "TB",
    "GNB": "GB",
}


@dataclass(frozen=True)
class UsageDataResult:
    player_usage: pd.DataFrame
    source_rows: int
    weeks_used: list[int]
    source_url: str


@dataclass(frozen=True)
class UsageEnrichmentResult:
    player_pool: pd.DataFrame
    match_report: pd.DataFrame
    unmatched_players: pd.DataFrame


def _normalize_name(value: object) -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", "", text)
    return re.sub(r"[^a-z0-9]", "", text)


def _normalize_team(value: object) -> str:
    team = str(value or "").upper().strip()
    return TEAM_ALIASES.get(team, team)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


class NflverseUsageService:
    """Download and summarize leak-free historical usage from nflverse.

    For a selected season/week, only games from earlier weeks are included.
    The default lookback is the three most recent completed regular-season
    weeks, which prevents the selected week's results from leaking into its
    projections.
    """

    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = int(timeout_seconds)

    def fetch_player_stats(self, season: int) -> pd.DataFrame:
        url = PLAYER_STATS_URL.format(season=int(season))
        request = Request(
            url,
            headers={"User-Agent": "dfs-football-optimizer/2.1"},
        )
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
        lookback_weeks: int = 3,
    ) -> UsageDataResult:
        if int(week) < 1:
            raise ValueError("NFL week must be at least 1.")
        if int(lookback_weeks) < 1:
            raise ValueError("Usage lookback must be at least one week.")

        source = self.fetch_player_stats(int(season))
        required = {"week", "player_name", "recent_team"}
        missing = required - set(source.columns)
        if missing:
            raise ValueError(
                "The nflverse file is missing required fields: "
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
            return UsageDataResult(
                player_usage=pd.DataFrame(),
                source_rows=0,
                weeks_used=[],
                source_url=PLAYER_STATS_URL.format(season=int(season)),
            )

        working["player_name"] = working["player_name"].fillna("").astype(str)
        working["team"] = working["recent_team"].map(_normalize_team)
        working["name_key"] = working["player_name"].map(_normalize_name)
        working["player_id"] = (
            working.get("player_id", pd.Series("", index=working.index))
            .fillna("")
            .astype(str)
        )

        metric_map = {
            "attempts": "passing_attempts",
            "carries": "carries",
            "targets": "targets",
            "receptions": "receptions",
            "rushing_yards": "rushing_yards",
            "receiving_yards": "receiving_yards",
            "passing_yards": "passing_yards",
            "fantasy_points_ppr": "recent_fantasy_points",
        }
        for source_column, output_column in metric_map.items():
            working[output_column] = _numeric(working, source_column)

        grouped = (
            working.groupby(["name_key", "team"], as_index=False)
            .agg(
                nflverse_player_id=("player_id", "last"),
                usage_player_name=("player_name", "last"),
                usage_games=("week", "nunique"),
                passing_attempts=("passing_attempts", "mean"),
                carries=("carries", "mean"),
                targets=("targets", "mean"),
                receptions=("receptions", "mean"),
                rushing_yards=("rushing_yards", "mean"),
                receiving_yards=("receiving_yards", "mean"),
                passing_yards=("passing_yards", "mean"),
                recent_fantasy_points=("recent_fantasy_points", "mean"),
            )
        )
        numeric_columns = [
            "passing_attempts",
            "carries",
            "targets",
            "receptions",
            "rushing_yards",
            "receiving_yards",
            "passing_yards",
            "recent_fantasy_points",
        ]
        grouped[numeric_columns] = grouped[numeric_columns].round(2)

        return UsageDataResult(
            player_usage=grouped,
            source_rows=len(working),
            weeks_used=weeks_used,
            source_url=PLAYER_STATS_URL.format(season=int(season)),
        )


def enrich_player_pool_with_usage(
    players: pd.DataFrame,
    usage: pd.DataFrame,
) -> UsageEnrichmentResult:
    """Attach summarized usage by normalized player name and team."""

    output = players.copy().reset_index(drop=True)
    output["name_key"] = output["name"].map(_normalize_name)
    output["team_key"] = output["team"].map(_normalize_team)

    if usage.empty:
        output["usage_matched"] = False
        output = output.drop(columns=["name_key", "team_key"])
        return UsageEnrichmentResult(
            player_pool=output,
            match_report=pd.DataFrame(
                [{"Players": len(output), "Matched": 0, "Match rate": 0.0}]
            ),
            unmatched_players=output[["name", "position", "team"]].copy(),
        )

    usage_copy = usage.copy()
    usage_copy["team_key"] = usage_copy["team"].map(_normalize_team)
    usage_copy = usage_copy.drop(columns=["team"], errors="ignore")

    output = output.merge(
        usage_copy,
        how="left",
        on=["name_key", "team_key"],
        validate="many_to_one",
    )
    output["usage_matched"] = output["usage_games"].notna()
    output["usage_games"] = pd.to_numeric(
        output["usage_games"], errors="coerce"
    ).fillna(0).astype(int)

    usage_columns = [
        "passing_attempts",
        "carries",
        "targets",
        "receptions",
        "rushing_yards",
        "receiving_yards",
        "passing_yards",
        "recent_fantasy_points",
    ]
    for column in usage_columns:
        output[column] = pd.to_numeric(output[column], errors="coerce")

    matched = int(output["usage_matched"].sum())
    match_rate = round(matched / len(output) * 100.0, 1) if len(output) else 0.0
    unmatched = output.loc[
        ~output["usage_matched"], ["name", "position", "team"]
    ].copy()
    output = output.drop(columns=["name_key", "team_key"])

    return UsageEnrichmentResult(
        player_pool=output,
        match_report=pd.DataFrame(
            [{"Players": len(output), "Matched": matched, "Match rate": match_rate}]
        ),
        unmatched_players=unmatched,
    )
