from __future__ import annotations

import pandas as pd
from ortools.sat.python import cp_model


BRING_BACK_POSITIONS = {
    "RB",
    "WR",
    "TE",
}


def add_bring_back_constraints(
    model: cp_model.CpModel,
    pool: pd.DataFrame,
    selected_player: dict[int, cp_model.IntVar],
    require_bring_back: bool,
) -> None:
    """
    Require each selected quarterback to have an opposing bring-back.

    Eligible bring-back positions are RB, WR, and TE.
    """

    if not require_bring_back:
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
        opponent = str(
            quarterback["opponent"]
        ).upper().strip()

        opponent_variables = [
            selected_player[player_index]
            for player_index, player in pool.iterrows()
            if str(player["team"]).upper().strip() == opponent
            and player["position"] in BRING_BACK_POSITIONS
        ]

        if not opponent_variables:
            model.Add(
                selected_player[qb_index] == 0
            )
            continue

        model.Add(
            sum(opponent_variables)
            >= selected_player[qb_index]
        )
