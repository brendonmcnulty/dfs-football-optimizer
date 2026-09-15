from __future__ import annotations

import pandas as pd
import streamlit as st

from database import DatabaseManager
from services.contest_results_service import ContestResultsService


st.set_page_config(page_title="Week Results", page_icon="🏁", layout="wide")

database = DatabaseManager()
service = ContestResultsService(database.database_path)
repo = database.contest_results_repository

st.title("🏁 Week Results & Portfolio Tracking")
st.caption(
    "Import the raw DraftKings contest-standings ZIP after a slate. Reserved entry IDs saved "
    "with the slate are matched automatically. For older slates, upload that week's DKEntries.csv. "
    "Contest Entry History remains optional when you want exact winnings/cash-rate data."
)

slates = database.list_slates()
if slates.empty:
    st.warning("Save the slate to the database before importing contest results.")
    st.stop()

slates = slates.sort_values(["season", "week", "id"], ascending=[False, False, False])
slate_options = slates["id"].astype(int).tolist()
slate_lookup = slates.set_index("id").to_dict("index")

selected_slate_id = st.selectbox(
    "Saved slate",
    slate_options,
    format_func=lambda value: (
        f"{slate_lookup[value]['season']} Week {slate_lookup[value]['week']} — "
        f"{slate_lookup[value]['slate_name']} (slate #{value})"
    ),
)

standings_file = st.file_uploader(
    "DraftKings contest standings ZIP",
    type=["zip"],
    help="Use the ZIP downloaded from DraftKings GameCenter / Standings.",
)
dk_entries_file = st.file_uploader(
    "DraftKings DKEntries.csv (only needed for older slates)",
    type=["csv"],
    help="Use the DKEntries.csv from this slate if its reserved entry IDs were not previously saved in the database.",
)
history_file = st.file_uploader(
    "DraftKings Contest Entry History CSV (optional finance detail)",
    type=["csv"],
    help="Optional. Supplies exact winnings and places-paid information for ROI/cash-rate reporting.",
)

if st.button(
    "Import Week Results",
    type="primary",
    use_container_width=True,
    disabled=standings_file is None,
):
    try:
        contest_id, counts = service.import_results(
            standings_zip=standings_file.getvalue(),
            slate_id=int(selected_slate_id),
            entry_history_csv=history_file.getvalue() if history_file else None,
            dk_entries_csv=dk_entries_file.getvalue() if dk_entries_file else None,
            dk_entries_name=dk_entries_file.name if dk_entries_file else "DKEntries.csv",
        )
        st.session_state["last_results_contest_id"] = int(contest_id)
        # Refresh warehouse immediately so actuals appear there too.
        database.warehouse_repository.sync_slate(int(selected_slate_id))
        source_label = {"entry_history": "Entry History", "reserved_entries": "saved/DKEntries IDs", "none": "no personal-entry source"}.get(counts.get("identification_source"), "unknown source")
        st.success(
            f"Imported contest {contest_id:,}: {counts['standings']:,} standings, "
            f"{counts['players']:,} player results, and {counts['user_entries']:,} of your entries "
            f"matched via {source_label}."
        )
    except Exception as exc:
        st.error(f"Could not import DraftKings results: {exc}")

contest_id = st.session_state.get("last_results_contest_id")
if contest_id is None:
    st.info("Import a contest to see the post-slate report.")
    st.stop()

summary = repo.contest_summary(int(contest_id))
if summary.empty:
    st.stop()
row = summary.iloc[0]

