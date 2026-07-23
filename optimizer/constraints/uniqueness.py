from __future__ import annotations

import pandas as pd
from ortools.sat.python import cp_model


def add_lineup_uniqueness_constraints(
    model: cp_model.CpModel,
    pool: pd.DataFrame,
    selected_player: dict[int, cp_model.IntVar],
    previous_player_sets: list[set[str]],
    maximum_overlap: int,
) -> None:
    """
    Limit how many players a new lineup may share with prior lineups.

    Example:
        A nine-player lineup requiring two unique players may overlap
        with each previous lineup by at most seven players.
    """

    if maximum_overlap < 0:
        raise ValueError(
            "Maximum lineup overlap cannot be negative."
        )

    missing_player_indexes = (
        set(pool.index)
        - set(selected_player)
    )

    if missing_player_indexes:
        raise ValueError(
            "Selected-player variables are missing for player "
            f"indexes: {sorted(missing_player_indexes)}"
        )

    normalized_previous_sets = [
        {
            str(player_id)
            for player_id in previous_player_ids
        }
        for previous_player_ids in previous_player_sets
    ]

    for previous_player_ids in normalized_previous_sets:
        overlap_variables = [
            selected_player[player_index]
            for player_index in pool.index
            if str(
                pool.at[
                    player_index,
                    "player_id",
                ]
            )
            in previous_player_ids
        ]

        if overlap_variables:
            model.Add(
                sum(overlap_variables)
                <= int(maximum_overlap)
            )