from __future__ import annotations

import pandas as pd
import streamlit as st

from database import DatabaseManager
from services import SimulationService


st.set_page_config(
    page_title="Simulation Lab",
    page_icon="🎲",
    layout="wide",
)

st.title("🎲 Simulation Lab")
st.caption(
    "Run correlated Monte Carlo simulations for saved lineups and compare "
    "their upside, downside, and portfolio performance."
)

st.info(
    "Portfolio first-place rate means first among the lineups selected here. "
    "It is not a literal GPP win probability because the contest field is not "
    "being simulated."
)

database = DatabaseManager()
service = SimulationService()
slates = database.list_slates()

if slates.empty:
    st.warning("Save a slate and at least one lineup before using simulations.")
    st.stop()

slate_options = {
    (
        f"#{int(row['id'])} — {int(row['season'])} Week {int(row['week'])} "
        f"— {row['site']} {row['slate_name']}"
    ): int(row["id"])
    for _, row in slates.iterrows()
}
selected_slate_label = st.selectbox(
    "Slate",
    options=list(slate_options.keys()),
)
selected_slate_id = slate_options[selected_slate_label]

saved_lineups = database.list_lineups(slate_id=selected_slate_id)
player_pool = database.load_player_pool(selected_slate_id)

if saved_lineups.empty:
    st.warning("This slate does not have any saved lineups.")
    st.stop()
if player_pool.empty:
    st.warning("This slate does not have a saved player pool.")
    st.stop()

lineup_labels = {
    int(row["id"]): (
        f"#{int(row['id'])} — {row['lineup_name']} "
        f"({float(row['total_projection']):.2f} projected)"
    )
    for _, row in saved_lineups.iterrows()
}

selected_lineup_ids = st.multiselect(
    "Lineups to simulate",
    options=list(lineup_labels.keys()),
    default=list(lineup_labels.keys()),
    format_func=lambda lineup_id: lineup_labels[lineup_id],
)

settings_column_1, settings_column_2, settings_column_3 = st.columns(3)
with settings_column_1:
    simulation_count = st.number_input(
        "Simulations",
        min_value=500,
        max_value=100_000,
        value=10_000,
        step=500,
    )
with settings_column_2:
    target_score = st.number_input(
        "Target score",
        min_value=0.0,
        max_value=400.0,
        value=180.0,
        step=5.0,
        help="Used to estimate how often each lineup reaches your chosen score.",
    )
with settings_column_3:
    random_seed = st.number_input(
        "Random seed",
        min_value=0,
        max_value=2_147_483_647,
        value=42,
        step=1,
        help="Keep this fixed for reproducible results.",
    )

if not selected_lineup_ids:
    st.warning("Select at least one lineup.")
    st.stop()

if st.button("Run simulations", type="primary", use_container_width=True):
    lineups: dict[int, pd.DataFrame] = {}
    lineup_names: dict[int, str] = {}

    for lineup_id in selected_lineup_ids:
        lineups[int(lineup_id)] = database.load_lineup_players(int(lineup_id))
        lineup_names[int(lineup_id)] = str(
            saved_lineups.loc[
                saved_lineups["id"] == int(lineup_id), "lineup_name"
            ].iloc[0]
        )

    try:
        with st.spinner("Simulating correlated player and lineup outcomes..."):
            result = service.run_portfolio_simulation(
                player_pool=player_pool,
                lineups=lineups,
                lineup_names=lineup_names,
                simulation_count=int(simulation_count),
                target_score=float(target_score),
                random_seed=int(random_seed),
            )
    except ValueError as error:
        st.error(str(error))
        st.stop()

    st.session_state["simulation_result"] = result
    st.session_state["simulation_slate_id"] = selected_slate_id

result = st.session_state.get("simulation_result")
result_slate_id = st.session_state.get("simulation_slate_id")

if result is None or result_slate_id != selected_slate_id:
    st.stop()

summary = result.lineup_summary.copy()
best = summary.iloc[0]

metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("Simulations", f"{result.simulation_count:,}")
metric_2.metric("Top simulated lineup", str(best["lineup_name"]))
metric_3.metric("Best first-place rate", f"{best['portfolio_first_rate']:.1%}")
metric_4.metric(
    f"Best {result.target_score:.0f}+ rate",
    f"{summary['target_hit_rate'].max():.1%}",
)

st.subheader("Lineup simulation results")
st.dataframe(
    summary,
    width="stretch",
    hide_index=True,
    column_config={
        "lineup_id": st.column_config.NumberColumn("ID", format="%d"),
        "lineup_name": st.column_config.TextColumn("Lineup"),
        "projected_points": st.column_config.NumberColumn("Projection", format="%.2f"),
        "simulated_mean": st.column_config.NumberColumn("Sim mean", format="%.2f"),
        "median": st.column_config.NumberColumn("Median", format="%.2f"),
        "p10": st.column_config.NumberColumn("10th pct", format="%.2f"),
        "p75": st.column_config.NumberColumn("75th pct", format="%.2f"),
        "p90": st.column_config.NumberColumn("90th pct", format="%.2f"),
        "p95": st.column_config.NumberColumn("95th pct", format="%.2f"),
        "portfolio_first_rate": st.column_config.NumberColumn(
            "Portfolio first", format="%.1%%"
        ),
        "portfolio_top_20_rate": st.column_config.NumberColumn(
            "Portfolio top 20%", format="%.1%%"
        ),
        "target_hit_rate": st.column_config.NumberColumn(
            f"{result.target_score:.0f}+ rate", format="%.1%%"
        ),
        "average_portfolio_rank": st.column_config.NumberColumn(
            "Avg rank", format="%.2f"
        ),
    },
)

chart_data = summary.set_index("lineup_name")[["p10", "median", "p90"]]
st.subheader("Outcome range by lineup")
st.bar_chart(chart_data)

st.subheader("Player outcome distributions")
st.dataframe(
    result.player_summary,
    width="stretch",
    hide_index=True,
    column_config={
        "projection": st.column_config.NumberColumn("Projection", format="%.2f"),
        "floor": st.column_config.NumberColumn("Floor", format="%.2f"),
        "ceiling": st.column_config.NumberColumn("Ceiling", format="%.2f"),
        "simulation_stdev": st.column_config.NumberColumn("Sim SD", format="%.2f"),
        "simulated_mean": st.column_config.NumberColumn("Sim mean", format="%.2f"),
        "p10": st.column_config.NumberColumn("10th pct", format="%.2f"),
        "p50": st.column_config.NumberColumn("Median", format="%.2f"),
        "p90": st.column_config.NumberColumn("90th pct", format="%.2f"),
        "ceiling_hit_rate": st.column_config.NumberColumn(
            "Ceiling hit", format="%.1%%"
        ),
    },
)

summary_csv = summary.to_csv(index=False).encode("utf-8")
scores_csv = result.lineup_scores.to_csv(index=False).encode("utf-8")
player_csv = result.player_summary.to_csv(index=False).encode("utf-8")

download_1, download_2, download_3 = st.columns(3)
with download_1:
    st.download_button(
        "Download lineup summary",
        data=summary_csv,
        file_name="simulation_lineup_summary.csv",
        mime="text/csv",
        use_container_width=True,
    )
with download_2:
    st.download_button(
        "Download simulation scores",
        data=scores_csv,
        file_name="simulation_lineup_scores.csv",
        mime="text/csv",
        use_container_width=True,
    )
with download_3:
    st.download_button(
        "Download player distributions",
        data=player_csv,
        file_name="simulation_player_distributions.csv",
        mime="text/csv",
        use_container_width=True,
    )
