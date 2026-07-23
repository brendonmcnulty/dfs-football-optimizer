from __future__ import annotations

import pandas as pd
from ortools.sat.python import cp_model


PASS_CATCHER_POSITIONS = {
    "WR",
    "TE",
}


def add_qb_stack_constraints(
    model: cp_model.CpModel,
    pool: pd.DataFrame,
    selected_player: dict[int, cp_model.IntVar],
    stack_size: int,
) -> None:
    """Require every selected QB to have same-team WR/TE partners."""

    if stack_size not in {0, 1, 2}:
        raise ValueError(
            "QB stack size must be 0, 1, or 2."
        )

    if stack_size == 0:
        return

    missing_player_indexes = (
        set(pool.index)
        - set(selected_player)
    )

    if missing_player_indexes:
        raise ValueError(
            "Selected-player variables are missing for player "
            f"indexes: {sorted(missing_player_indexes)}"
        )

    quarterbacks = pool.loc[
        pool["position"] == "QB"
    ]

    for qb_index, quarterback in quarterbacks.iterrows():
        teammate_variables = [
            selected_player[player_index]
            for player_index, player in pool.iterrows()
            if player_index != qb_index
            and player["team"] == quarterback["team"]
            and player["position"]
            in PASS_CATCHER_POSITIONS
        ]

        if len(teammate_variables) < stack_size:
            model.Add(
                selected_player[qb_index] == 0
            )
            continue

        model.Add(
            sum(teammate_variables)
            >= (
                int(stack_size)
                * selected_player[qb_index]
            )
        )
