from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from data_loader import merge_projections, normalize_player_pool
from database import DatabaseManager


st.set_page_config(
    page_title="Player Pool",
    page_icon="👥",
    layout="wide",
)

database = DatabaseManager()

st.title("👥 Player Pool")
st.caption("Import, edit, and save a DraftKings NFL player pool")

with st.sidebar:
    st.header("Slate information")

    current_year = datetime.now().year

    season = st.number_input(
        "NFL season",
        min_value=2000,
        max_value=current_year + 1,
        value=int(st.session_state.get("season", current_year)),
        step=1,
    )

    week = st.number_input(
        "NFL week",
        min_value=1,
        max_value=22,
        value=int(st.session_state.get("week", 1)),
        step=1,
    )

    site = st.selectbox(
        "DFS site",
        options=["DraftKings"],
        index=0,
    )

    slate_name = st.text_input(
        "Slate name",
        value=str(st.session_state.get("slate_name", "Main")),
    )

    st.markdown("---")

    st.write(
        "Upload one combined CSV containing projections, or upload a "
        "DraftKings salary CSV and a separate projections CSV."
    )

salary_file = st.file_uploader(
    "Upload salary/player-pool CSV",
    type=["csv"],
    key="player_pool_salary_upload",
)

projection_file = st.file_uploader(
    "Optional: upload separate projection CSV",
    type=["csv"],
    key="player_pool_projection_upload",
)

if salary_file is not None:
    try:
        raw_players = pd.read_csv(salary_file)
        imported_players = normalize_player_pool(raw_players)

        if projection_file is not None:
            raw_projections = pd.read_csv(projection_file)
            imported_players = merge_projections(
                imported_players,
                raw_projections,
            )

        uploaded_file_signature = (
            salary_file.name,
            salary_file.size,
            projection_file.name if projection_file is not None else None,
            projection_file.size if projection_file is not None else None,
        )

        previous_signature = st.session_state.get(
            "uploaded_file_signature"
        )

        if uploaded_file_signature != previous_signature:
            st.session_state.player_pool = imported_players
            st.session_state.uploaded_file_signature = (
                uploaded_file_signature
            )

            st.session_state.active_slate_id = None
            st.session_state.active_slate_name = (
                f"{season} Week {week} — {site} {slate_name}"
            )

    except Exception as exc:
        st.error(f"Could not read the uploaded file: {exc}")

if "player_pool" not in st.session_state:
    st.info(
        "Upload a player-pool CSV to begin, or use the **Saved Slates** "
        "page to load a previously saved slate."
    )
    st.stop()

players = st.session_state.player_pool.copy()

st.subheader("Active slate")

active_slate_name = st.session_state.get(
    "active_slate_name",
    f"{season} Week {week} — {site} {slate_name}",
)

st.write(f"**{active_slate_name}**")

st.subheader("Players")

st.write(
    "Edit projections directly. Check **Lock** to force a player into every "
    "generated lineup or **Exclude** to remove the player from consideration."
)

edited_players = st.data_editor(
    players,
    width="stretch",
    hide_index=True,
    key="player_pool_editor",
    disabled=[
        "player_id",
        "name",
        "position",
        "team",
        "opponent",
        "salary",
    ],
    column_config={
        "player_id": st.column_config.TextColumn(
            "Player ID",
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
            min_value=0.0,
            step=0.1,
            format="%.2f",
        ),
        "locked": st.column_config.CheckboxColumn(
            "Lock",
        ),
        "excluded": st.column_config.CheckboxColumn(
            "Exclude",
        ),
    },
)

st.session_state.player_pool = edited_players.copy()
st.session_state.season = int(season)
st.session_state.week = int(week)
st.session_state.site = site
st.session_state.slate_name = slate_name

valid_projection_count = int(
    (edited_players["projection"] > 0).sum()
)

locked_count = int(edited_players["locked"].sum())
excluded_count = int(edited_players["excluded"].sum())

metric_column_1, metric_column_2, metric_column_3 = st.columns(3)

metric_column_1.metric(
    "Players",
    len(edited_players),
)

metric_column_2.metric(
    "Positive projections",
    valid_projection_count,
)

metric_column_3.metric(
    "Locked / excluded",
    f"{locked_count} / {excluded_count}",
)

st.markdown("---")

button_column_1, button_column_2 = st.columns(2)

with button_column_1:
    save_session_clicked = st.button(
        "Save player-pool changes",
        use_container_width=True,
    )

with button_column_2:
    save_database_clicked = st.button(
        "Save slate to database",
        type="primary",
        use_container_width=True,
    )

if save_session_clicked:
    st.session_state.player_pool = edited_players.copy()
    st.success("Player-pool changes were saved for this session.")

if save_database_clicked:
    try:
        if not slate_name.strip():
            raise ValueError("Slate name cannot be blank.")

        slate_id = database.save_slate(
            season=int(season),
            week=int(week),
            site=site,
            slate_name=slate_name,
        )

        saved_count = database.save_player_pool(
            slate_id=slate_id,
            players=edited_players,
        )

        st.session_state.player_pool = edited_players.copy()
        st.session_state.active_slate_id = slate_id
        st.session_state.active_slate_name = (
            f"{season} Week {week} — {site} {slate_name}"
        )

        st.success(
            f"Saved {saved_count} players for "
            f"{season} Week {week} — {site} {slate_name}."
        )

    except Exception as exc:
        st.error(f"Database error: {exc}")