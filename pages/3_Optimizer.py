from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from config import SALARY_CAP
from core.settings import OptimizerSettings
from database import DatabaseManager
from services import OptimizerService


st.set_page_config(
    page_title="Optimizer",
    page_icon="⚙️",
    layout="wide",
)

database = DatabaseManager()
optimizer_service = OptimizerService()

st.title("⚙️ Lineup Optimizer")
st.caption(
    "Generate and analyze multiple unique DraftKings NFL Classic lineups"
)

if "player_pool" not in st.session_state:
    st.warning(
        "No player pool is currently loaded. Import a CSV from the "
        "**Player Pool** page or load a slate from **Saved Slates**."
    )
    st.stop()

players = st.session_state.player_pool.copy()

active_slate_name = st.session_state.get(
    "active_slate_name",
    "Unsaved player pool",
)

active_slate_id = st.session_state.get(
    "active_slate_id"
)

st.subheader("Active slate")
st.write(f"**{active_slate_name}**")

if active_slate_id is None:
    st.warning(
        "This player pool has not been saved to the database. "
        "You may generate lineups, but the slate must be saved "
        "before a lineup can be stored."
    )

with st.sidebar:
    st.header("Optimizer settings")

    salary_cap = st.number_input(
        "Salary cap",
        min_value=1,
        value=int(
            st.session_state.get(
                "salary_cap",
                SALARY_CAP,
            )
        ),
        step=500,
    )

    saved_minimum_salary = int(
        st.session_state.get(
            "minimum_salary",
            0,
        )
    )

    minimum_salary = st.number_input(
        "Minimum salary to use",
        min_value=0,
        max_value=int(salary_cap),
        value=min(
            saved_minimum_salary,
            int(salary_cap),
        ),
        step=100,
    )

    lineup_count = st.number_input(
        "Number of lineups",
        min_value=1,
        max_value=150,
        value=int(
            st.session_state.get(
                "lineup_count",
                5,
            )
        ),
        step=1,
    )

    minimum_unique_players = st.slider(
        "Minimum unique players",
        min_value=1,
        max_value=9,
        value=int(
            st.session_state.get(
                "minimum_unique_players",
                1,
            )
        ),
        help=(
            "Each generated lineup must differ from every earlier "
            "lineup by at least this many players."
        ),
    )

    st.session_state.salary_cap = int(
        salary_cap
    )

    st.session_state.minimum_salary = int(
        minimum_salary
    )

    st.session_state.lineup_count = int(
        lineup_count
    )

    st.session_state.minimum_unique_players = int(
        minimum_unique_players
    )

optimizer_settings = OptimizerSettings(
    salary_cap=int(salary_cap),
    minimum_salary=int(minimum_salary),
    lineup_count=int(lineup_count),
    minimum_unique_players=int(
        minimum_unique_players
    ),
)

st.subheader("Player-pool summary")

metric_column_1, metric_column_2, metric_column_3, metric_column_4 = (
    st.columns(4)
)

metric_column_1.metric(
    "Players",
    len(players),
)

metric_column_2.metric(
    "Positive projections",
    int(
        (
            players["projection"] > 0
        ).sum()
    ),
)

metric_column_3.metric(
    "Locked",
    int(
        players["locked"].sum()
    ),
)

metric_column_4.metric(
    "Excluded",
    int(
        players["excluded"].sum()
    ),
)

with st.expander(
    "Review active player pool"
):
    st.dataframe(
        players[
            [
                "name",
                "position",
                "team",
                "opponent",
                "salary",
                "projection",
                "locked",
                "excluded",
            ]
        ],
        width="stretch",
        hide_index=True,
        column_config={
            "salary": st.column_config.NumberColumn(
                "Salary",
                format="$%d",
            ),
            "projection": st.column_config.NumberColumn(
                "Projection",
                format="%.2f",
            ),
            "locked": st.column_config.CheckboxColumn(
                "Locked",
            ),
            "excluded": st.column_config.CheckboxColumn(
                "Excluded",
            ),
        },
    )

