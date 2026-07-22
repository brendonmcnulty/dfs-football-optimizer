from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from database.connection import create_connection


class LineupRepository:
    """Store and retrieve generated DFS lineups."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

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

        Returns the newly created lineup ID.
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

        if int(total_salary) <= 0:
            raise ValueError(
                "Total salary must be greater than zero."
            )

        if float(total_projection) < 0:
            raise ValueError(
                "Total projection cannot be negative."
            )

        if int(salary_cap) <= 0:
            raise ValueError(
                "Salary cap must be greater than zero."
            )

        if int(minimum_salary) < 0:
            raise ValueError(
                "Minimum salary cannot be negative."
            )

        if int(minimum_salary) > int(salary_cap):
            raise ValueError(
                "Minimum salary cannot exceed the salary cap."
            )

        created_at = datetime.now().isoformat(
            timespec="seconds"
        )

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
        """
        Return saved lineup summaries.

        Results may optionally be filtered to one slate.
        """

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

        with create_connection(self.database_path) as connection:
            return pd.read_sql_query(
                query,
                connection,
                params=parameters,
            )

    def load_lineup_players(
        self,
        lineup_id: int,
    ) -> pd.DataFrame:
        """Load the players belonging to one saved lineup."""

        with create_connection(self.database_path) as connection:
            lineup_players = pd.read_sql_query(
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

        if lineup_players.empty:
            return lineup_players

        lineup_players["player_id"] = (
            lineup_players["player_id"].astype(str)
        )

        return lineup_players

    def get_lineup(
        self,
        lineup_id: int,
    ) -> pd.DataFrame:
        """Return the summary record for one saved lineup."""

        with create_connection(self.database_path) as connection:
            return pd.read_sql_query(
                """
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
                WHERE lineups.id = ?
                """,
                connection,
                params=(int(lineup_id),),
            )

    def delete_lineup(
        self,
        lineup_id: int,
    ) -> bool:
        """
        Delete one saved lineup.

        Related lineup-player rows are deleted automatically through the
        foreign-key cascade.
        """

        with create_connection(self.database_path) as connection:
            cursor = connection.execute(
                """
                DELETE FROM lineups
                WHERE id = ?
                """,
                (int(lineup_id),),
            )

            connection.commit()

        return cursor.rowcount > 0