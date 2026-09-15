from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pandas as pd

from repositories.contest_results_repository import ContestResultsRepository
from services.draftkings_export_service import DraftKingsExportService


class ContestResultsService:
    """Parse DraftKings standings and identify the user's reserved entries."""

    def __init__(self, database_path: Path) -> None:
        self.repository = ContestResultsRepository(database_path)
        self.dk_export = DraftKingsExportService()

    def import_results(
        self,
        standings_zip: bytes,
        slate_id: int,
        entry_history_csv: bytes | None = None,
        dk_entries_csv: bytes | None = None,
        dk_entries_name: str = "DKEntries.csv",
    ) -> tuple[int, dict[str, int]]:
        contest_id, standings, player_results = self._parse_standings_zip(standings_zip)
        user_entries = pd.DataFrame()
        contest_name = ""
        identification_source = "none"

        if entry_history_csv:
            history = pd.read_csv(io.BytesIO(entry_history_csv))
            user_entries, contest_name = self._parse_history(history, contest_id)
            identification_source = "entry_history"
        else:
            reserved = pd.DataFrame()
            if dk_entries_csv:
                template = self.dk_export.parse_template(dk_entries_csv, source_name=dk_entries_name)
                reserved = template.entries.copy()
                self.repository.save_reserved_entries(int(slate_id), reserved, dk_entries_name)
            else:
                reserved = self.repository.reserved_entries(int(slate_id), int(contest_id))

            if not reserved.empty:
                user_entries, contest_name = self._match_reserved_entries(
                    reserved, standings, int(contest_id)
                )
                identification_source = "reserved_entries"

        counts = self.repository.save_import(
            contest_id=contest_id,
            slate_id=slate_id,
            standings=standings,
            player_results=player_results,
            user_entries=user_entries,
            contest_name=contest_name,
        )
        counts["identification_source"] = identification_source
        return contest_id, counts

    def _parse_standings_zip(self, payload: bytes) -> tuple[int, pd.DataFrame, pd.DataFrame]:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not csv_names:
                raise ValueError("The ZIP does not contain a CSV file.")
            csv_name = csv_names[0]
            match = re.search(r"contest-standings-(\d+)", csv_name, re.IGNORECASE)
            if not match:
                raise ValueError("Could not determine the DraftKings contest ID from the ZIP.")
            contest_id = int(match.group(1))
            with archive.open(csv_name) as handle:
                raw = pd.read_csv(handle)

        required = {"Rank", "EntryId", "EntryName", "Points", "Lineup", "Player", "Roster Position", "%Drafted", "FPTS"}
        missing = required - set(raw.columns)
        if missing:
            raise ValueError(f"DraftKings standings CSV is missing columns: {sorted(missing)}")

        standings = raw[["Rank", "EntryId", "EntryName", "Points", "Lineup"]].copy()
        standings = standings.dropna(subset=["EntryId", "Rank", "Points"])
        standings = standings.rename(columns={"Rank":"rank","EntryId":"entry_id","EntryName":"entry_name","Points":"points","Lineup":"lineup_text"})
        standings["entry_id"] = standings["entry_id"].astype("Int64").astype(str)
        standings["rank"] = pd.to_numeric(standings["rank"], errors="coerce")
        standings["points"] = pd.to_numeric(standings["points"], errors="coerce")
        standings = standings.dropna(subset=["rank", "points"]).drop_duplicates("entry_id")

        players = raw[["Player", "Roster Position", "%Drafted", "FPTS"]].copy()
        players = players.dropna(subset=["Player", "FPTS"]).rename(columns={"Player":"player_name","Roster Position":"roster_position","%Drafted":"actual_ownership","FPTS":"actual_points"})
        players["actual_ownership"] = pd.to_numeric(players["actual_ownership"].astype(str).str.replace("%", "", regex=False), errors="coerce")
        players["actual_points"] = pd.to_numeric(players["actual_points"], errors="coerce")
        players = players.dropna(subset=["actual_ownership", "actual_points"])
        players = players.sort_values("actual_ownership", ascending=False).drop_duplicates("player_name")
        return contest_id, standings.reset_index(drop=True), players.reset_index(drop=True)

    @staticmethod
    def _money(series: pd.Series) -> pd.Series:
        return pd.to_numeric(series.astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False), errors="coerce").fillna(0.0)

    def _parse_history(self, history: pd.DataFrame, contest_id: int) -> tuple[pd.DataFrame, str]:
        required = {"Entry_Key","Entry","Contest_Key","Place","Points","Winnings_Non_Ticket","Entry_Fee","Contest_Entries","Places_Paid"}
        missing = required - set(history.columns)
        if missing:
            raise ValueError(f"Entry history CSV is missing columns: {sorted(missing)}")
        contest_key = pd.to_numeric(history["Contest_Key"], errors="coerce")
        rows = history.loc[contest_key == int(contest_id)].copy()
        if rows.empty:
            return pd.DataFrame(), ""
        contest_name = re.sub(r"\s+\(\d+/\d+\)\s*$", "", str(rows.iloc[0]["Entry"]).strip())
        result = pd.DataFrame({
            "entry_id": rows["Entry_Key"].astype("Int64").astype(str),
            "place": pd.to_numeric(rows["Place"], errors="coerce"),
            "points": pd.to_numeric(rows["Points"], errors="coerce"),
            "winnings": self._money(rows["Winnings_Non_Ticket"]),
            "entry_fee": self._money(rows["Entry_Fee"]),
            "contest_entries": pd.to_numeric(rows["Contest_Entries"], errors="coerce"),
            "places_paid": pd.to_numeric(rows["Places_Paid"], errors="coerce"),
        }).dropna()
        return result, contest_name

    @staticmethod
    def _match_reserved_entries(reserved: pd.DataFrame, standings: pd.DataFrame, contest_id: int) -> tuple[pd.DataFrame, str]:
        work = reserved.copy()
        work["contest_id_num"] = pd.to_numeric(work["contest_id"], errors="coerce")
        work = work.loc[work["contest_id_num"] == int(contest_id)].copy()
        if work.empty:
            return pd.DataFrame(), ""
        work["entry_id"] = work["entry_id"].astype(str).str.strip()
        matched = work.merge(standings[["entry_id", "rank", "points"]], on="entry_id", how="inner")
        if matched.empty:
            return pd.DataFrame(), str(work.iloc[0].get("contest_name", ""))
        fee = pd.to_numeric(matched["entry_fee"].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False), errors="coerce").fillna(0.0)
        result = pd.DataFrame({
            "entry_id": matched["entry_id"], "place": matched["rank"], "points": matched["points"],
            "winnings": 0.0, "entry_fee": fee, "contest_entries": len(standings), "places_paid": 0,
        })
        return result, str(work.iloc[0].get("contest_name", ""))
