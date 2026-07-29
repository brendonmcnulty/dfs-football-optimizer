from __future__ import annotations

from pathlib import Path

import pandas as pd

from database.connection import create_connection
from repositories import (
    DataUpdateRepository,
    GameRepository,
    HistoricalRepository,
    LineupRepository,
    SlateRepository,
    WarehouseRepository,
)


DATABASE_PATH = Path("data") / "dfs_optimizer.db"


class DatabaseManager:
    """
    Initialize the SQLite database and coordinate repositories.

    Existing application pages may continue calling DatabaseManager while
    persistence logic is handled by dedicated repository classes.
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

        self.lineup_repository = LineupRepository(
            database_path=self.database_path,
        )

        self.data_update_repository = DataUpdateRepository(
            database_path=self.database_path,
        )

        self.game_repository = GameRepository(
            database_path=self.database_path,
        )

        self.historical_repository = HistoricalRepository(
            database_path=self.database_path,
        )

        self.warehouse_repository = WarehouseRepository(
            database_path=self.database_path,
        )

    def connect(self):
        """Open a configured SQLite database connection."""

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
                    ceiling REAL NOT NULL DEFAULT 0,
                    floor REAL NOT NULL DEFAULT 0,
                    ownership REAL NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0,
                    usage_games INTEGER NOT NULL DEFAULT 0,
                    passing_attempts REAL,
                    carries REAL,
                    targets REAL,
                    receptions REAL,
                    recent_fantasy_points REAL,
                    usage_adjustment REAL NOT NULL DEFAULT 0,
                    matchup_rating REAL,
                    matchup_label TEXT,
                    fantasy_points_allowed REAL,
                    matchup_games INTEGER,
                    matchup_adjustment REAL NOT NULL DEFAULT 0,
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
                CREATE TABLE IF NOT EXISTS data_updates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    season INTEGER NOT NULL,
                    week INTEGER NOT NULL,
                    site TEXT NOT NULL,
                    slate_name TEXT NOT NULL,
                    player_count INTEGER NOT NULL,
                    source_names TEXT NOT NULL,
                    aggregation TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )


            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    season INTEGER NOT NULL,
                    week INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    commence_time TEXT NOT NULL,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    home_team_name TEXT NOT NULL,
                    away_team_name TEXT NOT NULL,
                    home_spread REAL,
                    game_total REAL,
                    home_implied_total REAL,
                    away_implied_total REAL,
                    home_moneyline REAL,
                    away_moneyline REAL,
                    bookmaker_count INTEGER NOT NULL DEFAULT 0,
                    fetched_at TEXT NOT NULL,
                    UNIQUE(season, week, event_id)
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS warehouse_player_weeks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slate_id INTEGER NOT NULL,
                    season INTEGER NOT NULL,
                    week INTEGER NOT NULL,
                    site TEXT NOT NULL,
                    slate_name TEXT NOT NULL,
                    external_player_id TEXT NOT NULL,
                    player_name TEXT NOT NULL,
                    position TEXT NOT NULL,
                    team TEXT NOT NULL,
                    opponent TEXT,
                    salary INTEGER NOT NULL,
                    projection REAL NOT NULL DEFAULT 0,
                    ceiling REAL NOT NULL DEFAULT 0,
                    floor REAL NOT NULL DEFAULT 0,
                    ownership REAL NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0,
                    actual_points REAL,
                    is_home INTEGER,
                    game_total REAL,
                    team_implied_total REAL,
                    opponent_implied_total REAL,
                    team_spread REAL,
                    targets REAL,
                    carries REAL,
                    passing_attempts REAL,
                    receptions REAL,
                    recent_fantasy_points REAL,
                    usage_games INTEGER,
                    usage_adjustment REAL,
                    matchup_rating REAL,
                    matchup_label TEXT,
                    fantasy_points_allowed REAL,
                    matchup_games INTEGER,
                    matchup_adjustment REAL,
                    snaps REAL,
                    routes REAL,
                    red_zone_touches REAL,
                    weather_temperature REAL,
                    weather_wind_speed REAL,
                    weather_precipitation_probability REAL,
                    injury_status TEXT,
                    synced_at TEXT NOT NULL,
                    FOREIGN KEY (slate_id) REFERENCES slates(id) ON DELETE CASCADE,
                    UNIQUE(slate_id, external_player_id)
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS warehouse_import_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slate_id INTEGER NOT NULL,
                    player_count INTEGER NOT NULL,
                    synced_at TEXT NOT NULL,
                    FOREIGN KEY (slate_id) REFERENCES slates(id) ON DELETE CASCADE
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS historical_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slate_id INTEGER NOT NULL,
                    external_player_id TEXT NOT NULL,
                    player_name TEXT NOT NULL,
                    team TEXT NOT NULL,
                    actual_points REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (slate_id) REFERENCES slates(id) ON DELETE CASCADE,
                    UNIQUE(slate_id, external_player_id)
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

            player_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(players)"
                ).fetchall()
            }

            if "ceiling" not in player_columns:
                connection.execute(
                    "ALTER TABLE players ADD COLUMN ceiling REAL NOT NULL DEFAULT 0"
                )
                connection.execute("UPDATE players SET ceiling = projection")

            if "floor" not in player_columns:
                connection.execute(
                    "ALTER TABLE players ADD COLUMN floor REAL NOT NULL DEFAULT 0"
                )
                connection.execute("UPDATE players SET floor = projection")

            if "ownership" not in player_columns:
                connection.execute(
                    "ALTER TABLE players "
                    "ADD COLUMN ownership REAL NOT NULL DEFAULT 0"
                )

            if "confidence" not in player_columns:
                connection.execute(
                    "ALTER TABLE players "
                    "ADD COLUMN confidence REAL NOT NULL DEFAULT 0"
                )

            player_usage_columns = {
                "usage_games": "INTEGER NOT NULL DEFAULT 0",
                "passing_attempts": "REAL",
                "carries": "REAL",
                "targets": "REAL",
                "receptions": "REAL",
                "recent_fantasy_points": "REAL",
                "usage_adjustment": "REAL NOT NULL DEFAULT 0",
                "matchup_rating": "REAL",
                "matchup_label": "TEXT",
                "fantasy_points_allowed": "REAL",
                "matchup_games": "INTEGER",
                "matchup_adjustment": "REAL NOT NULL DEFAULT 0",
            }
            for column_name, column_type in player_usage_columns.items():
                if column_name not in player_columns:
                    connection.execute(
                        f"ALTER TABLE players ADD COLUMN {column_name} {column_type}"
                    )

            warehouse_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(warehouse_player_weeks)"
                ).fetchall()
            }
            warehouse_usage_columns = {
                "passing_attempts": "REAL",
                "receptions": "REAL",
                "recent_fantasy_points": "REAL",
                "usage_games": "INTEGER",
                "usage_adjustment": "REAL",
                "matchup_rating": "REAL",
                "matchup_label": "TEXT",
                "fantasy_points_allowed": "REAL",
                "matchup_games": "INTEGER",
                "matchup_adjustment": "REAL",
            }
            for column_name, column_type in warehouse_usage_columns.items():
                if column_name not in warehouse_columns:
                    connection.execute(
                        "ALTER TABLE warehouse_player_weeks "
                        f"ADD COLUMN {column_name} {column_type}"
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


            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_warehouse_season_week
                ON warehouse_player_weeks(season, week)
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_warehouse_player
                ON warehouse_player_weeks(external_player_id)
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_warehouse_position_salary
                ON warehouse_player_weeks(position, salary)
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
        """List saved slates through the slate repository."""

        return self.slate_repository.list_slates()

    def load_player_pool(
        self,
        slate_id: int,
    ) -> pd.DataFrame:
        """Load a saved player pool through the slate repository."""

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
        """Save a generated lineup through the lineup repository."""

        return self.lineup_repository.save_lineup(
            slate_id=slate_id,
            lineup=lineup,
            lineup_name=lineup_name,
            total_salary=total_salary,
            total_projection=total_projection,
            solver_status=solver_status,
            salary_cap=salary_cap,
            minimum_salary=minimum_salary,
        )

    def list_lineups(
        self,
        slate_id: int | None = None,
    ) -> pd.DataFrame:
        """List saved lineups through the lineup repository."""

        return self.lineup_repository.list_lineups(
            slate_id=slate_id,
        )

    def load_lineup_players(
        self,
        lineup_id: int,
    ) -> pd.DataFrame:
        """Load lineup players through the lineup repository."""

        return self.lineup_repository.load_lineup_players(
            lineup_id=lineup_id,
        )

    def get_lineup(
        self,
        lineup_id: int,
    ) -> pd.DataFrame:
        """Load one lineup summary through the lineup repository."""

        return self.lineup_repository.get_lineup(
            lineup_id=lineup_id,
        )

    def delete_lineup(
        self,
        lineup_id: int,
    ) -> bool:
        """Delete one lineup through the lineup repository."""

        return self.lineup_repository.delete_lineup(
            lineup_id=lineup_id,
        )

    def record_data_update(
        self,
        season: int,
        week: int,
        site: str,
        slate_name: str,
        player_count: int,
        source_names: list[str],
        aggregation: str,
    ) -> int:
        """Record one successful weekly data-pipeline run."""

        return self.data_update_repository.record_update(
            season=season,
            week=week,
            site=site,
            slate_name=slate_name,
            player_count=player_count,
            source_names=source_names,
            aggregation=aggregation,
        )

    def list_data_updates(self, limit: int = 25) -> pd.DataFrame:
        """Return recent weekly data-pipeline runs."""

        return self.data_update_repository.list_updates(limit=limit)

    def save_games(
        self,
        season: int,
        week: int,
        games: pd.DataFrame,
        fetched_at: str,
    ) -> int:
        """Replace cached Vegas games for one NFL week."""
        return self.game_repository.replace_games(
            season=season,
            week=week,
            games=games,
            fetched_at=fetched_at,
        )

    def load_games(self, season: int, week: int) -> pd.DataFrame:
        """Load cached Vegas games for one NFL week."""
        return self.game_repository.load_games(season=season, week=week)

    def save_historical_results(self, slate_id: int, results: pd.DataFrame) -> int:
        return self.historical_repository.save_results(slate_id, results)

    def load_historical_results(self, slate_id: int) -> pd.DataFrame:
        return self.historical_repository.load_results(slate_id)

    def load_historical_evaluation(self, slate_id: int) -> pd.DataFrame:
        return self.historical_repository.load_evaluation(slate_id)

    def sync_historical_slate_to_warehouse(self, slate_id: int) -> int:
        """Upsert one saved slate into the historical DFS warehouse."""
        return self.warehouse_repository.sync_slate(slate_id)

    def sync_all_slates_to_warehouse(self) -> tuple[int, int]:
        """Sync every saved slate into the historical DFS warehouse."""
        return self.warehouse_repository.sync_all_slates()

