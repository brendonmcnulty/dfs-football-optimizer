from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping

from services.draftkings_export_service import (
    DraftKingsEntryTemplate,
    DraftKingsExportService,
)


@dataclass(frozen=True)
class ActiveDraftKingsContest:
    """Metadata for the DraftKings entry file active in the current session."""

    source_name: str
    entry_count: int
    contest_count: int
    player_count: int


class DraftKingsContestService:
    """
    Store and retrieve one parsed DraftKings entry file through shared state.

    The raw CSV bytes are kept in Streamlit session state so Weekly Update,
    Optimizer, and DraftKings Export can share the same contest context
    without asking the user to upload the file again.
    """

    CONTENT_KEY = "_draftkings_entries_content"
    SOURCE_NAME_KEY = "_draftkings_entries_source_name"
    METADATA_KEY = "_draftkings_entries_metadata"

    def __init__(
        self,
        export_service: DraftKingsExportService | None = None,
    ) -> None:
        self.export_service = (
            export_service
            or DraftKingsExportService()
        )

    def has_active_contest(
        self,
        state: MutableMapping[str, Any],
    ) -> bool:
        """Return whether a DraftKings entries file is active."""

        content = state.get(self.CONTENT_KEY)
        return isinstance(content, bytes) and bool(content)

    def set_active_contest(
        self,
        state: MutableMapping[str, Any],
        content: bytes,
        *,
        source_name: str,
    ) -> DraftKingsEntryTemplate:
        """Parse and store one DraftKings entries file."""

        if not isinstance(content, bytes) or not content:
            raise ValueError(
                "DraftKings entry content must be non-empty bytes."
            )

        template = self.export_service.parse_template(
            content,
            source_name=source_name,
        )

        metadata = ActiveDraftKingsContest(
            source_name=str(source_name),
            entry_count=len(template.entries),
            contest_count=int(
                template.entries["contest_id"].nunique()
            ),
            player_count=len(template.players),
        )

        state[self.CONTENT_KEY] = bytes(content)
        state[self.SOURCE_NAME_KEY] = str(source_name)
        state[self.METADATA_KEY] = metadata

        # Clear any export built from an older contest file.
        state.pop("dk_export_result", None)
        state.pop("dk_export_template_name", None)

        return template

    def get_active_template(
        self,
        state: MutableMapping[str, Any],
    ) -> DraftKingsEntryTemplate | None:
        """Return the currently active parsed DraftKings entry template."""

        content = state.get(self.CONTENT_KEY)

        if not isinstance(content, bytes) or not content:
            return None

        source_name = str(
            state.get(
                self.SOURCE_NAME_KEY,
                "DKEntries.csv",
            )
        )

        return self.export_service.parse_template(
            content,
            source_name=source_name,
        )

    def get_metadata(
        self,
        state: MutableMapping[str, Any],
    ) -> ActiveDraftKingsContest | None:
        """Return metadata for the active contest file."""

        raw = state.get(self.METADATA_KEY)

        if isinstance(raw, ActiveDraftKingsContest):
            return raw

        template = self.get_active_template(state)

        if template is None:
            return None

        return ActiveDraftKingsContest(
            source_name=template.source_name,
            entry_count=len(template.entries),
            contest_count=int(
                template.entries["contest_id"].nunique()
            ),
            player_count=len(template.players),
        )

    def clear_active_contest(
        self,
        state: MutableMapping[str, Any],
    ) -> None:
        """Remove the active DraftKings contest and export state."""

        for key in (
            self.CONTENT_KEY,
            self.SOURCE_NAME_KEY,
            self.METADATA_KEY,
            "dk_export_result",
            "dk_export_template_name",
        ):
            state.pop(key, None)
