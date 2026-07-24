from __future__ import annotations

from dataclasses import dataclass

from config import SALARY_CAP


OPTIMIZATION_PRESETS: dict[str, dict[str, float]] = {
    "projection": {
        "projection": 1.00,
        "ceiling": 0.00,
        "floor": 0.00,
        "value": 0.00,
        "leverage": 0.00,
    },
    "ceiling": {
        "projection": 0.00,
        "ceiling": 1.00,
        "floor": 0.00,
        "value": 0.00,
        "leverage": 0.00,
    },
    "floor": {
        "projection": 0.00,
        "ceiling": 0.00,
        "floor": 1.00,
        "value": 0.00,
        "leverage": 0.00,
    },
    "balanced": {
        "projection": 0.40,
        "ceiling": 0.40,
        "floor": 0.00,
        "value": 0.20,
        "leverage": 0.00,
    },
    "cash": {
        "projection": 0.55,
        "ceiling": 0.00,
        "floor": 0.35,
        "value": 0.10,
        "leverage": 0.00,
    },
    "single_entry": {
        "projection": 0.40,
        "ceiling": 0.35,
        "floor": 0.05,
        "value": 0.10,
        "leverage": 0.10,
    },
    "large_field_gpp": {
        "projection": 0.20,
        "ceiling": 0.45,
        "floor": 0.00,
        "value": 0.10,
        "leverage": 0.25,
    },
}


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
    projection_weight: float = 35.0
    ceiling_weight: float = 35.0
    floor_weight: float = 10.0
    value_weight: float = 10.0
    leverage_weight: float = 10.0

    def validate(self) -> None:
        """Validate optimizer settings before they are used."""

        if self.salary_cap <= 0:
            raise ValueError("Salary cap must be greater than zero.")
        if self.minimum_salary < 0:
            raise ValueError("Minimum salary cannot be negative.")
        if self.minimum_salary > self.salary_cap:
            raise ValueError("Minimum salary cannot be greater than the salary cap.")
        if self.solver_timeout_seconds <= 0:
            raise ValueError("Solver timeout must be greater than zero seconds.")
        if self.lineup_count < 1:
            raise ValueError("At least one lineup must be requested.")
        if self.lineup_count > 150:
            raise ValueError("No more than 150 lineups may be generated at once.")
        if self.minimum_unique_players < 1:
            raise ValueError("Minimum unique players must be at least one.")
        if self.minimum_unique_players > 9:
            raise ValueError("Minimum unique players cannot exceed nine.")
        if self.qb_stack_size not in {0, 1, 2}:
            raise ValueError("QB stack size must be 0, 1, or 2.")
        if not isinstance(self.require_bring_back, bool):
            raise ValueError("Require bring-back must be true or false.")
        if self.maximum_players_per_team is not None and self.maximum_players_per_team < 1:
            raise ValueError("Maximum players per team must be at least one or None.")

        valid_dst_positions = {"QB", "RB", "WR", "TE"}
        normalized_dst_positions = {
            str(position).upper().strip()
            for position in self.blocked_dst_opposing_positions
        }
        invalid_dst_positions = normalized_dst_positions - valid_dst_positions
        if invalid_dst_positions:
            raise ValueError(
                "Unsupported DST correlation positions: "
                f"{sorted(invalid_dst_positions)}"
            )

        if self.minimum_players_from_primary_game is not None and self.minimum_players_from_primary_game not in {3, 4, 5}:
            raise ValueError(
                "Minimum players from the primary game must be 3, 4, 5, or None."
            )
        if self.maximum_players_per_game is not None and self.maximum_players_per_game not in {5, 6}:
            raise ValueError("Maximum players per game must be 5, 6, or None.")
        if (
            self.minimum_players_from_primary_game is not None
            and self.maximum_players_per_game is not None
            and self.minimum_players_from_primary_game > self.maximum_players_per_game
        ):
            raise ValueError(
                "The primary-game minimum cannot exceed the maximum players per game."
            )
        if self.maximum_total_ownership is not None and self.maximum_total_ownership < 0:
            raise ValueError("Maximum total ownership cannot be negative.")

        valid_targets = set(OPTIMIZATION_PRESETS) | {"custom"}
        if self.optimization_target not in valid_targets:
            raise ValueError(
                "Unsupported optimization target. Choose a preset or custom."
            )

        weights = self.objective_weights
        if any(weight < 0 or weight > 1 for weight in weights.values()):
            raise ValueError("Optimization weights must be between 0% and 100%.")
        if abs(sum(weights.values()) - 1.0) > 0.0001:
            raise ValueError("Optimization weights must total exactly 100%.")

    @property
    def objective_weights(self) -> dict[str, float]:
        """Return normalized objective weights for the selected strategy."""

        if self.optimization_target != "custom":
            return OPTIMIZATION_PRESETS[self.optimization_target].copy()

        return {
            "projection": self.projection_weight / 100.0,
            "ceiling": self.ceiling_weight / 100.0,
            "floor": self.floor_weight / 100.0,
            "value": self.value_weight / 100.0,
            "leverage": self.leverage_weight / 100.0,
        }

    @property
    def maximum_overlap(self) -> int:
        """Return the maximum shared players between two lineups."""

        return 9 - self.minimum_unique_players
