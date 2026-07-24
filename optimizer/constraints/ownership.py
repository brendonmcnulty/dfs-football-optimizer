from __future__ import annotations

import pandas as pd
from ortools.sat.python import cp_model


def add_ownership_constraints(
    model: cp_model.CpModel,
    pool: pd.DataFrame,
    selected_player: dict[int, cp_model.IntVar],
    maximum_total_ownership: float | None,
) -> None:
    """Limit the summed projected ownership of a lineup.

    Ownership values are stored as percentage points. For example, 18.5
    means an expected ownership of 18.5%, and a lineup total of 140 means
    the nine selected players sum to 140% projected ownership.
    """

    if maximum_total_ownership is None:
        return

    if maximum_total_ownership < 0:
        raise ValueError(
            "Maximum total ownership cannot be negative."
        )

    ownership_scale = 100
    maximum_scaled = int(
        round(float(maximum_total_ownership) * ownership_scale)
    )

    model.Add(
        sum(
            int(
                round(
                    float(pool.at[player_index, "ownership"])
                    * ownership_scale
                )
            )
            * selected_player[player_index]
            for player_index in pool.index
        )
        <= maximum_scaled
    )
