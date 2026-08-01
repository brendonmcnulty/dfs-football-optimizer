from __future__ import annotations

import importlib
from pathlib import Path

import pandas as pd
import streamlit as st

from database import DatabaseManager
from services import PlayerPoolService, SlateAnalysisService


st.set_page_config(
    page_title="Developer Diagnostics",
    page_icon="🛠️",
    layout="wide",
)

st.title("🛠️ Developer Diagnostics")
st.caption(
    "Check project health, inspect data coverage, and load a fully populated "
    "sample slate for offseason testing."
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_SAMPLE_PATH = PROJECT_ROOT / "data" / "sample" / "sample_players.csv"
ENRICHED_SAMPLE_PATH = (
    PROJECT_ROOT / "data" / "sample" / "enriched_sample_players.csv"
)
DATABASE_PATH = PROJECT_ROOT / "data" / "dfs_optimizer.db"
player_pool_service = PlayerPoolService()


def status_row(
    name: str,
    healthy: bool,
    detail: str,
) -> dict[str, object]:
    return {
        "Check": name,
        "Status": "PASS" if healthy else "FAIL",
        "Detail": detail,
    }


def test_import(module_name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(module_name)
    except Exception as error:  # noqa: BLE001 - diagnostics should report everything
        return False, f"{type(error).__name__}: {error}"
    return True, "Import successful"


st.subheader("Project health")
health_rows: list[dict[str, object]] = []

for module_name in (
    "services",
    "optimizer.lineup_optimizer",
    "projection_engine.engine",
    "database",
):
    healthy, detail = test_import(module_name)
    health_rows.append(
        status_row(
            f"Import {module_name}",
            healthy,
            detail,
        )
    )

health_rows.append(
    status_row(
        "Original sample pool",
        ORIGINAL_SAMPLE_PATH.exists(),
        str(ORIGINAL_SAMPLE_PATH),
    )
)
health_rows.append(
    status_row(
        "Enriched sample pool",
        ENRICHED_SAMPLE_PATH.exists(),
        str(ENRICHED_SAMPLE_PATH),
    )
)

try:
    database = DatabaseManager()
    with database.connect() as connection:
        connection.execute("SELECT 1").fetchone()
    database_ok = True
    database_detail = str(database.database_path)
except Exception as error:  # noqa: BLE001
    database = None
    database_ok = False
    database_detail = f"{type(error).__name__}: {error}"

health_rows.append(
    status_row(
        "SQLite database",
        database_ok,
        database_detail,
    )
)

health_frame = pd.DataFrame(health_rows)
st.dataframe(
    health_frame,
    hide_index=True,
    width="stretch",
    column_config={
        "Status": st.column_config.TextColumn("Status"),
    },
)

passed_checks = int((health_frame["Status"] == "PASS").sum())
metric_columns = st.columns(3)
metric_columns[0].metric("Checks passed", f"{passed_checks}/{len(health_frame)}")
metric_columns[1].metric(
    "Database file",
    "Present" if DATABASE_PATH.exists() else "Created on demand",
)
active_metadata = player_pool_service.get_metadata(st.session_state)
metric_columns[2].metric(
    "Active player pool",
    active_metadata.player_count,
)

st.markdown("---")
st.subheader("Offseason test fixtures")
st.write(
    "The enriched fixture contains illustrative ceiling, floor, ownership, "
    "Vegas, usage, matchup, and confidence fields. It is for software testing "
    "only and is not a real projection set."
)

fixture_columns = st.columns(2)

with fixture_columns[0]:
    if st.button(
        "Load original sample pool",
        use_container_width=True,
    ):
        if not ORIGINAL_SAMPLE_PATH.exists():
            st.error("The original sample CSV is missing.")
        else:
            players = pd.read_csv(ORIGINAL_SAMPLE_PATH)
            if "ceiling" not in players.columns:
                players["ceiling"] = players["projection"]
            if "floor" not in players.columns:
                players["floor"] = players["projection"]
            if "ownership" not in players.columns:
                players["ownership"] = 0.0
            if "confidence" not in players.columns:
                players["confidence"] = 0.0
            players["locked"] = False
            players["excluded"] = False
            player_pool_service.set_active_pool(
                st.session_state,
                players,
                source="Original sample fixture",
                active_slate_name="Original Sample Player Pool",
            )
            st.success("Original sample pool loaded into the active session.")
            st.rerun()

with fixture_columns[1]:
    if st.button(
        "Load enriched sample slate",
        type="primary",
        use_container_width=True,
    ):
        if not ENRICHED_SAMPLE_PATH.exists():
            st.error("The enriched sample CSV is missing.")
        else:
            players = pd.read_csv(ENRICHED_SAMPLE_PATH)
            players["locked"] = players["locked"].fillna(False).astype(bool)
            players["excluded"] = players["excluded"].fillna(False).astype(bool)
            player_pool_service.set_active_pool(
                st.session_state,
                players,
                source="Enriched offseason fixture",
                active_slate_name="Enriched Offseason Test Slate",
            )
            st.success(
                "Enriched sample slate loaded. You can now test Player Pool, "
                "Optimizer, Sunday Dashboard, and DFS Coach."
            )
            st.rerun()

active_pool = player_pool_service.get_active_pool(st.session_state)

if active_pool.empty:
    st.info("Load one of the sample pools above to inspect data coverage.")
    st.stop()

players = active_pool.copy()

st.markdown("---")
st.subheader("Active player-pool coverage")

coverage_frame = player_pool_service.build_coverage_report(players)
st.dataframe(
    coverage_frame,
    hide_index=True,
    width="stretch",
    column_config={
        "Coverage": st.column_config.ProgressColumn(
            "Coverage",
            min_value=0.0,
            max_value=1.0,
            format="%.0f%%",
        ),
    },
)

st.subheader("Active player-pool metadata")
metadata = player_pool_service.get_metadata(st.session_state)
metadata_columns = st.columns(4)
metadata_columns[0].metric("Source", metadata.source)
metadata_columns[1].metric("Revision", metadata.revision)
metadata_columns[2].metric("Season / Week", f"{metadata.season or '-'} / {metadata.week or '-'}")
metadata_columns[3].metric("Loaded", metadata.loaded_at if metadata.loaded_at != "Unknown" else "Unknown")

st.subheader("Slate Analysis smoke test")
if st.button(
    "Run SlateAnalysisService smoke test",
    use_container_width=True,
):
    try:
        result = SlateAnalysisService().analyze(players)
    except Exception as error:  # noqa: BLE001
        st.error(
            "Slate analysis failed: "
            f"{type(error).__name__}: {error}"
        )
    else:
        st.session_state["diagnostic_slate_analysis"] = result
        st.success("SlateAnalysisService completed successfully.")

result = st.session_state.get("diagnostic_slate_analysis")
if result is not None:
    overview = result.overview
    overview_columns = st.columns(4)
    overview_columns[0].metric("Players analyzed", overview["player_count"])
    overview_columns[1].metric("Games identified", overview["game_count"])
    overview_columns[2].metric(
        "Average projection",
        f"{overview['average_projection']:.2f}",
    )
    overview_columns[3].metric(
        "Top stack score",
        "—"
        if overview["top_stack_score"] is None
        else f"{overview['top_stack_score']:.2f}",
    )

    if result.alerts:
        st.warning(" | ".join(result.alerts))

    st.write("**Top value plays**")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Player": item.name,
                    "Position": item.position,
                    "Team": item.team,
                    "Projection": item.projection,
                    "Value": item.value,
                    "Recommendation": item.recommendation,
                }
                for item in result.best_value_plays[:10]
            ]
        ),
        hide_index=True,
        width="stretch",
    )

st.caption(
    "Simulation Lab still requires saved lineups. Load the enriched fixture, "
    "generate and save lineups, then open Simulation Lab."
)
