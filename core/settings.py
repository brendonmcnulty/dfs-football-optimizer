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
    maximum_players_per_team: int | None = None
    blocked_dst_opposing_positions: tuple[str, ...] = ("QB", "WR")
    minimum_players_from_primary_game: int | None = None
    maximum_players_per_game: int | None = None
    maximum_total_ownership: float | None = None
    optimization_target: str = "projection"

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

        if (
            self.maximum_players_per_team is not None
            and self.maximum_players_per_team < 1
        ):
            raise ValueError(
                "Maximum players per team must be at least one or None."
            )

        valid_dst_positions = {"QB", "RB", "WR", "TE"}
        normalized_dst_positions = {
            str(position).upper().strip()
            for position in self.blocked_dst_opposing_positions
        }
        invalid_dst_positions = (
            normalized_dst_positions - valid_dst_positions
        )

        if invalid_dst_positions:
            raise ValueError(
                "Unsupported DST correlation positions: "
                f"{sorted(invalid_dst_positions)}"
            )

        if (
            self.minimum_players_from_primary_game is not None
            and self.minimum_players_from_primary_game not in {3, 4, 5}
        ):
            raise ValueError(
                "Minimum players from the primary game must be "
                "3, 4, 5, or None."
            )

        if (
            self.maximum_players_per_game is not None
            and self.maximum_players_per_game not in {5, 6}
        ):
            raise ValueError(
                "Maximum players per game must be 5, 6, or None."
            )

        if (
            self.minimum_players_from_primary_game is not None
            and self.maximum_players_per_game is not None
            and self.minimum_players_from_primary_game
            > self.maximum_players_per_game
        ):
            raise ValueError(
                "The primary-game minimum cannot exceed the "
                "maximum players per game."
            )

        if (
            self.maximum_total_ownership is not None
            and self.maximum_total_ownership < 0
        ):
            raise ValueError(
                "Maximum total ownership cannot be negative."
            )

        valid_targets = {
            "projection",
            "ceiling",
            "floor",
            "balanced",
        }
        if self.optimization_target not in valid_targets:
            raise ValueError(
                "Optimization target must be projection, ceiling, "
                "floor, or balanced."
            )

    @property
    def maximum_overlap(self) -> int:
        """Return the maximum shared players between two lineups."""

        return 9 - self.minimum_unique_players
