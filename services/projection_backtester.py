from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from projection_engine.engine import POSITION_SALARY_MULTIPLIERS


@dataclass(frozen=True)
class BacktestResult:
    player_results: pd.DataFrame
    overall_summary: pd.DataFrame
    position_summary: pd.DataFrame
    salary_summary: pd.DataFrame
    confidence_summary: pd.DataFrame
    calibration_summary: pd.DataFrame


class ProjectionBacktester:
    """Evaluate saved projections against historical DraftKings results."""

    REQUIRED_COLUMNS = {
        "name",
        "position",
        "salary",
        "projection",
        "ceiling",
        "floor",
        "actual_points",
    }

    SALARY_BUCKETS = [0, 4000, 5500, 7000, 8500, float("inf")]
    SALARY_LABELS = ["Under $4K", "$4K–$5.5K", "$5.5K–$7K", "$7K–$8.5K", "$8.5K+"]
    CONFIDENCE_BUCKETS = [0, 50, 65, 80, 90, 101]
    CONFIDENCE_LABELS = ["Under 50", "50–64", "65–79", "80–89", "90+"]

    def evaluate(self, evaluation: pd.DataFrame) -> BacktestResult:
        missing = self.REQUIRED_COLUMNS - set(evaluation.columns)
        if missing:
            raise ValueError(
                "Backtest data is missing required columns: "
                f"{sorted(missing)}"
            )

        players = evaluation.copy().reset_index(drop=True)
        numeric_columns = [
            "salary",
            "projection",
            "ceiling",
            "floor",
            "actual_points",
            "confidence",
        ]
        for column in numeric_columns:
            if column not in players:
                players[column] = 0.0
            players[column] = pd.to_numeric(players[column], errors="coerce")

        players = players.dropna(
            subset=["salary", "projection", "ceiling", "floor", "actual_points"]
        ).copy()
        if players.empty:
            raise ValueError("No valid matched player results are available to backtest.")

        players["position"] = players["position"].astype(str).str.upper().str.strip()
        players["salary_baseline"] = (
            players["salary"]
            / 1000.0
            * players["position"].map(POSITION_SALARY_MULTIPLIERS).fillna(2.0)
        )

        players["error"] = players["projection"] - players["actual_points"]
        players["absolute_error"] = players["error"].abs()
        players["squared_error"] = players["error"].pow(2)
        players["baseline_error"] = (
            players["salary_baseline"] - players["actual_points"]
        )
        players["baseline_absolute_error"] = players["baseline_error"].abs()
        players["model_improvement"] = (
            players["baseline_absolute_error"] - players["absolute_error"]
        )
        players["inside_floor_ceiling"] = (
            (players["actual_points"] >= players["floor"])
            & (players["actual_points"] <= players["ceiling"])
        )
        players["above_ceiling"] = players["actual_points"] > players["ceiling"]
        players["below_floor"] = players["actual_points"] < players["floor"]
        players["salary_tier"] = pd.cut(
            players["salary"],
            bins=self.SALARY_BUCKETS,
            labels=self.SALARY_LABELS,
            right=False,
        )
        players["confidence_tier"] = pd.cut(
            players["confidence"].fillna(0.0),
            bins=self.CONFIDENCE_BUCKETS,
            labels=self.CONFIDENCE_LABELS,
            right=False,
        )

        overall_summary = self._overall_summary(players)
        position_summary = self._group_summary(players, "position")
        salary_summary = self._group_summary(players, "salary_tier")
        confidence_summary = self._group_summary(players, "confidence_tier")
        calibration_summary = self._calibration_summary(position_summary)

        display_round_columns = [
            "salary_baseline",
            "error",
            "absolute_error",
            "baseline_error",
            "baseline_absolute_error",
            "model_improvement",
        ]
        players[display_round_columns] = players[display_round_columns].round(2)

        return BacktestResult(
            player_results=players,
            overall_summary=overall_summary,
            position_summary=position_summary,
            salary_summary=salary_summary,
            confidence_summary=confidence_summary,
            calibration_summary=calibration_summary,
        )

    @staticmethod
    def _safe_correlation(frame: pd.DataFrame) -> float:
        if len(frame) < 2:
            return float("nan")
        return float(frame["projection"].corr(frame["actual_points"]))

    def _overall_summary(self, players: pd.DataFrame) -> pd.DataFrame:
        model_mae = float(players["absolute_error"].mean())
        baseline_mae = float(players["baseline_absolute_error"].mean())
        return pd.DataFrame(
            [
                {
                    "Players": len(players),
                    "Model MAE": model_mae,
                    "Salary baseline MAE": baseline_mae,
                    "MAE improvement": baseline_mae - model_mae,
                    "RMSE": float(players["squared_error"].mean() ** 0.5),
                    "Bias": float(players["error"].mean()),
                    "Correlation": self._safe_correlation(players),
                    "Inside floor/ceiling": float(
                        players["inside_floor_ceiling"].mean()
                    ),
                    "Above ceiling": float(players["above_ceiling"].mean()),
                    "Below floor": float(players["below_floor"].mean()),
                    "Model beat baseline": float(
                        (players["absolute_error"] < players["baseline_absolute_error"]).mean()
                    ),
                }
            ]
        ).round(4)

    def _group_summary(self, players: pd.DataFrame, group_column: str) -> pd.DataFrame:
        records: list[dict] = []
        observed = players.dropna(subset=[group_column])
        for group_value, group in observed.groupby(group_column, observed=True):
            model_mae = float(group["absolute_error"].mean())
            baseline_mae = float(group["baseline_absolute_error"].mean())
            records.append(
                {
                    group_column: str(group_value),
                    "Players": len(group),
                    "Projection": float(group["projection"].mean()),
                    "Actual": float(group["actual_points"].mean()),
                    "MAE": model_mae,
                    "Baseline MAE": baseline_mae,
                    "MAE improvement": baseline_mae - model_mae,
                    "RMSE": float(group["squared_error"].mean() ** 0.5),
                    "Bias": float(group["error"].mean()),
                    "Correlation": self._safe_correlation(group),
                    "Inside range": float(group["inside_floor_ceiling"].mean()),
                }
            )
        return pd.DataFrame(records).round(3)

    @staticmethod
    def _calibration_summary(position_summary: pd.DataFrame) -> pd.DataFrame:
        if position_summary.empty:
            return pd.DataFrame(
                columns=["position", "Current bias", "Suggested additive adjustment"]
            )
        calibration = position_summary[["position", "Players", "Bias", "MAE"]].copy()
        calibration = calibration.rename(columns={"Bias": "Current bias"})
        calibration["Suggested additive adjustment"] = -calibration["Current bias"]
        calibration["Interpretation"] = calibration["Current bias"].apply(
            lambda value: (
                "Model is too high"
                if value > 0.25
                else "Model is too low"
                if value < -0.25
                else "Well calibrated"
            )
        )
        return calibration.round(3)
