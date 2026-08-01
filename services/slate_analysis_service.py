from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class PlayerInsight:
    """Structured insight for one DFS player."""

    player_id: str
    name: str
    position: str
    team: str
    opponent: str
    salary: int
    projection: float
    ceiling: float
    floor: float
    ownership: float
    value: float
    leverage_score: float
    confidence: float
    matchup_rating: float
    recommendation: str
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GameInsight:
    """Structured insight for one NFL game environment."""

    game: str
    game_total: float
    highest_team_total: float
    combined_projection: float
    combined_ceiling: float
    player_count: int


@dataclass(frozen=True)
class StackInsight:
    """Structured insight for one quarterback stack."""

    stack_type: str
    game: str
    quarterback: str
    stack_players: tuple[str, ...]
    salary: int
    projection: float
    ceiling: float
    combined_ownership: float
    team_implied_total: float
    stack_score: float


@dataclass(frozen=True)
class SlateAnalysis:
    """Complete structured analysis for one DFS slate."""

    overview: dict[str, object]

    highest_total_game: GameInsight | None
    highest_ceiling_player: PlayerInsight | None
    best_game_stack: StackInsight | None

    best_value_plays: tuple[PlayerInsight, ...]
    ceiling_leaders: tuple[PlayerInsight, ...]
    cash_core: tuple[PlayerInsight, ...]
    gpp_core: tuple[PlayerInsight, ...]
    leverage_plays: tuple[PlayerInsight, ...]
    fade_candidates: tuple[PlayerInsight, ...]
    ownership_risks: tuple[PlayerInsight, ...]

    game_rankings: tuple[GameInsight, ...]
    stack_rankings: tuple[StackInsight, ...]

    alerts: tuple[str, ...]
    weather_alerts: tuple[str, ...] = field(default_factory=tuple)
    injury_alerts: tuple[str, ...] = field(default_factory=tuple)


