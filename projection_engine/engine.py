from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from data_loader import add_derived_metrics


POSITION_SALARY_MULTIPLIERS = {
    "QB": 3.25,
    "RB": 2.45,
    "WR": 2.35,
    "TE": 2.15,
    "DST": 1.35,
}

POSITION_VOLATILITY = {
    "QB": 0.38,
    "RB": 0.52,
    "WR": 0.62,
    "TE": 0.58,
    "DST": 0.72,
}

USAGE_OPPORTUNITY_BASELINES = {
    "QB": 34.0,
    "RB": 16.0,
    "WR": 14.0,
    "TE": 10.0,
    "DST": 0.0,
}

USAGE_ADJUSTMENT_SENSITIVITY = {
    "QB": 0.085,
    "RB": 0.13,
    "WR": 0.12,
    "TE": 0.11,
    "DST": 0.0,
}

MATCHUP_ADJUSTMENT_SENSITIVITY = {
    "QB": 0.040,
    "RB": 0.045,
    "WR": 0.040,
    "TE": 0.035,
    "DST": 0.0,
}

VEGAS_SENSITIVITY = {
    "QB": 0.16,
    "RB": 0.18,
    "WR": 0.14,
    "TE": 0.11,
    "DST": 0.09,
}


@dataclass(frozen=True)
class ProjectionEngineResult:
    player_pool: pd.DataFrame
    summary: pd.DataFrame


