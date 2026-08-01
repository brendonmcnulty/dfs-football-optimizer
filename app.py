from __future__ import annotations

import streamlit as st

from database import DatabaseManager
from services import PlayerPoolService


st.set_page_config(
    page_title="DFS Football Optimizer",
    page_icon="🏈",
    layout="wide",
)

database = DatabaseManager()
player_pool_service = PlayerPoolService()

saved_slates = database.list_slates()
saved_lineups = database.list_lineups()

st.title("🏈 DFS Football Optimizer")
st.caption("DraftKings NFL Classic analytics and lineup optimization")

st.markdown(
    """
    Use the sidebar navigation to import player pools, manage saved slates,
    run weekly data updates, generate optimized lineups, and review saved lineups.
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

active_pool = player_pool_service.get_active_pool(st.session_state)
active_pool_metadata = player_pool_service.get_metadata(st.session_state)
loaded_player_count = len(active_pool)

metric_column_3.metric(
    "Players currently loaded",
    loaded_player_count,
)

active_slate_name = active_pool_metadata.active_slate_name

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

    ### 5. Weekly Update

    Combine the DraftKings salary file with projection providers, live Vegas
    markets, and leak-free prior-week nflverse usage, then generate transparent
    projection, ceiling, floor, and confidence values before activating or
    saving the pool.

    ### 6. Settings

    Store and test local API credentials without committing them to Git.

    ### 7. Historical Slates

    Import past DraftKings slates and actual results and reload them for optimizer
    testing.

    ### 8. Projection Backtester

    Compare saved projections with actual fantasy points, benchmark them against
    a salary-only baseline, and review calibration by position, salary, and
    confidence tier.

    ### 9. Historical DFS Warehouse

    Consolidate saved slates into a research dataset containing projections,
    actual results, Vegas context, and prior-week usage metrics.

    ### 10. Defensive Matchups

    Review leak-free fantasy points allowed and position-specific matchup ratings.

    ### 11. Simulation Lab

    Run correlated Monte Carlo simulations for saved lineup portfolios and compare
    floor, median, upside, target-score probability, and portfolio rank.

    ### 12. Sunday Dashboard

    Review the slate in one place: action alerts, values, ceilings, leverage, game
    environments, stack rankings, portfolio exposure, duplicates, and simulation takeaways.

    ### 13. DFS Coach

    Review explainable player and lineup recommendations showing the strongest
    projection, ceiling, value, ownership, matchup, correlation, and simulation reasons.

    ### 14. Developer Diagnostics

    Check application health, inspect player-data coverage, load an enriched
    offseason test slate, and run a Slate Analysis smoke test.
    """
)

if not player_pool_service.has_active_pool(st.session_state):
    st.info(
        "Begin on the **Player Pool** page, or open **Saved Slates** to load "
        "a player pool already stored in the database."
    )
else:
    st.success(
        f"{loaded_player_count} players are loaded and ready for optimization."
    )