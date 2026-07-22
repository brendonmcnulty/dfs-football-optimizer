"""OR-Tools constraints used by the DFS lineup optimizer."""

from optimizer.constraints.salary import add_salary_constraints

__all__ = [
    "add_salary_constraints",
]