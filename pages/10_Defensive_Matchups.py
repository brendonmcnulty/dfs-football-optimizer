from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from services import DefensiveMatchupService


st.set_page_config(
    page_title="Defensive Matchups",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ Defensive Matchups")
st.caption(
    "Leak-free rolling DraftKings PPR points allowed by defense and position. "
    "Higher ratings indicate more favorable offensive matchups."
)

current_year = datetime.now().year
with st.sidebar:
    season = st.number_input(
        "NFL season",
        min_value=2000,
        max_value=current_year + 1,
        value=int(st.session_state.get("season", current_year)),
        step=1,
    )
    week = st.number_input(
        "Projecting week",
        min_value=1,
        max_value=22,
        value=int(st.session_state.get("week", 1)),
        step=1,
    )
    lookback = st.selectbox(
        "Completed weeks to average",
        options=[3, 4, 6, 8, 12],
        index=2,
    )

fetch_clicked = st.button(
    "Build defensive matchup ratings",
    type="primary",
    use_container_width=True,
)

if fetch_clicked:
    try:
        result = DefensiveMatchupService().summarize_for_week(
            season=int(season),
            week=int(week),
            lookback_weeks=int(lookback),
        )
        st.session_state.defensive_matchup_result = result
        st.session_state.defensive_matchup_signature = (
            int(season), int(week), int(lookback)
        )
    except Exception as exc:
        st.error(f"Could not build defensive matchup ratings: {exc}")

result = st.session_state.get("defensive_matchup_result")
signature = st.session_state.get("defensive_matchup_signature")
if result is None or signature != (int(season), int(week), int(lookback)):
    st.info("Choose a season, week, and lookback, then build the ratings.")
    st.stop()

ratings = result.ratings.copy()
if ratings.empty:
    st.warning("No completed prior weeks were available for the selected week.")
    st.stop()

m1, m2, m3 = st.columns(3)
m1.metric("Defenses rated", ratings["defense"].nunique())
m2.metric("Position ratings", len(ratings))
m3.metric("Weeks used", len(result.weeks_used))
st.caption(
    "Completed weeks used: "
    + ", ".join(str(value) for value in result.weeks_used)
)

position_tabs = st.tabs(["QB", "RB", "WR", "TE", "All ratings"])
for tab, position in zip(position_tabs[:4], ["QB", "RB", "WR", "TE"]):
    with tab:
        position_frame = ratings.loc[ratings["position"].eq(position)].copy()
        position_frame["rank"] = range(1, len(position_frame) + 1)
        st.dataframe(
            position_frame[
                [
                    "rank",
                    "defense",
                    "matchup_rating",
                    "matchup_label",
                    "fantasy_points_allowed",
                    "matchup_games",
                ]
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "rank": st.column_config.NumberColumn("Rank", format="%d"),
                "defense": "Opponent defense",
                "matchup_rating": st.column_config.NumberColumn(
                    "Rating", format="%.1f"
                ),
                "fantasy_points_allowed": st.column_config.NumberColumn(
                    "DK PPR allowed/game", format="%.2f"
                ),
                "matchup_games": st.column_config.NumberColumn(
                    "Games", format="%d"
                ),
            },
        )

with position_tabs[4]:
    st.dataframe(ratings, width="stretch", hide_index=True)

st.download_button(
    "Download matchup ratings CSV",
    data=ratings.to_csv(index=False).encode("utf-8"),
    file_name=f"{int(season)}_week_{int(week)}_defensive_matchups.csv",
    mime="text/csv",
    use_container_width=True,
)
