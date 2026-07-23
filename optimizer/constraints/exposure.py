from __future__ import annotations

import math

import pandas as pd


def normalize_player_exposures(
    player_max_exposures: dict[str, float] | None,
) -> dict[str, float]:
    """
    Normalize player IDs and validate maximum exposure values.

    Exposure values must be between 0.0 and 1.0.
    """

    normalized_exposures = {
        str(player_id): float(exposure)
        for player_id, exposure in (
            player_max_exposures
            or {}
        ).items()
    }

    for (
        player_id,
        exposure,
    ) in normalized_exposures.items():
        if exposure < 0 or exposure > 1:
            raise ValueError(
                "Player maximum exposures must be between "
                "0% and 100%. Invalid player ID: "
                f"{player_id}"
            )

    return normalized_exposures


def calculate_maximum_appearances(
    lineup_count: int,
    exposure: float,
) -> int:
    """
    Convert a maximum exposure percentage to a lineup count.

    Ceiling is used because small lineup portfolios cannot always
    represent percentages exactly.
    """

    if lineup_count < 1:
        raise ValueError(
            "Lineup count must be at least one."
        )

    if exposure < 0 or exposure > 1:
        raise ValueError(
            "Exposure must be between 0.0 and 1.0."
        )

    if exposure == 0:
        return 0

    return min(
        lineup_count,
        max(
            1,
            math.ceil(
                lineup_count
                * exposure
                - 1e-9
            ),
        ),
    )


def build_maximum_appearances(
    pool: pd.DataFrame,
    lineup_count: int,
    player_max_exposures: dict[str, float] | None,
) -> dict[str, int]:
    """
    Build the maximum number of appearances allowed for each player.

    Players without an explicit exposure setting default to 100%.
    Locked players are always allowed in every requested lineup.
    """

    if "player_id" not in pool.columns:
        raise ValueError(
            "Player pool is missing the player_id column."
        )

    normalized_exposures = normalize_player_exposures(
        player_max_exposures
    )

    maximum_appearances: dict[str, int] = {}

    for _, player in pool.iterrows():
        player_id = str(
            player["player_id"]
        )

        is_locked = bool(
            player.get(
                "locked",
                False,
            )
        )

        exposure = (
            1.0
            if is_locked
            else normalized_exposures.get(
                player_id,
                1.0,
            )
        )

        maximum_appearances[player_id] = (
            calculate_maximum_appearances(
                lineup_count=lineup_count,
                exposure=exposure,
            )
        )

    return maximum_appearances


def initialize_player_appearance_counts(
    pool: pd.DataFrame,
) -> dict[str, int]:
    """Create a zeroed appearance count for every player."""

    if "player_id" not in pool.columns:
        raise ValueError(
            "Player pool is missing the player_id column."
        )

    return {
        str(player_id): 0
        for player_id in (
            pool["player_id"]
            .astype(str)
        )
    }


def get_unavailable_player_ids(
    player_appearance_counts: dict[str, int],
    maximum_appearances: dict[str, int],
) -> set[str]:
    """
    Return players who have reached their maximum appearance count.
    """

    missing_player_ids = (
        set(player_appearance_counts)
        - set(maximum_appearances)
    )

    if missing_player_ids:
        raise ValueError(
            "Maximum appearances are missing for player IDs: "
            + ", ".join(
                sorted(
                    missing_player_ids
                )
            )
        )

    return {
        str(player_id)
        for (
            player_id,
            appearance_count,
        ) in player_appearance_counts.items()
        if int(appearance_count)
        >= int(
            maximum_appearances[
                player_id
            ]
        )
    }


def record_player_appearances(
    selected_player_ids: set[str],
    player_appearance_counts: dict[str, int],
) -> None:
    """Increment appearance counts after a lineup is generated."""

    for player_id in selected_player_ids:
        normalized_player_id = str(
            player_id
        )

        if normalized_player_id not in (
            player_appearance_counts
        ):
            raise ValueError(
                "Cannot record appearance for unknown player ID: "
                f"{normalized_player_id}"
            )

        player_appearance_counts[
            normalized_player_id
        ] += 1