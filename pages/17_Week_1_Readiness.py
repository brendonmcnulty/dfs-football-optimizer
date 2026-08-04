from __future__ import annotations

import pandas as pd
import streamlit as st

from services import WeekOneReadinessService


st.set_page_config(
    page_title="Week 1 Readiness",
    page_icon="✅",
    layout="wide",
)

st.title("✅ Week 1 Readiness Center")
st.caption(
    "One pre-lock checklist for DraftKings data, projections, portfolio health, "
    "and upload readiness."
)

service = WeekOneReadinessService()
report = service.assess(st.session_state)

status_icon = {
    "READY FOR UPLOAD": "🟢",
    "READY WITH WARNINGS": "🟡",
    "NOT READY": "🔴",
}.get(report.overall_status, "⚪")

headline_columns = st.columns(4)
headline_columns[0].metric(
    "Overall status",
    f"{status_icon} {report.overall_status}",
)
headline_columns[1].metric(
    "Critical failures",
    report.critical_failures,
)
headline_columns[2].metric(
    "Warnings",
    report.warnings,
)
headline_columns[3].metric(
    "Portfolio lineups",
    report.portfolio.lineup_count if report.portfolio else 0,
)

st.markdown("---")
st.subheader("Pre-lock checklist")

check_frame = pd.DataFrame(
    [
        {
            "Category": check.category,
            "Status": check.status,
            "Check": check.label,
            "Detail": check.detail,
        }
        for check in report.checks
    ]
)

st.dataframe(
    check_frame,
    width="stretch",
    hide_index=True,
    column_config={
        "Category": st.column_config.TextColumn("Category"),
        "Status": st.column_config.TextColumn("Status"),
        "Check": st.column_config.TextColumn("Check"),
        "Detail": st.column_config.TextColumn("Detail", width="large"),
    },
)

failed_destinations: list[tuple[str, str]] = []
for check in report.checks:
    if check.status != "PASS" and check.destination:
        pair = (check.destination, check.label)
        if pair not in failed_destinations:
            failed_destinations.append(pair)

if failed_destinations:
    st.write("**Resolve outstanding items:**")
    link_columns = st.columns(min(3, len(failed_destinations)))
    for index, (destination, label) in enumerate(failed_destinations):
        with link_columns[index % len(link_columns)]:
            st.page_link(
                destination,
                label=label,
                use_container_width=True,
            )

if report.portfolio is None:
    st.info(
        "Generate lineups on the Optimizer page to unlock portfolio-health "
        "analysis."
    )
    st.stop()

portfolio = report.portfolio
st.markdown("---")
st.subheader("Portfolio health")

metric_columns = st.columns(6)
metric_columns[0].metric("Lineups", portfolio.lineup_count)
metric_columns[1].metric("Average salary", f"${portfolio.average_salary:,.0f}")
metric_columns[2].metric("Average projection", f"{portfolio.average_projection:.2f}")
metric_columns[3].metric("Average ceiling", f"{portfolio.average_ceiling:.2f}")
metric_columns[4].metric("Average ownership", f"{portfolio.average_ownership:.1f}%")
metric_columns[5].metric("Unique players", portfolio.unique_player_count)

if portfolio.warnings:
    st.warning("Portfolio review found items worth checking:")
    for warning in portfolio.warnings:
        st.write(f"- {warning}")
else:
    st.success("No portfolio-health warnings were detected.")

summary_columns = st.columns(2)
with summary_columns[0]:
    st.write("**Salary and lineup distribution**")
    st.dataframe(
        portfolio.salary_distribution,
        width="stretch",
        hide_index=True,
        column_config={
            "salary": st.column_config.NumberColumn("Salary", format="$%d"),
            "salary_remaining": st.column_config.NumberColumn("Remaining", format="$%d"),
            "projection": st.column_config.NumberColumn("Projection", format="%.2f"),
            "ceiling": st.column_config.NumberColumn("Ceiling", format="%.2f"),
            "ownership": st.column_config.NumberColumn("Ownership", format="%.1f%%"),
        },
    )

with summary_columns[1]:
    st.write("**QB stack and bring-back summary**")
    st.dataframe(
        portfolio.stack_summary,
        width="stretch",
        hide_index=True,
    )

exposure_tabs = st.tabs(
    ["Player exposure", "QB exposure", "Team exposure", "Game exposure"]
)

with exposure_tabs[0]:
    st.dataframe(
        portfolio.player_exposure,
        width="stretch",
        hide_index=True,
        column_config={
            "exposure": st.column_config.ProgressColumn(
                "Exposure", min_value=0.0, max_value=1.0, format="%.0%%"
            )
        },
    )

with exposure_tabs[1]:
    st.dataframe(
        portfolio.qb_exposure,
        width="stretch",
        hide_index=True,
        column_config={
            "exposure": st.column_config.ProgressColumn(
                "Exposure", min_value=0.0, max_value=1.0, format="%.0%%"
            )
        },
    )

with exposure_tabs[2]:
    st.dataframe(
        portfolio.team_exposure,
        width="stretch",
        hide_index=True,
        column_config={
            "exposure": st.column_config.ProgressColumn(
                "Exposure", min_value=0.0, max_value=1.0, format="%.0%%"
            )
        },
    )

with exposure_tabs[3]:
    st.dataframe(
        portfolio.game_exposure,
        width="stretch",
        hide_index=True,
        column_config={
            "exposure": st.column_config.ProgressColumn(
                "Exposure", min_value=0.0, max_value=1.0, format="%.0%%"
            )
        },
    )

st.markdown("---")
if report.overall_status == "READY FOR UPLOAD":
    st.success(
        "The active slate has passed the current Week 1 readiness checks. "
        "Review the completed DraftKings file on the confirmation screen before "
        "accepting the upload."
    )
elif report.overall_status == "READY WITH WARNINGS":
    st.warning(
        "The slate has no blocking failures, but review the warnings before upload."
    )
else:
    st.error(
        "The slate is not ready for upload. Resolve the critical failures shown above."
    )
