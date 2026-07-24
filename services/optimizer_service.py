from __future__ import annotations

import pandas as pd

from core.settings import OptimizerSettings
from optimizer.lineup_optimizer import (
    OptimizationResult,
    optimize_lineups,
)


class OptimizerService:
    """Coordinate validation, optimization, and portfolio analysis."""

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
            raise ValueError(
                "The player pool is empty."
            )

        missing_columns = (
            self.REQUIRED_COLUMNS
            - set(players.columns)
        )

        if missing_columns:
            raise ValueError(
                "The player pool is missing required columns: "
                f"{sorted(missing_columns)}"
            )

        duplicate_player_ids = (
            players["player_id"]
            .astype(str)
            .duplicated()
        )

        if duplicate_player_ids.any():
            duplicated_names = players.loc[
                duplicate_player_ids,
                "name",
            ].astype(str)

            raise ValueError(
                "Duplicate player IDs were found for: "
                + ", ".join(
                    duplicated_names.tolist()
                )
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

        invalid_position_mask = (
            ~normalized_positions.isin(
                self.VALID_POSITIONS
            )
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

        locked = (
            players["locked"]
            .fillna(False)
            .astype(bool)
        )

        excluded = (
            players["excluded"]
            .fillna(False)
            .astype(bool)
        )

        conflicting_players = players.loc[
            locked & excluded,
            "name",
        ].astype(str)

        if not conflicting_players.empty:
            raise ValueError(
                "These players are both locked and excluded: "
                + ", ".join(
                    conflicting_players.tolist()
                )
            )

        available_players = players.loc[
            ~excluded
        ].copy()

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

        for position, minimum_count in (
            required_position_counts.items()
        ):
            available_count = int(
                (
                    available_positions
                    == position
                ).sum()
            )

            if available_count < minimum_count:
                raise ValueError(
                    f"At least {minimum_count} available "
                    f"{position} player(s) are required. "
                    f"Only {available_count} are currently "
                    "available."
                )

        flex_count = int(
            available_positions.isin(
                {"RB", "WR", "TE"}
            ).sum()
        )

        if flex_count < 7:
            raise ValueError(
                "At least seven available RB, WR, and TE "
                "players are required to fill the skill-position "
                "and FLEX slots."
            )

        locked_count = int(
            locked.sum()
        )

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

        for position, maximum_count in (
            locked_position_limits.items()
        ):
            position_count = int(
                (
                    locked_positions
                    == position
                ).sum()
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

        prepared = (
            players.copy()
            .reset_index(drop=True)
        )

        prepared["player_id"] = (
            prepared["player_id"]
            .astype(str)
        )

        prepared["name"] = (
            prepared["name"]
            .astype(str)
            .str.strip()
        )

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

    def validate_player_max_exposures(
        self,
        players: pd.DataFrame,
        player_max_exposures: dict[str, float],
    ) -> dict[str, float]:
        """Validate and normalize player maximum-exposure rules."""

        valid_player_ids = set(
            players["player_id"].astype(str)
        )

        normalized_exposures: dict[str, float] = {}

        for player_id, exposure in (
            player_max_exposures.items()
        ):
            normalized_player_id = str(player_id)
            normalized_exposure = float(exposure)

            if normalized_player_id not in valid_player_ids:
                raise ValueError(
                    "Maximum exposure was provided for an "
                    f"unknown player ID: {normalized_player_id}"
                )

            if (
                normalized_exposure < 0
                or normalized_exposure > 1
            ):
                raise ValueError(
                    "Maximum player exposure must be between "
                    "0% and 100%."
                )

            normalized_exposures[
                normalized_player_id
            ] = normalized_exposure

        locked_players = players.loc[
            players["locked"]
            .fillna(False)
            .astype(bool)
        ]

        for _, player in locked_players.iterrows():
            player_id = str(
                player["player_id"]
            )

            maximum_exposure = (
                normalized_exposures.get(
                    player_id,
                    1.0,
                )
            )

            if maximum_exposure < 1.0:
                raise ValueError(
                    f"{player['name']} is locked, so their "
                    "maximum exposure must be 100%."
                )

        return normalized_exposures

    def validate_team_max_exposures(
        self,
        players: pd.DataFrame,
        team_max_exposures: dict[str, float],
    ) -> dict[str, float]:
        """Validate and normalize team portfolio exposure limits."""

        valid_teams = {
            str(team).upper().strip()
            for team in players["team"]
            if str(team).strip()
        }
        normalized: dict[str, float] = {}

        for team, exposure in team_max_exposures.items():
            normalized_team = str(team).upper().strip()
            normalized_exposure = float(exposure)

            if normalized_team not in valid_teams:
                raise ValueError(
                    "Maximum exposure was provided for an unknown team: "
                    f"{normalized_team}"
                )
            if normalized_exposure < 0 or normalized_exposure > 1:
                raise ValueError(
                    "Maximum team exposure must be between 0% and 100%."
                )
            normalized[normalized_team] = normalized_exposure

        locked_teams = {
            str(team).upper().strip()
            for team in players.loc[
                players["locked"].fillna(False).astype(bool),
                "team",
            ]
        }
        for team in locked_teams:
            if normalized.get(team, 1.0) < 1.0:
                raise ValueError(
                    f"{team} has a locked player, so its maximum team "
                    "exposure must be 100%."
                )

        return normalized

    def generate_lineups(
        self,
        players: pd.DataFrame,
        settings: OptimizerSettings,
        player_max_exposures: (
            dict[str, float] | None
        ) = None,
        team_max_exposures: (
            dict[str, float] | None
        ) = None,
    ) -> list[OptimizationResult]:
        """Generate multiple unique, exposure-controlled lineups."""

        settings.validate()

        prepared_players = (
            self.prepare_player_pool(players)
        )

        normalized_exposures = (
            self.validate_player_max_exposures(
                players=prepared_players,
                player_max_exposures=(
                    player_max_exposures or {}
                ),
            )
        )

        normalized_team_exposures = self.validate_team_max_exposures(
            players=prepared_players,
            team_max_exposures=team_max_exposures or {},
        )

        results = optimize_lineups(
            players=prepared_players,
            lineup_count=settings.lineup_count,
            minimum_unique_players=(
                settings.minimum_unique_players
            ),
            salary_cap=settings.salary_cap,
            minimum_salary=settings.minimum_salary,
            solver_timeout_seconds=(
                settings.solver_timeout_seconds
            ),
            player_max_exposures=(
                normalized_exposures
            ),
            team_max_exposures=normalized_team_exposures,
            qb_stack_size=(
                settings.qb_stack_size
            ),
            require_bring_back=(
                settings.require_bring_back
            ),
            maximum_players_per_team=(
                settings.maximum_players_per_team
            ),
            blocked_dst_opposing_positions=(
                settings.blocked_dst_opposing_positions
            ),
            minimum_players_from_primary_game=(
                settings.minimum_players_from_primary_game
            ),
            maximum_players_per_game=(
                settings.maximum_players_per_game
            ),
        )

        if not results:
            raise ValueError(
                "The optimizer could not create a valid lineup. "
                "Review salary, locks, exclusions, uniqueness, "
                "maximum-exposure, stacking, team-limit, game-stack, "
                "and DST-correlation settings."
            )

        return results

    def generate_lineup(
        self,
        players: pd.DataFrame,
        settings: OptimizerSettings,
    ) -> OptimizationResult:
        """Generate one lineup for backward compatibility."""

        single_lineup_settings = OptimizerSettings(
            salary_cap=settings.salary_cap,
            minimum_salary=settings.minimum_salary,
            solver_timeout_seconds=(
                settings.solver_timeout_seconds
            ),
            lineup_count=1,
            minimum_unique_players=1,
            qb_stack_size=settings.qb_stack_size,
            require_bring_back=(
                settings.require_bring_back
            ),
            maximum_players_per_team=(
                settings.maximum_players_per_team
            ),
            blocked_dst_opposing_positions=(
                settings.blocked_dst_opposing_positions
            ),
            minimum_players_from_primary_game=(
                settings.minimum_players_from_primary_game
            ),
            maximum_players_per_game=(
                settings.maximum_players_per_game
            ),
        )

        return self.generate_lineups(
            players=players,
            settings=single_lineup_settings,
        )[0]

    def build_team_exposure_report(
        self,
        lineups: list[pd.DataFrame],
        team_max_exposures: dict[str, float] | None = None,
    ) -> pd.DataFrame:
        """Calculate how often each NFL team appears in the portfolio."""

        columns = [
            "team",
            "lineup_count",
            "exposure",
            "maximum_exposure",
        ]
        if not lineups:
            return pd.DataFrame(columns=columns)

        records: list[dict] = []
        for lineup_number, lineup in enumerate(lineups, start=1):
            for team in sorted(set(lineup["team"].astype(str))):
                records.append(
                    {
                        "lineup_number": lineup_number,
                        "team": str(team).upper().strip(),
                    }
                )

        report = (
            pd.DataFrame(records)
            .groupby("team", as_index=False)
            .agg(lineup_count=("lineup_number", "nunique"))
        )
        report["exposure"] = report["lineup_count"] / len(lineups)
        maximum_map = {
            str(team).upper().strip(): float(exposure)
            for team, exposure in (team_max_exposures or {}).items()
        }
        report["maximum_exposure"] = (
            report["team"].map(maximum_map).fillna(1.0)
        )
        return report.sort_values(
            ["exposure", "team"],
            ascending=[False, True],
        ).reset_index(drop=True)

    def build_exposure_report(
        self,
        lineups: list[pd.DataFrame],
        player_max_exposures: (
            dict[str, float] | None
        ) = None,
    ) -> pd.DataFrame:
        """Calculate actual and configured exposure."""

        columns = [
            "player_id",
            "name",
            "position",
            "team",
            "salary",
            "projection",
            "lineup_count",
            "exposure",
            "maximum_exposure",
        ]

        if not lineups:
            return pd.DataFrame(
                columns=columns
            )

        required_columns = {
            "player_id",
            "name",
            "position",
            "team",
            "salary",
            "projection",
        }

        portfolio_records: list[dict] = []

        for lineup_number, lineup in enumerate(
            lineups,
            start=1,
        ):
            missing_columns = (
                required_columns
                - set(lineup.columns)
            )

            if missing_columns:
                raise ValueError(
                    "Cannot calculate exposure. A lineup is "
                    "missing required columns: "
                    f"{sorted(missing_columns)}"
                )

            unique_lineup_players = (
                lineup.drop_duplicates(
                    subset=["player_id"]
                )
            )

            for _, player in (
                unique_lineup_players.iterrows()
            ):
                portfolio_records.append(
                    {
                        "lineup_number": lineup_number,
                        "player_id": str(
                            player["player_id"]
                        ),
                        "name": str(
                            player["name"]
                        ),
                        "position": str(
                            player["position"]
                        ),
                        "team": str(
                            player["team"]
                        ),
                        "salary": int(
                            player["salary"]
                        ),
                        "projection": float(
                            player["projection"]
                        ),
                    }
                )

        portfolio = pd.DataFrame(
            portfolio_records
        )

        total_lineups = len(lineups)

        exposure_report = (
            portfolio.groupby(
                [
                    "player_id",
                    "name",
                    "position",
                    "team",
                    "salary",
                    "projection",
                ],
                as_index=False,
            )
            .agg(
                lineup_count=(
                    "lineup_number",
                    "nunique",
                )
            )
        )

        exposure_report["exposure"] = (
            exposure_report["lineup_count"]
            / total_lineups
        )

        maximum_exposure_map = {
            str(player_id): float(exposure)
            for player_id, exposure in (
                player_max_exposures or {}
            ).items()
        }

        exposure_report["maximum_exposure"] = (
            exposure_report["player_id"]
            .map(maximum_exposure_map)
            .fillna(1.0)
        )

        position_order = {
            "QB": 1,
            "RB": 2,
            "WR": 3,
            "TE": 4,
            "DST": 5,
        }

        exposure_report["_position_order"] = (
            exposure_report["position"]
            .map(position_order)
            .fillna(99)
        )

        return (
            exposure_report.sort_values(
                by=[
                    "exposure",
                    "projection",
                    "_position_order",
                    "name",
                ],
                ascending=[
                    False,
                    False,
                    True,
                    True,
                ],
            )
            .drop(
                columns=["_position_order"]
            )
            .reset_index(drop=True)
        )
