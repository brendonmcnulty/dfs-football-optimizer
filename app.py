from __future__ import annotations

import pandas as pd
import streamlit as st

from config import SALARY_CAP
from data_loader import merge_projections, normalize_player_pool
from optimizer.lineup_optimizer import optimize_lineup


st.set_page_config(
    page_title="DFS Football Optimizer",
    page_icon="🏈",
    layout="wide",
)

st.title("🏈 DFS Football Optimizer")
st.caption("Phase 1 — DraftKings NFL Classic lineup optimization")

with st.sidebar:
    st.header("Slate settings")
    salary_cap = st.number_input(
        "Salary cap",
        min_value=1,
        value=SALARY_CAP,
        step=500,
    )
    minimum_salary = st.number_input(
        "Minimum salary to use",
        min_value=0,
        max_value=int(salary_cap),
        value=0,
        step=100,
    )

    st.markdown("---")
    st.write(
        "Upload one combined CSV containing projections, or upload a "
        "DraftKings salary CSV and a separate projection CSV."
    )

salary_file = st.file_uploader(
    "Upload salary/player-pool CSV",
    type=["csv"],
)

projection_file = st.file_uploader(
    "Optional: upload separate projection CSV",
    type=["csv"],
)

if salary_file is None:
    st.info(
        "Upload a player-pool CSV to begin. A sample file is included in "
        "`data/sample/sample_players.csv`."
    )
    st.stop()

try:
    raw_players = pd.read_csv(salary_file)
    players = normalize_player_pool(raw_players)

    if projection_file is not None:
        raw_projections = pd.read_csv(projection_file)
        players = merge_projections(players, raw_projections)
except Exception as exc:
    st.error(f"Could not read the uploaded file: {exc}")
    st.stop()

st.subheader("Player pool")
st.write(
    "Edit projections directly. Check **locked** to force a player into the "
    "lineup or **excluded** to remove a player."
)

edited_players = st.data_editor(
    players,
    width="stretch",
    hide_index=True,
    disabled=[
        "player_id",
        "name",
        "position",
        "team",
        "opponent",
        "salary",
    ],
    column_config={
        "projection": st.column_config.NumberColumn(
            "Projection",
            min_value=0.0,
            step=0.1,
            format="%.2f",
        ),
        "salary": st.column_config.NumberColumn(
            "Salary",
            format="$%d",
        ),
        "locked": st.column_config.CheckboxColumn("Lock"),
        "excluded": st.column_config.CheckboxColumn("Exclude"),
    },
)

valid_projection_count = int((edited_players["projection"] > 0).sum())
st.caption(
    f"{len(edited_players)} players loaded · "
    f"{valid_projection_count} have projections above zero"
)

if st.button("Generate optimal lineup", type="primary"):
    try:
        result = optimize_lineup(
            edited_players,
            salary_cap=int(salary_cap),
            minimum_salary=int(minimum_salary),
        )
    except Exception as exc:
        st.error(f"Optimizer error: {exc}")
        st.stop()

    if result.lineup.empty:
        st.error(
            "No valid lineup was found. Review locks, exclusions, salary "
            f"settings, and available positions. Solver status: {result.status}"
        )
        st.stop()

    st.success(f"Lineup generated — solver status: {result.status}")

    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("Projected points", f"{result.total_projection:.2f}")
    metric2.metric("Salary used", f"${result.total_salary:,}")
    metric3.metric(
        "Salary remaining",
        f"${int(salary_cap) - result.total_salary:,}",
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
        result.lineup[display_columns],
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
        },
    )

    export = result.lineup[
        ["roster_slot", "player_id", "name", "position", "team", "salary"]
    ].copy()

    st.download_button(
        "Download lineup CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name="optimized_lineup.csv",
        mime="text/csv",
    )
