from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContestStrategyPreset:
    """Recommended optimizer defaults for one NFL Classic contest style."""

    key: str
    label: str
    description: str
    lineup_count: int
    minimum_salary: int
    minimum_unique_players: int
    qb_stack_size: int
    require_bring_back: bool
    maximum_players_per_team: int | None
    minimum_players_from_primary_game: int | None
    maximum_players_per_game: int | None
    optimization_target: str
    limit_total_ownership: bool
    maximum_total_ownership: float | None
    default_player_max_exposure: float

    @property
    def summary_rows(self) -> tuple[tuple[str, str], ...]:
        """Return human-readable settings for the preset preview."""

        stack_label = (
            "Off"
            if self.qb_stack_size == 0
            else f"QB +{self.qb_stack_size} pass catcher(s)"
        )
        ownership_label = (
            "Off"
            if not self.limit_total_ownership
            else f"{self.maximum_total_ownership:.0f}% maximum total"
        )
        primary_game_label = (
            "Off"
            if self.minimum_players_from_primary_game is None
            else f"At least {self.minimum_players_from_primary_game} players"
        )
        maximum_game_label = (
            "No limit"
            if self.maximum_players_per_game is None
            else str(self.maximum_players_per_game)
        )

        return (
            ("Lineups", str(self.lineup_count)),
            ("Minimum salary", f"${self.minimum_salary:,}"),
            ("Minimum unique players", str(self.minimum_unique_players)),
            ("QB stack", stack_label),
            (
                "Opponent bring-back",
                "Required" if self.require_bring_back else "Off",
            ),
            (
                "Maximum players per team",
                "No limit"
                if self.maximum_players_per_team is None
                else str(self.maximum_players_per_team),
            ),
            ("Primary game stack", primary_game_label),
            ("Maximum players per game", maximum_game_label),
            ("Optimization target", self.optimization_target.replace("_", " ").title()),
            ("Ownership cap", ownership_label),
            (
                "Default player max exposure",
                f"{self.default_player_max_exposure:.0%}",
            ),
        )


CONTEST_STRATEGY_PRESETS: dict[str, ContestStrategyPreset] = {
    "cash": ContestStrategyPreset(
        key="cash",
        label="Cash Games",
        description=(
            "Prioritizes median projection, floor, value, and near-complete "
            "salary usage for head-to-heads, 50/50s, and double-ups."
        ),
        lineup_count=1,
        minimum_salary=49_800,
        minimum_unique_players=1,
        qb_stack_size=0,
        require_bring_back=False,
        maximum_players_per_team=4,
        minimum_players_from_primary_game=None,
        maximum_players_per_game=5,
        optimization_target="cash",
        limit_total_ownership=False,
        maximum_total_ownership=None,
        default_player_max_exposure=1.00,
    ),
    "single_entry_gpp": ContestStrategyPreset(
        key="single_entry_gpp",
        label="Single-Entry GPP",
        description=(
            "Builds one correlated tournament lineup with a QB stack and "
            "opponent bring-back while balancing projection and ceiling."
        ),
        lineup_count=1,
        minimum_salary=49_500,
        minimum_unique_players=1,
        qb_stack_size=1,
        require_bring_back=True,
        maximum_players_per_team=4,
        minimum_players_from_primary_game=3,
        maximum_players_per_game=5,
        optimization_target="single_entry",
        limit_total_ownership=False,
        maximum_total_ownership=None,
        default_player_max_exposure=1.00,
    ),
    "three_max_gpp": ContestStrategyPreset(
        key="three_max_gpp",
        label="3-Max GPP",
        description=(
            "Creates three differentiated, correlated tournament lineups. "
            "A 67% player cap generally limits a player to two of three lineups."
        ),
        lineup_count=3,
        minimum_salary=49_300,
        minimum_unique_players=2,
        qb_stack_size=1,
        require_bring_back=True,
        maximum_players_per_team=4,
        minimum_players_from_primary_game=3,
        maximum_players_per_game=5,
        optimization_target="single_entry",
        limit_total_ownership=False,
        maximum_total_ownership=None,
        default_player_max_exposure=0.67,
    ),
    "twenty_max_gpp": ContestStrategyPreset(
        key="twenty_max_gpp",
        label="20-Max GPP",
        description=(
            "Emphasizes double stacks, bring-backs, diversification, and "
            "moderate player exposure for multi-entry tournaments."
        ),
        lineup_count=20,
        minimum_salary=49_000,
        minimum_unique_players=3,
        qb_stack_size=2,
        require_bring_back=True,
        maximum_players_per_team=4,
        minimum_players_from_primary_game=3,
        maximum_players_per_game=5,
        optimization_target="large_field_gpp",
        limit_total_ownership=True,
        maximum_total_ownership=150.0,
        default_player_max_exposure=0.50,
    ),
    "one_fifty_max_gpp": ContestStrategyPreset(
        key="one_fifty_max_gpp",
        label="150-Max GPP",
        description=(
            "Uses aggressive correlation and diversification for large-field "
            "mass multi-entry portfolios. Review and customize exposures after applying."
        ),
        lineup_count=150,
        minimum_salary=48_500,
        minimum_unique_players=4,
        qb_stack_size=2,
        require_bring_back=True,
        maximum_players_per_team=4,
        minimum_players_from_primary_game=3,
        maximum_players_per_game=6,
        optimization_target="large_field_gpp",
        limit_total_ownership=True,
        maximum_total_ownership=135.0,
        default_player_max_exposure=0.35,
    ),
}


def get_contest_strategy_preset(key: str) -> ContestStrategyPreset:
    """Return one preset or raise a clear error."""

    try:
        return CONTEST_STRATEGY_PRESETS[str(key)]
    except KeyError as error:
        raise ValueError(f"Unknown contest strategy preset: {key}") from error