class SlateAnalysisService:
    """
    Build reusable, structured DFS slate insights.

    This service contains analysis logic only. It does not depend on
    Streamlit and does not generate page-specific UI output.
    """

    SKILL_POSITIONS = {"RB", "WR", "TE"}

    PLAYER_COLUMNS = [
        "player_id",
        "name",
        "position",
        "team",
        "opponent",
        "salary",
        "projection",
        "ceiling",
        "floor",
        "ownership",
        "confidence",
        "matchup_rating",
        "team_implied_total",
        "game_total",
        "usage_adjustment",
        "matchup_adjustment",
        "vegas_adjustment",
        "locked",
        "excluded",
    ]

    @staticmethod
    def _numeric(
        frame: pd.DataFrame,
        column: str,
        default: float = 0.0,
    ) -> pd.Series:
        """Return a numeric series, supplying a default when unavailable."""

        if column not in frame.columns:
            return pd.Series(
                default,
                index=frame.index,
                dtype=float,
            )

        return pd.to_numeric(
            frame[column],
            errors="coerce",
        ).fillna(default)

    @staticmethod
    def _boolean(
        frame: pd.DataFrame,
        column: str,
        default: bool = False,
    ) -> pd.Series:
        """Return a normalized boolean series."""

        if column not in frame.columns:
            return pd.Series(
                default,
                index=frame.index,
                dtype=bool,
            )

        values = frame[column]

        if values.dtype == bool:
            return values.fillna(default)

        normalized = (
            values.fillna(default)
            .astype(str)
            .str.lower()
            .str.strip()
        )

        return normalized.isin(
            {
                "true",
                "1",
                "yes",
                "y",
                "on",
            }
        )

    @staticmethod
    def _percentile(series: pd.Series) -> pd.Series:
        """Return percentile ranks from zero to 100."""

        if series.empty:
            return pd.Series(dtype=float)

        return (
            series.rank(
                method="average",
                pct=True,
            )
            .fillna(0.5)
            * 100.0
        )

    def prepare_player_pool(
        self,
        player_pool: pd.DataFrame,
    ) -> pd.DataFrame:
        """Normalize and enrich the player pool for analysis."""

        if player_pool.empty:
            raise ValueError(
                "The selected player pool is empty."
            )

        players = player_pool.copy().reset_index(drop=True)

        required_columns = {
            "name",
            "position",
            "team",
            "salary",
            "projection",
        }

        missing_columns = required_columns - set(players.columns)

        if missing_columns:
            raise ValueError(
                "The player pool is missing required columns: "
                f"{sorted(missing_columns)}"
            )

        if "player_id" not in players.columns:
            players["player_id"] = (
                players.index.astype(str)
            )

        if "opponent" not in players.columns:
            players["opponent"] = ""

        players["player_id"] = (
            players["player_id"]
            .astype(str)
            .str.strip()
        )

        players["name"] = (
            players["name"]
            .astype(str)
            .str.strip()
        )

        players["position"] = (
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

        players["team"] = (
            players["team"]
            .astype(str)
            .str.upper()
            .str.strip()
        )

        players["opponent"] = (
            players["opponent"]
            .fillna("")
            .astype(str)
            .str.upper()
            .str.strip()
            .str.replace("@", "", regex=False)
        )

        numeric_defaults = {
            "salary": 0.0,
            "projection": 0.0,
            "ceiling": 0.0,
            "floor": 0.0,
            "ownership": 0.0,
            "confidence": 0.0,
            "matchup_rating": 50.0,
            "team_implied_total": 0.0,
            "game_total": 0.0,
            "usage_adjustment": 0.0,
            "matchup_adjustment": 0.0,
            "vegas_adjustment": 0.0,
        }

        for column, default in numeric_defaults.items():
            players[column] = self._numeric(
                players,
                column,
                default,
            )

        players["locked"] = self._boolean(
            players,
            "locked",
            False,
        )

        players["excluded"] = self._boolean(
            players,
            "excluded",
            False,
        )

        players["salary"] = (
            players["salary"]
            .clip(lower=0)
            .round()
            .astype(int)
        )

        players["ownership"] = (
            players["ownership"]
            .clip(lower=0.0, upper=100.0)
        )

        players["confidence"] = (
            players["confidence"]
            .clip(lower=0.0, upper=100.0)
        )

        players["matchup_rating"] = (
            players["matchup_rating"]
            .clip(lower=0.0, upper=100.0)
        )

        salary_denominator = (
            players["salary"]
            .replace(0, pd.NA)
        )

        players["value"] = (
            players["projection"]
            / salary_denominator
            * 1000.0
        ).fillna(0.0)

        players["leverage_score"] = (
            players["ceiling"]
            * (
                1.0
                - players["ownership"] / 100.0
            )
        )

        players["ownership_value_gap"] = (
            players["ownership"]
            - self._position_percentile(
                players,
                "value",
            )
        )

        players["floor_gap"] = (
            players["projection"]
            - players["floor"]
        ).clip(lower=0.0)

        players["ceiling_gap"] = (
            players["ceiling"]
            - players["projection"]
        ).clip(lower=0.0)

        players["context_adjustment"] = (
            players["usage_adjustment"]
            + players["matchup_adjustment"]
            + players["vegas_adjustment"]
        )

        players["game_key"] = players.apply(
            self._build_game_key,
            axis=1,
        )

        for metric in (
            "projection",
            "ceiling",
            "floor",
            "value",
            "leverage_score",
        ):
            players[
                f"{metric}_percentile"
            ] = self._position_percentile(
                players,
                metric,
            )

        players["cash_score"] = (
            0.34 * players["projection_percentile"]
            + 0.28 * players["floor_percentile"]
            + 0.22 * players["value_percentile"]
            + 0.10 * players["confidence"]
            + 0.06 * players["matchup_rating"]
        )

        players["gpp_score"] = (
            0.36 * players["ceiling_percentile"]
            + 0.24 * players["leverage_score_percentile"]
            + 0.16 * players["projection_percentile"]
            + 0.10 * players["value_percentile"]
            + 0.08 * players["matchup_rating"]
            + 0.06 * players["confidence"]
        )

        players["overall_score"] = (
            0.26 * players["projection_percentile"]
            + 0.24 * players["ceiling_percentile"]
            + 0.17 * players["value_percentile"]
            + 0.15 * players["leverage_score_percentile"]
            + 0.10 * players["matchup_rating"]
            + 0.08 * players["confidence"]
        )

        return players

    def analyze(
        self,
        player_pool: pd.DataFrame,
        limit: int = 10,
    ) -> SlateAnalysis:
        """Return complete structured analysis for the player pool."""

        if limit <= 0:
            raise ValueError(
                "The analysis limit must be greater than zero."
            )

        players = self.prepare_player_pool(player_pool)

        eligible = players.loc[
            ~players["excluded"]
        ].copy()

        if eligible.empty:
            raise ValueError(
                "No eligible players remain after exclusions."
            )

        game_rankings = self._build_game_rankings(
            eligible
        )

        stack_rankings = self._build_stack_rankings(
            eligible
        )

        best_value_rows = (
            eligible.sort_values(
                [
                    "value",
                    "projection",
                ],
                ascending=[
                    False,
                    False,
                ],
            )
            .head(limit)
        )

        ceiling_rows = (
            eligible.sort_values(
                [
                    "ceiling",
                    "projection",
                ],
                ascending=[
                    False,
                    False,
                ],
            )
            .head(limit)
        )

        cash_rows = (
            eligible.sort_values(
                [
                    "cash_score",
                    "floor",
                    "projection",
                ],
                ascending=[
                    False,
                    False,
                    False,
                ],
            )
            .head(limit)
        )

        gpp_rows = (
            eligible.sort_values(
                [
                    "gpp_score",
                    "ceiling",
                    "leverage_score",
                ],
                ascending=[
                    False,
                    False,
                    False,
                ],
            )
            .head(limit)
        )

        leverage_rows = (
            eligible.loc[
                eligible["ownership"] <= 20.0
            ]
            .sort_values(
                [
                    "leverage_score",
                    "ceiling",
                ],
                ascending=[
                    False,
                    False,
                ],
            )
            .head(limit)
        )

        fade_rows = self._find_fade_candidates(
            eligible,
            limit,
        )

        ownership_risk_rows = (
            eligible.loc[
                eligible["ownership"] >= 15.0
            ]
            .sort_values(
                [
                    "ownership_value_gap",
                    "ownership",
                ],
                ascending=[
                    False,
                    False,
                ],
            )
            .head(limit)
        )

        highest_ceiling_player = None

        if not ceiling_rows.empty:
            highest_ceiling_player = (
                self._row_to_player_insight(
                    ceiling_rows.iloc[0]
                )
            )

        highest_total_game = (
            game_rankings[0]
            if game_rankings
            else None
        )

        best_game_stack = (
            stack_rankings[0]
            if stack_rankings
            else None
        )

        overview = self._build_overview(
            eligible,
            game_rankings,
            stack_rankings,
        )

        alerts = self._build_alerts(
            eligible
        )

        return SlateAnalysis(
            overview=overview,
            highest_total_game=highest_total_game,
            highest_ceiling_player=highest_ceiling_player,
            best_game_stack=best_game_stack,
            best_value_plays=self._rows_to_player_insights(
                best_value_rows
            ),
            ceiling_leaders=self._rows_to_player_insights(
                ceiling_rows
            ),
            cash_core=self._rows_to_player_insights(
                cash_rows
            ),
            gpp_core=self._rows_to_player_insights(
                gpp_rows
            ),
            leverage_plays=self._rows_to_player_insights(
                leverage_rows
            ),
            fade_candidates=self._rows_to_player_insights(
                fade_rows
            ),
            ownership_risks=self._rows_to_player_insights(
                ownership_risk_rows
            ),
            game_rankings=tuple(game_rankings),
            stack_rankings=tuple(stack_rankings),
            alerts=tuple(alerts),
            weather_alerts=(),
            injury_alerts=(),
        )

    def _position_percentile(
        self,
        players: pd.DataFrame,
        column: str,
    ) -> pd.Series:
        """Calculate percentiles within each position."""

        return (
            players.groupby(
                "position",
                group_keys=False,
            )[column]
            .transform(self._percentile)
        )

    @staticmethod
    def _build_game_key(
        row: pd.Series,
    ) -> str:
        """Build one stable key for both teams in a matchup."""

        team = str(
            row.get("team", "")
        ).upper().strip()

        opponent = str(
            row.get("opponent", "")
        ).upper().strip()

        if not opponent:
            return team

        return " @ ".join(
            sorted(
                {
                    team,
                    opponent,
                }
            )
        )

    def _build_overview(
        self,
        players: pd.DataFrame,
        game_rankings: list[GameInsight],
        stack_rankings: list[StackInsight],
    ) -> dict[str, object]:
        """Build slate-level summary metrics."""

        vegas_players = players.loc[
            players["game_total"] > 0
        ]

        ownership_players = players.loc[
            players["ownership"] > 0
        ]

        return {
            "player_count": int(len(players)),
            "game_count": int(
                players["game_key"].nunique()
            ),
            "average_projection": float(
                players["projection"].mean()
            ),
            "average_ceiling": float(
                players["ceiling"].mean()
            ),
            "average_confidence": float(
                players["confidence"].mean()
            ),
            "average_game_total": (
                float(
                    vegas_players["game_total"].mean()
                )
                if not vegas_players.empty
                else None
            ),
            "average_ownership": (
                float(
                    ownership_players[
                        "ownership"
                    ].mean()
                )
                if not ownership_players.empty
                else None
            ),
            "highest_game_total": (
                game_rankings[0].game_total
                if game_rankings
                else None
            ),
            "top_stack_score": (
                stack_rankings[0].stack_score
                if stack_rankings
                else None
            ),
        }

    def _build_game_rankings(
        self,
        players: pd.DataFrame,
    ) -> list[GameInsight]:
        """Rank the slate's game environments."""

        grouped = (
            players.groupby(
                "game_key",
                as_index=False,
            )
            .agg(
                game_total=(
                    "game_total",
                    "max",
                ),
                highest_team_total=(
                    "team_implied_total",
                    "max",
                ),
                combined_projection=(
                    "projection",
                    "sum",
                ),
                combined_ceiling=(
                    "ceiling",
                    "sum",
                ),
                player_count=(
                    "player_id",
                    "count",
                ),
            )
        )

        grouped["environment_score"] = (
            0.45 * grouped["game_total"]
            + 0.35 * grouped["combined_ceiling"]
            + 0.20 * grouped["combined_projection"]
        )

        grouped = grouped.sort_values(
            [
                "environment_score",
                "game_total",
                "combined_ceiling",
            ],
            ascending=[
                False,
                False,
                False,
            ],
        )

        return [
            GameInsight(
                game=str(row["game_key"]),
                game_total=float(row["game_total"]),
                highest_team_total=float(
                    row["highest_team_total"]
                ),
                combined_projection=float(
                    row["combined_projection"]
                ),
                combined_ceiling=float(
                    row["combined_ceiling"]
                ),
                player_count=int(
                    row["player_count"]
                ),
            )
            for _, row in grouped.iterrows()
        ]

    def _build_stack_rankings(
        self,
        players: pd.DataFrame,
    ) -> list[StackInsight]:
        """Build and rank QB stacks with optional bring-backs."""

        quarterbacks = players.loc[
            players["position"] == "QB"
        ]

        skill_players = players.loc[
            players["position"].isin(
                self.SKILL_POSITIONS
            )
        ]

        stack_records: list[StackInsight] = []

        for _, quarterback in quarterbacks.iterrows():
            teammates = (
                skill_players.loc[
                    skill_players["team"]
                    == quarterback["team"]
                ]
                .sort_values(
                    [
                        "ceiling",
                        "projection",
                    ],
                    ascending=[
                        False,
                        False,
                    ],
                )
                .head(5)
            )

            bring_backs = (
                skill_players.loc[
                    skill_players["team"]
                    == quarterback["opponent"]
                ]
                .sort_values(
                    [
                        "ceiling",
                        "projection",
                    ],
                    ascending=[
                        False,
                        False,
                    ],
                )
                .head(3)
            )

            for _, teammate in teammates.iterrows():
                stack_records.append(
                    self._create_stack_insight(
                        quarterback=quarterback,
                        teammates=[
                            teammate,
                        ],
                        bring_back=None,
                        stack_type="QB + 1",
                    )
                )

                for _, bring_back in bring_backs.iterrows():
                    stack_records.append(
                        self._create_stack_insight(
                            quarterback=quarterback,
                            teammates=[
                                teammate,
                            ],
                            bring_back=bring_back,
                            stack_type=(
                                "QB + 1 + bring-back"
                            ),
                        )
                    )

            top_two_teammates = teammates.head(2)

            if len(top_two_teammates) == 2:
                stack_records.append(
                    self._create_stack_insight(
                        quarterback=quarterback,
                        teammates=[
                            top_two_teammates.iloc[0],
                            top_two_teammates.iloc[1],
                        ],
                        bring_back=None,
                        stack_type="QB + 2",
                    )
                )

                for _, bring_back in bring_backs.iterrows():
                    stack_records.append(
                        self._create_stack_insight(
                            quarterback=quarterback,
                            teammates=[
                                top_two_teammates.iloc[0],
                                top_two_teammates.iloc[1],
                            ],
                            bring_back=bring_back,
                            stack_type=(
                                "QB + 2 + bring-back"
                            ),
                        )
                    )

        return sorted(
            stack_records,
            key=lambda stack: (
                stack.stack_score,
                stack.ceiling,
                stack.projection,
            ),
            reverse=True,
        )[:30]

    def _create_stack_insight(
        self,
        quarterback: pd.Series,
        teammates: list[pd.Series],
        bring_back: pd.Series | None,
        stack_type: str,
    ) -> StackInsight:
        """Create one scored stack insight."""

        members = [
            quarterback,
            *teammates,
        ]

        if bring_back is not None:
            members.append(bring_back)

        salary = sum(
            int(member["salary"])
            for member in members
        )

        projection = sum(
            float(member["projection"])
            for member in members
        )

        ceiling = sum(
            float(member["ceiling"])
            for member in members
        )

        combined_ownership = sum(
            float(member["ownership"])
            for member in members
        )

        team_implied_total = float(
            quarterback["team_implied_total"]
        )

        game_total = float(
            quarterback["game_total"]
        )

        stack_score = (
            ceiling
            + 0.22 * projection
            + 0.12 * team_implied_total
            + 0.06 * game_total
            - 0.14 * combined_ownership
        )

        return StackInsight(
            stack_type=stack_type,
            game=str(
                quarterback["game_key"]
            ),
            quarterback=str(
                quarterback["name"]
            ),
            stack_players=tuple(
                str(member["name"])
                for member in members
            ),
            salary=salary,
            projection=projection,
            ceiling=ceiling,
            combined_ownership=combined_ownership,
            team_implied_total=team_implied_total,
            stack_score=stack_score,
        )

    def _find_fade_candidates(
        self,
        players: pd.DataFrame,
        limit: int,
    ) -> pd.DataFrame:
        """Identify players whose ownership exceeds their value profile."""

        candidates = players.loc[
            players["ownership"] >= 10.0
        ].copy()

        candidates["fade_score"] = (
            0.45 * candidates["ownership"]
            + 0.30 * (
                100.0
                - candidates["value_percentile"]
            )
            + 0.15 * (
                100.0
                - candidates["ceiling_percentile"]
            )
            + 0.10 * (
                100.0
                - candidates["confidence"]
            )
        )

        return (
            candidates.sort_values(
                [
                    "fade_score",
                    "ownership",
                ],
                ascending=[
                    False,
                    False,
                ],
            )
            .head(limit)
        )

    def _rows_to_player_insights(
        self,
        rows: pd.DataFrame,
    ) -> tuple[PlayerInsight, ...]:
        """Convert player rows into typed insights."""

        return tuple(
            self._row_to_player_insight(row)
            for _, row in rows.iterrows()
        )

    def _row_to_player_insight(
        self,
        player: pd.Series,
    ) -> PlayerInsight:
        """Convert one normalized player row into an insight."""

        recommendation = self._recommend_player(
            player
        )

        reasons = tuple(
            self._build_player_reasons(
                player
            )
        )

        return PlayerInsight(
            player_id=str(
                player["player_id"]
            ),
            name=str(
                player["name"]
            ),
            position=str(
                player["position"]
            ),
            team=str(
                player["team"]
            ),
            opponent=str(
                player["opponent"]
            ),
            salary=int(
                player["salary"]
            ),
            projection=float(
                player["projection"]
            ),
            ceiling=float(
                player["ceiling"]
            ),
            floor=float(
                player["floor"]
            ),
            ownership=float(
                player["ownership"]
            ),
            value=float(
                player["value"]
            ),
            leverage_score=float(
                player["leverage_score"]
            ),
            confidence=float(
                player["confidence"]
            ),
            matchup_rating=float(
                player["matchup_rating"]
            ),
            recommendation=recommendation,
            reasons=reasons,
        )

    @staticmethod
    def _recommend_player(
        player: pd.Series,
    ) -> str:
        """Assign a reusable slate recommendation."""

        cash_score = float(
            player["cash_score"]
        )

        gpp_score = float(
            player["gpp_score"]
        )

        ownership = float(
            player["ownership"]
        )

        value_percentile = float(
            player["value_percentile"]
        )

        if cash_score >= 78.0 and gpp_score >= 75.0:
            return "Core play"

        if gpp_score >= 76.0 and ownership <= 20.0:
            return "Strong tournament play"

        if cash_score >= 74.0:
            return "Strong cash play"

        if gpp_score >= 66.0:
            return "Tournament target"

        if (
            ownership >= 18.0
            and value_percentile <= 35.0
        ):
            return "Potential fade"

        return "Secondary option"

    @staticmethod
    def _build_player_reasons(
        player: pd.Series,
    ) -> list[str]:
        """Return the strongest data-supported player reasons."""

        candidates: list[tuple[float, str]] = []

        candidates.append(
            (
                float(
                    player[
                        "projection_percentile"
                    ]
                ),
                (
                    f"Projects for "
                    f"{float(player['projection']):.1f} "
                    "DraftKings points."
                ),
            )
        )

        candidates.append(
            (
                float(
                    player[
                        "ceiling_percentile"
                    ]
                ),
                (
                    f"Carries a "
                    f"{float(player['ceiling']):.1f}"
                    "-point ceiling."
                ),
            )
        )

        candidates.append(
            (
                float(
                    player[
                        "value_percentile"
                    ]
                ),
                (
                    f"Provides "
                    f"{float(player['value']):.2f} "
                    "projected points per $1,000."
                ),
            )
        )

        candidates.append(
            (
                float(
                    player[
                        "leverage_score_percentile"
                    ]
                ),
                (
                    f"Pairs a "
                    f"{float(player['ceiling']):.1f}"
                    "-point ceiling with "
                    f"{float(player['ownership']):.1f}% "
                    "projected ownership."
                ),
            )
        )

        candidates.append(
            (
                float(
                    player["matchup_rating"]
                ),
                (
                    f"Matchup rating is "
                    f"{float(player['matchup_rating']):.0f}/100 "
                    f"against {player['opponent'] or 'an unlisted opponent'}."
                ),
            )
        )

        if float(
            player["team_implied_total"]
        ) > 0:
            candidates.append(
                (
                    min(
                        100.0,
                        float(
                            player[
                                "team_implied_total"
                            ]
                        )
                        * 3.0,
                    ),
                    (
                        f"{player['team']} has a "
                        f"{float(player['team_implied_total']):.1f}"
                        "-point implied total."
                    ),
                )
            )

        if abs(
            float(
                player["context_adjustment"]
            )
        ) >= 0.2:
            adjustment = float(
                player["context_adjustment"]
            )

            direction = (
                "adds"
                if adjustment > 0
                else "removes"
            )

            candidates.append(
                (
                    min(
                        100.0,
                        70.0
                        + abs(adjustment) * 5.0,
                    ),
                    (
                        "Vegas, usage, and matchup context "
                        f"{direction} "
                        f"{abs(adjustment):.1f} projection points."
                    ),
                )
            )

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return [
            reason
            for _, reason in candidates[:3]
        ]

    @staticmethod
    def _build_alerts(
        players: pd.DataFrame,
    ) -> list[str]:
        """Report incomplete data that may weaken the analysis."""

        alerts: list[str] = []

        zero_projections = int(
            (
                players["projection"] <= 0
            ).sum()
        )

        if zero_projections:
            alerts.append(
                f"{zero_projections} eligible players have "
                "zero or missing projections."
            )

        missing_ownership = int(
            (
                players["ownership"] <= 0
            ).sum()
        )

        if missing_ownership:
            alerts.append(
                f"{missing_ownership} eligible players have "
                "no projected ownership."
            )

        missing_vegas = int(
            (
                players["game_total"] <= 0
            ).sum()
        )

        if missing_vegas:
            alerts.append(
                f"Vegas context is missing for "
                f"{missing_vegas} eligible players."
            )

        low_confidence = int(
            (
                players["confidence"] < 50
            ).sum()
        )

        if low_confidence:
            alerts.append(
                f"{low_confidence} eligible players have "
                "projection confidence below 50."
            )

        matchup_defaults = int(
            (
                players["matchup_rating"] == 50
            ).sum()
        )

        if matchup_defaults:
            alerts.append(
                f"{matchup_defaults} eligible players still "
                "have the default matchup rating."
            )

        return alerts