from __future__ import annotations

import pandas as pd
import streamlit as st

from database import DatabaseManager
from services.projection_backtester import ProjectionBacktester


st.set_page_config(
    page_title="Projection Backtester",
    page_icon="🧪",
    layout="wide",
)


def _slate_label(row: pd.Series) -> str:
    return (
        f"{int(row['season'])} Week {int(row['week'])} — "
        f"{row['site']} {row['slate_name']}"
    )


def _format_metric(value: float, percent: bool = False, signed: bool = False) -> str:
    if pd.isna(value):
        return "N/A"
    if percent:
        return f"{value:.1%}"
    if signed:
        return f"{value:+.2f}"
    return f"{value:.2f}"


database = DatabaseManager()
backtester = ProjectionBacktester()

st.title("🧪 Projection Backtester")
st.caption(
    "Measure projection accuracy against saved historical DraftKings results, "
    "compare the model with a simple salary baseline, and identify calibration "
    "changes worth testing."
)

slates = database.list_slates()
if slates.empty:
    st.info("Save a historical slate with actual results before running a backtest.")
    st.stop()

available: list[tuple[str, int, pd.DataFrame]] = []
for _, row in slates.iterrows():
    slate_id = int(row["id"])
    evaluation = database.load_historical_evaluation(slate_id)
    if not evaluation.empty:
        available.append((_slate_label(row), slate_id, evaluation))

if not available:
    st.info(
        "Historical slates exist, but none has matched actual fantasy results. "
        "Open Historical Slates and import an actual-results CSV first."
    )
    st.stop()

labels = [label for label, _, _ in available]
with st.sidebar:
    st.header("Backtest scope")
    scope = st.radio(
        "Evaluate",
        ["One slate", "All available slates"],
        horizontal=False,
    )
    selected_label = st.selectbox(
        "Historical slate",
        labels,
        disabled=scope == "All available slates",
    )

if scope == "One slate":
    frames = [evaluation for label, _, evaluation in available if label == selected_label]
    scope_name = selected_label
else:
    frames = []
    for label, slate_id, evaluation in available:
        tagged = evaluation.copy()
        tagged["slate"] = label
        tagged["slate_id"] = slate_id
        frames.append(tagged)
    scope_name = f"All historical slates ({len(frames)})"

combined = pd.concat(frames, ignore_index=True)

try:
    result = backtester.evaluate(combined)
except Exception as exc:
    st.error(f"Backtest failed: {exc}")
    st.stop()

st.subheader(scope_name)
overall = result.overall_summary.iloc[0]
metric_columns = st.columns(6)
metric_columns[0].metric("Players", int(overall["Players"]))
metric_columns[1].metric("Model MAE", _format_metric(overall["Model MAE"]))
metric_columns[2].metric(
    "Salary baseline MAE",
    _format_metric(overall["Salary baseline MAE"]),
)
metric_columns[3].metric(
    "MAE improvement",
    _format_metric(overall["MAE improvement"], signed=True),
)
metric_columns[4].metric("RMSE", _format_metric(overall["RMSE"]))
metric_columns[5].metric("Correlation", _format_metric(overall["Correlation"]))

coverage_columns = st.columns(4)
coverage_columns[0].metric("Bias", _format_metric(overall["Bias"], signed=True))
coverage_columns[1].metric(
    "Inside floor/ceiling",
    _format_metric(overall["Inside floor/ceiling"], percent=True),
)
coverage_columns[2].metric(
    "Above ceiling",
    _format_metric(overall["Above ceiling"], percent=True),
)
coverage_columns[3].metric(
    "Model beat baseline",
    _format_metric(overall["Model beat baseline"], percent=True),
)

if overall["MAE improvement"] > 0:
    st.success(
        "The current projection beat the salary-only baseline by "
        f"{overall['MAE improvement']:.2f} fantasy points of MAE."
    )
elif overall["MAE improvement"] < 0:
    st.warning(
        "The salary-only baseline beat the current projection by "
        f"{abs(overall['MAE improvement']):.2f} fantasy points of MAE."
    )
else:
    st.info("The current projection and salary baseline produced the same MAE.")

st.markdown("---")
st.subheader("Accuracy by position")
position = result.position_summary.copy()
st.dataframe(position, hide_index=True, width="stretch")
if not position.empty:
    st.bar_chart(position.set_index("position")[["MAE", "Baseline MAE"]])

st.subheader("Calibration recommendations")
st.caption(
    "A positive bias means projections were too high. The suggested adjustment "
    "is a simple starting point for testing—not an automatic model change."
)
st.dataframe(result.calibration_summary, hide_index=True, width="stretch")

left, right = st.columns(2)
with left:
    st.subheader("Accuracy by salary tier")
    st.dataframe(result.salary_summary, hide_index=True, width="stretch")
with right:
    st.subheader("Accuracy by confidence tier")
    st.dataframe(result.confidence_summary, hide_index=True, width="stretch")

st.markdown("---")
st.subheader("Projection vs. actual")
chart_data = result.player_results[["projection", "actual_points"]].rename(
    columns={"projection": "Projection", "actual_points": "Actual points"}
)
st.scatter_chart(chart_data, x="Projection", y="Actual points")

st.subheader("Player-level results")
player_columns = [
    column
    for column in [
        "slate",
        "name",
        "position",
        "team",
        "salary",
        "projection",
        "actual_points",
        "error",
        "absolute_error",
        "salary_baseline",
        "baseline_absolute_error",
        "model_improvement",
        "floor",
        "ceiling",
        "inside_floor_ceiling",
        "confidence",
    ]
    if column in result.player_results.columns
]
player_results = result.player_results[player_columns].sort_values(
    "absolute_error",
    ascending=False,
)
st.dataframe(player_results, hide_index=True, width="stretch")

st.download_button(
    "Download player-level backtest CSV",
    player_results.to_csv(index=False).encode("utf-8"),
    file_name="projection_backtest_players.csv",
    mime="text/csv",
    use_container_width=True,
)
