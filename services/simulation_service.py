from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SimulationResult:
    """Outputs produced by a portfolio Monte Carlo simulation."""

    lineup_summary: pd.DataFrame
    player_summary: pd.DataFrame
    lineup_scores: pd.DataFrame
    simulation_count: int
    target_score: float


class SimulationService:
    """Run correlated Monte Carlo simulations for saved DFS lineups.

    The service uses each player's projection, floor, and ceiling to estimate
    an outcome distribution. Shared team and game factors introduce modest
    correlation, while the same simulated player outcome is reused anywhere
    that player appears in the portfolio.

    Results compare lineups inside the selected portfolio. They are not a
    literal contest win probability unless a representative field is supplied.
    """

    REQUIRED_PLAYER_COLUMNS = {
        "player_id",
        "name",
        "position",
        "team",
        "opponent",
        "projection",
        "ceiling",
        "floor",
    }

    POSITION_VOLATILITY = {
        "QB": 0.28,
        "RB": 0.42,
        "WR": 0.52,
        "TE": 0.50,
        "DST": 0.60,
    }

    def run_portfolio_simulation(
        self,
        player_pool: pd.DataFrame,
        lineups: dict[int, pd.DataFrame],
        lineup_names: dict[int, str] | None = None,
        simulation_count: int = 10_000,
        target_score: float = 180.0,
        random_seed: int | None = 42,
    ) -> SimulationResult:
        """Simulate player outcomes and summarize selected lineups."""

        if simulation_count < 500:
            raise ValueError("Run at least 500 simulations.")
        if simulation_count > 100_000:
            raise ValueError("Simulation count cannot exceed 100,000.")
        if not lineups:
            raise ValueError("Select at least one lineup to simulate.")

        prepared_players = self._prepare_player_pool(player_pool)
        lineup_matrix, lineup_meta = self._build_lineup_matrix(
            prepared_players=prepared_players,
            lineups=lineups,
            lineup_names=lineup_names or {},
        )

        player_scores = self._simulate_player_scores(
            players=prepared_players,
            simulation_count=simulation_count,
            random_seed=random_seed,
        )

        # rows = simulations, columns = lineups
        lineup_score_values = player_scores @ lineup_matrix.T
        lineup_ids = lineup_meta["lineup_id"].astype(int).tolist()
        lineup_scores = pd.DataFrame(
            lineup_score_values,
            columns=lineup_ids,
        )
        lineup_scores.index.name = "simulation"
        lineup_scores.index = lineup_scores.index + 1

        lineup_summary = self._summarize_lineups(
            lineup_scores=lineup_scores,
            lineup_meta=lineup_meta,
            target_score=float(target_score),
        )
        player_summary = self._summarize_players(
            players=prepared_players,
            player_scores=player_scores,
        )

        return SimulationResult(
            lineup_summary=lineup_summary,
            player_summary=player_summary,
            lineup_scores=lineup_scores.reset_index(),
            simulation_count=simulation_count,
            target_score=float(target_score),
        )

    def _prepare_player_pool(self, player_pool: pd.DataFrame) -> pd.DataFrame:
        if player_pool.empty:
            raise ValueError("The saved player pool is empty.")

        missing = self.REQUIRED_PLAYER_COLUMNS - set(player_pool.columns)
        if missing:
            raise ValueError(
                "The player pool is missing simulation columns: "
                f"{sorted(missing)}"
            )

        players = player_pool.copy().reset_index(drop=True)
        players["player_id"] = players["player_id"].astype(str)
        players["name"] = players["name"].astype(str)
        players["position"] = (
            players["position"].astype(str).str.upper().str.strip()
            .replace({"D/ST": "DST", "DEF": "DST"})
        )
        players["team"] = players["team"].astype(str).str.upper().str.strip()
        players["opponent"] = (
            players["opponent"].fillna("").astype(str).str.upper().str.strip()
        )

        for column in ("projection", "ceiling", "floor"):
            players[column] = pd.to_numeric(players[column], errors="coerce")

        if players[["projection", "ceiling", "floor"]].isna().any().any():
            raise ValueError(
                "Projection, ceiling, and floor must be numeric for every player."
            )

        players["floor"] = players[["floor", "projection"]].min(axis=1)
        players["ceiling"] = players[["ceiling", "projection"]].max(axis=1)

        range_stdev = (players["ceiling"] - players["floor"]) / 3.29
        fallback_stdev = players.apply(
            lambda row: max(
                float(row["projection"])
                * self.POSITION_VOLATILITY.get(str(row["position"]), 0.45),
                1.5,
            ),
            axis=1,
        )
        players["simulation_stdev"] = np.where(
            range_stdev > 0.75,
            range_stdev,
            fallback_stdev,
        )
        players["simulation_stdev"] = players["simulation_stdev"].clip(lower=1.0)
        players["game_key"] = players.apply(self._game_key, axis=1)
        return players

    @staticmethod
    def _game_key(player: pd.Series) -> str:
        team = str(player["team"])
        opponent = str(player["opponent"])
        if not opponent:
            return team
        return "@".join(sorted((team, opponent)))

    def _build_lineup_matrix(
        self,
        prepared_players: pd.DataFrame,
        lineups: dict[int, pd.DataFrame],
        lineup_names: dict[int, str],
    ) -> tuple[np.ndarray, pd.DataFrame]:
        player_index = {
            player_id: index
            for index, player_id in enumerate(prepared_players["player_id"])
        }
        matrix = np.zeros((len(lineups), len(prepared_players)), dtype=float)
        metadata: list[dict[str, object]] = []

        for row_index, (lineup_id, lineup) in enumerate(lineups.items()):
            if lineup.empty:
                raise ValueError(f"Lineup {lineup_id} has no players.")
            if "player_id" not in lineup.columns:
                raise ValueError(f"Lineup {lineup_id} is missing player_id.")

            player_ids = lineup["player_id"].astype(str).tolist()
            missing_ids = sorted(set(player_ids) - set(player_index))
            if missing_ids:
                raise ValueError(
                    f"Lineup {lineup_id} contains players not found in its "
                    f"saved player pool: {missing_ids}"
                )
            for player_id in player_ids:
                matrix[row_index, player_index[player_id]] += 1.0

            metadata.append(
                {
                    "lineup_id": int(lineup_id),
                    "lineup_name": lineup_names.get(
                        int(lineup_id), f"Lineup {lineup_id}"
                    ),
                    "projected_points": float(
                        prepared_players.loc[
                            prepared_players["player_id"].isin(player_ids),
                            "projection",
                        ].sum()
                    ),
                }
            )

        return matrix, pd.DataFrame(metadata)

    def _simulate_player_scores(
        self,
        players: pd.DataFrame,
        simulation_count: int,
        random_seed: int | None,
    ) -> np.ndarray:
        rng = np.random.default_rng(random_seed)
        player_count = len(players)

        unique_games = players["game_key"].unique().tolist()
        unique_teams = players["team"].unique().tolist()
        game_index = {value: index for index, value in enumerate(unique_games)}
        team_index = {value: index for index, value in enumerate(unique_teams)}

        game_factors = rng.standard_normal((simulation_count, len(unique_games)))
        team_factors = rng.standard_normal((simulation_count, len(unique_teams)))
        individual_factors = rng.standard_normal((simulation_count, player_count))

        game_weight = 0.22
        team_weight = 0.16
        individual_weight = sqrt(1.0 - game_weight**2 - team_weight**2)

        combined = np.empty((simulation_count, player_count), dtype=float)

        for player_number, player in players.iterrows():
            game_component = game_factors[:, game_index[player["game_key"]]]
            team_component = team_factors[:, team_index[player["team"]]]

            # DST scoring generally moves opposite the offensive environment.
            if player["position"] == "DST":
                game_component = -game_component

            combined[:, player_number] = (
                game_weight * game_component
                + team_weight * team_component
                + individual_weight * individual_factors[:, player_number]
            )

        means = players["projection"].to_numpy(dtype=float)
        stdevs = players["simulation_stdev"].to_numpy(dtype=float)
        scores = means + combined * stdevs
        return np.clip(scores, 0.0, None)

    @staticmethod
    def _summarize_lineups(
        lineup_scores: pd.DataFrame,
        lineup_meta: pd.DataFrame,
        target_score: float,
    ) -> pd.DataFrame:
        values = lineup_scores.to_numpy(dtype=float)
        lineup_count = values.shape[1]

        # Split ties evenly rather than awarding every tied lineup a full win.
        row_maximums = values.max(axis=1, keepdims=True)
        winners = np.isclose(values, row_maximums)
        win_shares = winners / winners.sum(axis=1, keepdims=True)

        order = np.argsort(-values, axis=1)
        ranks = np.empty_like(order)
        row_numbers = np.arange(values.shape[0])[:, None]
        ranks[row_numbers, order] = np.arange(1, lineup_count + 1)
        top_count = max(1, int(np.ceil(lineup_count * 0.20)))

        records: list[dict[str, object]] = []
        for column_number, lineup_id in enumerate(lineup_scores.columns):
            scores = values[:, column_number]
            meta = lineup_meta.loc[
                lineup_meta["lineup_id"] == int(lineup_id)
            ].iloc[0]
            records.append(
                {
                    "lineup_id": int(lineup_id),
                    "lineup_name": str(meta["lineup_name"]),
                    "projected_points": float(meta["projected_points"]),
                    "simulated_mean": float(np.mean(scores)),
                    "median": float(np.median(scores)),
                    "p10": float(np.percentile(scores, 10)),
                    "p75": float(np.percentile(scores, 75)),
                    "p90": float(np.percentile(scores, 90)),
                    "p95": float(np.percentile(scores, 95)),
                    "portfolio_first_rate": float(
                        win_shares[:, column_number].mean()
                    ),
                    "portfolio_top_20_rate": float(
                        (ranks[:, column_number] <= top_count).mean()
                    ),
                    "target_hit_rate": float((scores >= target_score).mean()),
                    "average_portfolio_rank": float(
                        ranks[:, column_number].mean()
                    ),
                }
            )

        return pd.DataFrame(records).sort_values(
            ["portfolio_first_rate", "p90", "simulated_mean"],
            ascending=[False, False, False],
        ).reset_index(drop=True)

    @staticmethod
    def _summarize_players(
        players: pd.DataFrame,
        player_scores: np.ndarray,
    ) -> pd.DataFrame:
        summary = players[
            [
                "player_id",
                "name",
                "position",
                "team",
                "opponent",
                "projection",
                "floor",
                "ceiling",
                "simulation_stdev",
            ]
        ].copy()
        summary["simulated_mean"] = player_scores.mean(axis=0)
        summary["p10"] = np.percentile(player_scores, 10, axis=0)
        summary["p50"] = np.percentile(player_scores, 50, axis=0)
        summary["p90"] = np.percentile(player_scores, 90, axis=0)
        summary["ceiling_hit_rate"] = (
            player_scores >= players["ceiling"].to_numpy(dtype=float)
        ).mean(axis=0)
        return summary.sort_values(
            ["p90", "simulated_mean"], ascending=[False, False]
        ).reset_index(drop=True)
