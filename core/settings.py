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
    qb_stack_size: int = 0
    require_bring_back: bool = False
    maximum_players_per_team: int = 0

    def validate(self) -> None:
        """Validate optimizer settings before they are used."""

        if self.salary_cap <= 0:
            raise ValueError(
                "Salary cap must be greater than zero."
            )

        if self.minimum_salary < 0:
            raise ValueError(
                "Minimum salary cannot be negative."
            )

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

        if self.qb_stack_size not in {0, 1, 2}:
            raise ValueError(
                "QB stack size must be 0, 1, or 2."
            )

        if not isinstance(
            self.require_bring_back,
            bool,
        ):
            raise ValueError(
                "Require bring-back must be true or false."
            )

        if self.maximum_players_per_team not in {0, 3, 4, 5}:
            raise ValueError(
                "Maximum players per team must be 0, 3, 4, or 5."
            )

    @property
    def maximum_overlap(self) -> int:
        """Return the maximum shared players between two lineups."""

        return 9 - self.minimum_unique_players
