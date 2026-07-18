from __future__ import annotations

from dataclasses import dataclass

from config import SALARY_CAP


@dataclass(frozen=True)
class OptimizerSettings:
    """Configuration values used when generating DFS lineups."""

    salary_cap: int = SALARY_CAP
    minimum_salary: int = 0
    solver_timeout_seconds: float = 15.0

    def validate(self) -> None:
        """Validate optimizer settings before they are used."""

        if self.salary_cap <= 0:
            raise ValueError("Salary cap must be greater than zero.")

        if self.minimum_salary < 0:
            raise ValueError("Minimum salary cannot be negative.")

        if self.minimum_salary > self.salary_cap:
            raise ValueError(
                "Minimum salary cannot be greater than the salary cap."
            )

        if self.solver_timeout_seconds <= 0:
            raise ValueError(
                "Solver timeout must be greater than zero seconds."
            )