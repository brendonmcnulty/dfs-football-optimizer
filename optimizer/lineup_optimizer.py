from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from ortools.sat.python import cp_model

from config import ROSTER_SLOTS, SALARY_CAP
from optimizer.constraints import (
    add_bring_back_constraints,
    add_dst_correlation_constraints,
    add_lineup_uniqueness_constraints,
    add_player_availability_constraints,
    add_position_constraints,
    add_qb_stack_constraints,
    add_salary_constraints,
    add_team_limit_constraints,
    build_maximum_appearances,
    get_unavailable_player_ids,
    initialize_player_appearance_counts,
    record_player_appearances,
)


@dataclass
class OptimizationResult:
    """Represent one completed lineup optimization result."""

    lineup: pd.DataFrame
    total_salary: int
    total_projection: float
    status: str


def _prepare_players(
    players: pd.DataFrame,
) -> pd.DataFrame:
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

    pool["team"] = (
        pool["team"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    pool["opponent"] = (
        pool["opponent"]
        .fillna("")
        .astype(str)
        .str.upper()
        .str.strip()
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
        conflicting_names = (
            pool.loc[
                conflicting_mask,
                "name",
            ]
            .astype(str)
            .tolist()
        )

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
    unavailable_player_ids: set[str],
    qb_stack_size: int,
    require_bring_back: bool,
    maximum_players_per_team: int | None,
    blocked_dst_opposing_positions: tuple[str, ...],
) -> OptimizationResult:
    """Solve one lineup."""

    model = cp_model.CpModel()

    assignment, selected_player = add_position_constraints(
        model=model,
        pool=pool,
        roster_slots=list(ROSTER_SLOTS),
    )

    add_player_availability_constraints(
        model=model,
        pool=pool,
        selected_player=selected_player,
        unavailable_player_ids=unavailable_player_ids,
    )

    add_salary_constraints(
        model=model,
        pool=pool,
        selected_player=selected_player,
        salary_cap=int(salary_cap),
        minimum_salary=int(minimum_salary),
    )

    add_lineup_uniqueness_constraints(
        model=model,
        pool=pool,
        selected_player=selected_player,
        previous_player_sets=previous_player_sets,
        maximum_overlap=int(maximum_overlap),
    )

    add_qb_stack_constraints(
        model=model,
        pool=pool,
        selected_player=selected_player,
        stack_size=int(qb_stack_size),
    )

    add_bring_back_constraints(
        model=model,
        pool=pool,
        selected_player=selected_player,
        require_bring_back=bool(
            require_bring_back
        ),
    )

    add_team_limit_constraints(
        model=model,
        pool=pool,
        selected_player=selected_player,
        maximum_players_per_team=maximum_players_per_team,
    )

    add_dst_correlation_constraints(
        model=model,
        pool=pool,
        selected_player=selected_player,
        blocked_opposing_positions=blocked_dst_opposing_positions,
    )

    projection_expression = sum(
        int(
            round(
                float(
                    pool.at[
                        player_index,
                        "projection",
                    ]
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

            player_record["roster_slot"] = roster_slot
            selected_rows.append(player_record)

    lineup = pd.DataFrame(selected_rows)

    slot_order = {
        roster_slot: order
        for order, roster_slot in enumerate(
            ROSTER_SLOTS
        )
    }

    lineup["_slot_order"] = (
        lineup["roster_slot"]
        .map(slot_order)
    )

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
    player_max_exposures: (
        dict[str, float] | None
    ) = None,
    qb_stack_size: int = 0,
    require_bring_back: bool = False,
    maximum_players_per_team: int | None = None,
    blocked_dst_opposing_positions: tuple[str, ...] = ("QB", "WR"),
) -> list[OptimizationResult]:
    """Generate multiple lineups with exposure and QB stacking."""

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

    roster_size = len(ROSTER_SLOTS)

    if minimum_unique_players > roster_size:
        raise ValueError(
            "Minimum unique players cannot exceed "
            f"{roster_size}."
        )

    if qb_stack_size not in {0, 1, 2}:
        raise ValueError(
            "QB stack size must be 0, 1, or 2."
        )

    pool = _prepare_players(players)

    maximum_appearances = build_maximum_appearances(
        pool=pool,
        lineup_count=int(lineup_count),
        player_max_exposures=player_max_exposures,
    )

    maximum_overlap = (
        roster_size
        - int(minimum_unique_players)
    )

    generated_results: list[
        OptimizationResult
    ] = []

    previous_player_sets: list[
        set[str]
    ] = []

    player_appearance_counts = (
        initialize_player_appearance_counts(
            pool=pool
        )
    )

    for _ in range(lineup_count):
        unavailable_player_ids = (
            get_unavailable_player_ids(
                player_appearance_counts=(
                    player_appearance_counts
                ),
                maximum_appearances=(
                    maximum_appearances
                ),
            )
        )

        result = _solve_lineup(
            pool=pool,
            salary_cap=int(salary_cap),
            minimum_salary=int(minimum_salary),
            solver_timeout_seconds=float(
                solver_timeout_seconds
            ),
            previous_player_sets=(
                previous_player_sets
            ),
            maximum_overlap=maximum_overlap,
            unavailable_player_ids=(
                unavailable_player_ids
            ),
            qb_stack_size=int(qb_stack_size),
            require_bring_back=bool(
                require_bring_back
            ),
            maximum_players_per_team=maximum_players_per_team,
            blocked_dst_opposing_positions=tuple(
                blocked_dst_opposing_positions
            ),
        )

        if result.lineup.empty:
            break

        generated_results.append(result)

        selected_player_ids = set(
            result.lineup[
                "player_id"
            ].astype(str)
        )

        previous_player_sets.append(
            selected_player_ids
        )

        record_player_appearances(
            selected_player_ids=(
                selected_player_ids
            ),
            player_appearance_counts=(
                player_appearance_counts
            ),
        )

    return generated_results


def optimize_lineup(
    players: pd.DataFrame,
    salary_cap: int = SALARY_CAP,
    minimum_salary: int = 0,
    solver_timeout_seconds: float = 15.0,
    qb_stack_size: int = 0,
    require_bring_back: bool = False,
    maximum_players_per_team: int | None = None,
    blocked_dst_opposing_positions: tuple[str, ...] = ("QB", "WR"),
) -> OptimizationResult:
    """Generate one optimized lineup."""

    results = optimize_lineups(
        players=players,
        lineup_count=1,
        minimum_unique_players=1,
        salary_cap=salary_cap,
        minimum_salary=minimum_salary,
        solver_timeout_seconds=(
            solver_timeout_seconds
        ),
        qb_stack_size=int(qb_stack_size),
        require_bring_back=bool(
            require_bring_back
        ),
    )

    if not results:
        return OptimizationResult(
            lineup=pd.DataFrame(),
            total_salary=0,
            total_projection=0.0,
            status="INFEASIBLE",
        )

    return results[0]
