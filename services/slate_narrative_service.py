from __future__ import annotations

from dataclasses import dataclass, field

from services.slate_analysis_service import (
    GameInsight,
    PlayerInsight,
    SlateAnalysis,
    StackInsight,
)


@dataclass(frozen=True)
class NarrativeSection:
    """One titled section in the deterministic slate report."""

    title: str
    summary: str
    items: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SlateNarrative:
    """Readable, evidence-backed narrative for one DFS slate."""

    headline: str
    executive_summary: str
    sections: tuple[NarrativeSection, ...]
    alerts: tuple[str, ...]


class SlateNarrativeService:
    """
    Convert structured slate analysis into readable explanations.

    This service does not rank players or calculate projections. It only
    explains a ``SlateAnalysis`` produced by ``SlateAnalysisService``.
    """

    def build(
        self,
        analysis: SlateAnalysis,
        *,
        slate_name: str = "Active slate",
        player_limit: int = 5,
        stack_limit: int = 5,
    ) -> SlateNarrative:
        """Build a complete deterministic narrative report."""

        if player_limit < 1:
            raise ValueError("Player limit must be at least one.")

        if stack_limit < 1:
            raise ValueError("Stack limit must be at least one.")

        sections = (
            self._player_section(
                "Best value plays",
                "Players offering the strongest projected return for salary.",
                analysis.best_value_plays[:player_limit],
            ),
            self._player_section(
                "Tournament targets",
                "Players combining ceiling, leverage, and tournament appeal.",
                analysis.gpp_core[:player_limit],
            ),
            self._player_section(
                "Cash-game core",
                "Players with strong projection, floor, value, and confidence profiles.",
                analysis.cash_core[:player_limit],
            ),
            self._player_section(
                "Leverage plays",
                "Lower-owned players whose ceiling creates tournament leverage.",
                analysis.leverage_plays[:player_limit],
            ),
            self._player_section(
                "Potential fades",
                "Popular players whose value or ceiling profile creates risk.",
                analysis.fade_candidates[:player_limit],
            ),
            self._game_section(
                analysis.game_rankings[:player_limit],
            ),
            self._stack_section(
                analysis.stack_rankings[:stack_limit],
            ),
        )

        alerts = tuple(
            dict.fromkeys(
                (
                    *analysis.alerts,
                    *analysis.weather_alerts,
                    *analysis.injury_alerts,
                )
            )
        )

        return SlateNarrative(
            headline=f"{slate_name} analysis",
            executive_summary=self._executive_summary(analysis),
            sections=sections,
            alerts=alerts,
        )

    def explain_player(self, player: PlayerInsight) -> NarrativeSection:
        """Build a focused explanation for one player insight."""

        summary = (
            f"{player.name} is classified as {player.recommendation.lower()} "
            f"with a {player.projection:.1f}-point projection, "
            f"{player.ceiling:.1f}-point ceiling, and "
            f"{player.ownership:.1f}% projected ownership."
        )

        items = player.reasons or (
            f"Value: {player.value:.2f} projected points per $1,000.",
            f"Matchup rating: {player.matchup_rating:.0f}/100.",
            f"Projection confidence: {player.confidence:.0f}/100.",
        )

        return NarrativeSection(
            title=f"Why {player.name}?",
            summary=summary,
            items=items,
        )

    @staticmethod
    def _executive_summary(analysis: SlateAnalysis) -> str:
        """Create the top-level slate summary from the strongest signals."""

        sentences: list[str] = []
        overview = analysis.overview

        player_count = int(overview.get("player_count", 0) or 0)
        game_count = int(overview.get("game_count", 0) or 0)

        sentences.append(
            f"The current pool contains {player_count} eligible players "
            f"across {game_count} game environments."
        )

        game = analysis.highest_total_game
        if game is not None:
            if game.game_total > 0:
                sentences.append(
                    f"{game.game} owns the strongest game environment at "
                    f"{game.game_total:.1f} expected points and "
                    f"{game.combined_ceiling:.1f} combined player ceiling points."
                )
            else:
                sentences.append(
                    f"{game.game} ranks as the strongest available game environment "
                    "based on the loaded projections and ceilings."
                )

        player = analysis.highest_ceiling_player
        if player is not None:
            sentences.append(
                f"{player.name} leads the slate in ceiling at "
                f"{player.ceiling:.1f} points."
            )

        stack = analysis.best_game_stack
        if stack is not None:
            members = ", ".join(stack.stack_players)
            sentences.append(
                f"The top-rated stack is {members}, with a "
                f"{stack.ceiling:.1f}-point combined ceiling and "
                f"{stack.combined_ownership:.1f}% combined ownership."
            )

        if analysis.alerts:
            sentences.append(
                "Review the data-quality alerts before treating these rankings "
                "as final recommendations."
            )

        return " ".join(sentences)

    def _player_section(
        self,
        title: str,
        summary: str,
        players: tuple[PlayerInsight, ...],
    ) -> NarrativeSection:
        """Create one section from ranked player insights."""

        items = tuple(
            self._player_sentence(player)
            for player in players
        )

        if not items:
            items = (
                "No players met the current criteria with the available data.",
            )

        return NarrativeSection(
            title=title,
            summary=summary,
            items=items,
        )

    @staticmethod
    def _player_sentence(player: PlayerInsight) -> str:
        """Create one concise, metric-backed player explanation."""

        reason = (
            player.reasons[0]
            if player.reasons
            else (
                f"Projects for {player.projection:.1f} points with a "
                f"{player.ceiling:.1f}-point ceiling."
            )
        )

        return (
            f"{player.name} ({player.position}, {player.team}) — "
            f"{player.recommendation}. {reason} "
            f"Ownership: {player.ownership:.1f}%; "
            f"value: {player.value:.2f} per $1,000."
        )

    @staticmethod
    def _game_section(
        games: tuple[GameInsight, ...],
    ) -> NarrativeSection:
        """Create the ranked game-environment section."""

        items = tuple(
            (
                f"{game.game} — total {game.game_total:.1f}, "
                f"highest implied team total {game.highest_team_total:.1f}, "
                f"combined ceiling {game.combined_ceiling:.1f}."
            )
            for game in games
        )

        if not items:
            items = (
                "No complete game environments are available.",
            )

        return NarrativeSection(
            title="Game environments",
            summary=(
                "Games ranked by total, implied scoring, projection, and ceiling context."
            ),
            items=items,
        )

    @staticmethod
    def _stack_section(
        stacks: tuple[StackInsight, ...],
    ) -> NarrativeSection:
        """Create the ranked stack section."""

        items = tuple(
            (
                f"{stack.stack_type}: {', '.join(stack.stack_players)} — "
                f"projection {stack.projection:.1f}, ceiling {stack.ceiling:.1f}, "
                f"ownership {stack.combined_ownership:.1f}%, "
                f"score {stack.stack_score:.1f}."
            )
            for stack in stacks
        )

        if not items:
            items = (
                "No valid quarterback stacks were found in the active pool.",
            )

        return NarrativeSection(
            title="Best stacks",
            summary=(
                "Quarterback stacks ranked by ceiling, projection, implied totals, "
                "and ownership cost."
            ),
            items=items,
        )
