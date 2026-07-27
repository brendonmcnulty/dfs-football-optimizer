from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from database.connection import create_connection


class DataUpdateRepository:
    """Store an audit trail of weekly data-pipeline runs."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def record_update(
        self,
        season: int,
        week: int,
        site: str,
        slate_name: str,
        player_count: int,
        source_names: list[str],
        aggregation: str,
    ) -> int:
        created_at = datetime.now().isoformat(timespec="seconds")
        source_text = ", ".join(source_names) if source_names else "Salary file only"

        with create_connection(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO data_updates (
                    season,
                    week,
                    site,
                    slate_name,
                    player_count,
                    source_names,
                    aggregation,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(season),
                    int(week),
                    site.strip(),
                    slate_name.strip(),
                    int(player_count),
                    source_text,
                    aggregation,
                    created_at,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_updates(self, limit: int = 25) -> pd.DataFrame:
        with create_connection(self.database_path) as connection:
            return pd.read_sql_query(
                """
                SELECT
                    id,
                    season,
                    week,
                    site,
                    slate_name,
                    player_count,
                    source_names,
                    aggregation,
                    created_at
                FROM data_updates
                ORDER BY id DESC
                LIMIT ?
                """,
                connection,
                params=(int(limit),),
            )
