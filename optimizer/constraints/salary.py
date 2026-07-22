from __future__ import annotations

import pandas as pd
from ortools.sat.python import cp_model


def add_salary_constraints(
    model: cp_model.CpModel,
    pool: pd.DataFrame,
    selected_player: dict[int, cp_model.IntVar],
    salary_cap: int,
    minimum_salary: int = 0,
) -> cp_model.LinearExpr:
    """
    Add maximum and optional minimum salary constraints.

    Returns the salary expression so the optimizer may reuse it later
    for reporting or additional rules.
    """

    if salary_cap <= 0:
        raise ValueError(
            "Salary cap must be greater than zero."
        )

    if minimum_salary < 0:
        raise ValueError(
            "Minimum salary cannot be negative."
        )

    if minimum_salary > salary_cap:
        raise ValueError(
            "Minimum salary cannot exceed the salary cap."
        )

    missing_player_indexes = (
        set(pool.index)
        - set(selected_player)
    )

    if missing_player_indexes:
        raise ValueError(
            "Selected-player variables are missing for "
            f"player indexes: {sorted(missing_player_indexes)}"
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

    return salary_expression