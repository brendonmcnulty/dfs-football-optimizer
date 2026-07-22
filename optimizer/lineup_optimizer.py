from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from ortools.sat.python import cp_model

from config import ROSTER_SLOTS, SALARY_CAP


@dataclass
class OptimizationResult:
    """Represent one completed lineup optimization result."""

    lineup: pd.DataFrame
    total_salary: int
    total_projection: float
    status: str


def _eligible_slots(position: str) -> list[str]:
    """Return roster slots that a position may fill."""

    normalized_position = position.upper().strip()

    if normalized_position == "QB":
        return ["QB"]

    if normalized_position == "RB":
        return ["RB1", "RB2", "FLEX"]

    if normalized_position == "WR":
        return ["WR1", "WR2", "WR3", "FLEX"]

    if normalized_position == "TE":
        return ["TE", "FLEX"]

    if normalized_position in {"DST", "D/ST", "DEF"}:
        return ["DST"]

    return []


def _prepare_players(players: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize the optimizer player pool."""

    required_columns = {
        "player_id",
        "name",
        "position",
        "team",
        "opponent",
        "salary",
        "projection",
        "locked",
        "excluded",
    }

    missing_columns = required_columns - set(players.columns)

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            f"{sorted(missing_columns)}"
        )

    pool = players.copy().reset_index(drop=True)

    pool["player_id"] = pool["player_id"].astype(str)

    pool["position"] = (
        pool["position"]
        .astype(str)
        .str.upper()
        .str.strip()
        .replace(
            {
                "D/ST": "DST",
                "DEF": "DST",
            }
        )
    )

    pool["salary"] = pd.to_numeric(
        pool["salary"],
        errors="raise",
    ).astype(int)

    pool["projection"] = pd.to_numeric(
        pool["projection"],
        errors="raise",
    ).astype(float)

    pool["locked"] = (
        pool["locked"]
        .fillna(False)
        .astype(bool)
    )

    pool["excluded"] = (
        pool["excluded"]
        .fillna(False)
        .astype(bool)
    )

    conflicting_mask = pool["locked"] & pool["excluded"]

    if conflicting_mask.any():
        conflicting_names = pool.loc[
            conflicting_mask,
            "name",
        ].astype(str).tolist()

        raise ValueError(
            "A player cannot be both locked and excluded: "
            + ", ".join(conflicting_names)
        )

    return pool


def _solve_lineup(
    pool: pd.DataFrame,
    salary_cap: int,
    minimum_salary: int,
    solver_timeout_seconds: float,
    previous_player_sets: list[set[str]],
    maximum_overlap: int,
) -> OptimizationResult:
    """Solve one lineup while respecting prior-lineup overlap limits."""

    model = cp_model.CpModel()

    assignment: dict[
        tuple[int, str],
        cp_model.IntVar,
    ] = {}

    selected_player: dict[
        int,
        cp_model.IntVar,
    ] = {}

    for player_index, player in pool.iterrows():
        player_id = str(player["player_id"])

        selected_player[player_index] = model.NewBoolVar(
            f"selected_{player_index}_{player_id}"
        )

        eligible_slots = _eligible_slots(
            str(player["position"])
        )

        player_slot_variables: list[cp_model.IntVar] = []

        for roster_slot in eligible_slots:
            slot_variable = model.NewBoolVar(
                f"player_{player_index}_{roster_slot}"
            )

            assignment[
                (player_index, roster_slot)
            ] = slot_variable

            player_slot_variables.append(slot_variable)

        if player_slot_variables:
            model.Add(
                selected_player[player_index]
                == sum(player_slot_variables)
            )
        else:
            model.Add(
                selected_player[player_index] == 0
            )

    for roster_slot in ROSTER_SLOTS:
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
            sum(roster_slot_variables) == 1
        )

    for player_index in pool.index:
        player_variables = [
            variable
            for (
                assigned_player_index,
                roster_slot,
            ), variable in assignment.items()
            if assigned_player_index == player_index
        ]

        if player_variables:
            model.Add(
                sum(player_variables) <= 1
            )

        if bool(pool.at[player_index, "locked"]):
            model.Add(
                selected_player[player_index] == 1
            )

        if bool(pool.at[player_index, "excluded"]):
            model.Add(
                selected_player[player_index] == 0
            )

    salary_expression = sum(
        int(pool.at[player_index, "salary"])
        * selected_player[player_index]
        for player_index in pool.index
    )

    model.Add(
        salary_expression <= int(salary_cap)
    )

    if minimum_salary > 0:
        model.Add(
            salary_expression >= int(minimum_salary)
        )

    for previous_player_ids in previous_player_sets:
        overlap_variables = [
            selected_player[player_index]
            for player_index in pool.index
            if str(
                pool.at[player_index, "player_id"]
            ) in previous_player_ids
        ]

        if overlap_variables:
            model.Add(
                sum(overlap_variables)
                <= int(maximum_overlap)
            )

    projection_expression = sum(
        int(
            round(
                float(
                    pool.at[player_index, "projection"]
                )
                * 100
            )
        )
        * selected_player[player_index]
        for player_index in pool.index
    )

    model.Maximize(projection_expression)

    solver = cp_model.CpSolver()

    solver.parameters.max_time_in_seconds = float(
        solver_timeout_seconds
    )

    status_code = solver.Solve(model)
    status_name = solver.StatusName(status_code)

    if status_code not in {
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
    }:
        return OptimizationResult(
            lineup=pd.DataFrame(),
            total_salary=0,
            total_projection=0.0,
            status=status_name,
        )

    selected_rows: list[dict] = []

    for (
        player_index,
        roster_slot,
    ), variable in assignment.items():
        if solver.Value(variable) == 1:
            player_record = pool.loc[
                player_index
            ].to_dict()

            player_record["roster_slot"] = (
                roster_slot
            )

            selected_rows.append(player_record)

    lineup = pd.DataFrame(selected_rows)

    slot_order = {
        roster_slot: order
        for order, roster_slot in enumerate(
            ROSTER_SLOTS
        )
    }

    lineup["_slot_order"] = lineup[
        "roster_slot"
    ].map(slot_order)

    lineup = (
        lineup.sort_values("_slot_order")
        .drop(columns=["_slot_order"])
        .reset_index(drop=True)
    )

    return OptimizationResult(
        lineup=lineup,
        total_salary=int(
            lineup["salary"].sum()
        ),
        total_projection=float(
            lineup["projection"].sum()
        ),
        status=status_name,
    )


def optimize_lineups(
    players: pd.DataFrame,
    lineup_count: int = 1,
    minimum_unique_players: int = 1,
    salary_cap: int = SALARY_CAP,
    minimum_salary: int = 0,
    solver_timeout_seconds: float = 15.0,
) -> list[OptimizationResult]:
    """
    Generate multiple lineups with a minimum uniqueness requirement.

    Each lineup must differ from every previously generated lineup by at
    least `minimum_unique_players`.
    """

    if lineup_count < 1:
        raise ValueError(
            "Lineup count must be at least one."
        )

    if lineup_count > 150:
        raise ValueError(
            "Lineup count cannot exceed 150."
        )

    if minimum_unique_players < 1:
        raise ValueError(
            "Minimum unique players must be at least one."
        )

    if minimum_unique_players > 9:
        raise ValueError(
            "Minimum unique players cannot exceed nine."
        )

    pool = _prepare_players(players)

    maximum_overlap = (
        9 - int(minimum_unique_players)
    )

    generated_results: list[
        OptimizationResult
    ] = []

    previous_player_sets: list[
        set[str]
    ] = []

    for lineup_number in range(lineup_count):
        result = _solve_lineup(
            pool=pool,
            salary_cap=int(salary_cap),
            minimum_salary=int(minimum_salary),
            solver_timeout_seconds=float(
                solver_timeout_seconds
            ),
            previous_player_sets=previous_player_sets,
            maximum_overlap=maximum_overlap,
        )

        if result.lineup.empty:
            break

        generated_results.append(result)

        previous_player_sets.append(
            set(
                result.lineup[
                    "player_id"
                ].astype(str)
            )
        )

    return generated_results


def optimize_lineup(
    players: pd.DataFrame,
    salary_cap: int = SALARY_CAP,
    minimum_salary: int = 0,
    solver_timeout_seconds: float = 15.0,
) -> OptimizationResult:
    """
    Generate one optimized lineup.

    This wrapper preserves compatibility with existing application code.
    """

    results = optimize_lineups(
        players=players,
        lineup_count=1,
        minimum_unique_players=1,
        salary_cap=salary_cap,
        minimum_salary=minimum_salary,
        solver_timeout_seconds=solver_timeout_seconds,
    )

    if not results:
        return OptimizationResult(
            lineup=pd.DataFrame(),
            total_salary=0,
            total_projection=0.0,
            status="INFEASIBLE",
        )

    return results[0]