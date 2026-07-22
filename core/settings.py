from __future__ import annotations

from dataclasses import dataclass

from config import SALARY_CAP


@dataclass(frozen=True)
class OptimizerSettings:
    """Configuration values used when generating DFS lineups."""

    salary_cap: int = SALARY_CAP
    minimum_salary: int = 0
    solver_timeout_seconds: float = 15.0
    lineup_count: int = 1
    minimum_unique_players: int = 1

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

        if self.lineup_count < 1:
            raise ValueError(
                "At least one lineup must be requested."
            )

        if self.lineup_count > 150:
            raise ValueError(
                "No more than 150 lineups may be generated at once."
            )

        if self.minimum_unique_players < 1:
            raise ValueError(
                "Minimum unique players must be at least one."
            )

        if self.minimum_unique_players > 9:
            raise ValueError(
                "Minimum unique players cannot exceed nine."
            )

    @property
    def maximum_overlap(self) -> int:
        """
        Return the maximum number of shared players between two lineups.

        A DraftKings NFL Classic lineup contains nine players.
        """

        return 9 - self.minimum_unique_players