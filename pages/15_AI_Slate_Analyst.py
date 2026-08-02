from __future__ import annotations

from dataclasses import asdict

import pandas as pd
import streamlit as st

from database import DatabaseManager
from services import (
    PlayerPoolService,
    SlateAnalysisService,
    SlateNarrativeService,
)


st.set_page_config(
    page_title="AI Slate Analyst",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 AI Slate Analyst")
st.caption(
    "Deterministic, evidence-backed slate analysis generated from your own "
    "projections, ownership, Vegas, usage, matchup, and stack data."
)

st.info(
    "This page does not call an external language model and does not invent "
    "football news. Every statement is produced from the data currently loaded "
    "in the application."
)

database = DatabaseManager()
player_pool_service = PlayerPoolService()
analysis_service = SlateAnalysisService()
narrative_service = SlateNarrativeService()

slates = database.list_slates()
source_options: list[str] = []

if player_pool_service.has_active_pool(st.session_state):
    source_options.append("Active player pool")

if not slates.empty:
    source_options.append("Saved slate")

if not source_options:
    st.warning(
        "Load an active player pool or save a slate before opening AI Slate Analyst."
    )
    st.stop()

source = st.radio(
    "Data source",
    source_options,
    horizontal=True,
)

if source == "Active player pool":
    player_pool = player_pool_service.get_active_pool(st.session_state)
    metadata = player_pool_service.get_metadata(st.session_state)
    slate_name = metadata.active_slate_name
else:
    slate_options = {
        (
            f"#{int(row['id'])} — {int(row['season'])} Week "
            f"{int(row['week'])} — {row['slate_name']}"
        ): int(row["id"])
        for _, row in slates.iterrows()
    }
    selected_label = st.selectbox(
        "Slate",
        list(slate_options.keys()),
    )
    player_pool = database.load_player_pool(
        slate_options[selected_label]
    )
    slate_name = selected_label

control_columns = st.columns(2)
player_limit = control_columns[0].slider(
    "Players per section",
    min_value=3,
    max_value=10,
    value=5,
)
stack_limit = control_columns[1].slider(
    "Stacks to display",
    min_value=3,
    max_value=10,
    value=5,
)

try:
    analysis = analysis_service.analyze(
        player_pool,
        limit=max(player_limit, stack_limit),
    )
    narrative = narrative_service.build(
        analysis,
        slate_name=slate_name,
        player_limit=player_limit,
        stack_limit=stack_limit,
    )
except ValueError as error:
    st.error(str(error))
    st.stop()

st.subheader(narrative.headline)
st.markdown(narrative.executive_summary)

overview = analysis.overview
metric_columns = st.columns(4)
metric_columns[0].metric(
    "Eligible players",
    int(overview.get("player_count", 0) or 0),
)
metric_columns[1].metric(
    "Games",
    int(overview.get("game_count", 0) or 0),
)
metric_columns[2].metric(
    "Average projection",
    f"{float(overview.get('average_projection', 0.0) or 0.0):.1f}",
)
metric_columns[3].metric(
    "Average confidence",
    f"{float(overview.get('average_confidence', 0.0) or 0.0):.0f}/100",
)

if narrative.alerts:
    st.subheader("Slate risks and data alerts")
    for alert in narrative.alerts:
        st.warning(alert)

for section in narrative.sections:
    st.subheader(section.title)
    st.caption(section.summary)
    for item in section.items:
        st.markdown(f"- {item}")

st.subheader("Why a player?")
player_groups = {
    "Value": analysis.best_value_plays,
    "Tournament": analysis.gpp_core,
    "Cash": analysis.cash_core,
    "Leverage": analysis.leverage_plays,
    "Fades": analysis.fade_candidates,
}

available_groups = {
    name: players
    for name, players in player_groups.items()
    if players
}

if not available_groups:
    st.info("No ranked players are available for an explanation.")
else:
    group_name = st.selectbox(
        "Recommendation group",
        list(available_groups.keys()),
    )
    selected_group = available_groups[group_name]
    player_labels = {
        (
            f"{player.name} — {player.position} {player.team} — "
            f"{player.recommendation}"
        ): player
        for player in selected_group
    }
    selected_label = st.selectbox(
        "Player",
        list(player_labels.keys()),
    )
    selected_player = player_labels[selected_label]
    explanation = narrative_service.explain_player(
        selected_player
    )

    st.markdown(f"### {explanation.title}")
    st.write(explanation.summary)

    player_metrics = st.columns(6)
    player_metrics[0].metric(
        "Projection",
        f"{selected_player.projection:.1f}",
    )
    player_metrics[1].metric(
        "Ceiling",
        f"{selected_player.ceiling:.1f}",
    )
    player_metrics[2].metric(
        "Floor",
        f"{selected_player.floor:.1f}",
    )
    player_metrics[3].metric(
        "Ownership",
        f"{selected_player.ownership:.1f}%",
    )
    player_metrics[4].metric(
        "Value",
        f"{selected_player.value:.2f}",
    )
    player_metrics[5].metric(
        "Matchup",
        f"{selected_player.matchup_rating:.0f}/100",
    )

    for item in explanation.items:
        st.markdown(f"- {item}")

export_rows: list[dict[str, object]] = []
for section in narrative.sections:
    for item_number, item in enumerate(section.items, start=1):
        export_rows.append(
            {
                "slate": slate_name,
                "section": section.title,
                "section_summary": section.summary,
                "item_number": item_number,
                "analysis": item,
            }
        )

export_frame = pd.DataFrame(export_rows)
st.download_button(
    "Download slate analysis",
    data=export_frame.to_csv(index=False).encode("utf-8"),
    file_name="ai_slate_analyst.csv",
    mime="text/csv",
)

with st.expander("Structured analysis details"):
    st.json(asdict(narrative))
