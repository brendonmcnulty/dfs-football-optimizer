from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DFSCoachResult:
    """Explainable slate and lineup recommendations."""

    player_rankings: pd.DataFrame
    slate_takeaways: list[str]
    lineup_rankings: pd.DataFrame


class DFSCoachService:
    """Turn projections and portfolio metrics into transparent DFS guidance."""

    SKILL_POSITIONS = {"RB", "WR", "TE"}

    @staticmethod
    def _numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(default, index=frame.index, dtype=float)
        return pd.to_numeric(frame[column], errors="coerce").fillna(default)

    @staticmethod
    def _percentile(series: pd.Series) -> pd.Series:
        if series.empty:
            return pd.Series(dtype=float)
        return series.rank(method="average", pct=True).fillna(0.5) * 100.0

    def prepare_players(self, player_pool: pd.DataFrame) -> pd.DataFrame:
        if player_pool.empty:
            raise ValueError("The selected player pool is empty.")

        players = player_pool.copy().reset_index(drop=True)
        for column, default in (
            ("salary", 0.0),
            ("projection", 0.0),
            ("ceiling", 0.0),
            ("floor", 0.0),
            ("ownership", 0.0),
            ("confidence", 0.0),
            ("team_implied_total", 0.0),
            ("game_total", 0.0),
            ("matchup_rating", 50.0),
            ("usage_adjustment", 0.0),
            ("matchup_adjustment", 0.0),
            ("vegas_adjustment", 0.0),
        ):
            players[column] = self._numeric(players, column, default)

        players["player_id"] = players.get("player_id", players.index).astype(str)
        players["name"] = players["name"].astype(str).str.strip()
        players["position"] = players["position"].astype(str).str.upper().str.strip()
        players["team"] = players["team"].astype(str).str.upper().str.strip()
        players["opponent"] = players.get("opponent", "").astype(str).str.upper().str.strip()
        players["excluded"] = players.get("excluded", False).fillna(False).astype(bool)
        players = players.loc[~players["excluded"]].copy()

        players["value"] = (
            players["projection"] / players["salary"].replace(0, pd.NA) * 1000.0
        ).fillna(0.0)
        players["ceiling_value"] = (
            players["ceiling"] / players["salary"].replace(0, pd.NA) * 1000.0
        ).fillna(0.0)
        players["leverage"] = players["ceiling"] * (
            1.0 - players["ownership"].clip(0, 100) / 100.0
        )

        grouped = players.groupby("position", group_keys=False)
        players["projection_percentile"] = grouped["projection"].transform(self._percentile)
        players["ceiling_percentile"] = grouped["ceiling"].transform(self._percentile)
        players["floor_percentile"] = grouped["floor"].transform(self._percentile)
        players["value_percentile"] = grouped["value"].transform(self._percentile)
        players["leverage_percentile"] = grouped["leverage"].transform(self._percentile)

        players["coach_score"] = (
            0.27 * players["projection_percentile"]
            + 0.25 * players["ceiling_percentile"]
            + 0.18 * players["value_percentile"]
            + 0.15 * players["leverage_percentile"]
            + 0.08 * players["matchup_rating"].clip(0, 100)
            + 0.07 * players["confidence"].clip(0, 100)
        )

        recommendations: list[str] = []
        reason_1: list[str] = []
        reason_2: list[str] = []
        reason_3: list[str] = []
        summaries: list[str] = []

        for _, player in players.iterrows():
            recommendation = self._recommendation(player)
            reasons = self._player_reasons(player)
            recommendations.append(recommendation)
            reason_1.append(reasons[0])
            reason_2.append(reasons[1])
            reason_3.append(reasons[2])
            summaries.append(" ".join(reasons))

        players["recommendation"] = recommendations
        players["reason_1"] = reason_1
        players["reason_2"] = reason_2
        players["reason_3"] = reason_3
        players["coach_summary"] = summaries
        return players.sort_values(
            ["coach_score", "ceiling", "projection"], ascending=[False, False, False]
        ).reset_index(drop=True)

    def build(
        self,
        player_pool: pd.DataFrame,
        lineups: list[tuple[str, pd.DataFrame]] | None = None,
        simulation_summary: pd.DataFrame | None = None,
    ) -> DFSCoachResult:
        players = self.prepare_players(player_pool)
        return DFSCoachResult(
            player_rankings=players,
            slate_takeaways=self._slate_takeaways(players),
            lineup_rankings=self.analyze_lineups(
                lineups or [], players, simulation_summary=simulation_summary
            ),
        )

    def _recommendation(self, player: pd.Series) -> str:
        score = float(player["coach_score"])
        floor_pct = float(player["floor_percentile"])
        ceiling_pct = float(player["ceiling_percentile"])
        ownership = float(player["ownership"])
        value_pct = float(player["value_percentile"])

        if score >= 82 and floor_pct >= 70 and value_pct >= 65:
            return "Core play"
        if score >= 76 and ceiling_pct >= 80 and ownership <= 18:
            return "Strong tournament play"
        if score >= 72 and floor_pct >= 75:
            return "Strong cash play"
        if score >= 65:
            return "Secondary target"
        if ownership >= 20 and value_pct <= 35:
            return "Potential fade"
        return "Neutral"

    def _player_reasons(self, player: pd.Series) -> list[str]:
        candidates: list[tuple[float, str]] = []
        projection = float(player["projection"])
        ceiling = float(player["ceiling"])
        ownership = float(player["ownership"])
        matchup = float(player["matchup_rating"])
        confidence = float(player["confidence"])
        team_total = float(player["team_implied_total"])
        value = float(player["value"])

        candidates.append((float(player["projection_percentile"]), f"Projects for {projection:.1f} points, placing near the top of the {player['position']} pool."))
        candidates.append((float(player["ceiling_percentile"]), f"Carries a {ceiling:.1f}-point ceiling and strong slate-relative upside."))
        candidates.append((float(player["value_percentile"]), f"Returns {value:.2f} projected points per $1,000 of salary."))
        candidates.append((float(player["leverage_percentile"]), f"Offers ceiling relative to {ownership:.1f}% projected ownership."))
        candidates.append((matchup, f"Faces {player['opponent'] or 'an unlisted opponent'} with a {matchup:.0f}/100 matchup rating."))
        candidates.append((confidence, f"Projection confidence is {confidence:.0f}/100."))
        if team_total > 0:
            candidates.append((min(100.0, team_total * 3.0), f"The offense carries a {team_total:.1f}-point implied team total."))

        adjustment = (
            float(player.get("usage_adjustment", 0.0))
            + float(player.get("matchup_adjustment", 0.0))
            + float(player.get("vegas_adjustment", 0.0))
        )
        if abs(adjustment) >= 0.2:
            direction = "adds" if adjustment > 0 else "removes"
            candidates.append((70.0 + min(abs(adjustment) * 5.0, 25.0), f"Usage, matchup, and Vegas context {direction} {abs(adjustment):.1f} points to the projection."))

        candidates.sort(key=lambda item: item[0], reverse=True)
        reasons = [text for _, text in candidates[:3]]
        while len(reasons) < 3:
            reasons.append("Additional context is limited until the weekly data pipeline is fully populated.")
        return reasons

    def _slate_takeaways(self, players: pd.DataFrame) -> list[str]:
        takeaways: list[str] = []
        if players.empty:
            return ["No eligible players are available for analysis."]

        top = players.iloc[0]
        takeaways.append(
            f"Top overall coach target: {top['name']} ({top['position']}, {top['team']}) — {top['recommendation'].lower()}."
        )

        leverage = players.loc[players["ownership"] <= 15].nlargest(1, "leverage")
        if not leverage.empty:
            row = leverage.iloc[0]
            takeaways.append(
                f"Best low-owned upside profile: {row['name']} at {row['ownership']:.1f}% ownership with a {row['ceiling']:.1f}-point ceiling."
            )

        values = players.nlargest(1, "value")
        if not values.empty:
            row = values.iloc[0]
            takeaways.append(
                f"Best salary value: {row['name']} at {row['value']:.2f} projected points per $1,000."
            )

        games = players.loc[players["game_total"] > 0]
        if not games.empty:
            row = games.nlargest(1, "game_total").iloc[0]
            takeaways.append(
                f"Best game environment: {row['team']} vs. {row['opponent']} with a {row['game_total']:.1f}-point total."
            )
        else:
            takeaways.append("Vegas game totals are unavailable; run Weekly Update before relying on game-environment advice.")
        return takeaways

    def analyze_lineups(
        self,
        lineups: list[tuple[str, pd.DataFrame]],
        players: pd.DataFrame,
        simulation_summary: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        columns = [
            "lineup_name", "recommendation", "coach_score", "salary", "projection",
            "ceiling", "ownership", "stack", "bring_back", "low_owned_players",
            "summary",
        ]
        if not lineups:
            return pd.DataFrame(columns=columns)

        player_lookup = players.set_index("player_id", drop=False)
        records: list[dict[str, object]] = []
        for lineup_name, lineup in lineups:
            roster = lineup.copy()
            if "player_id" in roster.columns:
                roster["player_id"] = roster["player_id"].astype(str)
                missing_metrics = [
                    column for column in players.columns
                    if column not in roster.columns and column != "player_id"
                ]
                if missing_metrics:
                    roster = roster.merge(
                        players[["player_id"] + missing_metrics], on="player_id", how="left"
                    )

            for column in ("salary", "projection", "ceiling", "ownership", "coach_score"):
                roster[column] = self._numeric(roster, column, 0.0)
            roster["position"] = roster["position"].astype(str).str.upper().str.strip()
            roster["team"] = roster["team"].astype(str).str.upper().str.strip()
            roster["opponent"] = roster.get("opponent", "").astype(str).str.upper().str.strip()

            qb_rows = roster.loc[roster["position"] == "QB"]
            stack = "None"
            bring_back = "No"
            if not qb_rows.empty:
                qb = qb_rows.iloc[0]
                teammates = roster.loc[
                    roster["position"].isin(self.SKILL_POSITIONS)
                    & (roster["team"] == qb["team"])
                ]
                opponents = roster.loc[
                    roster["position"].isin(self.SKILL_POSITIONS)
                    & (roster["team"] == qb["opponent"])
                ]
                if not teammates.empty:
                    stack = f"{qb['name']} + " + " + ".join(teammates["name"].astype(str))
                bring_back = "Yes" if not opponents.empty else "No"

            projection = float(roster["projection"].sum())
            ceiling = float(roster["ceiling"].sum())
            ownership = float(roster["ownership"].sum())
            salary = int(roster["salary"].sum())
            base_score = float(roster["coach_score"].mean())
            stack_bonus = 4.0 if stack != "None" else -3.0
            bringback_bonus = 2.0 if bring_back == "Yes" else 0.0
            salary_bonus = min(max((salary - 49000) / 250.0, -4.0), 4.0)
            lineup_score = base_score + stack_bonus + bringback_bonus + salary_bonus
            low_owned = int((roster["ownership"] <= 10).sum())

            if lineup_score >= 80 and ceiling >= 180:
                recommendation = "Elite tournament lineup"
            elif lineup_score >= 74:
                recommendation = "Strong lineup"
            elif lineup_score >= 66:
                recommendation = "Playable lineup"
            else:
                recommendation = "Needs review"

            summary_parts = [
                f"Projects for {projection:.1f} with a {ceiling:.1f}-point ceiling.",
                f"Combined ownership is {ownership:.1f}% with {low_owned} players at 10% or lower.",
            ]
            if stack != "None":
                summary_parts.append(f"Uses the correlated stack {stack}.")
            else:
                summary_parts.append("No QB pass-catcher stack was detected.")
            if bring_back == "Yes":
                summary_parts.append("Includes an opponent bring-back for added game correlation.")

            records.append({
                "lineup_name": lineup_name,
                "recommendation": recommendation,
                "coach_score": lineup_score,
                "salary": salary,
                "projection": projection,
                "ceiling": ceiling,
                "ownership": ownership,
                "stack": stack,
                "bring_back": bring_back,
                "low_owned_players": low_owned,
                "summary": " ".join(summary_parts),
            })

        result = pd.DataFrame(records)
        if simulation_summary is not None and not simulation_summary.empty and "lineup_name" in simulation_summary.columns:
            simulation_columns = [
                column for column in (
                    "lineup_name", "median", "p90", "target_hit_rate",
                    "portfolio_first_rate", "top_20_rate", "average_rank",
                ) if column in simulation_summary.columns
            ]
            result = result.merge(
                simulation_summary[simulation_columns].drop_duplicates("lineup_name"),
                on="lineup_name", how="left",
            )
            if "portfolio_first_rate" in result.columns:
                result["coach_score"] += result["portfolio_first_rate"].fillna(0.0) * 20.0

        return result.sort_values(
            ["coach_score", "ceiling", "projection"], ascending=[False, False, False]
        ).reset_index(drop=True)
