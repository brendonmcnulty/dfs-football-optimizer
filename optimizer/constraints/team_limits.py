from __future__ import annotations

import pandas as pd
from ortools.sat.python import cp_model


def add_team_limit_constraints(
    model: cp_model.CpModel,
    pool: pd.DataFrame,
    selected_player: dict[int, cp_model.IntVar],
    maximum_players_per_team: int | None,
) -> None:
    """Limit the number of selected players from any one team."""

    if maximum_players_per_team is None:
        return

    maximum_players_per_team = int(maximum_players_per_team)

    if maximum_players_per_team < 1:
        raise ValueError(
            "Maximum players per team must be at least one or None."
        )

    missing_player_indexes = set(pool.index) - set(selected_player)
    if missing_player_indexes:
        raise ValueError(
            "Selected-player variables are missing for player indexes: "
            f"{sorted(missing_player_indexes)}"
        )

    teams = sorted(
        {
            str(team).upper().strip()
            for team in pool["team"].dropna().tolist()
            if str(team).strip()
        }
    )

    for team in teams:
        team_variables = [
            selected_player[player_index]
            for player_index, player in pool.iterrows()
            if str(player["team"]).upper().strip() == team
        ]

        if team_variables:
            model.Add(
                sum(team_variables) <= maximum_players_per_team
            )
