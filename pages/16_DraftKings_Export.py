from __future__ import annotations

import pandas as pd
import streamlit as st

from database import DatabaseManager
from services import (
    DraftKingsContestService,
    DraftKingsExportService,
    PlayerPoolService,
)


st.set_page_config(
    page_title="DraftKings Export",
    page_icon="📤",
    layout="wide",
)

st.title("📤 DraftKings Bulk Export")
st.caption(
    "Fill a DraftKings Edit Entries template with generated or saved NFL "
    "Classic lineups, validate every roster, and download an upload-ready CSV."
)

database = DatabaseManager()
player_pool_service = PlayerPoolService()
export_service = DraftKingsExportService()
contest_service = DraftKingsContestService(
    export_service
)

st.info(
    "DraftKings Export now reuses the `DKEntries.csv` loaded on Weekly Update. "
    "Reserve the entries you plan to use, download DKEntries.csv, and upload "
    "it once on Weekly Update before generating lineups."
)

template = contest_service.get_active_template(
    st.session_state
)

if template is None:
    st.warning(
        "No DraftKings contest is loaded. Open Weekly Update, upload "
        "`DKEntries.csv`, and build the weekly player pool first."
    )
    st.page_link(
        "pages/5_Weekly_Update.py",
        label="Open Weekly Update",
        icon="🔄",
    )
    st.stop()

metric_columns = st.columns(4)
metric_columns[0].metric(
    "Reserved entries",
    len(template.entries),
)
metric_columns[1].metric(
    "DraftKings players",
    len(template.players),
)
metric_columns[2].metric(
    "Contests",
    template.entries["contest_id"].nunique(),
)
metric_columns[3].metric(
    "Template",
    "NFL Classic",
)

with st.expander(
    "Review reserved entries",
    expanded=False,
):
    st.dataframe(
        template.entries[
            [
                "entry_id",
                "contest_name",
                "contest_id",
                "entry_fee",
            ]
        ],
        width="stretch",
        hide_index=True,
    )

with st.expander(
    "Review embedded DraftKings player list",
    expanded=False,
):
    st.dataframe(
        template.players[
            [
                "player_id",
                "name_plus_id",
                "position",
                "roster_position",
                "team",
                "opponent",
                "salary",
                "game_info",
            ]
        ],
        width="stretch",
        hide_index=True,
    )

st.markdown("---")
st.subheader("Choose lineups")

generated_lineups = st.session_state.get(
    "generated_lineups",
    [],
)

saved_lineup_summaries = database.list_lineups()
active_metadata = player_pool_service.get_metadata(
    st.session_state
)
if (
    active_metadata.active_slate_id is not None
    and not saved_lineup_summaries.empty
):
    saved_lineup_summaries = saved_lineup_summaries.loc[
        saved_lineup_summaries["slate_id"]
        == int(active_metadata.active_slate_id)
    ].copy()

source_options: list[str] = []
if generated_lineups:
    source_options.append(
        "Generated lineups from this session"
    )
if not saved_lineup_summaries.empty:
    source_options.append(
        "Saved lineups from the active slate"
    )

if not source_options:
    st.warning(
        "No generated or saved lineups are available. Generate lineups on "
        "the Optimizer page, then return here."
    )
    st.stop()

lineup_source = st.radio(
    "Lineup source",
    options=source_options,
    horizontal=True,
)

selected_lineups: list[pd.DataFrame] = []
lineup_labels: list[str] = []

if lineup_source == "Generated lineups from this session":
    maximum = min(
        len(generated_lineups),
        len(template.entries),
    )
    selected_count = st.number_input(
        "Generated lineups to export",
        min_value=1,
        max_value=max(
            1,
            len(generated_lineups),
        ),
        value=max(
            1,
            maximum,
        ),
        step=1,
    )
    selected_lineups = [
        lineup.copy()
        for lineup in generated_lineups[
            : int(selected_count)
        ]
    ]
    lineup_labels = [
        f"Generated lineup {number}"
        for number in range(
            1,
            len(selected_lineups) + 1,
        )
    ]
