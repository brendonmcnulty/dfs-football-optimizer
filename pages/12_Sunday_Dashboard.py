from __future__ import annotations

import pandas as pd
import streamlit as st

from database import DatabaseManager
from services import PlayerPoolService, SlateDashboardService


st.set_page_config(page_title="Sunday Dashboard", page_icon="🏟️", layout="wide")
st.title("🏟️ Sunday Dashboard")
st.caption("One-page slate research, stack rankings, portfolio status, and simulation takeaways.")

database = DatabaseManager()
service = SlateDashboardService()
player_pool_service = PlayerPoolService()
slates = database.list_slates()

source_options = (
    ["Active player pool"]
    if player_pool_service.has_active_pool(st.session_state)
    else []
)
if not slates.empty:
    source_options.append("Saved slate")
if not source_options:
    st.warning("Load a player pool or save a slate before opening the dashboard.")
    st.stop()

source = st.radio("Data source", source_options, horizontal=True)
selected_slate_id = None
active_metadata = player_pool_service.get_metadata(st.session_state)
selected_slate_name = active_metadata.active_slate_name

if source == "Active player pool":
    player_pool = player_pool_service.get_active_pool(st.session_state)
    selected_slate_id = active_metadata.active_slate_id
else:
    slate_options = {
        f"#{int(row['id'])} — {int(row['season'])} Week {int(row['week'])} — {row['slate_name']}": int(row["id"])
        for _, row in slates.iterrows()
    }
    label = st.selectbox("Slate", list(slate_options.keys()))
    selected_slate_id = slate_options[label]
    selected_slate_name = label
    player_pool = database.load_player_pool(selected_slate_id)

try:
    dashboard = service.build(player_pool)
except ValueError as error:
    st.error(str(error))
    st.stop()

st.subheader(str(selected_slate_name))
metrics = st.columns(6)
metrics[0].metric("Players", f"{dashboard.overview['player_count']:,}")
metrics[1].metric("Games", f"{dashboard.overview['game_count']:,}")
metrics[2].metric("Avg projection", f"{dashboard.overview['average_projection']:.1f}")
metrics[3].metric(
    "Avg game total",
    "—" if dashboard.overview["average_game_total"] is None else f"{dashboard.overview['average_game_total']:.1f}",
)
metrics[4].metric(
    "Top team total",
    "—" if dashboard.overview["highest_team_total"] is None else f"{dashboard.overview['highest_team_total']:.1f}",
)
metrics[5].metric("Avg confidence", f"{dashboard.overview['data_confidence']:.0f}")

if dashboard.alerts:
    st.subheader("Action center")
    for alert in dashboard.alerts:
        st.warning(alert)

left, right = st.columns(2)
with left:
    st.subheader("Best values")
    st.dataframe(dashboard.top_values, hide_index=True, width="stretch")
with right:
    st.subheader("Ceiling leaders")
    st.dataframe(dashboard.ceiling_leaders, hide_index=True, width="stretch")

left, right = st.columns(2)
with left:
    st.subheader("Leverage targets")
    st.dataframe(dashboard.leverage_plays, hide_index=True, width="stretch")
with right:
    st.subheader("Potential ownership fades")
    st.caption("High ownership combined with weaker point-per-dollar value. This is a research flag, not an automatic exclusion.")
    st.dataframe(dashboard.fades, hide_index=True, width="stretch")

st.subheader("Game environments")
st.dataframe(dashboard.game_environment, hide_index=True, width="stretch")

st.subheader("Stack rankings")
st.caption("Stack score combines ceiling, projection, implied team total, and an ownership penalty.")
st.dataframe(
    dashboard.stack_rankings,
    hide_index=True,
    width="stretch",
    column_config={
        "salary": st.column_config.NumberColumn("Salary", format="$%d"),
        "projection": st.column_config.NumberColumn("Projection", format="%.2f"),
        "ceiling": st.column_config.NumberColumn("Ceiling", format="%.2f"),
        "combined_ownership": st.column_config.NumberColumn("Ownership", format="%.1f%%"),
        "team_implied_total": st.column_config.NumberColumn("Team total", format="%.1f"),
        "stack_score": st.column_config.NumberColumn("Stack score", format="%.2f"),
    },
)

st.subheader("Portfolio health")
if selected_slate_id is None:
    st.info("Save the active slate and its lineups to unlock portfolio analysis.")
else:
    saved_lineups = database.list_lineups(slate_id=int(selected_slate_id))
    if saved_lineups.empty:
        st.info("No saved lineups exist for this slate yet.")
    else:
        lineup_frames: list[pd.DataFrame] = []
        duplicate_keys: dict[tuple[str, ...], list[str]] = {}
        for _, lineup_row in saved_lineups.iterrows():
            lineup = database.load_lineup_players(int(lineup_row["id"]))
            lineup_frames.append(lineup)
            key = tuple(sorted(lineup["player_id"].astype(str)))
            duplicate_keys.setdefault(key, []).append(str(lineup_row["lineup_name"]))

        all_players = pd.concat(lineup_frames, ignore_index=True)
        exposure = (
            all_players.groupby(["player_id", "name", "position", "team"], as_index=False)
            .size().rename(columns={"size": "lineup_count"})
        )
        exposure["exposure"] = exposure["lineup_count"] / len(lineup_frames)
        exposure = exposure.sort_values(["exposure", "name"], ascending=[False, True])
        duplicates = [names for names in duplicate_keys.values() if len(names) > 1]

        portfolio_metrics = st.columns(4)
        portfolio_metrics[0].metric("Saved lineups", len(lineup_frames))
        portfolio_metrics[1].metric("Unique players used", all_players["player_id"].nunique())
        portfolio_metrics[2].metric("Duplicate groups", len(duplicates))
        portfolio_metrics[3].metric("Highest exposure", f"{exposure['exposure'].max():.0%}")
        st.dataframe(exposure.head(30), hide_index=True, width="stretch")
        if duplicates:
            st.error("Duplicate lineup groups: " + "; ".join(", ".join(group) for group in duplicates))

st.subheader("Latest simulation takeaways")
simulation = st.session_state.get("simulation_result")
simulation_slate_id = st.session_state.get("simulation_slate_id")
if simulation is None or (selected_slate_id is not None and simulation_slate_id != selected_slate_id):
    st.info("Run Simulation Lab for this slate to display upside and portfolio-first rankings here.")
else:
    summary = simulation.lineup_summary.copy()
    best_median = summary.nlargest(1, "median").iloc[0]
    best_upside = summary.nlargest(1, "p90").iloc[0]
    best_first = summary.nlargest(1, "portfolio_first_rate").iloc[0]
    sim_metrics = st.columns(3)
    sim_metrics[0].metric("Best median", str(best_median["lineup_name"]), f"{best_median['median']:.1f} pts")
    sim_metrics[1].metric("Best 90th percentile", str(best_upside["lineup_name"]), f"{best_upside['p90']:.1f} pts")
    sim_metrics[2].metric("Best portfolio-first", str(best_first["lineup_name"]), f"{best_first['portfolio_first_rate']:.1%}")
    st.dataframe(summary.head(20), hide_index=True, width="stretch")

csv_data = dashboard.stack_rankings.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download stack rankings",
    data=csv_data,
    file_name="sunday_dashboard_stack_rankings.csv",
    mime="text/csv",
)
