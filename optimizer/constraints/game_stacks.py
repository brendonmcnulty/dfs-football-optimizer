from __future__ import annotations

import pandas as pd
from ortools.sat.python import cp_model


def _game_key(team: str, opponent: str) -> tuple[str, str] | None:
    """Return a stable two-team identifier for a game."""

    normalized_team = str(team).upper().strip()
    normalized_opponent = str(opponent).upper().strip()

    if not normalized_team or not normalized_opponent:
        return None

    if normalized_team == normalized_opponent:
        return None

    return tuple(sorted((normalized_team, normalized_opponent)))


def add_game_stack_constraints(
    model: cp_model.CpModel,
    pool: pd.DataFrame,
    selected_player: dict[int, cp_model.IntVar],
    minimum_players_from_primary_game: int | None,
    maximum_players_per_game: int | None,
) -> None:
    """Apply minimum primary-game and maximum per-game lineup rules."""

    if (
        minimum_players_from_primary_game is None
        and maximum_players_per_game is None
    ):
        return

    game_player_indexes: dict[tuple[str, str], list[int]] = {}

    for player_index, player in pool.iterrows():
        game = _game_key(
            player["team"],
            player["opponent"],
        )

        if game is None:
            continue

        game_player_indexes.setdefault(game, []).append(player_index)

    if maximum_players_per_game is not None:
        maximum = int(maximum_players_per_game)

        for player_indexes in game_player_indexes.values():
            model.Add(
                sum(selected_player[index] for index in player_indexes)
                <= maximum
            )

    if minimum_players_from_primary_game is None:
        return

    minimum = int(minimum_players_from_primary_game)
    eligible_games = {
        game: player_indexes
        for game, player_indexes in game_player_indexes.items()
        if len(player_indexes) >= minimum
    }

    if not eligible_games:
        model.Add(0 == 1)
        return

    primary_game_variables: list[cp_model.IntVar] = []

    for game, player_indexes in eligible_games.items():
        variable_name = (
            "primary_game_"
            + "_".join(game)
        )
        is_primary_game = model.NewBoolVar(variable_name)
        primary_game_variables.append(is_primary_game)

        model.Add(
            sum(selected_player[index] for index in player_indexes)
            >= minimum * is_primary_game
        )

    model.AddExactlyOne(primary_game_variables)
