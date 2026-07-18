from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from database.connection import create_connection
from repositories import SlateRepository


DATABASE_PATH = Path("data") / "dfs_optimizer.db"


class DatabaseManager:
    """
    Coordinate database initialization and repository access.

    Existing pages can continue using DatabaseManager while data-access
    responsibilities are gradually moved into dedicated repositories.
    """

    def __init__(
        self,
        database_path: Path = DATABASE_PATH,
    ) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.create_tables()

        self.slate_repository = SlateRepository(
            database_path=self.database_path,
        )

    def connect(self):
        """Open a configured SQLite connection."""

        return create_connection(self.database_path)

    def create_tables(self) -> None:
        """Create all required database tables and indexes."""

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
        """Save a slate through the slate repository."""

        return self.slate_repository.save_slate(
            season=season,
            week=week,
            site=site,
            slate_name=slate_name,
        )

    def save_player_pool(
        self,
        slate_id: int,
        players: pd.DataFrame,
    ) -> int:
        """Save a player pool through the slate repository."""

        return self.slate_repository.save_player_pool(
            slate_id=slate_id,
            players=players,
        )

    def list_slates(self) -> pd.DataFrame:
        """List slates through the slate repository."""

        return self.slate_repository.list_slates()

    def load_player_pool(
        self,
        slate_id: int,
    ) -> pd.DataFrame:
        """Load a player pool through the slate repository."""

        return self.slate_repository.load_player_pool(
            slate_id=slate_id,
        )

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
        """Save one generated lineup and its players."""

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

        created_at = datetime.now().isoformat(
            timespec="seconds"
        )

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
                    "The active slate has not been saved "
                    "to the database."
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
                opponent = player["opponent"]

                if pd.isna(opponent):
                    opponent = ""

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
                        str(opponent),
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
        """Return saved lineup summaries."""

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
            ORDER BY
                lineups.created_at DESC,
                lineups.id DESC
        """

        with self.connect() as connection:
            return pd.read_sql_query(
                query,
                connection,
                params=parameters,
            )

    def load_lineup_players(
        self,
        lineup_id: int,
    ) -> pd.DataFrame:
        """Load the players belonging to one lineup."""

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