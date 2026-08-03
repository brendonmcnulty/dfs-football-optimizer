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