generate_clicked = st.button(
    "Generate lineups",
    type="primary",
    use_container_width=True,
)

if generate_clicked:
    try:
        results = (
            optimizer_service.generate_lineups(
                players=players,
                settings=optimizer_settings,
            )
        )

        generated_lineups = [
            result.lineup.copy()
            for result in results
        ]

        st.session_state.generated_lineups = (
            generated_lineups
        )

        st.session_state.generated_lineup_metadata = [
            {
                "total_salary": (
                    result.total_salary
                ),
                "total_projection": (
                    result.total_projection
                ),
                "status": result.status,
            }
            for result in results
        ]

        st.session_state.generated_exposure_report = (
            optimizer_service.build_exposure_report(
                generated_lineups
            )
        )

        st.session_state.generated_lineup_settings = {
            "salary_cap": int(
                optimizer_settings.salary_cap
            ),
            "minimum_salary": int(
                optimizer_settings.minimum_salary
            ),
            "lineup_count": int(
                optimizer_settings.lineup_count
            ),
            "minimum_unique_players": int(
                optimizer_settings.minimum_unique_players
            ),
        }

        st.session_state.saved_generated_lineups = {}

    except Exception as exc:
        st.error(
            f"Optimizer error: {exc}"
        )

if "generated_lineups" not in st.session_state:
    st.info(
        "Configure the optimizer and generate one or more lineups."
    )
    st.stop()

generated_lineups = (
    st.session_state.generated_lineups
)

generated_metadata = (
    st.session_state.generated_lineup_metadata
)

generated_settings = (
    st.session_state.get(
        "generated_lineup_settings",
        {
            "salary_cap": int(salary_cap),
            "minimum_salary": int(
                minimum_salary
            ),
            "lineup_count": len(
                generated_lineups
            ),
            "minimum_unique_players": int(
                minimum_unique_players
            ),
        },
    )
)

generated_salary_cap = int(
    generated_settings["salary_cap"]
)

requested_lineup_count = int(
    generated_settings["lineup_count"]
)

generated_count = len(
    generated_lineups
)

if generated_count < requested_lineup_count:
    st.warning(
        f"The optimizer generated {generated_count} of the "
        f"{requested_lineup_count} requested lineups. The player pool "
        "could not support more lineups under the current uniqueness, "
        "lock, exclusion, and salary rules."
    )
else:
    st.success(
        f"Generated {generated_count} unique lineups."
    )

summary_records: list[dict] = []

for lineup_index, metadata in enumerate(
    generated_metadata,
    start=1,
):
    summary_records.append(
        {
            "lineup_number": lineup_index,
            "total_salary": int(
                metadata["total_salary"]
            ),
            "salary_remaining": (
                generated_salary_cap
                - int(
                    metadata["total_salary"]
                )
            ),
            "total_projection": float(
                metadata["total_projection"]
            ),
            "status": str(
                metadata["status"]
            ),
        }
    )

summary_frame = pd.DataFrame(
    summary_records
)

st.subheader("Generated lineup summary")

st.dataframe(
    summary_frame,
    width="stretch",
    hide_index=True,
    column_config={
        "lineup_number": st.column_config.NumberColumn(
            "Lineup",
            format="%d",
        ),
        "total_salary": st.column_config.NumberColumn(
            "Salary",
            format="$%d",
        ),
        "salary_remaining": st.column_config.NumberColumn(
            "Remaining",
            format="$%d",
        ),
        "total_projection": st.column_config.NumberColumn(
            "Projection",
            format="%.2f",
        ),
        "status": st.column_config.TextColumn(
            "Status",
        ),
    },
)

st.markdown("---")
st.subheader("Portfolio exposure")

exposure_report = (
    st.session_state.get(
        "generated_exposure_report"
    )
)

if exposure_report is None:
    exposure_report = (
        optimizer_service.build_exposure_report(
            generated_lineups
        )
    )

    st.session_state.generated_exposure_report = (
        exposure_report
    )