else:
    display = saved_lineup_summaries.copy()
    display["selection_label"] = (
        display["lineup_name"].astype(str)
        + " — $"
        + display["total_salary"].astype(int).map(
            "{:,}".format
        )
        + " — "
        + display["total_projection"].astype(float).map(
            lambda value: f"{value:.2f} pts"
        )
    )
    selected_ids = st.multiselect(
        "Saved lineups to export",
        options=display["id"].astype(int).tolist(),
        default=display["id"].astype(int).head(
            len(template.entries)
        ).tolist(),
        format_func=lambda lineup_id: display.loc[
            display["id"] == int(lineup_id),
            "selection_label",
        ].iloc[0],
    )
    for lineup_id in selected_ids:
        selected_lineups.append(
            database.load_lineup_players(
                int(lineup_id)
            )
        )
        lineup_labels.append(
            display.loc[
                display["id"] == int(lineup_id),
                "lineup_name",
            ].iloc[0]
        )

if len(selected_lineups) > len(template.entries):
    st.error(
        f"You selected {len(selected_lineups)} lineups for only "
        f"{len(template.entries)} reserved entries."
    )

st.caption(
    f"Selected {len(selected_lineups)} lineup(s) for "
    f"{len(template.entries)} reserved entry row(s)."
)

player_cell_format = st.radio(
    "DraftKings player-cell format",
    options=[
        "Name + ID",
        "ID only",
    ],
    horizontal=True,
    help=(
        "DraftKings accepts values from either the Name + ID column or the "
        "ID column. Name + ID is easier to inspect before upload."
    ),
)

validate_clicked = st.button(
    "Validate and build DraftKings upload CSV",
    type="primary",
    use_container_width=True,
    disabled=not selected_lineups,
)

if validate_clicked:
    result = export_service.export_lineups(
        template=template,
        lineups=selected_lineups,
        use_name_plus_id=(
            player_cell_format
            == "Name + ID"
        ),
    )
    st.session_state.dk_export_result = result
    st.session_state.dk_export_template_name = (
        template.source_name
    )

result = st.session_state.get(
    "dk_export_result"
)

if result is None:
    st.stop()

st.markdown("---")
st.subheader("Pre-upload validation")

error_count = len(
    result.critical_errors
)
pass_count = (
    int(
        (
            result.validation_report[
                "severity"
            ]
            == "PASS"
        ).sum()
    )
    if not result.validation_report.empty
    else 0
)

validation_metrics = st.columns(4)
validation_metrics[0].metric(
    "Lineups completed",
    len(result.completed_entries),
)
validation_metrics[1].metric(
    "Reserved entries",
    len(template.entries),
)
validation_metrics[2].metric(
    "Passed checks",
    pass_count,
)
validation_metrics[3].metric(
    "Critical errors",
    error_count,
)

if result.critical_errors:
    st.error(
        "Export is blocked until these issues are resolved:"
    )
    for error in result.critical_errors:
        st.write(
            f"- {error}"
        )
else:
    st.success(
        "All selected lineups passed DraftKings roster, ID, salary, and "
        "duplicate-lineup validation."
    )

if not result.validation_report.empty:
    st.dataframe(
        result.validation_report,
        width="stretch",
        hide_index=True,
    )

if not result.duplicate_lineups.empty:
    st.subheader("Duplicate lineups")
    st.dataframe(
        result.duplicate_lineups,
        width="stretch",
        hide_index=True,
    )

st.subheader("Completed entry preview")
st.dataframe(
    result.completed_entries,
    width="stretch",
    hide_index=True,
)

st.download_button(
    "Download DraftKings upload CSV",
    data=result.csv_bytes,
    file_name="DKEntries_completed.csv",
    mime="text/csv",
    use_container_width=True,
    type="primary",
    disabled=not result.is_valid,
)

st.caption(
    "Upload the completed file through DraftKings Edit Entries. Review the "
    "DraftKings confirmation screen before accepting the changes."
)
