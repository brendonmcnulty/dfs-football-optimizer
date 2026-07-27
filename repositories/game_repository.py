from __future__ import annotations

from pathlib import Path

import pandas as pd

from database.connection import create_connection


class GameRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def replace_games(self, season: int, week: int, games: pd.DataFrame, fetched_at: str) -> int:
        with create_connection(self.database_path) as connection:
            connection.execute(
                'DELETE FROM games WHERE season = ? AND week = ?',
                (int(season), int(week)),
            )
            count = 0
            for _, game in games.iterrows():
                connection.execute(
                    '''
                    INSERT INTO games (
                        season, week, event_id, commence_time,
                        home_team, away_team, home_team_name, away_team_name,
                        home_spread, game_total, home_implied_total,
                        away_implied_total, home_moneyline, away_moneyline,
                        bookmaker_count, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        int(season), int(week), str(game.get('event_id', '')),
                        str(game.get('commence_time', '')), str(game.get('home_team', '')),
                        str(game.get('away_team', '')), str(game.get('home_team_name', '')),
                        str(game.get('away_team_name', '')), _nullable(game.get('home_spread')),
                        _nullable(game.get('game_total')), _nullable(game.get('home_implied_total')),
                        _nullable(game.get('away_implied_total')), _nullable(game.get('home_moneyline')),
                        _nullable(game.get('away_moneyline')), int(game.get('bookmaker_count', 0)),
                        fetched_at,
                    ),
                )
                count += 1
            connection.commit()
        return count

    def load_games(self, season: int, week: int) -> pd.DataFrame:
        with create_connection(self.database_path) as connection:
            return pd.read_sql_query(
                '''SELECT event_id, commence_time, home_team_name, away_team_name,
                          home_team, away_team, home_spread, game_total,
                          home_implied_total, away_implied_total,
                          home_moneyline, away_moneyline, bookmaker_count, fetched_at
                   FROM games WHERE season = ? AND week = ? ORDER BY commence_time''',
                connection,
                params=(int(season), int(week)),
            )


def _nullable(value):
    return None if pd.isna(value) else float(value)