if exposure_report.empty:
    st.info(
        "No exposure data is available."
    )
else:
    exposure_metric_1, exposure_metric_2, exposure_metric_3 = (
        st.columns(3)
    )

    highest_exposure = float(
        exposure_report["exposure"].max()
    )

    full_exposure_count = int(
        (
            exposure_report["exposure"]
            == 1.0
        ).sum()
    )

    unique_players_used = int(
        len(exposure_report)
    )

    exposure_metric_1.metric(
        "Players used",
        unique_players_used,
    )

    exposure_metric_2.metric(
        "100% exposed players",
        full_exposure_count,
    )

    exposure_metric_3.metric(
        "Highest exposure",
        f"{highest_exposure:.0%}",
    )

    position_options = [
        "All",
        "QB",
        "RB",
        "WR",
        "TE",
        "DST",
    ]

    selected_position = st.selectbox(
        "Filter exposure by position",
        options=position_options,
    )

    minimum_exposure_percentage = st.slider(
        "Minimum displayed exposure",
        min_value=0,
        max_value=100,
        value=0,
        step=5,
    )

    filtered_exposure = (
        exposure_report.copy()
    )

    if selected_position != "All":
        filtered_exposure = (
            filtered_exposure.loc[
                filtered_exposure["position"]
                == selected_position
            ]
        )

    filtered_exposure = (
        filtered_exposure.loc[
            filtered_exposure["exposure"]
            >= (
                minimum_exposure_percentage
                / 100
            )
        ]
        .reset_index(drop=True)
    )

    if filtered_exposure.empty:
        st.info(
            "No players match the current exposure filters."
        )
    else:
        st.dataframe(
            filtered_exposure[
                [
                    "name",
                    "position",
                    "team",
                    "salary",
                    "projection",
                    "lineup_count",
                    "exposure",
                ]
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "name": st.column_config.TextColumn(
                    "Player",
                ),
                "position": st.column_config.TextColumn(
                    "Position",
                ),
                "team": st.column_config.TextColumn(
                    "Team",
                ),
                "salary": st.column_config.NumberColumn(
                    "Salary",
                    format="$%d",
                ),
                "projection": st.column_config.NumberColumn(
                    "Projection",
                    format="%.2f",
                ),
                "lineup_count": st.column_config.NumberColumn(
                    "Lineups",
                    format="%d",
                ),
                "exposure": st.column_config.ProgressColumn(
                    "Exposure",
                    min_value=0.0,
                    max_value=1.0,
                    format="percent",
                ),
            },
        )

    exposure_export = (
        exposure_report.copy()
    )

    exposure_export["exposure_percentage"] = (
        exposure_export["exposure"]
        * 100
    )

    exposure_export = exposure_export[
        [
            "player_id",
            "name",
            "position",
            "team",
            "salary",
            "projection",
            "lineup_count",
            "exposure_percentage",
        ]
    ]

    st.download_button(
        "Download exposure report CSV",
        data=exposure_export.to_csv(
            index=False
        ).encode("utf-8"),
        file_name="lineup_exposure_report.csv",
        mime="text/csv",
    )

st.markdown("---")
st.subheader("Lineup review")

selected_lineup_number = st.selectbox(
    "Select a lineup to review",
    options=list(
        range(
            1,
            generated_count + 1,
        )
    ),
    format_func=lambda number: (
        f"Lineup {number}"
    ),
)

selected_index = (
    int(selected_lineup_number) - 1
)

selected_lineup = (
    generated_lineups[
        selected_index
    ].copy()
)

selected_metadata = (
    generated_metadata[
        selected_index
    ]
)

total_salary = int(
    selected_metadata["total_salary"]
)

total_projection = float(
    selected_metadata["total_projection"]
)

status = str(
    selected_metadata["status"]
)

st.subheader(
    f"Lineup {selected_lineup_number}"
)

metric_column_1, metric_column_2, metric_column_3 = (
    st.columns(3)
)

metric_column_1.metric(
    "Projected points",
    f"{total_projection:.2f}",
)

