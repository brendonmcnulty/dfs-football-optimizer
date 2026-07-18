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

st.title("🏈 DFS Football Optimizer")
st.caption("DraftKings NFL Classic analytics and lineup optimization")

st.markdown(
    """
    Welcome to the DFS Football Optimizer.

    Use the navigation menu in the sidebar to import player pools,
    manage saved slates, and generate optimized lineups.
    """
)

metric_column_1, metric_column_2, metric_column_3 = st.columns(3)

metric_column_1.metric(
    "Saved slates",
    len(saved_slates),
)

if "player_pool" in st.session_state:
    loaded_player_count = len(st.session_state.player_pool)
else:
    loaded_player_count = 0

metric_column_2.metric(
    "Players currently loaded",
    loaded_player_count,
)

if "active_slate_name" in st.session_state:
    active_slate_name = st.session_state.active_slate_name
else:
    active_slate_name = "None"

metric_column_3.metric(
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
    """
)

st.info(
    "Begin on the **Player Pool** page, or open **Saved Slates** to load a "
    "player pool already stored in the database."
)