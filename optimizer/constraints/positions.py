from __future__ import annotations

import pandas as pd
from ortools.sat.python import cp_model


def eligible_roster_slots(position: str) -> list[str]:
    """Return the roster slots a player position may fill."""

    normalized_position = (
        str(position)
        .upper()
        .strip()
    )

    if normalized_position == "QB":
        return ["QB"]

    if normalized_position == "RB":
        return [
            "RB1",
            "RB2",
            "FLEX",
        ]

    if normalized_position == "WR":
        return [
            "WR1",
            "WR2",
            "WR3",
            "FLEX",
        ]

    if normalized_position == "TE":
        return [
            "TE",
            "FLEX",
        ]

    if normalized_position in {
        "DST",
        "D/ST",
        "DEF",
    }:
        return ["DST"]

    return []


def add_position_constraints(
    model: cp_model.CpModel,
    pool: pd.DataFrame,
    roster_slots: list[str],
) -> tuple[
    dict[tuple[int, str], cp_model.IntVar],
    dict[int, cp_model.IntVar],
]:
    """
    Create assignment variables and add roster-position constraints.

    Returns:
        assignment:
            Maps each eligible player/roster-slot combination to an
            OR-Tools Boolean variable.

        selected_player:
            Maps each player index to a Boolean variable indicating
            whether that player appears anywhere in the lineup.
    """

    required_columns = {
        "player_id",
        "position",
    }

    missing_columns = (
        required_columns
        - set(pool.columns)
    )

    if missing_columns:
        raise ValueError(
            "Missing columns required for position constraints: "
            f"{sorted(missing_columns)}"
        )

    if not roster_slots:
        raise ValueError(
            "At least one roster slot is required."
        )

    assignment: dict[
        tuple[int, str],
        cp_model.IntVar,
    ] = {}

    selected_player: dict[
        int,
        cp_model.IntVar,
    ] = {}

    for player_index, player in pool.iterrows():
        player_id = str(
            player["player_id"]
        )

        selected_player[player_index] = (
            model.NewBoolVar(
                f"selected_{player_index}_{player_id}"
            )
        )

        eligible_slots = eligible_roster_slots(
            str(player["position"])
        )

        player_slot_variables: list[
            cp_model.IntVar
        ] = []

        for roster_slot in eligible_slots:
            if roster_slot not in roster_slots:
                continue

            slot_variable = model.NewBoolVar(
                f"player_{player_index}_{roster_slot}"
            )

            assignment[
                (
                    player_index,
                    roster_slot,
                )
            ] = slot_variable

            player_slot_variables.append(
                slot_variable
            )

        if player_slot_variables:
            model.Add(
                selected_player[player_index]
                == sum(player_slot_variables)
            )
        else:
            model.Add(
                selected_player[player_index]
                == 0
            )

    for roster_slot in roster_slots:
        roster_slot_variables = [
            variable
            for (
                player_index,
                assigned_slot,
            ), variable in assignment.items()
            if assigned_slot == roster_slot
        ]

        if not roster_slot_variables:
            raise ValueError(
                "No eligible players are available for the "
                f"{roster_slot} roster slot."
            )

        model.Add(
            sum(roster_slot_variables)
            == 1
        )

    for player_index in pool.index:
        player_assignment_variables = [
            variable
            for (
                assigned_player_index,
                roster_slot,
            ), variable in assignment.items()
            if assigned_player_index == player_index
        ]

        if player_assignment_variables:
            model.Add(
                sum(player_assignment_variables)
                <= 1
            )

    return (
        assignment,
        selected_player,
    )