class ProjectionEngine:
    """Create transparent rule-based NFL DFS projections.

    Version 1.5 intentionally uses only information already present in the
    weekly player pool: salary, optional imported projections, position,
    opponent, home/away status, spread, implied team total, and leak-free
    recent usage and opponent matchup ratings from completed prior weeks. The engine is
    deterministic and exposes every adjustment it applies.
    """

    def project(self, players: pd.DataFrame) -> ProjectionEngineResult:
        required = {"name", "position", "team", "salary", "projection"}
        missing = required - set(players.columns)
        if missing:
            raise ValueError(
                "Projection engine is missing required columns: "
                f"{sorted(missing)}"
            )

        output = players.copy().reset_index(drop=True)
        output["position"] = output["position"].astype(str).str.upper().str.strip()
        output["salary"] = pd.to_numeric(output["salary"], errors="coerce")
        if output["salary"].isna().any():
            raise ValueError("Every player needs a valid salary.")

        imported_projection = pd.to_numeric(
            output["projection"], errors="coerce"
        ).fillna(0.0)
        salary_baseline = (
            output["salary"] / 1000.0
            * output["position"].map(POSITION_SALARY_MULTIPLIERS).fillna(2.0)
        )
        has_imported_projection = imported_projection > 0
        output["base_projection"] = imported_projection.where(
            has_imported_projection, salary_baseline
        )
        output["projection_source"] = has_imported_projection.map(
            {True: "Imported projection", False: "Salary baseline"}
        )

        team_total = pd.to_numeric(
            output.get("team_implied_total", pd.Series(index=output.index, dtype=float)),
            errors="coerce",
        )
        total_delta = (team_total - 22.5).clip(lower=-10.0, upper=10.0)
        output["vegas_adjustment"] = (
            total_delta
            * output["position"].map(VEGAS_SENSITIVITY).fillna(0.10)
        ).fillna(0.0)

        is_home = output.get("is_home", pd.Series(False, index=output.index))
        is_home = is_home.fillna(False).astype(bool)
        home_bonus = output["position"].map(
            {"QB": 0.20, "RB": 0.25, "WR": 0.15, "TE": 0.12, "DST": 0.35}
        ).fillna(0.10)
        output["home_adjustment"] = home_bonus.where(is_home, 0.0)

        spread = pd.to_numeric(
            output.get("team_spread", pd.Series(index=output.index, dtype=float)),
            errors="coerce",
        ).clip(lower=-14.0, upper=14.0)
        position = output["position"]
        spread_adjustment = pd.Series(0.0, index=output.index)
        spread_adjustment.loc[position == "RB"] = (
            -spread.loc[position == "RB"] * 0.055
        )
        spread_adjustment.loc[position.isin(["QB", "WR", "TE"])] = (
            spread.loc[position.isin(["QB", "WR", "TE"])] * 0.025
        )
        spread_adjustment.loc[position == "DST"] = (
            -spread.loc[position == "DST"] * 0.070
        )
        output["spread_adjustment"] = spread_adjustment.fillna(0.0)

        passing_attempts = pd.to_numeric(
            output.get("passing_attempts", pd.Series(index=output.index, dtype=float)),
            errors="coerce",
        )
        carries = pd.to_numeric(
            output.get("carries", pd.Series(index=output.index, dtype=float)),
            errors="coerce",
        )
        targets = pd.to_numeric(
            output.get("targets", pd.Series(index=output.index, dtype=float)),
            errors="coerce",
        )
        usage_games = pd.to_numeric(
            output.get("usage_games", pd.Series(0, index=output.index)),
            errors="coerce",
        ).fillna(0.0)

        opportunity = pd.Series(0.0, index=output.index)
        opportunity.loc[position == "QB"] = (
            passing_attempts.loc[position == "QB"].fillna(0.0)
            + carries.loc[position == "QB"].fillna(0.0) * 1.5
        )
        opportunity.loc[position == "RB"] = (
            carries.loc[position == "RB"].fillna(0.0)
            + targets.loc[position == "RB"].fillna(0.0) * 1.5
        )
        opportunity.loc[position.isin(["WR", "TE"])] = (
            targets.loc[position.isin(["WR", "TE"])] * 2.0
        ).fillna(0.0)
        output["usage_opportunity"] = opportunity

        usage_delta = (
            opportunity
            - position.map(USAGE_OPPORTUNITY_BASELINES).fillna(0.0)
        )
        usage_adjustment = (
            usage_delta
            * position.map(USAGE_ADJUSTMENT_SENSITIVITY).fillna(0.0)
        ).clip(lower=-3.0, upper=3.0)
        output["usage_adjustment"] = usage_adjustment.where(usage_games > 0, 0.0)

        matchup_rating = pd.to_numeric(
            output.get("matchup_rating", pd.Series(index=output.index, dtype=float)),
            errors="coerce",
        )
        output["matchup_rating"] = matchup_rating
        if "fantasy_points_allowed" not in output.columns:
            output["fantasy_points_allowed"] = pd.Series(
                index=output.index, dtype=float
            )
        matchup_games = pd.to_numeric(
            output.get("matchup_games", pd.Series(0, index=output.index)),
            errors="coerce",
        ).fillna(0.0)
        matchup_adjustment = (
            (matchup_rating - 50.0)
            * position.map(MATCHUP_ADJUSTMENT_SENSITIVITY).fillna(0.0)
        ).clip(lower=-2.25, upper=2.25)
        output["matchup_adjustment"] = matchup_adjustment.where(
            matchup_games > 0, 0.0
        ).fillna(0.0)

        output["model_adjustment"] = (
            output["vegas_adjustment"]
            + output["home_adjustment"]
            + output["spread_adjustment"]
            + output["usage_adjustment"]
            + output["matchup_adjustment"]
        )
        output["projection"] = (
            output["base_projection"] + output["model_adjustment"]
        ).clip(lower=0.0)

        confidence = pd.Series(30.0, index=output.index)
        confidence += has_imported_projection.astype(float) * 30.0
        confidence += team_total.notna().astype(float) * 15.0
        confidence += spread.notna().astype(float) * 5.0
        confidence += usage_games.gt(0).astype(float) * 10.0
        confidence += usage_games.ge(3).astype(float) * 5.0
        confidence += matchup_games.gt(0).astype(float) * 5.0
        if "opponent" in output.columns:
            confidence += (
                output["opponent"].fillna("").astype(str).str.strip().ne("")
            ).astype(float) * 5.0
        output["confidence"] = confidence.clip(lower=20.0, upper=95.0)

        volatility = output["position"].map(POSITION_VOLATILITY).fillna(0.55)
        uncertainty = 1.0 + (100.0 - output["confidence"]) / 180.0
        output["ceiling"] = (
            output["projection"] * (1.0 + volatility * uncertainty)
        ).clip(lower=output["projection"])
        output["floor"] = (
            output["projection"] * (1.0 - volatility * 0.62 * uncertainty)
        ).clip(lower=0.0, upper=output["projection"])

        round_columns = [
            "base_projection", "vegas_adjustment", "home_adjustment",
            "spread_adjustment", "usage_opportunity", "usage_adjustment",
            "matchup_rating", "fantasy_points_allowed", "matchup_adjustment",
            "model_adjustment", "projection", "ceiling",
            "floor", "confidence",
        ]
        output[round_columns] = output[round_columns].round(2)
        output = add_derived_metrics(output)

        summary = pd.DataFrame(
            [
                {
                    "Players": len(output),
                    "Imported bases": int(has_imported_projection.sum()),
                    "Salary baselines": int((~has_imported_projection).sum()),
                    "Vegas covered": int(team_total.notna().sum()),
                    "Usage covered": int(usage_games.gt(0).sum()),
                    "Matchups covered": int(matchup_games.gt(0).sum()),
                    "Average projection": round(float(output["projection"].mean()), 2),
                    "Average confidence": round(float(output["confidence"].mean()), 1),
                }
            ]
        )
        return ProjectionEngineResult(player_pool=output, summary=summary)
