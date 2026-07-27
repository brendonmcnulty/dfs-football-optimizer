from __future__ import annotations

import pandas as pd
import streamlit as st

from database import DatabaseManager


st.set_page_config(
    page_title="Historical DFS Warehouse",
    page_icon="🏛️",
    layout="wide",
)


def _percent(value: float) -> str:
    return "0%" if pd.isna(value) else f"{value:.0%}"


database = DatabaseManager()
warehouse = database.warehouse_repository

st.title("🏛️ Historical DFS Warehouse")
st.caption(
    "Create one durable player-week dataset across every saved slate. The "
    "warehouse preserves projections, actual results, Vegas context, and "
    "reserved fields for usage, weather, and injury data added later."
)

summary = warehouse.summary()
summary_row = summary.iloc[0] if not summary.empty else pd.Series(dtype="object")

with st.sidebar:
    st.header("Warehouse actions")
    if st.button("Sync all saved slates", type="primary", use_container_width=True):
        try:
            slate_count, player_count = warehouse.sync_all_slates()
            st.success(
                f"Synced {player_count:,} player rows from {slate_count:,} saved slates."
            )
            st.rerun()
        except Exception as exc:
            st.error(f"Warehouse sync failed: {exc}")

    st.caption(
        "Sync is safe to run repeatedly. Existing player-week rows are updated "
        "instead of duplicated."
    )

if summary.empty or int(summary_row.get("player_weeks", 0) or 0) == 0:
    st.info(
        "The warehouse is empty. Save at least one slate, then click "
        "**Sync all saved slates**."
    )
    st.stop()

metrics = st.columns(6)
metrics[0].metric("Player-weeks", f"{int(summary_row['player_weeks']):,}")
metrics[1].metric("Slates", f"{int(summary_row['slates']):,}")
metrics[2].metric("Seasons", f"{int(summary_row['seasons']):,}")
metrics[3].metric("Unique players", f"{int(summary_row['unique_players']):,}")
metrics[4].metric(
    "Actual-result coverage",
    _percent(float(summary_row["actual_result_rows"]) / float(summary_row["player_weeks"])),
)
metrics[5].metric(
    "Vegas coverage",
    _percent(float(summary_row["vegas_rows"]) / float(summary_row["player_weeks"])),
)

st.caption(f"Last synchronized: {summary_row.get('last_synced_at') or 'Never'}")

coverage = warehouse.coverage_by_season()
with st.expander("Data coverage by season and week", expanded=False):
    display_coverage = coverage.copy()
    if not display_coverage.empty:
        display_coverage["Actual coverage"] = (
            display_coverage["actual_rows"] / display_coverage["player_weeks"]
        )
        display_coverage["Vegas coverage"] = (
            display_coverage["vegas_rows"] / display_coverage["player_weeks"]
        )
        display_coverage["Usage coverage"] = (
            display_coverage["usage_rows"] / display_coverage["player_weeks"]
        )
        st.dataframe(
            display_coverage,
            hide_index=True,
            width="stretch",
            column_config={
                "Actual coverage": st.column_config.ProgressColumn(
                    format="percent", min_value=0.0, max_value=1.0
                ),
                "Vegas coverage": st.column_config.ProgressColumn(
                    format="percent", min_value=0.0, max_value=1.0
                ),
                "Usage coverage": st.column_config.ProgressColumn(
                    format="percent", min_value=0.0, max_value=1.0
                ),
            },
        )

st.subheader("Research query")
filters = warehouse.available_filters()

filter_columns = st.columns(4)
with filter_columns[0]:
    selected_seasons = st.multiselect(
        "Season", filters["seasons"], default=filters["seasons"]
    )
with filter_columns[1]:
    selected_weeks = st.multiselect("Week", filters["weeks"])
with filter_columns[2]:
    selected_positions = st.multiselect("Position", filters["positions"])
with filter_columns[3]:
    selected_teams = st.multiselect("Team", filters["teams"])

salary_columns = st.columns([1, 1, 1])
with salary_columns[0]:
    minimum_salary = st.number_input(
        "Minimum salary", min_value=0, max_value=20000, value=0, step=100
    )
with salary_columns[1]:
    maximum_salary = st.number_input(
        "Maximum salary", min_value=0, max_value=20000, value=20000, step=100
    )
with salary_columns[2]:
    actuals_only = st.checkbox("Only rows with actual results", value=False)

rows = warehouse.load_rows(
    seasons=[int(value) for value in selected_seasons] or None,
    weeks=[int(value) for value in selected_weeks] or None,
    positions=[str(value) for value in selected_positions] or None,
    teams=[str(value) for value in selected_teams] or None,
    minimum_salary=int(minimum_salary),
    maximum_salary=int(maximum_salary),
    actuals_only=actuals_only,
)

st.metric("Matching player-weeks", f"{len(rows):,}")

if rows.empty:
    st.warning("No warehouse rows match the selected filters.")
    st.stop()

analysis_rows = rows.copy()
analysis_rows["value"] = (
    analysis_rows["projection"] / analysis_rows["salary"].replace(0, pd.NA) * 1000
)
analysis_rows["actual_value"] = (
    analysis_rows["actual_points"] / analysis_rows["salary"].replace(0, pd.NA) * 1000
)
analysis_rows["projection_error"] = (
    analysis_rows["projection"] - analysis_rows["actual_points"]
)

if analysis_rows["actual_points"].notna().any():
    evaluated = analysis_rows.dropna(subset=["actual_points"])
    evaluation_metrics = st.columns(5)
    evaluation_metrics[0].metric("Evaluated rows", f"{len(evaluated):,}")
    evaluation_metrics[1].metric(
        "Average actual DK points", f"{evaluated['actual_points'].mean():.2f}"
    )
    evaluation_metrics[2].metric(
        "Projection MAE", f"{evaluated['projection_error'].abs().mean():.2f}"
    )
    evaluation_metrics[3].metric(
        "Average actual value", f"{evaluated['actual_value'].mean():.2f}x"
    )
    boom_rate = (evaluated["actual_value"] >= 4.0).mean()
    evaluation_metrics[4].metric("4x value rate", f"{boom_rate:.1%}")

st.dataframe(
    analysis_rows,
    hide_index=True,
    width="stretch",
    column_config={
        "ownership": st.column_config.NumberColumn(format="%.1f%%"),
        "confidence": st.column_config.NumberColumn(format="%.0f"),
        "value": st.column_config.NumberColumn(format="%.2fx"),
        "actual_value": st.column_config.NumberColumn(format="%.2fx"),
    },
)

st.download_button(
    "Download filtered warehouse CSV",
    analysis_rows.to_csv(index=False).encode("utf-8"),
    file_name="dfs_historical_warehouse.csv",
    mime="text/csv",
    use_container_width=True,
)

st.info(
    "Usage, weather, and injury columns are intentionally present even when "
    "empty. Future data connectors will populate these same warehouse rows, "
    "so the backtester and projection model can measure whether each new feature helps."
)
