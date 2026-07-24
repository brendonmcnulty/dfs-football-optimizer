from __future__ import annotations

import pandas as pd
from ortools.sat.python import cp_model

from optimizer.constraints.exposure import calculate_maximum_appearances


def normalize_team_exposures(
    team_max_exposures: dict[str, float] | None,
) -> dict[str, float]:
    """Normalize team names and validate maximum exposure values."""

    normalized = {
        str(team).upper().strip(): float(exposure)
        for team, exposure in (team_max_exposures or {}).items()
    }

    for team, exposure in normalized.items():
        if not team:
            raise ValueError("Team exposure contains a blank team name.")
        if exposure < 0 or exposure > 1:
            raise ValueError(
                "Team maximum exposures must be between 0% and 100%. "
                f"Invalid team: {team}"
            )

    return normalized


def build_team_maximum_appearances(
    pool: pd.DataFrame,
    lineup_count: int,
    team_max_exposures: dict[str, float] | None,
) -> dict[str, int]:
    """Convert each team's maximum exposure into a lineup count."""

    if "team" not in pool.columns:
        raise ValueError("Player pool is missing the team column.")

    normalized = normalize_team_exposures(team_max_exposures)
    teams = sorted(
        {
            str(team).upper().strip()
            for team in pool["team"]
            if str(team).strip()
        }
    )

    unknown_teams = set(normalized) - set(teams)
    if unknown_teams:
        raise ValueError(
            "Maximum exposure was provided for an unknown team: "
            + ", ".join(sorted(unknown_teams))
        )

    return {
        team: calculate_maximum_appearances(
            lineup_count=lineup_count,
            exposure=normalized.get(team, 1.0),
        )
        for team in teams
    }


def initialize_team_appearance_counts(
    pool: pd.DataFrame,
) -> dict[str, int]:
    """Create a zeroed lineup-appearance count for every team."""

    return {
        str(team).upper().strip(): 0
        for team in pool["team"]
        if str(team).strip()
    }


def get_unavailable_teams(
    team_appearance_counts: dict[str, int],
    maximum_appearances: dict[str, int],
) -> set[str]:
    """Return teams that have reached their portfolio exposure cap."""

    return {
        team
        for team, count in team_appearance_counts.items()
        if count >= maximum_appearances[team]
    }


def add_unavailable_team_constraints(
    model: cp_model.CpModel,
    pool: pd.DataFrame,
    selected_player: dict[int, cp_model.IntVar],
    unavailable_teams: set[str],
) -> None:
    """Prevent players from teams that have reached their exposure cap."""

    normalized_unavailable = {
        str(team).upper().strip()
        for team in unavailable_teams
    }

    for player_index, player in pool.iterrows():
        team = str(player["team"]).upper().strip()
        if team in normalized_unavailable:
            model.Add(selected_player[player_index] == 0)


def record_team_appearances(
    selected_teams: set[str],
    team_appearance_counts: dict[str, int],
) -> None:
    """Count each selected NFL team once for a generated lineup."""

    for team in selected_teams:
        normalized_team = str(team).upper().strip()
        if normalized_team not in team_appearance_counts:
            raise ValueError(
                "Cannot record exposure for unknown team: "
                f"{normalized_team}"
            )
        team_appearance_counts[normalized_team] += 1
