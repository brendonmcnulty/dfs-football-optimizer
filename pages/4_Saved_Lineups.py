from __future__ import annotations

import streamlit as st

from database import DatabaseManager


st.set_page_config(
    page_title="Saved Lineups",
    page_icon="📋",
    layout="wide",
)

database = DatabaseManager()

st.title("📋 Saved Lineups")
st.caption("Review and export lineups stored in SQLite")

saved_lineups = database.list_lineups()

if saved_lineups.empty:
    st.info(
        "No saved lineups were found. Generate and save a lineup from the "
        "**Optimizer** page."
    )
    st.stop()

display_lineups = saved_lineups.copy()

display_lineups["slate_display"] = (
    display_lineups["season"].astype(str)
    + " Week "
    + display_lineups["week"].astype(str)
    + " — "
    + display_lineups["site"].astype(str)
    + " "
    + display_lineups["slate_name"].astype(str)
)

display_lineups["lineup_display"] = (
    "#"
    + display_lineups["id"].astype(str)
    + " — "
    + display_lineups["lineup_name"].astype(str)
    + " — "
    + display_lineups["slate_display"].astype(str)
)

st.subheader("Lineup history")

metric_column_1, metric_column_2, metric_column_3 = st.columns(3)

metric_column_1.metric(
    "Saved lineups",
    len(display_lineups),
)

metric_column_2.metric(
    "Saved slates represented",
    int(display_lineups["slate_id"].nunique()),
)

average_projection = float(
    display_lineups["total_projection"].mean()
)

metric_column_3.metric(
    "Average projection",
    f"{average_projection:.2f}",
)

st.dataframe(
    display_lineups[
        [
            "id",
            "lineup_name",
            "season",
            "week",
            "site",
            "slate_name",
            "total_salary",
            "total_projection",
            "solver_status",
            "created_at",
        ]
    ],
    width="stretch",
    hide_index=True,
    column_config={
        "id": st.column_config.NumberColumn(
            "Lineup ID",
            format="%d",
        ),
        "lineup_name": st.column_config.TextColumn(
            "Lineup name",
        ),
        "season": st.column_config.NumberColumn(
            "Season",
            format="%d",
        ),
        "week": st.column_config.NumberColumn(
            "Week",
            format="%d",
        ),
        "site": st.column_config.TextColumn(
            "Site",
        ),
        "slate_name": st.column_config.TextColumn(
            "Slate",
        ),
        "total_salary": st.column_config.NumberColumn(
            "Salary",
            format="$%d",
        ),
        "total_projection": st.column_config.NumberColumn(
            "Projection",
            format="%.2f",
        ),
        "solver_status": st.column_config.TextColumn(
            "Status",
        ),
        "created_at": st.column_config.TextColumn(
            "Created",
        ),
    },
)

st.markdown("---")

lineup_options = {
    row["lineup_display"]: int(row["id"])
    for _, row in display_lineups.iterrows()
}

selected_lineup_display = st.selectbox(
    "Select a lineup to review",
    options=list(lineup_options.keys()),
)

selected_lineup_id = lineup_options[selected_lineup_display]

selected_lineup = display_lineups.loc[
    display_lineups["id"] == selected_lineup_id
].iloc[0]

lineup_players = database.load_lineup_players(
    selected_lineup_id
)

st.subheader("Selected lineup")

st.write(f"**{selected_lineup['lineup_name']}**")
st.caption(selected_lineup["slate_display"])

total_projection = float(
    selected_lineup["total_projection"]
)

total_salary = int(
    selected_lineup["total_salary"]
)

salary_cap = int(
    selected_lineup["salary_cap"]
)

salary_remaining = salary_cap - total_salary

metric_column_1, metric_column_2, metric_column_3 = st.columns(3)

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
    f"${salary_remaining:,}",
)

if lineup_players.empty:
    st.warning(
        "No player records were found for the selected lineup."
    )
    st.stop()

st.dataframe(
    lineup_players[
        [
            "roster_slot",
            "name",
            "position",
            "team",
            "opponent",
            "salary",
            "projection",
        ]
    ],
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

export = lineup_players[
    [
        "roster_slot",
        "player_id",
        "name",
        "position",
        "team",
        "salary",
    ]
].copy()

safe_lineup_name = "".join(
    character
    if character.isalnum() or character in {"-", "_"}
    else "_"
    for character in str(selected_lineup["lineup_name"])
)

download_filename = (
    f"{safe_lineup_name}_lineup_{selected_lineup_id}.csv"
)

st.download_button(
    "Download selected lineup CSV",
    data=export.to_csv(index=False).encode("utf-8"),
    file_name=download_filename,
    mime="text/csv",
)