metric_column_2.metric(
    "Salary used",
    f"${total_salary:,}",
)

metric_column_3.metric(
    "Salary remaining",
    f"${generated_salary_cap - total_salary:,}",
)

st.dataframe(
    selected_lineup[
        [
            "roster_slot",
            "name",
            "position",
            "team",
            "opponent",
            "salary",
            "projection",
        ]
    ],
    width="stretch",
    hide_index=True,
    column_config={
        "roster_slot": st.column_config.TextColumn(
            "Roster slot",
        ),
        "name": st.column_config.TextColumn(
            "Player",
        ),
        "position": st.column_config.TextColumn(
            "Position",
        ),
        "team": st.column_config.TextColumn(
            "Team",
        ),
        "opponent": st.column_config.TextColumn(
            "Opponent",
        ),
        "salary": st.column_config.NumberColumn(
            "Salary",
            format="$%d",
        ),
        "projection": st.column_config.NumberColumn(
            "Projection",
            format="%.2f",
        ),
    },
)

st.markdown("---")
st.subheader("Save selected lineup")

saved_generated_lineups = (
    st.session_state.get(
        "saved_generated_lineups",
        {},
    )
)

selected_lineup_saved = (
    selected_index
    in saved_generated_lineups
)

default_lineup_name = (
    f"Lineup {selected_lineup_number} - "
    + datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )
)

lineup_name = st.text_input(
    "Lineup name",
    value=default_lineup_name,
    key=(
        "lineup_name_"
        f"{selected_lineup_number}"
    ),
    disabled=selected_lineup_saved,
)

save_lineup_clicked = st.button(
    "Save selected lineup to database",
    use_container_width=True,
    disabled=(
        active_slate_id is None
        or selected_lineup_saved
    ),
)

if save_lineup_clicked:
    try:
        lineup_id = database.save_lineup(
            slate_id=int(
                active_slate_id
            ),
            lineup=selected_lineup,
            lineup_name=lineup_name,
            total_salary=total_salary,
            total_projection=total_projection,
            solver_status=status,
            salary_cap=generated_salary_cap,
            minimum_salary=int(
                generated_settings[
                    "minimum_salary"
                ]
            ),
        )

        saved_generated_lineups[
            selected_index
        ] = lineup_id

        st.session_state.saved_generated_lineups = (
            saved_generated_lineups
        )

        st.rerun()

    except Exception as exc:
        st.error(
            f"Could not save lineup: {exc}"
        )

if selected_lineup_saved:
    saved_lineup_id = (
        saved_generated_lineups[
            selected_index
        ]
    )

    st.success(
        "This lineup is saved in the database as "
        f"lineup #{saved_lineup_id}."
    )

selected_export = selected_lineup[
    [
        "roster_slot",
        "player_id",
        "name",
        "position",
        "team",
        "salary",
    ]
].copy()

st.download_button(
    "Download selected lineup CSV",
    data=selected_export.to_csv(
        index=False
    ).encode("utf-8"),
    file_name=(
        f"optimized_lineup_"
        f"{selected_lineup_number}.csv"
    ),
    mime="text/csv",
)

portfolio_export_records: list[dict] = []

for lineup_index, lineup in enumerate(
    generated_lineups,
    start=1,
):
    for _, player in lineup.iterrows():
        portfolio_export_records.append(
            {
                "lineup_number": lineup_index,
                "roster_slot": (
                    player["roster_slot"]
                ),
                "player_id": (
                    player["player_id"]
                ),
                "name": player["name"],
                "position": (
                    player["position"]
                ),
                "team": player["team"],
                "salary": player["salary"],
                "projection": (
                    player["projection"]
                ),
            }
        )

portfolio_export = pd.DataFrame(
    portfolio_export_records
)

st.download_button(
    "Download all generated lineups CSV",
    data=portfolio_export.to_csv(
        index=False
    ).encode("utf-8"),
    file_name="generated_lineups.csv",
    mime="text/csv",
)