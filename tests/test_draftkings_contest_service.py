from __future__ import annotations

from pathlib import Path

from services import (
    DraftKingsContestService,
    DraftKingsExportService,
)


def test_contest_context_round_trip() -> None:
    project_root = Path(__file__).resolve().parents[1]
    fixture = project_root / "tests" / "fixtures" / "DKEntries.csv"

    if not fixture.exists():
        return

    state: dict = {}
    service = DraftKingsContestService(
        DraftKingsExportService()
    )

    template = service.set_active_contest(
        state,
        fixture.read_bytes(),
        source_name=fixture.name,
    )

    assert service.has_active_contest(state)
    assert len(template.entries) > 0

    loaded = service.get_active_template(state)

    assert loaded is not None
    assert len(loaded.entries) == len(template.entries)
    assert len(loaded.players) == len(template.players)

    metadata = service.get_metadata(state)

    assert metadata is not None
    assert metadata.entry_count == len(template.entries)
    assert metadata.player_count == len(template.players)


def test_clear_contest_context() -> None:
    service = DraftKingsContestService()
    state = {
        service.CONTENT_KEY: b"data",
        service.SOURCE_NAME_KEY: "DKEntries.csv",
        "dk_export_result": object(),
    }

    service.clear_active_contest(state)

    assert not service.has_active_contest(state)
    assert "dk_export_result" not in state


def test_entries_continue_after_embedded_salary_header() -> None:
    """DraftKings can interleave later entries with the embedded salary table."""

    csv_text = "\n".join(
        [
            "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions",
            "1001,Contest A,9001,$0.10,,,,,,,,,,,Instruction 1",
            "1002,Contest A,9001,$0.10,,,,,,,,,,,Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame",
            "1003,Contest A,9001,$0.10,,,,,,,,,,,QB,Player One (111),Player One,111,QB,5000,AAA@BBB 09/13/2026 01:00PM ET,AAA,10.0",
            "2001,Contest B,9002,$1.00,,,,,,,,,,,RB,Player Two (222),Player Two,222,RB/FLEX,4000,AAA@BBB 09/13/2026 01:00PM ET,BBB,8.0",
            ",,,,,,,,,,,,,,WR,Player Three (333),Player Three,333,WR/FLEX,3000,CCC@DDD 09/13/2026 04:00PM ET,CCC,7.0",
        ]
    )

    service = DraftKingsExportService()
    template = service.parse_template(csv_text, source_name="DKEntries.csv")

    assert len(template.entries) == 4
    assert template.entries["entry_id"].tolist() == ["1001", "1002", "1003", "2001"]
    assert template.entries["contest_id"].nunique() == 2
    assert len(template.players) == 3
