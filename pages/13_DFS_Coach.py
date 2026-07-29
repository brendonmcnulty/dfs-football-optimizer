from __future__ import annotations

import pandas as pd
import streamlit as st

from database import DatabaseManager
from services import DFSCoachService


st.set_page_config(page_title="DFS Coach", page_icon="🧠", layout="wide")
st.title("🧠 DFS Coach")
st.caption("Explainable player and lineup recommendations built from your projections, ownership, Vegas, usage, matchups, and simulations.")

st.info(
    "Coach recommendations are transparent model-based research signals—not guarantees. "
    "Review late news and contest context before submitting lineups."
)

database = DatabaseManager()
service = DFSCoachService()
slates = database.list_slates()

source_options = ["Active player pool"] if "player_pool" in st.session_state else []
if not slates.empty:
    source_options.append("Saved slate")
if not source_options:
    st.warning("Load a player pool or save a slate before opening DFS Coach.")
    st.stop()

source = st.radio("Data source", source_options, horizontal=True)
selected_slate_id = None
selected_slate_name = st.session_state.get("active_slate_name", "Active player pool")

if source == "Active player pool":
    player_pool = st.session_state.player_pool.copy()
    selected_slate_id = st.session_state.get("active_slate_id")
else:
    slate_options = {
        f"#{int(row['id'])} — {int(row['season'])} Week {int(row['week'])} — {row['slate_name']}": int(row["id"])
        for _, row in slates.iterrows()
    }
    selected_label = st.selectbox("Slate", list(slate_options.keys()))
    selected_slate_id = slate_options[selected_label]
    selected_slate_name = selected_label
    player_pool = database.load_player_pool(selected_slate_id)

lineups: list[tuple[str, pd.DataFrame]] = []
if selected_slate_id is not None:
    saved_lineups = database.list_lineups(slate_id=int(selected_slate_id))
    for _, lineup_row in saved_lineups.iterrows():
        lineups.append((
            str(lineup_row["lineup_name"]),
            database.load_lineup_players(int(lineup_row["id"])),
        ))
elif "generated_lineups" in st.session_state:
    metadata = st.session_state.get("generated_lineup_metadata", [])
    for index, lineup in enumerate(st.session_state.generated_lineups, start=1):
        name = f"Lineup {index}"
        if index - 1 < len(metadata):
            name = str(metadata[index - 1].get("lineup_name", name))
        lineups.append((name, lineup.copy()))

simulation_summary = None
simulation = st.session_state.get("simulation_result")
simulation_slate_id = st.session_state.get("simulation_slate_id")
if simulation is not None and (
    selected_slate_id is None or simulation_slate_id == selected_slate_id
):
    simulation_summary = simulation.lineup_summary.copy()

try:
    result = service.build(
        player_pool=player_pool,
        lineups=lineups,
        simulation_summary=simulation_summary,
    )
except ValueError as error:
    st.error(str(error))
    st.stop()

st.subheader(str(selected_slate_name))
for takeaway in result.slate_takeaways:
    st.success(takeaway)

st.subheader("Player coach")
rankings = result.player_rankings.copy()
filter_columns = st.columns(3)
positions = ["All"] + sorted(rankings["position"].dropna().unique().tolist())
position_filter = filter_columns[0].selectbox("Position", positions)
recommendations = ["All"] + sorted(rankings["recommendation"].dropna().unique().tolist())
recommendation_filter = filter_columns[1].selectbox("Recommendation", recommendations)
max_ownership = filter_columns[2].slider("Maximum ownership", 0.0, 100.0, 100.0, 1.0)

filtered = rankings.loc[rankings["ownership"] <= max_ownership].copy()
if position_filter != "All":
    filtered = filtered.loc[filtered["position"] == position_filter]
if recommendation_filter != "All":
    filtered = filtered.loc[filtered["recommendation"] == recommendation_filter]

display_columns = [
    "name", "position", "team", "opponent", "salary", "projection", "ceiling",
    "ownership", "value", "matchup_rating", "confidence", "coach_score", "recommendation",
]
st.dataframe(
    filtered[display_columns],
    hide_index=True,
    width="stretch",
    column_config={
        "salary": st.column_config.NumberColumn("Salary", format="$%d"),
        "projection": st.column_config.NumberColumn("Projection", format="%.2f"),
        "ceiling": st.column_config.NumberColumn("Ceiling", format="%.2f"),
        "ownership": st.column_config.NumberColumn("Ownership", format="%.1f%%"),
        "value": st.column_config.NumberColumn("Value", format="%.2f"),
        "matchup_rating": st.column_config.NumberColumn("Matchup", format="%.0f"),
        "confidence": st.column_config.NumberColumn("Confidence", format="%.0f"),
        "coach_score": st.column_config.NumberColumn("Coach score", format="%.1f"),
    },
)

if not filtered.empty:
    player_labels = {
        f"{row['name']} — {row['position']} {row['team']} — {row['recommendation']}": index
        for index, row in filtered.iterrows()
    }
    selected_player_label = st.selectbox("Explain a player", list(player_labels.keys()))
    player = filtered.loc[player_labels[selected_player_label]]
    st.markdown(f"### {player['name']} — {player['recommendation']}")
    metrics = st.columns(5)
    metrics[0].metric("Projection", f"{player['projection']:.1f}")
    metrics[1].metric("Ceiling", f"{player['ceiling']:.1f}")
    metrics[2].metric("Ownership", f"{player['ownership']:.1f}%")
    metrics[3].metric("Matchup", f"{player['matchup_rating']:.0f}/100")
    metrics[4].metric("Coach score", f"{player['coach_score']:.1f}")
    st.markdown(
        f"- {player['reason_1']}\n"
        f"- {player['reason_2']}\n"
        f"- {player['reason_3']}"
    )

st.subheader("Lineup coach")
if result.lineup_rankings.empty:
    st.info("Generate or save lineups to receive lineup-level coaching.")
else:
    lineup_display = result.lineup_rankings.drop(columns=["summary"], errors="ignore")
    st.dataframe(
        lineup_display,
        hide_index=True,
        width="stretch",
        column_config={
            "salary": st.column_config.NumberColumn("Salary", format="$%d"),
            "projection": st.column_config.NumberColumn("Projection", format="%.2f"),
            "ceiling": st.column_config.NumberColumn("Ceiling", format="%.2f"),
            "ownership": st.column_config.NumberColumn("Ownership", format="%.1f%%"),
            "coach_score": st.column_config.NumberColumn("Coach score", format="%.1f"),
            "portfolio_first_rate": st.column_config.NumberColumn("Portfolio first", format="%.1%%"),
            "top_20_rate": st.column_config.NumberColumn("Top 20%", format="%.1%%"),
            "target_hit_rate": st.column_config.NumberColumn("Target hit", format="%.1%%"),
        },
    )
    lineup_names = result.lineup_rankings["lineup_name"].astype(str).tolist()
    selected_lineup = st.selectbox("Explain a lineup", lineup_names)
    lineup_row = result.lineup_rankings.loc[
        result.lineup_rankings["lineup_name"].astype(str) == selected_lineup
    ].iloc[0]
    st.markdown(f"### {selected_lineup} — {lineup_row['recommendation']}")
    st.write(lineup_row["summary"])
    if simulation_summary is None:
        st.caption("Run Simulation Lab to add simulated median, upside, target-hit, and portfolio-first context.")

st.download_button(
    "Download player coach rankings",
    data=rankings.to_csv(index=False).encode("utf-8"),
    file_name="dfs_coach_player_rankings.csv",
    mime="text/csv",
)
