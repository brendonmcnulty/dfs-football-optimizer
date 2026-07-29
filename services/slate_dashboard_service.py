from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SlateDashboardResult:
    overview: dict[str, object]
    top_values: pd.DataFrame
    ceiling_leaders: pd.DataFrame
    leverage_plays: pd.DataFrame
    fades: pd.DataFrame
    game_environment: pd.DataFrame
    stack_rankings: pd.DataFrame
    alerts: list[str]


class SlateDashboardService:
    """Build Sunday-morning research tables from the active player pool."""

    SKILL_POSITIONS = {"RB", "WR", "TE"}

    @staticmethod
    def _numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(default, index=frame.index, dtype=float)
        return pd.to_numeric(frame[column], errors="coerce").fillna(default)

    def prepare(self, player_pool: pd.DataFrame) -> pd.DataFrame:
        if player_pool.empty:
            raise ValueError("The selected player pool is empty.")

        players = player_pool.copy().reset_index(drop=True)
        for column, default in (
            ("projection", 0.0), ("ceiling", 0.0), ("floor", 0.0),
            ("ownership", 0.0), ("confidence", 0.0), ("salary", 0.0),
            ("team_implied_total", 0.0), ("game_total", 0.0),
            ("usage_adjustment", 0.0), ("matchup_adjustment", 0.0),
            ("matchup_rating", 50.0),
        ):
            players[column] = self._numeric(players, column, default)

        players["position"] = players["position"].astype(str).str.upper().str.strip()
        players["team"] = players["team"].astype(str).str.upper().str.strip()
        players["opponent"] = players.get("opponent", "").astype(str).str.upper().str.strip()
        players["name"] = players["name"].astype(str).str.strip()
        players["value"] = players["projection"] / players["salary"].replace(0, pd.NA) * 1000
        players["value"] = players["value"].fillna(0.0)
        players["leverage_score"] = (
            players["ceiling"] * (1.0 - players["ownership"].clip(0, 100) / 100.0)
        )
        players["risk_gap"] = (players["projection"] - players["floor"]).clip(lower=0)
        players["ceiling_gap"] = (players["ceiling"] - players["projection"]).clip(lower=0)
        players["game_key"] = players.apply(
            lambda row: " @ ".join(sorted([str(row["team"]), str(row["opponent"])]))
            if str(row["opponent"]) else str(row["team"]), axis=1
        )
        return players

    def build(self, player_pool: pd.DataFrame) -> SlateDashboardResult:
        players = self.prepare(player_pool)
        eligible = players.loc[~players.get("excluded", False).fillna(False).astype(bool)].copy()

        game_count = int(eligible["game_key"].nunique())
        overview = {
            "player_count": int(len(eligible)),
            "game_count": game_count,
            "average_projection": float(eligible["projection"].mean()),
            "average_game_total": float(eligible.loc[eligible["game_total"] > 0, "game_total"].mean())
            if (eligible["game_total"] > 0).any() else None,
            "highest_team_total": float(eligible["team_implied_total"].max())
            if (eligible["team_implied_total"] > 0).any() else None,
            "data_confidence": float(eligible["confidence"].mean()),
        }

        columns = [
            "name", "position", "team", "opponent", "salary", "projection",
            "ceiling", "floor", "ownership", "value", "confidence",
            "matchup_rating", "usage_adjustment", "matchup_adjustment",
        ]
        columns = [column for column in columns if column in eligible.columns]

        top_values = eligible.sort_values(
            ["value", "projection"], ascending=[False, False]
        ).head(15)[columns]
        ceiling_leaders = eligible.sort_values(
            ["ceiling", "projection"], ascending=[False, False]
        ).head(15)[columns]
        leverage_plays = eligible.loc[eligible["ownership"] <= 20].sort_values(
            ["leverage_score", "ceiling"], ascending=[False, False]
        ).head(15)[columns + ["leverage_score"]]
        fades = eligible.loc[eligible["ownership"] >= 10].sort_values(
            ["ownership", "value"], ascending=[False, True]
        ).head(15)[columns]

        game_environment = (
            eligible.groupby("game_key", as_index=False)
            .agg(
                game_total=("game_total", "max"),
                highest_team_total=("team_implied_total", "max"),
                projected_players=("projection", lambda s: int((s > 0).sum())),
                combined_projection=("projection", "sum"),
                ceiling_sum=("ceiling", "sum"),
            )
            .sort_values(["game_total", "ceiling_sum"], ascending=[False, False])
            .reset_index(drop=True)
        )

        stack_rankings = self._build_stack_rankings(eligible)
        alerts = self._build_alerts(eligible, overview)

        return SlateDashboardResult(
            overview=overview,
            top_values=top_values.reset_index(drop=True),
            ceiling_leaders=ceiling_leaders.reset_index(drop=True),
            leverage_plays=leverage_plays.reset_index(drop=True),
            fades=fades.reset_index(drop=True),
            game_environment=game_environment,
            stack_rankings=stack_rankings,
            alerts=alerts,
        )

    def _build_stack_rankings(self, players: pd.DataFrame) -> pd.DataFrame:
        quarterbacks = players.loc[players["position"] == "QB"]
        skill = players.loc[players["position"].isin(self.SKILL_POSITIONS)]
        records: list[dict[str, object]] = []

        for _, qb in quarterbacks.iterrows():
            teammates = skill.loc[skill["team"] == qb["team"]].nlargest(5, "ceiling")
            bringbacks = skill.loc[skill["team"] == qb["opponent"]].nlargest(3, "ceiling")
            for _, teammate in teammates.iterrows():
                combinations = [(None, "QB + 1")]
                combinations.extend((bringback, "QB + 1 + bring-back") for _, bringback in bringbacks.iterrows())
                for bringback, stack_type in combinations:
                    members = [qb, teammate] + ([] if bringback is None else [bringback])
                    projection = sum(float(member["projection"]) for member in members)
                    ceiling = sum(float(member["ceiling"]) for member in members)
                    ownership = sum(float(member["ownership"]) for member in members)
                    salary = sum(int(member["salary"]) for member in members)
                    team_total = float(qb.get("team_implied_total", 0.0))
                    score = ceiling + 0.20 * projection + 0.10 * team_total - 0.12 * ownership
                    records.append({
                        "stack_type": stack_type,
                        "game": qb["game_key"],
                        "stack": " + ".join(str(member["name"]) for member in members),
                        "salary": salary,
                        "projection": projection,
                        "ceiling": ceiling,
                        "combined_ownership": ownership,
                        "team_implied_total": team_total,
                        "stack_score": score,
                    })

        if not records:
            return pd.DataFrame(columns=[
                "stack_type", "game", "stack", "salary", "projection", "ceiling",
                "combined_ownership", "team_implied_total", "stack_score",
            ])
        return pd.DataFrame(records).sort_values(
            ["stack_score", "ceiling"], ascending=[False, False]
        ).head(25).reset_index(drop=True)

    def _build_alerts(self, players: pd.DataFrame, overview: dict[str, object]) -> list[str]:
        alerts: list[str] = []
        missing_projection = int((players["projection"] <= 0).sum())
        if missing_projection:
            alerts.append(f"{missing_projection} players have zero or missing projections.")
        missing_ownership = int((players["ownership"] <= 0).sum())
        if missing_ownership:
            alerts.append(f"{missing_ownership} players have no projected ownership.")
        missing_vegas = int((players["game_total"] <= 0).sum())
        if missing_vegas:
            alerts.append(f"Vegas context is missing for {missing_vegas} players.")
        low_confidence = int((players["confidence"] < 50).sum())
        if low_confidence:
            alerts.append(f"{low_confidence} players have projection confidence below 50.")
        strong_matchups = players.loc[players["matchup_rating"] >= 80].nlargest(3, "projection")
        if not strong_matchups.empty:
            names = ", ".join(str(name) for name in strong_matchups["name"])
            alerts.append(f"Top favorable-matchup plays: {names}.")
        if overview.get("average_game_total") is None:
            alerts.append("Run the Weekly Update Vegas step to unlock game-environment rankings.")
        return alerts
