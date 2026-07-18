from __future__ import annotations

import pandas as pd

from core.settings import OptimizerSettings
from optimizer.lineup_optimizer import (
    OptimizationResult,
    optimize_lineup,
)


class OptimizerService:
    """
    Coordinate player-pool validation and lineup optimization.

    Streamlit pages should use this service rather than calling the
    OR-Tools optimizer directly.
    """

    REQUIRED_COLUMNS = {
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

    VALID_POSITIONS = {
        "QB",
        "RB",
        "WR",
        "TE",
        "DST",
    }

    def validate_player_pool(
        self,
        players: pd.DataFrame,
    ) -> None:
        """Validate a player pool before optimization."""

        if players.empty:
            raise ValueError("The player pool is empty.")

        missing_columns = self.REQUIRED_COLUMNS - set(players.columns)

        if missing_columns:
            raise ValueError(
                "The player pool is missing required columns: "
                f"{sorted(missing_columns)}"
            )

        duplicate_player_ids = players["player_id"].astype(str).duplicated()

        if duplicate_player_ids.any():
            duplicated_names = players.loc[
                duplicate_player_ids,
                "name",
            ].astype(str)

            raise ValueError(
                "Duplicate player IDs were found for: "
                + ", ".join(duplicated_names.tolist())
            )

        normalized_positions = (
            players["position"]
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

        invalid_position_mask = ~normalized_positions.isin(
            self.VALID_POSITIONS
        )

        if invalid_position_mask.any():
            invalid_positions = sorted(
                normalized_positions.loc[
                    invalid_position_mask
                ].unique().tolist()
            )

            raise ValueError(
                "Unsupported player positions were found: "
                f"{invalid_positions}"
            )

        salaries = pd.to_numeric(
            players["salary"],
            errors="coerce",
        )

        if salaries.isna().any():
            raise ValueError(
                "One or more players have an invalid salary."
            )

        if (salaries <= 0).any():
            raise ValueError(
                "Every player salary must be greater than zero."
            )

        projections = pd.to_numeric(
            players["projection"],
            errors="coerce",
        )

        if projections.isna().any():
            raise ValueError(
                "One or more players have an invalid projection."
            )

        if (projections < 0).any():
            raise ValueError(
                "Player projections cannot be negative."
            )

        locked = players["locked"].fillna(False).astype(bool)
        excluded = players["excluded"].fillna(False).astype(bool)

        conflicting_players = players.loc[
            locked & excluded,
            "name",
        ].astype(str)

        if not conflicting_players.empty:
            raise ValueError(
                "These players are both locked and excluded: "
                + ", ".join(conflicting_players.tolist())
            )

        available_players = players.loc[~excluded].copy()

        available_positions = (
            available_players["position"]
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

        required_position_counts = {
            "QB": 1,
            "RB": 2,
            "WR": 3,
            "TE": 1,
            "DST": 1,
        }

        for position, minimum_count in required_position_counts.items():
            available_count = int(
                (available_positions == position).sum()
            )

            if available_count < minimum_count:
                raise ValueError(
                    f"At least {minimum_count} available {position} "
                    f"player(s) are required. Only {available_count} "
                    "are currently available."
                )

        flex_count = int(
            available_positions.isin(
                {"RB", "WR", "TE"}
            ).sum()
        )

        if flex_count < 7:
            raise ValueError(
                "At least seven available RB, WR, and TE players are "
                "required to fill the skill-position and FLEX slots."
            )

        locked_count = int(locked.sum())

        if locked_count > 9:
            raise ValueError(
                "No more than nine players may be locked."
            )

        locked_positions = (
            players.loc[locked, "position"]
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

        locked_position_limits = {
            "QB": 1,
            "RB": 3,
            "WR": 4,
            "TE": 2,
            "DST": 1,
        }

        for position, maximum_count in locked_position_limits.items():
            position_count = int(
                (locked_positions == position).sum()
            )

            if position_count > maximum_count:
                raise ValueError(
                    f"Too many {position} players are locked. "
                    f"The maximum possible is {maximum_count}."
                )

    def prepare_player_pool(
        self,
        players: pd.DataFrame,
    ) -> pd.DataFrame:
        """Return a normalized copy of a validated player pool."""

        self.validate_player_pool(players)

        prepared = players.copy().reset_index(drop=True)

        prepared["player_id"] = prepared["player_id"].astype(str)
        prepared["name"] = prepared["name"].astype(str).str.strip()

        prepared["position"] = (
            prepared["position"]
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

        prepared["team"] = (
            prepared["team"]
            .astype(str)
            .str.upper()
            .str.strip()
        )

        prepared["opponent"] = (
            prepared["opponent"]
            .fillna("")
            .astype(str)
            .str.upper()
            .str.strip()
        )

        prepared["salary"] = pd.to_numeric(
            prepared["salary"],
            errors="raise",
        ).astype(int)

        prepared["projection"] = pd.to_numeric(
            prepared["projection"],
            errors="raise",
        ).astype(float)

        prepared["locked"] = (
            prepared["locked"]
            .fillna(False)
            .astype(bool)
        )

        prepared["excluded"] = (
            prepared["excluded"]
            .fillna(False)
            .astype(bool)
        )

        return prepared

    def generate_lineup(
        self,
        players: pd.DataFrame,
        settings: OptimizerSettings,
    ) -> OptimizationResult:
        """Validate inputs and generate one optimized lineup."""

        settings.validate()

        prepared_players = self.prepare_player_pool(players)

        result = optimize_lineup(
            players=prepared_players,
            salary_cap=settings.salary_cap,
            minimum_salary=settings.minimum_salary,
        )

        if result.lineup.empty:
            raise ValueError(
                "The optimizer could not create a valid lineup. "
                f"Solver status: {result.status}"
            )

        return result