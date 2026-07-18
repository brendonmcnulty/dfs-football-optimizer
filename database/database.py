from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd


DATABASE_PATH = Path("data") / "dfs_optimizer.db"


class DatabaseManager:
    """Manage SQLite storage for slates and player pools."""

    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.create_tables()

    def connect(self) -> sqlite3.Connection:
        """Open a SQLite database connection."""

        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create_tables(self) -> None:
        """Create the initial database tables if they do not exist."""

        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS slates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    season INTEGER NOT NULL,
                    week INTEGER NOT NULL,
                    site TEXT NOT NULL,
                    slate_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(season, week, site, slate_name)
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slate_id INTEGER NOT NULL,
                    external_player_id TEXT NOT NULL,
                    player_name TEXT NOT NULL,
                    position TEXT NOT NULL,
                    team TEXT NOT NULL,
                    opponent TEXT,
                    salary INTEGER NOT NULL,
                    projection REAL NOT NULL DEFAULT 0,
                    locked INTEGER NOT NULL DEFAULT 0,
                    excluded INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (slate_id)
                        REFERENCES slates(id)
                        ON DELETE CASCADE,
                    UNIQUE(slate_id, external_player_id)
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_players_slate_id
                ON players(slate_id)
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_players_name
                ON players(player_name)
                """
            )

            connection.commit()

    def save_slate(
        self,
        season: int,
        week: int,
        site: str,
        slate_name: str,
    ) -> int:
        """
        Create a slate or return the ID of an existing matching slate.
        """

        clean_site = site.strip()
        clean_slate_name = slate_name.strip()
        created_at = datetime.now().isoformat(timespec="seconds")

        if not clean_site:
            raise ValueError("Site cannot be blank.")

        if not clean_slate_name:
            raise ValueError("Slate name cannot be blank.")

        with self.connect() as connection:
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
        """
        Save or update every player in a slate.

        Returns the number of player rows processed.
        """

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

        with self.connect() as connection:
            for _, player in players.iterrows():
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
                        str(player["opponent"]),
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

        with self.connect() as connection:
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
                ORDER BY season DESC, week DESC, created_at DESC
                """,
                connection,
            )

    def load_player_pool(self, slate_id: int) -> pd.DataFrame:
        """Load a saved player pool in the optimizer's expected format."""

        with self.connect() as connection:
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
                ORDER BY position, salary DESC, player_name
                """,
                connection,
                params=(int(slate_id),),
            )

        if players.empty:
            return players

        players["locked"] = players["locked"].astype(bool)
        players["excluded"] = players["excluded"].astype(bool)

        return players