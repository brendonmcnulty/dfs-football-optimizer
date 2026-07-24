from __future__ import annotations

import pandas as pd
from ortools.sat.python import cp_model


def add_team_limit_constraints(
    model: cp_model.CpModel,
    pool: pd.DataFrame,
    selected_player: dict[int, cp_model.IntVar],
    maximum_players_per_team: int,
) -> None:
    """Limit the number of selected players from each team.

    A value of zero disables the constraint.
    """

    if maximum_players_per_team == 0:
        return

    if maximum_players_per_team < 1:
        raise ValueError(
            "Maximum players per team must be zero or greater."
        )

    missing_player_indexes = set(pool.index) - set(selected_player)

    if missing_player_indexes:
        raise ValueError(
            "Selected-player variables are missing for player "
            f"indexes: {sorted(missing_player_indexes)}"
        )

    teams = sorted(
        team
        for team in pool["team"].dropna().astype(str).unique()
        if team.strip()
    )

    for team in teams:
        team_variables = [
            selected_player[player_index]
            for player_index, player in pool.iterrows()
            if str(player["team"]).strip() == team
        ]

        if team_variables:
            model.Add(
                sum(team_variables)
                <= int(maximum_players_per_team)
            )
