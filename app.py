from __future__ import annotations

import streamlit as st

from database import DatabaseManager


st.set_page_config(
    page_title="DFS Football Optimizer",
    page_icon="🏈",
    layout="wide",
)

database = DatabaseManager()

saved_slates = database.list_slates()
saved_lineups = database.list_lineups()

st.title("🏈 DFS Football Optimizer")
st.caption("DraftKings NFL Classic analytics and lineup optimization")

st.markdown(
    """
    Use the sidebar navigation to import player pools, manage saved slates,
    generate optimized lineups, and review previously saved lineups.
    """
)

metric_column_1, metric_column_2, metric_column_3, metric_column_4 = (
    st.columns(4)
)

metric_column_1.metric(
    "Saved slates",
    len(saved_slates),
)

metric_column_2.metric(
    "Saved lineups",
    len(saved_lineups),
)

if "player_pool" in st.session_state:
    loaded_player_count = len(st.session_state.player_pool)
else:
    loaded_player_count = 0

metric_column_3.metric(
    "Players currently loaded",
    loaded_player_count,
)

active_slate_name = st.session_state.get(
    "active_slate_name",
    "None",
)

metric_column_4.metric(
    "Active slate",
    active_slate_name,
)

st.markdown("---")

st.subheader("Application workflow")

st.markdown(
    """
    ### 1. Player Pool

    Upload a DraftKings salary file or a combined salary and projection file.
    Edit projections, lock players, exclude players, and save the slate to
    SQLite.

    ### 2. Saved Slates

    View previously saved slates and load one into the active session.

    ### 3. Optimizer

    Generate an optimal lineup from the active player pool. Configure the
    salary cap and minimum salary before optimizing.

    ### 4. Saved Lineups

    Review lineups stored in SQLite, inspect every roster spot, and download
    previously generated lineups as CSV files.
    """
)

if "player_pool" not in st.session_state:
    st.info(
        "Begin on the **Player Pool** page, or open **Saved Slates** to load "
        "a player pool already stored in the database."
    )
else:
    st.success(
        f"{loaded_player_count} players are loaded and ready for optimization."
    )