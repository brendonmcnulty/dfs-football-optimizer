from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from database.connection import create_connection


class ContestResultsRepository:
    """Persist DraftKings contest standings, player actuals, and user results."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def save_reserved_entries(self, slate_id: int, entries: pd.DataFrame, source_name: str = "DKEntries.csv") -> int:
        if entries is None or entries.empty:
            return 0
        with create_connection(self.database_path) as connection:
            connection.execute("DELETE FROM dk_reserved_entries WHERE slate_id = ?", (int(slate_id),))
            saved = 0
            for _, row in entries.iterrows():
                contest = str(row.get("contest_id", "")).strip()
                entry_id = str(row.get("entry_id", "")).strip()
                if not contest or not entry_id:
                    continue
                fee_text = str(row.get("entry_fee", "0")).replace("$", "").replace(",", "").strip()
                try: fee = float(fee_text or 0)
                except ValueError: fee = 0.0
                connection.execute("""INSERT INTO dk_reserved_entries
                    (slate_id, contest_id, contest_name, entry_id, entry_fee, source_name) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(slate_id, entry_id) DO UPDATE SET contest_id=excluded.contest_id,
                    contest_name=excluded.contest_name, entry_fee=excluded.entry_fee, source_name=excluded.source_name""",
                    (int(slate_id), int(float(contest)), str(row.get("contest_name", "")), entry_id, fee, str(source_name)))
                saved += 1
            connection.commit()
        return saved

    def reserved_entries(self, slate_id: int, contest_id: int | None = None) -> pd.DataFrame:
        with create_connection(self.database_path) as connection:
            sql = "SELECT contest_id, contest_name, entry_id, entry_fee, source_name FROM dk_reserved_entries WHERE slate_id = ?"
            params = [int(slate_id)]
            if contest_id is not None:
                sql += " AND contest_id = ?"
                params.append(int(contest_id))
            return pd.read_sql_query(sql, connection, params=params)

    def save_import(
        self,
        contest_id: int,
        slate_id: int,
        standings: pd.DataFrame,
        player_results: pd.DataFrame,
        user_entries: pd.DataFrame | None = None,
        contest_name: str = "",
    ) -> dict[str, int]:
        imported_at = datetime.now().isoformat(timespec="seconds")
        user_entries = user_entries if user_entries is not None else pd.DataFrame()

        with create_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO dk_contests (
                    contest_id, slate_id, contest_name, field_size, imported_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(contest_id) DO UPDATE SET
                    slate_id = excluded.slate_id,
                    contest_name = CASE
                        WHEN excluded.contest_name <> '' THEN excluded.contest_name
                        ELSE dk_contests.contest_name END,
                    field_size = excluded.field_size,
                    imported_at = excluded.imported_at
                """,
                (
                    int(contest_id), int(slate_id), str(contest_name),
                    int(len(standings)), imported_at,
                ),
            )

            connection.execute(
                "DELETE FROM dk_contest_standings WHERE contest_id = ?",
                (int(contest_id),),
            )
            for _, row in standings.iterrows():
                connection.execute(
                    """
                    INSERT INTO dk_contest_standings (
                        contest_id, entry_id, entry_name, rank, points, lineup_text
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(contest_id), str(row["entry_id"]), str(row["entry_name"]),
                        int(row["rank"]), float(row["points"]), str(row["lineup_text"]),
                    ),
                )

            connection.execute(
                "DELETE FROM dk_contest_player_results WHERE contest_id = ?",
                (int(contest_id),),
            )
            for _, row in player_results.iterrows():
                connection.execute(
                    """
                    INSERT INTO dk_contest_player_results (
                        contest_id, player_name, roster_position,
                        actual_ownership, actual_points
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        int(contest_id), str(row["player_name"]),
                        str(row["roster_position"]), float(row["actual_ownership"]),
                        float(row["actual_points"]),
                    ),
                )

            if not user_entries.empty:
                connection.execute(
                    "DELETE FROM dk_user_entries WHERE contest_id = ?",
                    (int(contest_id),),
                )
                for _, row in user_entries.iterrows():
                    connection.execute(
                        """
                        INSERT INTO dk_user_entries (
                            contest_id, entry_id, place, points, winnings,
                            entry_fee, contest_entries, places_paid
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(contest_id), str(row["entry_id"]), int(row["place"]),
                            float(row["points"]), float(row["winnings"]),
                            float(row["entry_fee"]), int(row["contest_entries"]),
                            int(row["places_paid"]),
                        ),
                    )

            # Feed actual player results into the existing historical-results table.
            slate_players = pd.read_sql_query(
                """
                SELECT external_player_id, player_name, team
                FROM players WHERE slate_id = ?
                """,
                connection,
                params=(int(slate_id),),
            )
            if not slate_players.empty and not player_results.empty:
                actual_map = {
                    self._normalize_name(row["player_name"]): float(row["actual_points"])
                    for _, row in player_results.iterrows()
                }
                for _, player in slate_players.iterrows():
                    actual = actual_map.get(self._normalize_name(player["player_name"]))
                    if actual is None:
                        continue
                    connection.execute(
                        """
                        INSERT INTO historical_results (
                            slate_id, external_player_id, player_name, team,
                            actual_points, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(slate_id, external_player_id) DO UPDATE SET
                            player_name = excluded.player_name,
                            team = excluded.team,
                            actual_points = excluded.actual_points,
                            updated_at = excluded.updated_at
                        """,
                        (
                            int(slate_id), str(player["external_player_id"]),
                            str(player["player_name"]), str(player["team"]),
                            float(actual), imported_at,
                        ),
                    )
            connection.commit()

        return {
            "standings": int(len(standings)),
            "players": int(len(player_results)),
            "user_entries": int(len(user_entries)),
        }

    def contest_summary(self, contest_id: int) -> pd.DataFrame:
        with create_connection(self.database_path) as connection:
            return pd.read_sql_query(
                """
                SELECT c.contest_id, c.contest_name, c.field_size, c.imported_at,
                       COUNT(u.entry_id) AS user_entries,
                       COALESCE(SUM(u.entry_fee), 0) AS entry_fees,
                       COALESCE(SUM(u.winnings), 0) AS winnings,
                       COALESCE(AVG(u.points), 0) AS average_points,
                       COALESCE(MAX(u.points), 0) AS best_points,
                       COALESCE(MIN(u.place), 0) AS best_finish,
                       COALESCE(SUM(CASE WHEN u.place <= u.places_paid THEN 1 ELSE 0 END), 0)
                           AS cashed_entries
                FROM dk_contests c
                LEFT JOIN dk_user_entries u ON u.contest_id = c.contest_id
                WHERE c.contest_id = ?
                GROUP BY c.contest_id
                """,
                connection,
                params=(int(contest_id),),
            )

    def user_entries(self, contest_id: int) -> pd.DataFrame:
        with create_connection(self.database_path) as connection:
            return pd.read_sql_query(
                """
                SELECT u.entry_id, u.place, u.points, u.winnings, u.entry_fee,
                       u.contest_entries, u.places_paid, s.entry_name, s.lineup_text
                FROM dk_user_entries u
                LEFT JOIN dk_contest_standings s
                  ON s.contest_id = u.contest_id AND s.entry_id = u.entry_id
                WHERE u.contest_id = ?
                ORDER BY u.place
                """,
                connection,
                params=(int(contest_id),),
            )

    def player_comparison(self, contest_id: int, slate_id: int) -> pd.DataFrame:
        with create_connection(self.database_path) as connection:
            return pd.read_sql_query(
                """
                SELECT p.player_name AS name, p.position, p.team, p.salary,
                       p.projection, p.ceiling, p.floor, p.ownership AS projected_ownership,
                       r.actual_ownership, r.actual_points,
                       (r.actual_points - p.projection) AS projection_delta,
                       (r.actual_ownership - p.ownership) AS ownership_delta
                FROM players p
                LEFT JOIN dk_contest_player_results r
                  ON r.contest_id = ?
                 AND LOWER(REPLACE(REPLACE(REPLACE(p.player_name, '.', ''), '''', ''), '-', ' ')) =
                     LOWER(REPLACE(REPLACE(REPLACE(r.player_name, '.', ''), '''', ''), '-', ' '))
                WHERE p.slate_id = ? AND r.actual_points IS NOT NULL
                ORDER BY ABS(r.actual_points - p.projection) DESC
                """,
                connection,
                params=(int(contest_id), int(slate_id)),
            )

    def unmatched_player_results(self, contest_id: int, slate_id: int) -> pd.DataFrame:
        with create_connection(self.database_path) as connection:
            results = pd.read_sql_query("SELECT player_name, roster_position, actual_ownership, actual_points FROM dk_contest_player_results WHERE contest_id = ?", connection, params=(int(contest_id),))
            slate = pd.read_sql_query("SELECT player_name FROM players WHERE slate_id = ?", connection, params=(int(slate_id),))
        slate_names = {self._normalize_name(v) for v in slate["player_name"].tolist()}
        if results.empty:
            return results
        return results.loc[~results["player_name"].map(self._normalize_name).isin(slate_names)].reset_index(drop=True)

    @staticmethod
    def _normalize_name(value: object) -> str:
        text = str(value).lower().replace(".", "").replace("'", "").replace("-", " ")
        return " ".join(text.split())
