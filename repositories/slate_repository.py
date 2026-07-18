from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from database.connection import create_connection


class SlateRepository:
    """Store and retrieve slates and their player pools."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def save_slate(
        self,
        season: int,
        week: int,
        site: str,
        slate_name: str,
    ) -> int:
        """Create a slate or return the matching existing slate ID."""

        clean_site = site.strip()
        clean_slate_name = slate_name.strip()
        created_at = datetime.now().isoformat(timespec="seconds")

        if not clean_site:
            raise ValueError("Site cannot be blank.")

        if not clean_slate_name:
            raise ValueError("Slate name cannot be blank.")

        with create_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO slates (
                    season,
                    week,
                    site,
                    slate_name,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(season, week, site, slate_name)
                DO NOTHING
                """,
                (
                    int(season),
                    int(week),
                    clean_site,
                    clean_slate_name,
                    created_at,
                ),
            )

            row = connection.execute(
                """
                SELECT id
                FROM slates
                WHERE season = ?
                  AND week = ?
                  AND site = ?
                  AND slate_name = ?
                """,
                (
                    int(season),
                    int(week),
                    clean_site,
                    clean_slate_name,
                ),
            ).fetchone()

            if row is None:
                raise RuntimeError("The slate could not be saved.")

            connection.commit()

            return int(row["id"])

    def save_player_pool(
        self,
        slate_id: int,
        players: pd.DataFrame,
    ) -> int:
        """Save or update every player belonging to a slate."""

        required_columns = {
            "player_id",
            "name",
            "position",
            "team",
            "opponent",
            "salary",
            "projection",
            "locked",
            "excluded",
        }

        missing_columns = required_columns - set(players.columns)

        if missing_columns:
            raise ValueError(
                "Cannot save player pool. Missing columns: "
                f"{sorted(missing_columns)}"
            )

        current_time = datetime.now().isoformat(timespec="seconds")
        records_processed = 0

        with create_connection(self.database_path) as connection:
            slate_exists = connection.execute(
                """
                SELECT id
                FROM slates
                WHERE id = ?
                """,
                (int(slate_id),),
            ).fetchone()

            if slate_exists is None:
                raise ValueError(
                    f"Slate ID {slate_id} does not exist."
                )

            for _, player in players.iterrows():
                opponent = player["opponent"]

                if pd.isna(opponent):
                    opponent = ""

                connection.execute(
                    """
                    INSERT INTO players (
                        slate_id,
                        external_player_id,
                        player_name,
                        position,
                        team,
                        opponent,
                        salary,
                        projection,
                        locked,
                        excluded,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(slate_id, external_player_id)
                    DO UPDATE SET
                        player_name = excluded.player_name,
                        position = excluded.position,
                        team = excluded.team,
                        opponent = excluded.opponent,
                        salary = excluded.salary,
                        projection = excluded.projection,
                        locked = excluded.locked,
                        excluded = excluded.excluded,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(slate_id),
                        str(player["player_id"]),
                        str(player["name"]),
                        str(player["position"]),
                        str(player["team"]),
                        str(opponent),
                        int(player["salary"]),
                        float(player["projection"]),
                        int(bool(player["locked"])),
                        int(bool(player["excluded"])),
                        current_time,
                        current_time,
                    ),
                )

                records_processed += 1

            connection.commit()

        return records_processed

    def list_slates(self) -> pd.DataFrame:
        """Return all saved slates, newest first."""

        with create_connection(self.database_path) as connection:
            return pd.read_sql_query(
                """
                SELECT
                    id,
                    season,
                    week,
                    site,
                    slate_name,
                    created_at
                FROM slates
                ORDER BY
                    season DESC,
                    week DESC,
                    created_at DESC,
                    id DESC
                """,
                connection,
            )

    def load_player_pool(
        self,
        slate_id: int,
    ) -> pd.DataFrame:
        """Load a saved slate's player pool."""

        with create_connection(self.database_path) as connection:
            players = pd.read_sql_query(
                """
                SELECT
                    external_player_id AS player_id,
                    player_name AS name,
                    position,
                    team,
                    opponent,
                    salary,
                    projection,
                    locked,
                    excluded
                FROM players
                WHERE slate_id = ?
                ORDER BY
                    CASE position
                        WHEN 'QB' THEN 1
                        WHEN 'RB' THEN 2
                        WHEN 'WR' THEN 3
                        WHEN 'TE' THEN 4
                        WHEN 'DST' THEN 5
                        ELSE 99
                    END,
                    salary DESC,
                    player_name
                """,
                connection,
                params=(int(slate_id),),
            )

        if players.empty:
            return players

        players["player_id"] = players["player_id"].astype(str)
        players["locked"] = players["locked"].astype(bool)
        players["excluded"] = players["excluded"].astype(bool)

        return players