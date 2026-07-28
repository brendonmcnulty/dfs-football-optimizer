from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from database.connection import create_connection


class WarehouseRepository:
    """Maintain a durable, cross-slate NFL DFS player-week warehouse."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def sync_slate(self, slate_id: int) -> int:
        """Upsert one saved slate into the historical warehouse."""

        synced_at = datetime.now().isoformat(timespec="seconds")
        saved = 0

        with create_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    s.id AS slate_id,
                    s.season,
                    s.week,
                    s.site,
                    s.slate_name,
                    p.external_player_id,
                    p.player_name,
                    p.position,
                    p.team,
                    p.opponent,
                    p.salary,
                    p.projection,
                    p.ceiling,
                    p.floor,
                    p.ownership,
                    p.confidence,
                    p.targets,
                    p.carries,
                    p.passing_attempts,
                    p.receptions,
                    p.recent_fantasy_points,
                    p.usage_games,
                    p.usage_adjustment,
                    h.actual_points,
                    CASE WHEN g.home_team = p.team THEN 1
                         WHEN g.away_team = p.team THEN 0
                         ELSE NULL END AS is_home,
                    g.game_total,
                    CASE WHEN g.home_team = p.team THEN g.home_implied_total
                         WHEN g.away_team = p.team THEN g.away_implied_total
                         ELSE NULL END AS team_implied_total,
                    CASE WHEN g.home_team = p.team THEN g.away_implied_total
                         WHEN g.away_team = p.team THEN g.home_implied_total
                         ELSE NULL END AS opponent_implied_total,
                    CASE WHEN g.home_team = p.team THEN g.home_spread
                         WHEN g.away_team = p.team THEN -g.home_spread
                         ELSE NULL END AS team_spread
                FROM slates s
                JOIN players p ON p.slate_id = s.id
                LEFT JOIN historical_results h
                  ON h.slate_id = p.slate_id
                 AND h.external_player_id = p.external_player_id
                LEFT JOIN games g
                  ON g.season = s.season
                 AND g.week = s.week
                 AND (
                    (g.home_team = p.team AND g.away_team = p.opponent)
                    OR (g.away_team = p.team AND g.home_team = p.opponent)
                 )
                WHERE s.id = ?
                """,
                (int(slate_id),),
            ).fetchall()

            if not rows:
                return 0

            columns = [description[0] for description in connection.execute(
                """
                SELECT
                    s.id AS slate_id, s.season, s.week, s.site, s.slate_name,
                    p.external_player_id, p.player_name, p.position, p.team,
                    p.opponent, p.salary, p.projection, p.ceiling, p.floor,
                    p.ownership, p.confidence, p.targets, p.carries,
                    p.passing_attempts, p.receptions, p.recent_fantasy_points,
                    p.usage_games, p.usage_adjustment, h.actual_points,
                    NULL AS is_home, NULL AS game_total,
                    NULL AS team_implied_total, NULL AS opponent_implied_total,
                    NULL AS team_spread
                FROM slates s JOIN players p ON 1 = 0
                LEFT JOIN historical_results h ON 1 = 0
                """
            ).description]

            for row in rows:
                record = dict(zip(columns, row))
                connection.execute(
                    """
                    INSERT INTO warehouse_player_weeks (
                        slate_id, season, week, site, slate_name,
                        external_player_id, player_name, position, team, opponent,
                        salary, projection, ceiling, floor, ownership, confidence,
                        targets, carries, passing_attempts, receptions,
                        recent_fantasy_points, usage_games, usage_adjustment,
                        actual_points, is_home, game_total, team_implied_total,
                        opponent_implied_total, team_spread, synced_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    ON CONFLICT(slate_id, external_player_id)
                    DO UPDATE SET
                        season = excluded.season,
                        week = excluded.week,
                        site = excluded.site,
                        slate_name = excluded.slate_name,
                        player_name = excluded.player_name,
                        position = excluded.position,
                        team = excluded.team,
                        opponent = excluded.opponent,
                        salary = excluded.salary,
                        projection = excluded.projection,
                        ceiling = excluded.ceiling,
                        floor = excluded.floor,
                        ownership = excluded.ownership,
                        confidence = excluded.confidence,
                        targets = excluded.targets,
                        carries = excluded.carries,
                        passing_attempts = excluded.passing_attempts,
                        receptions = excluded.receptions,
                        recent_fantasy_points = excluded.recent_fantasy_points,
                        usage_games = excluded.usage_games,
                        usage_adjustment = excluded.usage_adjustment,
                        actual_points = excluded.actual_points,
                        is_home = excluded.is_home,
                        game_total = excluded.game_total,
                        team_implied_total = excluded.team_implied_total,
                        opponent_implied_total = excluded.opponent_implied_total,
                        team_spread = excluded.team_spread,
                        synced_at = excluded.synced_at
                    """,
                    (
                        record["slate_id"], record["season"], record["week"],
                        record["site"], record["slate_name"],
                        record["external_player_id"], record["player_name"],
                        record["position"], record["team"], record["opponent"],
                        record["salary"], record["projection"], record["ceiling"],
                        record["floor"], record["ownership"], record["confidence"],
                        record["targets"], record["carries"],
                        record["passing_attempts"], record["receptions"],
                        record["recent_fantasy_points"], record["usage_games"],
                        record["usage_adjustment"], record["actual_points"],
                        record["is_home"], record["game_total"],
                        record["team_implied_total"], record["opponent_implied_total"],
                        record["team_spread"], synced_at,
                    ),
                )
                saved += 1

            connection.execute(
                """
                INSERT INTO warehouse_import_runs (
                    slate_id, player_count, synced_at
                ) VALUES (?, ?, ?)
                """,
                (int(slate_id), int(saved), synced_at),
            )
            connection.commit()

        return saved

    def sync_all_slates(self) -> tuple[int, int]:
        """Sync every saved slate and return (slates, player rows)."""

        with create_connection(self.database_path) as connection:
            slate_ids = [
                int(row["id"])
                for row in connection.execute(
                    "SELECT id FROM slates ORDER BY season, week, id"
                ).fetchall()
            ]

        total_rows = sum(self.sync_slate(slate_id) for slate_id in slate_ids)
        return len(slate_ids), total_rows

    def load_rows(
        self,
        seasons: list[int] | None = None,
        weeks: list[int] | None = None,
        positions: list[str] | None = None,
        teams: list[str] | None = None,
        minimum_salary: int | None = None,
        maximum_salary: int | None = None,
        actuals_only: bool = False,
    ) -> pd.DataFrame:
        """Load warehouse rows using optional analysis filters."""

        clauses: list[str] = []
        params: list[object] = []

        def add_in(column: str, values: list[object] | None) -> None:
            if values:
                placeholders = ", ".join("?" for _ in values)
                clauses.append(f"{column} IN ({placeholders})")
                params.extend(values)

        add_in("season", seasons)
        add_in("week", weeks)
        add_in("position", positions)
        add_in("team", teams)

        if minimum_salary is not None:
            clauses.append("salary >= ?")
            params.append(int(minimum_salary))
        if maximum_salary is not None:
            clauses.append("salary <= ?")
            params.append(int(maximum_salary))
        if actuals_only:
            clauses.append("actual_points IS NOT NULL")

        where = " WHERE " + " AND ".join(clauses) if clauses else ""

        with create_connection(self.database_path) as connection:
            return pd.read_sql_query(
                f"""
                SELECT
                    season, week, site, slate_name,
                    external_player_id AS player_id,
                    player_name AS name,
                    position, team, opponent, salary,
                    projection, ceiling, floor, ownership, confidence,
                    actual_points, is_home, game_total, team_implied_total,
                    opponent_implied_total, team_spread,
                    targets, carries, passing_attempts, receptions,
                    recent_fantasy_points, usage_games, usage_adjustment,
                    snaps, routes, red_zone_touches,
                    weather_temperature, weather_wind_speed,
                    weather_precipitation_probability, injury_status,
                    synced_at
                FROM warehouse_player_weeks
                {where}
                ORDER BY season DESC, week DESC, actual_points DESC,
                         projection DESC, player_name
                """,
                connection,
                params=params,
            )

    def available_filters(self) -> dict[str, list]:
        """Return values currently available for warehouse filters."""

        with create_connection(self.database_path) as connection:
            result: dict[str, list] = {}
            for key, column in (
                ("seasons", "season"),
                ("weeks", "week"),
                ("positions", "position"),
                ("teams", "team"),
            ):
                rows = connection.execute(
                    f"SELECT DISTINCT {column} AS value "
                    "FROM warehouse_player_weeks "
                    f"WHERE {column} IS NOT NULL ORDER BY {column}"
                ).fetchall()
                result[key] = [row["value"] for row in rows]
            return result

    def summary(self) -> pd.DataFrame:
        """Return one-row warehouse summary metrics."""

        with create_connection(self.database_path) as connection:
            return pd.read_sql_query(
                """
                SELECT
                    COUNT(*) AS player_weeks,
                    COUNT(DISTINCT slate_id) AS slates,
                    COUNT(DISTINCT season) AS seasons,
                    COUNT(DISTINCT external_player_id) AS unique_players,
                    SUM(CASE WHEN actual_points IS NOT NULL THEN 1 ELSE 0 END)
                        AS actual_result_rows,
                    SUM(CASE WHEN game_total IS NOT NULL THEN 1 ELSE 0 END)
                        AS vegas_rows,
                    MIN(season) AS first_season,
                    MAX(season) AS latest_season,
                    MAX(synced_at) AS last_synced_at
                FROM warehouse_player_weeks
                """,
                connection,
            )

    def coverage_by_season(self) -> pd.DataFrame:
        """Show data coverage by season and week."""

        with create_connection(self.database_path) as connection:
            return pd.read_sql_query(
                """
                SELECT
                    season,
                    week,
                    COUNT(DISTINCT slate_id) AS slates,
                    COUNT(*) AS player_weeks,
                    SUM(CASE WHEN actual_points IS NOT NULL THEN 1 ELSE 0 END)
                        AS actual_rows,
                    SUM(CASE WHEN game_total IS NOT NULL THEN 1 ELSE 0 END)
                        AS vegas_rows,
                    SUM(CASE WHEN targets IS NOT NULL OR carries IS NOT NULL
                             THEN 1 ELSE 0 END) AS usage_rows
                FROM warehouse_player_weeks
                GROUP BY season, week
                ORDER BY season DESC, week DESC
                """,
                connection,
            )
