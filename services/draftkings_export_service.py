from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
import re
from typing import Iterable

import pandas as pd


ENTRY_METADATA_COLUMNS = (
    "Entry ID",
    "Contest Name",
    "Contest ID",
    "Entry Fee",
)

DRAFTKINGS_ROSTER_SLOTS = (
    "QB",
    "RB1",
    "RB2",
    "WR1",
    "WR2",
    "WR3",
    "TE",
    "FLEX",
    "DST",
)

DRAFTKINGS_TEMPLATE_HEADERS = (
    "QB",
    "RB",
    "RB",
    "WR",
    "WR",
    "WR",
    "TE",
    "FLEX",
    "DST",
)

SALARY_CAP = 50_000


@dataclass(frozen=True)
class DraftKingsEntryTemplate:
    """Parsed DraftKings bulk-entry file."""

    header_row: tuple[str, ...]
    entries: pd.DataFrame
    players: pd.DataFrame
    source_name: str


@dataclass(frozen=True)
class DraftKingsExportResult:
    """Completed DraftKings upload file and validation details."""

    csv_bytes: bytes
    completed_entries: pd.DataFrame
    validation_report: pd.DataFrame
    duplicate_lineups: pd.DataFrame
    critical_errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.critical_errors


class DraftKingsExportError(ValueError):
    """Raised when a DraftKings template or lineup cannot be exported."""


