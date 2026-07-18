from __future__ import annotations

import streamlit as st

from database import DatabaseManager


st.set_page_config(
    page_title="Saved Slates",
    page_icon="💾",
    layout="wide",
)

database = DatabaseManager()

st.title("💾 Saved Slates")
st.caption("View and load player pools stored in SQLite")

saved_slates = database.list_slates()

if saved_slates.empty:
    st.info(
        "No saved slates were found. Import and save a player pool from the "
        "**Player Pool** page."
    )
    st.stop()

display_slates = saved_slates.copy()

display_slates["display_name"] = (
    display_slates["season"].astype(str)
    + " Week "
    + display_slates["week"].astype(str)
    + " — "
    + display_slates["site"].astype(str)
    + " "
    + display_slates["slate_name"].astype(str)
)

st.subheader("Available slates")

st.dataframe(
    display_slates[
        [
            "season",
            "week",
            "site",
            "slate_name",
            "created_at",
        ]
    ],
    width="stretch",
    hide_index=True,
    column_config={
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
        "created_at": st.column_config.TextColumn(
            "Created",
        ),
    },
)

slate_options = {
    row["display_name"]: int(row["id"])
    for _, row in display_slates.iterrows()
}

selected_display_name = st.selectbox(
    "Select a slate",
    options=list(slate_options.keys()),
)

selected_slate_id = slate_options[selected_display_name]

selected_row = display_slates.loc[
    display_slates["id"] == selected_slate_id
].iloc[0]

preview_players = database.load_player_pool(selected_slate_id)

st.subheader("Player-pool preview")

if preview_players.empty:
    st.warning("This slate does not contain any saved players.")

else:
    metric_column_1, metric_column_2, metric_column_3 = st.columns(3)

    metric_column_1.metric(
        "Players",
        len(preview_players),
    )

    metric_column_2.metric(
        "Positive projections",
        int((preview_players["projection"] > 0).sum()),
    )

    metric_column_3.metric(
        "Total salary pool",
        f"${int(preview_players['salary'].sum()):,}",
    )

    st.dataframe(
        preview_players[
            [
                "name",
                "position",
                "team",
                "opponent",
                "salary",
                "projection",
                "locked",
                "excluded",
            ]
        ],
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
            "locked": st.column_config.CheckboxColumn(
                "Locked",
            ),
            "excluded": st.column_config.CheckboxColumn(
                "Excluded",
            ),
        },
    )

load_clicked = st.button(
    "Load selected slate",
    type="primary",
    use_container_width=True,
    disabled=preview_players.empty,
)

if load_clicked:
    st.session_state.player_pool = preview_players.copy()
    st.session_state.active_slate_id = selected_slate_id

    st.session_state.season = int(selected_row["season"])
    st.session_state.week = int(selected_row["week"])
    st.session_state.site = str(selected_row["site"])
    st.session_state.slate_name = str(selected_row["slate_name"])

    st.session_state.active_slate_name = selected_display_name

    st.success(
        f"Loaded {len(preview_players)} players from "
        f"{selected_display_name}."
    )

    st.info(
        "Open the **Player Pool** page to edit the players or the "
        "**Optimizer** page to generate a lineup."
    )