from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from database.connection import create_connection


class HistoricalRepository:
    """Store historical actual fantasy results for saved slates."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def save_results(self, slate_id: int, results: pd.DataFrame) -> int:
        required = {"player_id", "name", "team", "actual_points"}
        missing = required - set(results.columns)
        if missing:
            raise ValueError(f"Historical results are missing columns: {sorted(missing)}")

        saved = 0
        updated_at = datetime.now().isoformat(timespec="seconds")
        with create_connection(self.database_path) as connection:
            for _, row in results.iterrows():
                actual = pd.to_numeric(pd.Series([row["actual_points"]]), errors="coerce").iloc[0]
                if pd.isna(actual):
                    continue
                connection.execute(
                    """
                    INSERT INTO historical_results (
                        slate_id, external_player_id, player_name, team,
                        actual_points, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(slate_id, external_player_id)
                    DO UPDATE SET
                        player_name = excluded.player_name,
                        team = excluded.team,
                        actual_points = excluded.actual_points,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(slate_id), str(row["player_id"]), str(row["name"]),
                        str(row["team"]), float(actual), updated_at,
                    ),
                )
                saved += 1
            connection.commit()
        return saved

    def load_results(self, slate_id: int) -> pd.DataFrame:
        with create_connection(self.database_path) as connection:
            return pd.read_sql_query(
                """
                SELECT external_player_id AS player_id, player_name AS name,
                       team, actual_points, updated_at
                FROM historical_results
                WHERE slate_id = ?
                ORDER BY actual_points DESC, player_name
                """,
                connection,
                params=(int(slate_id),),
            )

    def load_evaluation(self, slate_id: int) -> pd.DataFrame:
        with create_connection(self.database_path) as connection:
            return pd.read_sql_query(
                """
                SELECT p.external_player_id AS player_id,
                       p.player_name AS name, p.position, p.team, p.opponent,
                       p.salary, p.projection, p.ceiling, p.floor,
                       p.ownership, p.confidence, h.actual_points
                FROM players p
                JOIN historical_results h
                  ON h.slate_id = p.slate_id
                 AND h.external_player_id = p.external_player_id
                WHERE p.slate_id = ?
                ORDER BY h.actual_points DESC, p.player_name
                """,
                connection,
                params=(int(slate_id),),
            )