class DraftKingsExportService:
    """Parse DraftKings entries files and create validated upload CSVs."""

    def parse_template(
        self,
        content: bytes | str,
        source_name: str = "DKEntries.csv",
    ) -> DraftKingsEntryTemplate:
        """Parse the entry rows and embedded salary table from DKEntries.csv."""

        text = (
            content.decode("utf-8-sig", errors="replace")
            if isinstance(content, bytes)
            else str(content)
        )
        rows = list(csv.reader(StringIO(text)))

        if not rows:
            raise DraftKingsExportError("The DraftKings file is empty.")

        header = tuple(cell.strip() for cell in rows[0])
        self._validate_entry_header(header)

        salary_header_index = self._find_salary_header_index(rows)
        if salary_header_index is None:
            raise DraftKingsExportError(
                "Could not find the embedded DraftKings player list. "
                "Upload the DKEntries.csv downloaded from Edit Entries."
            )

        entry_records: list[dict[str, object]] = []
        for row_number, row in enumerate(
            rows[1:salary_header_index],
            start=2,
        ):
            padded = self._pad_row(row, len(header))
            entry_id = padded[0].strip()
            if not entry_id:
                continue

            record: dict[str, object] = {
                "template_row": row_number,
                "entry_id": entry_id,
                "contest_name": padded[1].strip(),
                "contest_id": padded[2].strip(),
                "entry_fee": padded[3].strip(),
            }
            for slot_index, slot_name in enumerate(
                DRAFTKINGS_ROSTER_SLOTS,
                start=4,
            ):
                record[slot_name] = padded[slot_index].strip()
            entry_records.append(record)

        if not entry_records:
            raise DraftKingsExportError(
                "No reserved or entered contests were found in the file."
            )

        salary_header_row = rows[salary_header_index]
        offset = self._salary_table_offset(salary_header_row)
        salary_columns = [
            cell.strip()
            for cell in salary_header_row[offset:]
        ]

        player_records: list[dict[str, object]] = []
        for row_number, row in enumerate(
            rows[salary_header_index + 1:],
            start=salary_header_index + 2,
        ):
            if len(row) <= offset:
                continue
            values = row[offset:offset + len(salary_columns)]
            values += [""] * (len(salary_columns) - len(values))
            raw = dict(zip(salary_columns, values))
            player_id = self._clean_player_id(raw.get("ID", ""))
            name = str(raw.get("Name", "")).strip()
            if not player_id or not name:
                continue

            position = self._normalize_position(raw.get("Position", ""))
            roster_position = str(raw.get("Roster Position", "")).strip()
            game_info = str(raw.get("Game Info", "")).strip()
            team = str(raw.get("TeamAbbrev", "")).upper().strip()
            opponent = self._opponent_from_game_info(game_info, team)

            player_records.append(
                {
                    "source_row": row_number,
                    "player_id": player_id,
                    "name_plus_id": str(raw.get("Name + ID", "")).strip()
                    or f"{name} ({player_id})",
                    "name": name,
                    "position": position,
                    "roster_position": roster_position,
                    "salary": self._safe_int(raw.get("Salary", "")),
                    "game_info": game_info,
                    "team": team,
                    "opponent": opponent,
                    "avg_points_per_game": self._safe_float(
                        raw.get("AvgPointsPerGame", "")
                    ),
                }
            )

        players = pd.DataFrame(player_records)
        if players.empty:
            raise DraftKingsExportError(
                "The embedded DraftKings player list did not contain usable players."
            )

        duplicate_ids = players["player_id"].duplicated(keep=False)
        if duplicate_ids.any():
            duplicates = sorted(
                players.loc[duplicate_ids, "player_id"].astype(str).unique()
            )
            raise DraftKingsExportError(
                "The embedded player list contains duplicate DraftKings IDs: "
                + ", ".join(duplicates[:10])
            )

        return DraftKingsEntryTemplate(
            header_row=header,
            entries=pd.DataFrame(entry_records),
            players=players.reset_index(drop=True),
            source_name=source_name,
        )

    def build_player_pool(
        self,
        template: DraftKingsEntryTemplate,
    ) -> pd.DataFrame:
        """Create an optimizer-ready player pool from the embedded salary table."""

        pool = template.players.copy()
        pool["projection"] = 0.0
        pool["ceiling"] = 0.0
        pool["floor"] = 0.0
        pool["ownership"] = 0.0
        pool["confidence"] = 0.0
        pool["locked"] = False
        pool["excluded"] = False
        pool["value"] = 0.0
        pool["leverage"] = 0.0

        columns = [
            "player_id",
            "name_plus_id",
            "name",
            "position",
            "roster_position",
            "team",
            "opponent",
            "salary",
            "game_info",
            "projection",
            "ceiling",
            "floor",
            "value",
            "ownership",
            "leverage",
            "confidence",
            "locked",
            "excluded",
        ]
        return pool[columns].reset_index(drop=True)

    def export_lineups(
        self,
        template: DraftKingsEntryTemplate,
        lineups: Iterable[pd.DataFrame],
        *,
        use_name_plus_id: bool = True,
        salary_cap: int = SALARY_CAP,
    ) -> DraftKingsExportResult:
        """Validate lineups and fill the corresponding DraftKings entry rows."""

        lineup_list = [lineup.copy() for lineup in lineups]
        critical_errors: list[str] = []

        if not lineup_list:
            critical_errors.append("No lineups were selected for export.")

        if len(lineup_list) > len(template.entries):
            critical_errors.append(
                f"{len(lineup_list)} lineups were selected, but the template "
                f"contains only {len(template.entries)} entry row(s)."
            )

        player_lookup = template.players.set_index("player_id", drop=False)
        validation_records: list[dict[str, object]] = []
        lineup_rows: list[list[str]] = []
        signatures: list[tuple[str, ...]] = []

        export_count = min(len(lineup_list), len(template.entries))

        for lineup_number, lineup in enumerate(
            lineup_list[:export_count],
            start=1,
        ):
            normalized, issues = self._normalize_lineup(
                lineup=lineup,
                player_lookup=player_lookup,
                salary_cap=int(salary_cap),
            )

            for issue in issues:
                validation_records.append(
                    {
                        "lineup_number": lineup_number,
                        "severity": "ERROR",
                        "check": issue[0],
                        "detail": issue[1],
                    }
                )

            if issues:
                critical_errors.append(
                    f"Lineup {lineup_number} failed validation."
                )
                lineup_rows.append([""] * len(DRAFTKINGS_ROSTER_SLOTS))
                signatures.append(tuple())
                continue

            ids = tuple(
                normalized.loc[
                    normalized["roster_slot"].isin(DRAFTKINGS_ROSTER_SLOTS),
                    "player_id",
                ].astype(str)
            )
            signatures.append(tuple(sorted(ids)))

            output_values: list[str] = []
            for slot in DRAFTKINGS_ROSTER_SLOTS:
                player_id = str(
                    normalized.loc[
                        normalized["roster_slot"] == slot,
                        "player_id",
                    ].iloc[0]
                )
                player = player_lookup.loc[player_id]
                output_values.append(
                    str(player["name_plus_id"])
                    if use_name_plus_id
                    else player_id
                )
            lineup_rows.append(output_values)

            validation_records.extend(
                [
                    {
                        "lineup_number": lineup_number,
                        "severity": "PASS",
                        "check": "Roster construction",
                        "detail": "All nine DraftKings roster slots are valid.",
                    },
                    {
                        "lineup_number": lineup_number,
                        "severity": "PASS",
                        "check": "DraftKings player IDs",
                        "detail": "Every player ID exists in the uploaded template.",
                    },
                    {
                        "lineup_number": lineup_number,
                        "severity": "PASS",
                        "check": "Salary cap",
                        "detail": (
                            f"Salary ${int(normalized['dk_salary'].sum()):,} "
                            f"of ${int(salary_cap):,}."
                        ),
                    },
                ]
            )

        duplicate_records: list[dict[str, object]] = []
        signature_to_numbers: dict[tuple[str, ...], list[int]] = {}
        for lineup_number, signature in enumerate(signatures, start=1):
            if not signature:
                continue
            signature_to_numbers.setdefault(signature, []).append(lineup_number)

        for numbers in signature_to_numbers.values():
            if len(numbers) > 1:
                duplicate_records.append(
                    {
                        "lineup_numbers": ", ".join(map(str, numbers)),
                        "duplicate_count": len(numbers),
                    }
                )
                critical_errors.append(
                    "Duplicate lineups were detected: "
                    + ", ".join(map(str, numbers))
                )

        completed_rows: list[list[str]] = []
        completed_records: list[dict[str, object]] = []

        for index in range(export_count):
            entry = template.entries.iloc[index]
            roster_values = lineup_rows[index]
            row = [
                str(entry["entry_id"]),
                str(entry["contest_name"]),
                str(entry["contest_id"]),
                str(entry["entry_fee"]),
                *roster_values,
            ]
            completed_rows.append(row)
            completed_records.append(
                {
                    "Entry ID": entry["entry_id"],
                    "Contest Name": entry["contest_name"],
                    "Contest ID": entry["contest_id"],
                    "Entry Fee": entry["entry_fee"],
                    **dict(zip(DRAFTKINGS_ROSTER_SLOTS, roster_values)),
                }
            )

        output = StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(
            [
                *ENTRY_METADATA_COLUMNS,
                *DRAFTKINGS_TEMPLATE_HEADERS,
            ]
        )
        writer.writerows(completed_rows)

        deduped_errors = tuple(dict.fromkeys(critical_errors))
        return DraftKingsExportResult(
            csv_bytes=output.getvalue().encode("utf-8-sig"),
            completed_entries=pd.DataFrame(completed_records),
            validation_report=pd.DataFrame(validation_records),
            duplicate_lineups=pd.DataFrame(duplicate_records),
            critical_errors=deduped_errors,
        )

    def _normalize_lineup(
        self,
        lineup: pd.DataFrame,
        player_lookup: pd.DataFrame,
        salary_cap: int,
    ) -> tuple[pd.DataFrame, list[tuple[str, str]]]:
        issues: list[tuple[str, str]] = []
        required = {"player_id", "roster_slot"}
        missing = required - set(lineup.columns)
        if missing:
            return lineup.copy(), [
                (
                    "Required columns",
                    f"Missing lineup columns: {sorted(missing)}",
                )
            ]

        normalized = lineup.copy().reset_index(drop=True)
        normalized["player_id"] = normalized["player_id"].map(
            self._clean_player_id
        )
        normalized["roster_slot"] = normalized["roster_slot"].astype(str).str.upper().str.strip()
        normalized["roster_slot"] = normalized["roster_slot"].replace(
            {
                "RB": "RB1",
                "WR": "WR1",
                "D/ST": "DST",
                "DEF": "DST",
            }
        )

        if len(normalized) != 9:
            issues.append(
                ("Player count", f"Expected 9 players; found {len(normalized)}.")
            )

        slot_counts = normalized["roster_slot"].value_counts().to_dict()
        for slot in DRAFTKINGS_ROSTER_SLOTS:
            count = int(slot_counts.get(slot, 0))
            if count != 1:
                issues.append(
                    (
                        "Roster slots",
                        f"Roster slot {slot} appears {count} time(s); expected 1.",
                    )
                )

        unexpected = sorted(
            set(normalized["roster_slot"]) - set(DRAFTKINGS_ROSTER_SLOTS)
        )
        if unexpected:
            issues.append(
                ("Roster slots", f"Unexpected roster slots: {unexpected}.")
            )

        duplicate_ids = normalized["player_id"].duplicated(keep=False)
        if duplicate_ids.any():
            names = (
                normalized.loc[duplicate_ids, "player_id"]
                .astype(str)
                .drop_duplicates()
                .tolist()
            )
            issues.append(
                ("Duplicate players", "Duplicate player IDs: " + ", ".join(names))
            )

        unknown_ids = [
            player_id
            for player_id in normalized["player_id"].astype(str)
            if player_id not in player_lookup.index
        ]
        if unknown_ids:
            issues.append(
                (
                    "DraftKings player IDs",
                    "IDs not found in DKEntries.csv: "
                    + ", ".join(sorted(set(unknown_ids))),
                )
            )

        if issues:
            return normalized, issues

        dk_salary: list[int] = []
        for _, row in normalized.iterrows():
            player = player_lookup.loc[str(row["player_id"])]
            slot = str(row["roster_slot"])
            eligible = self._eligible_slots(player)
            if slot not in eligible:
                issues.append(
                    (
                        "Position eligibility",
                        f"{player['name']} ({player['player_id']}) is not "
                        f"eligible for {slot}. Eligible: {sorted(eligible)}.",
                    )
                )
            dk_salary.append(int(player["salary"]))

        normalized["dk_salary"] = dk_salary
        total_salary = int(normalized["dk_salary"].sum())
        if total_salary > salary_cap:
            issues.append(
                (
                    "Salary cap",
                    f"Salary ${total_salary:,} exceeds ${salary_cap:,}.",
                )
            )

        return normalized, issues

    @staticmethod
    def _eligible_slots(player: pd.Series) -> set[str]:
        position = str(player["position"]).upper().strip()
        if position == "QB":
            return {"QB"}
        if position == "RB":
            return {"RB1", "RB2", "FLEX"}
        if position == "WR":
            return {"WR1", "WR2", "WR3", "FLEX"}
        if position == "TE":
            return {"TE", "FLEX"}
        if position == "DST":
            return {"DST"}
        return set()

    @staticmethod
    def _validate_entry_header(header: tuple[str, ...]) -> None:
        if len(header) < 13:
            raise DraftKingsExportError(
                "The DraftKings entry header has fewer columns than expected."
            )
        expected_metadata = list(ENTRY_METADATA_COLUMNS)
        if list(header[:4]) != expected_metadata:
            raise DraftKingsExportError(
                "This does not appear to be a DraftKings entry-edit CSV. "
                f"Expected the first columns to be {expected_metadata}."
            )
        if list(header[4:13]) != list(DRAFTKINGS_TEMPLATE_HEADERS):
            raise DraftKingsExportError(
                "The roster columns do not match DraftKings NFL Classic: "
                "QB, RB, RB, WR, WR, WR, TE, FLEX, DST."
            )

    @staticmethod
    def _find_salary_header_index(rows: list[list[str]]) -> int | None:
        for index, row in enumerate(rows):
            if (
                "Position" in row
                and "Name + ID" in row
                and "ID" in row
                and "Roster Position" in row
                and "Salary" in row
            ):
                return index
        return None

    @staticmethod
    def _salary_table_offset(row: list[str]) -> int:
        try:
            return row.index("Position")
        except ValueError as error:
            raise DraftKingsExportError(
                "The embedded player-list header is malformed."
            ) from error

    @staticmethod
    def _pad_row(row: list[str], length: int) -> list[str]:
        return row + [""] * max(0, length - len(row))

    @staticmethod
    def _clean_player_id(value: object) -> str:
        text = str(value).strip()
        if text.endswith(".0"):
            text = text[:-2]
        match = re.search(r"\((\d+)\)\s*$", text)
        return match.group(1) if match else text

    @staticmethod
    def _normalize_position(value: object) -> str:
        position = str(value).upper().strip()
        return {"D/ST": "DST", "DEF": "DST"}.get(position, position)

    @staticmethod
    def _safe_int(value: object) -> int:
        try:
            return int(float(str(value).replace("$", "").replace(",", "").strip()))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_float(value: object) -> float:
        try:
            return float(str(value).replace("%", "").strip())
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _opponent_from_game_info(game_info: str, team: str) -> str:
        matchup = str(game_info).split(" ", 1)[0]
        if "@" not in matchup:
            return ""
        away, home = matchup.split("@", 1)
        away = away.upper().strip()
        home = home.upper().strip()
        if team == away:
            return home
        if team == home:
            return away
        return ""
