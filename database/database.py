from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd


DATABASE_PATH = Path("data") / "dfs_optimizer.db"


class DatabaseManager:
    """Manage SQLite storage for DFS slates, players, and lineups."""

    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.create_tables()

    def connect(self) -> sqlite3.Connection:
        """Open a configured SQLite database connection."""

        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create_tables(self) -> None:
        """Create all application tables if they do not already exist."""

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
                CREATE TABLE IF NOT EXISTS lineups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slate_id INTEGER NOT NULL,
                    lineup_name TEXT NOT NULL,
                    total_salary INTEGER NOT NULL,
                    total_projection REAL NOT NULL,
                    solver_status TEXT NOT NULL,
                    salary_cap INTEGER NOT NULL,
                    minimum_salary INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (slate_id)
                        REFERENCES slates(id)
                        ON DELETE CASCADE
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS lineup_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lineup_id INTEGER NOT NULL,
                    external_player_id TEXT NOT NULL,
                    roster_slot TEXT NOT NULL,
                    player_name TEXT NOT NULL,
                    position TEXT NOT NULL,
                    team TEXT NOT NULL,
                    opponent TEXT,
                    salary INTEGER NOT NULL,
                    projection REAL NOT NULL,
                    FOREIGN KEY (lineup_id)
                        REFERENCES lineups(id)
                        ON DELETE CASCADE,
                    UNIQUE(lineup_id, roster_slot),
                    UNIQUE(lineup_id, external_player_id)
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

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lineups_slate_id
                ON lineups(slate_id)
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lineup_players_lineup_id
                ON lineup_players(lineup_id)
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
        """Create a slate or return the ID of an existing matching slate."""

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

    def save_lineup(
        self,
        slate_id: int,
        lineup: pd.DataFrame,
        lineup_name: str,
        total_salary: int,
        total_projection: float,
        solver_status: str,
        salary_cap: int,
        minimum_salary: int,
    ) -> int:
        """
        Save one generated lineup and its players.

        Returns the new lineup ID.
        """

        required_columns = {
            "player_id",
            "roster_slot",
            "name",
            "position",
            "team",
            "opponent",
            "salary",
            "projection",
        }

        missing_columns = required_columns - set(lineup.columns)

        if missing_columns:
            raise ValueError(
                "Cannot save lineup. Missing columns: "
                f"{sorted(missing_columns)}"
            )

        if lineup.empty:
            raise ValueError("Cannot save an empty lineup.")

        clean_lineup_name = lineup_name.strip()

        if not clean_lineup_name:
            raise ValueError("Lineup name cannot be blank.")

        created_at = datetime.now().isoformat(timespec="seconds")

        with self.connect() as connection:
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
                    "The active slate has not been saved to the database."
                )

            cursor = connection.execute(
                """
                INSERT INTO lineups (
                    slate_id,
                    lineup_name,
                    total_salary,
                    total_projection,
                    solver_status,
                    salary_cap,
                    minimum_salary,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(slate_id),
                    clean_lineup_name,
                    int(total_salary),
                    float(total_projection),
                    str(solver_status),
                    int(salary_cap),
                    int(minimum_salary),
                    created_at,
                ),
            )

            lineup_id = int(cursor.lastrowid)

            for _, player in lineup.iterrows():
                connection.execute(
                    """
                    INSERT INTO lineup_players (
                        lineup_id,
                        external_player_id,
                        roster_slot,
                        player_name,
                        position,
                        team,
                        opponent,
                        salary,
                        projection
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lineup_id,
                        str(player["player_id"]),
                        str(player["roster_slot"]),
                        str(player["name"]),
                        str(player["position"]),
                        str(player["team"]),
                        str(player["opponent"]),
                        int(player["salary"]),
                        float(player["projection"]),
                    ),
                )

            connection.commit()

        return lineup_id

    def list_lineups(
        self,
        slate_id: int | None = None,
    ) -> pd.DataFrame:
        """Return saved lineup summaries, optionally filtered by slate."""

        query = """
            SELECT
                lineups.id,
                lineups.slate_id,
                lineups.lineup_name,
                slates.season,
                slates.week,
                slates.site,
                slates.slate_name,
                lineups.total_salary,
                lineups.total_projection,
                lineups.solver_status,
                lineups.salary_cap,
                lineups.minimum_salary,
                lineups.created_at
            FROM lineups
            INNER JOIN slates
                ON slates.id = lineups.slate_id
        """

        parameters: tuple[int, ...] = ()

        if slate_id is not None:
            query += """
                WHERE lineups.slate_id = ?
            """
            parameters = (int(slate_id),)

        query += """
            ORDER BY lineups.created_at DESC, lineups.id DESC
        """

        with self.connect() as connection:
            return pd.read_sql_query(
                query,
                connection,
                params=parameters,
            )

    def load_lineup_players(self, lineup_id: int) -> pd.DataFrame:
        """Load the players belonging to one saved lineup."""

        with self.connect() as connection:
            return pd.read_sql_query(
                """
                SELECT
                    external_player_id AS player_id,
                    roster_slot,
                    player_name AS name,
                    position,
                    team,
                    opponent,
                    salary,
                    projection
                FROM lineup_players
                WHERE lineup_id = ?
                ORDER BY
                    CASE roster_slot
                        WHEN 'QB' THEN 1
                        WHEN 'RB1' THEN 2
                        WHEN 'RB2' THEN 3
                        WHEN 'WR1' THEN 4
                        WHEN 'WR2' THEN 5
                        WHEN 'WR3' THEN 6
                        WHEN 'TE' THEN 7
                        WHEN 'FLEX' THEN 8
                        WHEN 'DST' THEN 9
                        ELSE 99
                    END
                """,
                connection,
                params=(int(lineup_id),),
            )