from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from ortools.sat.python import cp_model

from config import FLEX_POSITIONS, ROSTER_SLOTS, SALARY_CAP


@dataclass
class OptimizationResult:
    lineup: pd.DataFrame
    total_salary: int
    total_projection: float
    status: str


def _eligible_slots(position: str) -> list[str]:
    position = position.upper().strip()

    if position == "QB":
        return ["QB"]
    if position == "RB":
        return ["RB1", "RB2", "FLEX"]
    if position == "WR":
        return ["WR1", "WR2", "WR3", "FLEX"]
    if position == "TE":
        return ["TE", "FLEX"]
    if position in {"DST", "D/ST", "DEF"}:
        return ["DST"]

    return []


def optimize_lineup(
    players: pd.DataFrame,
    salary_cap: int = SALARY_CAP,
    minimum_salary: int = 0,
) -> OptimizationResult:
    required = {
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
    missing = required - set(players.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    pool = players.copy().reset_index(drop=True)
    pool["position"] = pool["position"].astype(str).str.upper().str.strip()
    pool["salary"] = pd.to_numeric(pool["salary"], errors="raise").astype(int)
    pool["projection"] = pd.to_numeric(pool["projection"], errors="raise").astype(float)
    pool["locked"] = pool["locked"].fillna(False).astype(bool)
    pool["excluded"] = pool["excluded"].fillna(False).astype(bool)

    if (pool["locked"] & pool["excluded"]).any():
        names = pool.loc[pool["locked"] & pool["excluded"], "name"].tolist()
        raise ValueError(
            "A player cannot be both locked and excluded: " + ", ".join(names)
        )

    model = cp_model.CpModel()
    assignment: dict[tuple[int, str], cp_model.IntVar] = {}

    for i, row in pool.iterrows():
        for slot in _eligible_slots(row["position"]):
            assignment[(i, slot)] = model.new_bool_var(f"p_{i}_{slot}")

    # Every roster slot must contain exactly one player.
    for slot in ROSTER_SLOTS:
        slot_vars = [
            variable
            for (player_index, roster_slot), variable in assignment.items()
            if roster_slot == slot
        ]
        if not slot_vars:
            raise ValueError(f"No eligible players are available for the {slot} slot.")
        model.add(sum(slot_vars) == 1)

    # A player may appear no more than once.
    for i in pool.index:
        player_vars = [
            variable
            for (player_index, _), variable in assignment.items()
            if player_index == i
        ]
        if player_vars:
            model.add(sum(player_vars) <= 1)

            if bool(pool.at[i, "locked"]):
                model.add(sum(player_vars) == 1)

            if bool(pool.at[i, "excluded"]):
                model.add(sum(player_vars) == 0)

    salary_expression = sum(
        int(pool.at[i, "salary"]) * variable
        for (i, _), variable in assignment.items()
    )
    model.add(salary_expression <= int(salary_cap))

    if minimum_salary > 0:
        model.add(salary_expression >= int(minimum_salary))

    # CP-SAT uses integer coefficients, so scale projections by 100.
    projection_expression = sum(
        int(round(float(pool.at[i, "projection"]) * 100)) * variable
        for (i, _), variable in assignment.items()
    )
    model.maximize(projection_expression)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15.0
    status_code = solver.solve(model)
    status_name = solver.status_name(status_code)

    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return OptimizationResult(
            lineup=pd.DataFrame(),
            total_salary=0,
            total_projection=0.0,
            status=status_name,
        )

    selected_rows: list[dict] = []
    for (i, slot), variable in assignment.items():
        if solver.value(variable) == 1:
            row = pool.loc[i].to_dict()
            row["roster_slot"] = slot
            selected_rows.append(row)

    lineup = pd.DataFrame(selected_rows)
    slot_order = {slot: order for order, slot in enumerate(ROSTER_SLOTS)}
    lineup["_slot_order"] = lineup["roster_slot"].map(slot_order)
    lineup = (
        lineup.sort_values("_slot_order")
        .drop(columns=["_slot_order"])
        .reset_index(drop=True)
    )

    return OptimizationResult(
        lineup=lineup,
        total_salary=int(lineup["salary"].sum()),
        total_projection=float(lineup["projection"].sum()),
        status=status_name,
    )
