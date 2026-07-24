from __future__ import annotations

import pandas as pd
from ortools.sat.python import cp_model


VALID_BLOCKED_POSITIONS = {"QB", "RB", "WR", "TE"}


def add_dst_correlation_constraints(
    model: cp_model.CpModel,
    pool: pd.DataFrame,
    selected_player: dict[int, cp_model.IntVar],
    blocked_opposing_positions: set[str] | frozenset[str] | tuple[str, ...],
) -> None:
    """Block selected DSTs from being paired with specified opposing positions."""

    normalized_positions = {
        str(position).upper().strip()
        for position in blocked_opposing_positions
    }

    invalid_positions = normalized_positions - VALID_BLOCKED_POSITIONS
    if invalid_positions:
        raise ValueError(
            "Unsupported DST correlation positions: "
            f"{sorted(invalid_positions)}"
        )

    if not normalized_positions:
        return

    missing_player_indexes = set(pool.index) - set(selected_player)
    if missing_player_indexes:
        raise ValueError(
            "Selected-player variables are missing for player indexes: "
            f"{sorted(missing_player_indexes)}"
        )

    defenses = pool.loc[pool["position"] == "DST"]

    for dst_index, defense in defenses.iterrows():
        opponent = str(defense["opponent"]).upper().strip()
        if not opponent:
            continue

        opposing_indexes = [
            player_index
            for player_index, player in pool.iterrows()
            if str(player["team"]).upper().strip() == opponent
            and str(player["position"]).upper().strip()
            in normalized_positions
        ]

        for player_index in opposing_indexes:
            model.Add(
                selected_player[dst_index]
                + selected_player[player_index]
                <= 1
            )