st.subheader("Portfolio results")
entries = repo.user_entries(int(contest_id))
metrics = st.columns(7)
metrics[0].metric("Contest", f"{int(row['contest_id'])}")
metrics[1].metric("Field", f"{int(row['field_size']):,}")
metrics[2].metric("Your entries", f"{int(row['user_entries']):,}")
metrics[3].metric("Entry fees", f"${float(row['entry_fees']):.2f}")
finance_complete = (not entries.empty) and bool((entries["places_paid"] > 0).any()) if "entries" in locals() else False
metrics[4].metric("Winnings", f"${float(row['winnings']):.2f}" if finance_complete else "—")
roi = ((float(row['winnings']) - float(row['entry_fees'])) / float(row['entry_fees'])) if finance_complete and float(row['entry_fees']) else None
metrics[5].metric("ROI", f"{roi:.1%}" if roi is not None else "—")
metrics[6].metric("Best finish", f"{int(row['best_finish']):,}" if int(row['best_finish']) else "—")

if str(row.get("contest_name", "")):
    st.caption(str(row["contest_name"]))

if not entries.empty:
    finance_complete = bool((entries["places_paid"] > 0).any())
    cash_rate = (entries["place"] <= entries["places_paid"]).mean() if finance_complete else None
    c1, c2, c3 = st.columns(3)
    c1.metric("Cash rate", f"{cash_rate:.1%}" if cash_rate is not None else "—")
    c2.metric("Average score", f"{entries['points'].mean():.2f}")
    c3.metric("Best score", f"{entries['points'].max():.2f}")
    st.dataframe(entries, hide_index=True, width="stretch")
    st.download_button(
        "Download my contest results CSV",
        entries.to_csv(index=False).encode("utf-8"),
        file_name=f"contest_{contest_id}_my_results.csv",
        mime="text/csv",
        use_container_width=True,
    )
else:
    st.info(
        "No personal entries were matched. For an older slate, upload that slate's DKEntries.csv and re-import. "
        "Future slates save reserved entry IDs automatically when you save the slate."
    )

st.subheader("Projection & ownership review")
comparison = repo.player_comparison(int(contest_id), int(selected_slate_id))
if comparison.empty:
    st.warning("No player results matched the saved slate.")
else:
    evaluated = comparison.dropna(subset=["actual_points"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Matched players", f"{len(evaluated):,}")
    m2.metric("Projection MAE", f"{(evaluated['actual_points'] - evaluated['projection']).abs().mean():.2f}")
    m3.metric("Projection bias", f"{(evaluated['projection'] - evaluated['actual_points']).mean():+.2f}")
    ownership_rows = evaluated.dropna(subset=["actual_ownership", "projected_ownership"])
    m4.metric(
        "Ownership MAE",
        f"{(ownership_rows['actual_ownership'] - ownership_rows['projected_ownership']).abs().mean():.2f} pts"
        if not ownership_rows.empty else "—",
    )
    st.dataframe(
        comparison,
        hide_index=True,
        width="stretch",
        column_config={
            "projected_ownership": st.column_config.NumberColumn(format="%.1f%%"),
            "actual_ownership": st.column_config.NumberColumn(format="%.1f%%"),
            "ownership_delta": st.column_config.NumberColumn(format="%+.1f"),
            "projection_delta": st.column_config.NumberColumn(format="%+.2f"),
        },
    )
    st.download_button(
        "Download projection vs actual CSV",
        comparison.to_csv(index=False).encode("utf-8"),
        file_name=f"contest_{contest_id}_projection_review.csv",
        mime="text/csv",
        use_container_width=True,
    )


st.subheader("Unmatched player audit")
unmatched = repo.unmatched_player_results(int(contest_id), int(selected_slate_id))
if unmatched.empty:
    st.success("Every DraftKings player result matched a player in the saved slate.")
else:
    st.caption(
        f"{len(unmatched):,} DraftKings player result(s) did not match the saved slate. "
        "These are retained for audit instead of being silently discarded."
    )
    st.dataframe(unmatched, hide_index=True, width="stretch")
    st.download_button(
        "Download unmatched-player audit CSV",
        unmatched.to_csv(index=False).encode("utf-8"),
        file_name=f"contest_{contest_id}_unmatched_players.csv",
        mime="text/csv",
        use_container_width=True,
    )
