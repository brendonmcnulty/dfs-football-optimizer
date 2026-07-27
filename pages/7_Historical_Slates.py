from __future__ import annotations

from datetime import datetime
import re

import pandas as pd
import streamlit as st

from data_pipeline import DataSourceInput, WeeklyDataPipeline
from database import DatabaseManager


st.set_page_config(page_title="Historical Slates", page_icon="📚", layout="wide")

ACTUAL_ALIASES = [
    "actual_points", "Actual Points", "actual", "Actual", "FPTS",
    "FantasyPoints", "Fantasy Points", "DKFP", "DraftKings Points",
]
NAME_ALIASES = ["name", "Name", "player", "Player", "player_name", "Player Name"]
ID_ALIASES = ["player_id", "Player ID", "ID", "Id", "id"]
TEAM_ALIASES = ["team", "Team", "TeamAbbrev", "team_abbrev"]


def _find(columns: list[str], aliases: list[str]) -> str | None:
    return next((alias for alias in aliases if alias in columns), None)


def _name_key(value: object) -> str:
    text = re.sub(r"\s+\(\d+\)$", "", str(value).strip())
    text = re.sub(r"[^a-zA-Z0-9 ]+", " ", text)
    return " ".join(text.lower().split())


def _normalize_actuals(frame: pd.DataFrame, pool: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = list(frame.columns)
    actual_col = _find(columns, ACTUAL_ALIASES)
    name_col = _find(columns, NAME_ALIASES)
    id_col = _find(columns, ID_ALIASES)
    team_col = _find(columns, TEAM_ALIASES)

    if actual_col is None:
        raise ValueError(
            "Results CSV must contain an actual fantasy-points column such as "
            "Actual Points, FPTS, DKFP, or Fantasy Points."
        )
    if name_col is None and id_col is None:
        raise ValueError("Results CSV must contain a player name or player ID column.")

    source = pd.DataFrame(index=frame.index)
    source["source_player_id"] = frame[id_col].astype(str).str.strip() if id_col else ""
    source["source_name"] = frame[name_col].astype(str).str.strip() if name_col else ""
    source["source_team"] = frame[team_col].astype(str).str.upper().str.strip() if team_col else ""
    source["actual_points"] = pd.to_numeric(frame[actual_col], errors="coerce")
    source["name_key"] = source["source_name"].map(_name_key)

    base = pool.copy().reset_index(drop=True)
    base["id_key"] = base["player_id"].astype(str).str.strip()
    base["name_key"] = base["name"].map(_name_key)
    base["team_key"] = base["team"].astype(str).str.upper().str.strip()

    matched: list[dict] = []
    unmatched: list[dict] = []
    for _, row in source.iterrows():
        candidates = pd.DataFrame()
        method = ""
        if row["source_player_id"]:
            candidates = base.loc[base["id_key"] == row["source_player_id"]]
            method = "player_id"
        if len(candidates) != 1 and row["name_key"] and row["source_team"]:
            candidates = base.loc[
                (base["name_key"] == row["name_key"])
                & (base["team_key"] == row["source_team"])
            ]
            method = "name_team"
        if len(candidates) != 1 and row["name_key"]:
            candidates = base.loc[base["name_key"] == row["name_key"]]
            method = "unique_name"

        if len(candidates) == 1 and pd.notna(row["actual_points"]):
            player = candidates.iloc[0]
            matched.append({
                "player_id": str(player["player_id"]),
                "name": str(player["name"]),
                "team": str(player["team"]),
                "actual_points": float(row["actual_points"]),
                "match_method": method,
            })
        else:
            unmatched.append({
                "source_player_id": row["source_player_id"],
                "source_name": row["source_name"],
                "source_team": row["source_team"],
                "actual_points": row["actual_points"],
            })

    return pd.DataFrame(matched), pd.DataFrame(unmatched)


def _accuracy_summary(evaluation: pd.DataFrame) -> dict[str, float]:
    errors = evaluation["projection"] - evaluation["actual_points"]
    result = {
        "players": float(len(evaluation)),
        "mae": float(errors.abs().mean()),
        "rmse": float((errors.pow(2).mean()) ** 0.5),
        "bias": float(errors.mean()),
        "correlation": float(evaluation["projection"].corr(evaluation["actual_points"])),
        "inside_range": float(
            ((evaluation["actual_points"] >= evaluation["floor"])
             & (evaluation["actual_points"] <= evaluation["ceiling"])).mean()
        ),
    }
    return result


database = DatabaseManager()
pipeline = WeeklyDataPipeline()

st.title("📚 Historical Slate Manager")
st.caption(
    "Import real past salary slates and actual DraftKings results, reload them "
    "for optimizer testing, and measure projection accuracy."
)

with st.sidebar:
    st.header("Historical slate")
    current_year = datetime.now().year
    season = st.number_input("Season", min_value=2000, max_value=current_year, value=current_year - 1)
    week = st.number_input("Week", min_value=1, max_value=22, value=1)
    slate_name = st.text_input("Slate name", value="Main")
    site = "DraftKings"

st.subheader("1. Import a historical slate")
salary_file = st.file_uploader("Historical DraftKings salary CSV", type=["csv"], key="hist_salary")
projection_file = st.file_uploader(
    "Optional historical projection/ownership CSV",
    type=["csv"],
    key="hist_projection",
)
actual_file = st.file_uploader(
    "Optional actual fantasy-results CSV",
    type=["csv"],
    key="hist_actual",
)

if st.button("Build historical slate", type="primary", use_container_width=True):
    if salary_file is None:
        st.error("Upload a historical salary CSV first.")
    else:
        try:
            sources = []
            if projection_file is not None:
                sources.append(DataSourceInput("Historical projections", pd.read_csv(projection_file)))
            result = pipeline.run(pd.read_csv(salary_file), sources, aggregation="mean")
            actuals = pd.DataFrame()
            unmatched = pd.DataFrame()
            if actual_file is not None:
                actuals, unmatched = _normalize_actuals(pd.read_csv(actual_file), result.player_pool)

            st.session_state.historical_pool = result.player_pool
            st.session_state.historical_actuals = actuals
            st.session_state.historical_unmatched = unmatched
            st.success(f"Built a historical pool with {len(result.player_pool)} players.")
        except Exception as exc:
            st.error(f"Historical import failed: {exc}")

if "historical_pool" in st.session_state:
    pool = st.session_state.historical_pool
    actuals = st.session_state.get("historical_actuals", pd.DataFrame())
    st.dataframe(pool, hide_index=True, width="stretch")

    if not actuals.empty:
        st.metric("Actual-results matches", f"{len(actuals)} / {len(pool)}")
        st.dataframe(actuals, hide_index=True, width="stretch")
        unmatched = st.session_state.get("historical_unmatched", pd.DataFrame())
        if not unmatched.empty:
            with st.expander(f"Unmatched result rows ({len(unmatched)})"):
                st.dataframe(unmatched, hide_index=True, width="stretch")

    save_col, activate_col = st.columns(2)
    with save_col:
        if st.button("Save historical slate", use_container_width=True):
            slate_id = database.save_slate(int(season), int(week), site, slate_name)
            player_count = database.save_player_pool(slate_id, pool)
            actual_count = 0
            if not actuals.empty:
                actual_count = database.save_historical_results(slate_id, actuals)
            st.session_state.historical_selected_slate_id = slate_id
            st.success(f"Saved {player_count} players and {actual_count} actual results.")
    with activate_col:
        if st.button("Use imported slate as active player pool", use_container_width=True):
            st.session_state.player_pool = pool.copy()
            st.session_state.season = int(season)
            st.session_state.week = int(week)
            st.session_state.site = site
            st.session_state.slate_name = slate_name
            st.session_state.active_slate_name = f"{season} Week {week} — {site} {slate_name}"
            st.success("Historical player pool is now active. Open Optimizer to test it.")

st.markdown("---")
st.subheader("2. Load and evaluate saved historical slates")
slates = database.list_slates()
if slates.empty:
    st.info("No saved slates are available yet.")
else:
    labels = {
        f"{int(row.season)} Week {int(row.week)} — {row.site} {row.slate_name}": int(row.id)
        for _, row in slates.iterrows()
    }
    selected_label = st.selectbox("Saved slate", list(labels))
    selected_id = labels[selected_label]
    saved_pool = database.load_player_pool(selected_id)
    saved_results = database.load_historical_results(selected_id)

    m1, m2, m3 = st.columns(3)
    m1.metric("Players", len(saved_pool))
    m2.metric("Actual results", len(saved_results))
    m3.metric("Results coverage", f"{len(saved_results) / len(saved_pool):.0%}" if len(saved_pool) else "0%")

    load_col, evaluate_col = st.columns(2)
    with load_col:
        if st.button("Load saved historical slate into optimizer", use_container_width=True):
            st.session_state.player_pool = saved_pool.copy()
            st.session_state.active_slate_id = selected_id
            st.session_state.active_slate_name = selected_label
            st.success("Historical slate loaded into the active player pool.")
    with evaluate_col:
        show_evaluation = st.button("Evaluate projections", use_container_width=True)

    if show_evaluation:
        evaluation = database.load_historical_evaluation(selected_id)
        if evaluation.empty:
            st.warning("This slate does not have matched actual results yet.")
        else:
            summary = _accuracy_summary(evaluation)
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("MAE", f"{summary['mae']:.2f}")
            c2.metric("RMSE", f"{summary['rmse']:.2f}")
            c3.metric("Bias", f"{summary['bias']:+.2f}")
            corr = summary["correlation"]
            c4.metric("Correlation", "N/A" if pd.isna(corr) else f"{corr:.3f}")
            c5.metric("Inside floor/ceiling", f"{summary['inside_range']:.0%}")

            evaluation["error"] = evaluation["projection"] - evaluation["actual_points"]
            evaluation["absolute_error"] = evaluation["error"].abs()
            st.dataframe(evaluation, hide_index=True, width="stretch")
            st.download_button(
                "Download evaluation CSV",
                evaluation.to_csv(index=False).encode("utf-8"),
                file_name=f"historical_evaluation_{selected_id}.csv",
                mime="text/csv",
                use_container_width=True,
            )
