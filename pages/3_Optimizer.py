from __future__ import annotations

from datetime import datetime

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
st.caption("Generate and save DraftKings NFL Classic lineups")

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
        "This player pool has not been saved to the database. You may "
        "generate a lineup, but you must save the slate from the "
        "**Player Pool** page before the lineup can be stored."
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

    st.session_state.salary_cap = int(salary_cap)
    st.session_state.minimum_salary = int(
        minimum_salary
    )

optimizer_settings = OptimizerSettings(
    salary_cap=int(salary_cap),
    minimum_salary=int(minimum_salary),
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
    int((players["projection"] > 0).sum()),
)

metric_column_3.metric(
    "Locked",
    int(players["locked"].sum()),
)

metric_column_4.metric(
    "Excluded",
    int(players["excluded"].sum()),
)

with st.expander("Review active player pool"):
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

optimize_clicked = st.button(
    "Generate optimal lineup",
    type="primary",
    use_container_width=True,
)

if optimize_clicked:
    try:
        result = optimizer_service.generate_lineup(
            players=players,
            settings=optimizer_settings,
        )

        st.session_state.latest_lineup = (
            result.lineup.copy()
        )

        st.session_state.latest_lineup_salary = (
            result.total_salary
        )

        st.session_state.latest_lineup_projection = (
            result.total_projection
        )

        st.session_state.latest_lineup_status = (
            result.status
        )

        st.session_state.latest_lineup_saved = False
        st.session_state.latest_lineup_id = None

    except Exception as exc:
        st.error(f"Optimizer error: {exc}")

if "latest_lineup" not in st.session_state:
    st.info(
        "Configure the optimizer and generate a lineup."
    )
    st.stop()

lineup = st.session_state.latest_lineup.copy()

total_salary = int(
    st.session_state.latest_lineup_salary
)

total_projection = float(
    st.session_state.latest_lineup_projection
)

status = str(
    st.session_state.latest_lineup_status
)

st.success(
    f"Lineup generated — solver status: {status}"
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
    f"${int(salary_cap) - total_salary:,}",
)

display_columns = [
    "roster_slot",
    "name",
    "position",
    "team",
    "opponent",
    "salary",
    "projection",
]

st.dataframe(
    lineup[display_columns],
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
st.subheader("Save lineup")

default_lineup_name = (
    "Lineup "
    + datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )
)

latest_lineup_saved = bool(
    st.session_state.get(
        "latest_lineup_saved",
        False,
    )
)

lineup_name = st.text_input(
    "Lineup name",
    value=default_lineup_name,
    disabled=latest_lineup_saved,
)

save_lineup_clicked = st.button(
    "Save lineup to database",
    use_container_width=True,
    disabled=(
        active_slate_id is None
        or latest_lineup_saved
    ),
)

if save_lineup_clicked:
    try:
        lineup_id = database.save_lineup(
            slate_id=int(active_slate_id),
            lineup=lineup,
            lineup_name=lineup_name,
            total_salary=total_salary,
            total_projection=total_projection,
            solver_status=status,
            salary_cap=optimizer_settings.salary_cap,
            minimum_salary=(
                optimizer_settings.minimum_salary
            ),
        )

        st.session_state.latest_lineup_saved = True
        st.session_state.latest_lineup_id = lineup_id

        st.rerun()

    except Exception as exc:
        st.error(
            f"Could not save lineup: {exc}"
        )

if st.session_state.get(
    "latest_lineup_saved",
    False,
):
    saved_lineup_id = st.session_state.get(
        "latest_lineup_id"
    )

    st.success(
        "This lineup is saved in the database as "
        f"lineup #{saved_lineup_id}."
    )

export = lineup[
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
    "Download lineup CSV",
    data=export.to_csv(
        index=False
    ).encode("utf-8"),
    file_name="optimized_lineup.csv",
    mime="text/csv",
)