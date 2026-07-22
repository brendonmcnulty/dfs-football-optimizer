from __future__ import annotations

import pandas as pd
from ortools.sat.python import cp_model


def add_player_availability_constraints(
    model: cp_model.CpModel,
    pool: pd.DataFrame,
    selected_player: dict[int, cp_model.IntVar],
    unavailable_player_ids: set[str] | None = None,
) -> None:
    """
    Add lock, exclusion, and temporary availability constraints.

    Locked players must appear in the lineup.

    Excluded players cannot appear in the lineup.

    Unavailable players cannot appear in the current lineup. This is
    used when a player has already reached a maximum exposure limit.
    """

    required_columns = {
        "player_id",
        "locked",
        "excluded",
    }

    missing_columns = (
        required_columns
        - set(pool.columns)
    )

    if missing_columns:
        raise ValueError(
            "Missing columns required for player availability "
            f"constraints: {sorted(missing_columns)}"
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

    normalized_unavailable_ids = {
        str(player_id)
        for player_id in (
            unavailable_player_ids
            or set()
        )
    }

    for player_index in pool.index:
        player_id = str(
            pool.at[
                player_index,
                "player_id",
            ]
        )

        is_locked = bool(
            pool.at[
                player_index,
                "locked",
            ]
        )

        is_excluded = bool(
            pool.at[
                player_index,
                "excluded",
            ]
        )

        is_unavailable = (
            player_id
            in normalized_unavailable_ids
        )

        if is_locked and is_excluded:
            player_name = (
                str(
                    pool.at[
                        player_index,
                        "name",
                    ]
                )
                if "name" in pool.columns
                else player_id
            )

            raise ValueError(
                "A player cannot be both locked and excluded: "
                f"{player_name}"
            )

        if is_locked and is_unavailable:
            player_name = (
                str(
                    pool.at[
                        player_index,
                        "name",
                    ]
                )
                if "name" in pool.columns
                else player_id
            )

            raise ValueError(
                "A locked player has reached the maximum exposure "
                f"limit: {player_name}"
            )

        if is_locked:
            model.Add(
                selected_player[player_index]
                == 1
            )

        if is_excluded or is_unavailable:
            model.Add(
                selected_player[player_index]
                == 0
            )