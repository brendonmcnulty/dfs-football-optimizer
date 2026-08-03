from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core.local_settings import get_odds_api_key
from data_pipeline import DataSourceInput, PipelineResult, WeeklyDataPipeline
from database import DatabaseManager
from projection_engine import ProjectionEngine
from services import (
    DraftKingsContestService,
    DraftKingsExportService,
    PlayerPoolService,
)
from services.odds_api_service import (
    OddsApiService,
    enrich_player_pool_with_vegas,
    filter_games_for_week,
    nfl_week_bounds,
)
from services.defensive_matchup_service import (
    DefensiveMatchupService,
    enrich_player_pool_with_matchups,
)
from services.nflverse_usage_service import (
    NflverseUsageService,
    enrich_player_pool_with_usage,
)


st.set_page_config(page_title="Weekly Update", page_icon="🔄", layout="wide")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PLAYER_PATH = PROJECT_ROOT / "data" / "sample" / "sample_players.csv"
player_pool_service = PlayerPoolService()
draftkings_export_service = DraftKingsExportService()
draftkings_contest_service = DraftKingsContestService(
    draftkings_export_service
)


def _read_csv(uploaded_file) -> pd.DataFrame:
    uploaded_file.seek(0)
    return pd.read_csv(uploaded_file)


def _empty_pipeline_result(player_pool: pd.DataFrame) -> PipelineResult:
    """Wrap an existing normalized pool so it can use the weekly workflow."""
    return PipelineResult(
        player_pool=player_pool.copy().reset_index(drop=True),
        coverage_report=pd.DataFrame(),
        source_report=pd.DataFrame(),
        unmatched_report=pd.DataFrame(),
        duplicate_report=pd.DataFrame(),
    )


def _metadata(
    season: int,
    week: int,
    site: str,
    slate_name: str,
    source_names: list[str],
    aggregation: str,
) -> dict:
    return {
        "season": int(season),
        "week": int(week),
        "site": site,
        "slate_name": slate_name.strip() or "Main",
        "source_names": source_names,
        "aggregation": aggregation,
    }


def _set_pipeline_result(result: PipelineResult, metadata: dict) -> None:
    st.session_state.weekly_pipeline_result = result
    st.session_state.weekly_pipeline_metadata = metadata
    st.session_state.pop("weekly_usage_player_pool", None)
    st.session_state.pop("weekly_usage_match_report", None)
    st.session_state.pop("weekly_usage_unmatched", None)
    st.session_state.pop("weekly_usage_metadata", None)
    st.session_state.pop("weekly_matchup_player_pool", None)
    st.session_state.pop("weekly_matchup_report", None)
    st.session_state.pop("weekly_matchup_unmatched", None)
    st.session_state.pop("weekly_matchup_metadata", None)
    st.session_state.pop("weekly_model_player_pool", None)
    st.session_state.pop("weekly_model_summary", None)


def _clear_stale_odds_state() -> None:
    st.session_state.pop("weekly_odds_result", None)
    st.session_state.pop("weekly_cached_games", None)


database = DatabaseManager()
pipeline = WeeklyDataPipeline()
projection_engine = ProjectionEngine()
usage_service = NflverseUsageService()
matchup_service = DefensiveMatchupService()

st.title("🔄 Weekly Data Update")
st.caption(
    "Build or reuse a player pool, load only the selected NFL week's betting "
    "markets, and generate transparent in-house projections."
)

with st.sidebar:
    st.header("Slate information")
    current_year = datetime.now().year
    season = st.number_input(
        "NFL season",
        min_value=2000,
        max_value=current_year + 1,
        value=int(st.session_state.get("season", current_year)),
        step=1,
    )
    week = st.number_input(
        "NFL week",
        min_value=1,
        max_value=22,
        value=int(st.session_state.get("week", 1)),
        step=1,
    )
    site = st.selectbox("DFS site", options=["DraftKings"])
    slate_name = st.text_input(
        "Slate name",
        value=str(st.session_state.get("slate_name", "Main")),
    )
    st.markdown("---")
    aggregation_label = st.selectbox(
        "Combine matching sources using",
        options=["Average", "Median", "First source"],
    )
    aggregation = {
        "Average": "mean",
        "Median": "median",
        "First source": "first",
    }[aggregation_label]

st.subheader("1. Choose the player-pool foundation")
st.write(
    "For a live slate, upload `DKEntries.csv` from DraftKings Edit Entries. "
    "That single file supplies the reserved entries, contest metadata, "
    "DraftKings player IDs, salaries, and the slate player list."
)

entries_file = st.file_uploader(
    "DraftKings DKEntries.csv",
    type=["csv"],
    key="weekly_entries_file",
    help=(
        "Reserve your contest entries first, then download DKEntries.csv "
        "from DraftKings Edit Entries."
    ),
)

legacy_salary_file = st.file_uploader(
    "Optional fallback: DKSalaries.csv",
    type=["csv"],
    key="weekly_salary_file",
    help=(
        "Use this only when you are researching a slate without reserved "
        "entries. A salary-only file cannot support bulk entry export."
    ),
)

foundation_col_1, foundation_col_2 = st.columns(2)

with foundation_col_1:
    active_pool_available = player_pool_service.has_active_pool(
        st.session_state
    )
    use_active_clicked = st.button(
        "Use current active player pool",
        disabled=not active_pool_available,
        use_container_width=True,
    )

with foundation_col_2:
    load_sample_clicked = st.button(
        "Load included sample player pool",
        disabled=not SAMPLE_PLAYER_PATH.exists(),
        use_container_width=True,
    )

if use_active_clicked:
    result = _empty_pipeline_result(
        player_pool_service.get_active_pool(
            st.session_state
        )
    )
    metadata = _metadata(
        season,
        week,
        site,
        slate_name,
        ["Active player pool"],
        aggregation,
    )
    _set_pipeline_result(
        result,
        metadata,
    )
    st.success(
        f"Loaded {len(result.player_pool)} players from the active pool."
    )

if load_sample_clicked:
    try:
        result = pipeline.run(
            salary_frame=pd.read_csv(
                SAMPLE_PLAYER_PATH
            ),
            data_sources=[],
            aggregation=aggregation,
        )
        metadata = _metadata(
            season,
            week,
            site,
            slate_name,
            ["Included sample player pool"],
            aggregation,
        )
        _set_pipeline_result(
            result,
            metadata,
        )
        st.success(
            f"Loaded {len(result.player_pool)} sample players."
        )
    except Exception as exc:
        st.error(
            f"Could not load the sample player pool: {exc}"
        )

active_contest_metadata = (
    draftkings_contest_service.get_metadata(
        st.session_state
    )
)

if active_contest_metadata is not None:
    contest_columns = st.columns(4)
    contest_columns[0].metric(
        "Reserved entries",
        active_contest_metadata.entry_count,
    )
    contest_columns[1].metric(
        "Contests",
        active_contest_metadata.contest_count,
    )
    contest_columns[2].metric(
        "DraftKings players",
        active_contest_metadata.player_count,
    )
    contest_columns[3].metric(
        "Source",
        active_contest_metadata.source_name,
    )
    st.success(
        "DraftKings contest context is loaded and will be reused automatically "
        "by DraftKings Export."
    )

st.subheader("2. Optional projection and ownership sources")
st.write("Upload up to three provider CSVs. Players match by ID first, then name and team.")
source_columns = st.columns(3)
source_uploads = []
for index, column in enumerate(source_columns, start=1):
    with column:
        source_name = st.text_input(
            f"Source {index} name",
            value=f"Source {index}",
            key=f"weekly_source_name_{index}",
        )
        source_file = st.file_uploader(
            f"Source {index} CSV",
            type=["csv"],
            key=f"weekly_source_file_{index}",
        )
        source_uploads.append((source_name, source_file))

build_clicked = st.button(
    "Build weekly player pool",
    type="primary",
    use_container_width=True,
)

if build_clicked:
    if entries_file is None and legacy_salary_file is None:
        st.error(
            "Upload DKEntries.csv, upload DKSalaries.csv, or use one of the "
            "existing player-pool buttons above."
        )
    else:
        try:
            sources = [
                DataSourceInput(
                    name=name.strip() or file.name,
                    frame=_read_csv(file),
                )
                for name, file in source_uploads
                if file is not None
            ]

            if entries_file is not None:
                template = (
                    draftkings_contest_service.set_active_contest(
                        st.session_state,
                        entries_file.getvalue(),
                        source_name=entries_file.name,
                    )
                )
                salary_frame = (
                    draftkings_export_service.build_player_pool(
                        template
                    )
                )
                foundation_source = (
                    f"DraftKings entries file: {entries_file.name}"
                )
                detected_slate_name = str(
                    template.entries.iloc[0][
                        "contest_name"
                    ]
                )
            else:
                salary_frame = _read_csv(
                    legacy_salary_file
                )
                foundation_source = (
                    f"DraftKings salary file: "
                    f"{legacy_salary_file.name}"
                )
                detected_slate_name = slate_name

            result = pipeline.run(
                salary_frame=salary_frame,
                data_sources=sources,
                aggregation=aggregation,
            )
            metadata = _metadata(
                season,
                week,
                site,
                (
                    detected_slate_name
                    if entries_file is not None
                    else slate_name
                ),
                [
                    foundation_source,
                    *[
                        source.name
                        for source in sources
                    ],
                ],
                aggregation,
            )
            _set_pipeline_result(
                result,
                metadata,
            )

            player_pool_service.set_active_pool(
                st.session_state,
                result.player_pool,
                source=foundation_source,
                active_slate_name=(
                    detected_slate_name
                    if entries_file is not None
                    else slate_name
                ),
                season=int(season),
                week=int(week),
                site=site,
                slate_name=(
                    detected_slate_name
                    if entries_file is not None
                    else slate_name
                ),
            )

            if entries_file is not None:
                st.success(
                    "DraftKings entries, contest metadata, player IDs, and "
                    "player pool are loaded. The Export page will reuse this "
                    "file automatically."
                )
            else:
                st.success(
                    "Salary-only player pool built. Bulk entry export will "
                    "still require a DKEntries.csv foundation."
                )
        except Exception as exc:
            st.error(
                f"Weekly update failed: {exc}"
            )

if "weekly_pipeline_result" in st.session_state:
    import_result = st.session_state.weekly_pipeline_result

    if not import_result.source_report.empty:
        st.subheader("Projection-source match report")
        st.dataframe(
            import_result.source_report,
            width="stretch",
            hide_index=True,
            column_config={
                "match_rate": st.column_config.ProgressColumn(
                    "Match rate",
                    min_value=0.0,
                    max_value=1.0,
                    format="percent",
                ),
            },
        )

    if not import_result.coverage_report.empty:
        st.subheader("Imported metric coverage")
        st.dataframe(
            import_result.coverage_report,
            width="stretch",
            hide_index=True,
            column_config={
                "coverage": st.column_config.ProgressColumn(
                    "Coverage",
                    min_value=0.0,
                    max_value=1.0,
                    format="percent",
                ),
            },
        )

    if not getattr(import_result, "duplicate_report", pd.DataFrame()).empty:
        st.error(
            "Duplicate rows were found in one or more projection sources. "
            "Those rows were excluded from the merge."
        )
        st.dataframe(
            getattr(import_result, "duplicate_report", pd.DataFrame()),
            width="stretch",
            hide_index=True,
        )
        st.download_button(
            "Download duplicate projection rows",
            data=getattr(import_result, "duplicate_report", pd.DataFrame()).to_csv(
                index=False
            ).encode("utf-8"),
            file_name="projection_duplicate_rows.csv",
            mime="text/csv",
        )

    if not import_result.unmatched_report.empty:
        st.warning(
            f"{len(import_result.unmatched_report)} projection-source row(s) "
            "could not be matched uniquely."
        )
        st.dataframe(
            import_result.unmatched_report,
            width="stretch",
            hide_index=True,
        )
        st.download_button(
            "Download unmatched projection rows",
            data=import_result.unmatched_report.to_csv(
                index=False
            ).encode("utf-8"),
            file_name="projection_unmatched_rows.csv",
            mime="text/csv",
        )

st.markdown("---")
st.subheader("3. Live Vegas data")
week_start, week_end = nfl_week_bounds(int(season), int(week))
st.caption(
    f"Selected Week {int(week)} window: "
    f"{week_start.strftime('%b %d, %Y')} through "
    f"{(week_end - pd.Timedelta(seconds=1)).strftime('%b %d, %Y')} (UTC)."
)
api_key = get_odds_api_key()
if api_key:
    st.caption("The Odds API key is configured. Fetching odds uses plan credits.")
else:
    st.warning("Configure your key on the Settings page before fetching Vegas data.")

fetch_col, cache_col = st.columns(2)
with fetch_col:
    fetch_odds_clicked = st.button(
        "Fetch selected week's NFL odds",
        disabled=not bool(api_key),
        use_container_width=True,
    )
with cache_col:
    load_cached_clicked = st.button(
        "Load cached odds for this week",
        use_container_width=True,
    )

if fetch_odds_clicked:
    try:
        raw_odds_result = OddsApiService(api_key).fetch_nfl_odds()
        filtered_games = filter_games_for_week(
            raw_odds_result.games,
            int(season),
            int(week),
        )
        _clear_stale_odds_state()
        st.session_state.weekly_odds_result = raw_odds_result
        st.session_state.weekly_filtered_odds_games = filtered_games
        st.session_state.weekly_odds_season = int(season)
        st.session_state.weekly_odds_week = int(week)
        saved = database.save_games(
            int(season),
            int(week),
            filtered_games,
            raw_odds_result.fetched_at,
        )
        if saved:
            st.success(
                f"Fetched {len(raw_odds_result.games)} upcoming games and "
                f"cached {saved} for Week {int(week)}."
            )
        else:
            st.warning(
                f"The API returned {len(raw_odds_result.games)} upcoming games, "
                f"but none fell inside the selected Week {int(week)} window."
            )
    except Exception as exc:
        st.error(f"Vegas update failed: {exc}")

if load_cached_clicked:
    cached = database.load_games(int(season), int(week))
    if cached.empty:
        st.warning("No cached Vegas games were found for this season and week.")
    else:
        _clear_stale_odds_state()
        st.session_state.weekly_cached_games = cached
        st.session_state.weekly_cached_season = int(season)
        st.session_state.weekly_cached_week = int(week)
        st.success(f"Loaded {len(cached)} cached Week {int(week)} games.")

odds_games = pd.DataFrame()
odds_meta = None
if (
    "weekly_filtered_odds_games" in st.session_state
    and st.session_state.get("weekly_odds_season") == int(season)
    and st.session_state.get("weekly_odds_week") == int(week)
):
    odds_games = st.session_state.weekly_filtered_odds_games
    odds_meta = st.session_state.get("weekly_odds_result")
elif (
    "weekly_cached_games" in st.session_state
    and st.session_state.get("weekly_cached_season") == int(season)
    and st.session_state.get("weekly_cached_week") == int(week)
):
    odds_games = st.session_state.weekly_cached_games

if not odds_games.empty:
    if odds_meta is not None:
        m1, m2, m3 = st.columns(3)
        m1.metric("Week games", len(odds_games))
        m2.metric("Requests remaining", odds_meta.requests_remaining or "Unknown")
        m3.metric("Last request cost", odds_meta.request_cost or "Unknown")
    st.dataframe(
        odds_games[
            [
                "commence_time",
                "away_team",
                "home_team",
                "home_spread",
                "game_total",
                "away_implied_total",
                "home_implied_total",
                "bookmaker_count",
            ]
        ],
        width="stretch",
        hide_index=True,
    )

if "weekly_pipeline_result" in st.session_state:
    result = st.session_state.weekly_pipeline_result
    metadata = st.session_state.weekly_pipeline_metadata
    player_pool = result.player_pool.copy()
    if not odds_games.empty:
        player_pool = enrich_player_pool_with_vegas(player_pool, odds_games)

    st.markdown("---")
    st.subheader("4. Recent NFL usage data")
    st.write(
        "Download prior-week player statistics from nflverse and summarize a "
        "leak-free rolling window. The selected week's results are never used "
        "to project that same week."
    )
    usage_col_1, usage_col_2 = st.columns([1, 2])
    with usage_col_1:
        usage_lookback = st.selectbox(
            "Completed weeks to average",
            options=[1, 2, 3, 4, 6, 8],
            index=2,
            key="weekly_usage_lookback",
        )
    with usage_col_2:
        st.caption(
            "Available fields include passing attempts, carries, targets, "
            "receptions, yards, and recent PPR fantasy points. Snap and route "
            "data are not included in this first nflverse integration."
        )

    fetch_usage_clicked = st.button(
        "Fetch and merge prior-week usage",
        use_container_width=True,
    )
    if fetch_usage_clicked:
        try:
            usage_result = usage_service.summarize_for_week(
                season=int(season),
                week=int(week),
                lookback_weeks=int(usage_lookback),
            )
            enrichment = enrich_player_pool_with_usage(
                player_pool,
                usage_result.player_usage,
            )
            st.session_state.weekly_usage_player_pool = enrichment.player_pool
            st.session_state.weekly_usage_match_report = enrichment.match_report
            st.session_state.weekly_usage_unmatched = enrichment.unmatched_players
            st.session_state.weekly_usage_metadata = {
                "season": int(season),
                "week": int(week),
                "weeks_used": usage_result.weeks_used,
                "source_rows": usage_result.source_rows,
                "source_url": usage_result.source_url,
            }
            st.session_state.pop("weekly_model_player_pool", None)
            st.session_state.pop("weekly_model_summary", None)
            if usage_result.weeks_used:
                st.success(
                    "Usage merged from completed weeks "
                    + ", ".join(str(value) for value in usage_result.weeks_used)
                    + "."
                )
            else:
                st.warning(
                    "No completed prior weeks were available for this season/week. "
                    "The player pool was left without usage adjustments."
                )
        except Exception as exc:
            st.error(f"NFL usage update failed: {exc}")

    usage_metadata = st.session_state.get("weekly_usage_metadata")
    if (
        "weekly_usage_player_pool" in st.session_state
        and usage_metadata
        and usage_metadata.get("season") == int(season)
        and usage_metadata.get("week") == int(week)
    ):
        player_pool = st.session_state.weekly_usage_player_pool.copy()
        if "weekly_usage_match_report" in st.session_state:
            st.dataframe(
                st.session_state.weekly_usage_match_report,
                width="stretch",
                hide_index=True,
            )
        weeks_used = usage_metadata.get("weeks_used", [])
        if weeks_used:
            st.caption(
                f"Using {usage_metadata.get('source_rows', 0)} nflverse rows "
                f"from weeks {', '.join(str(value) for value in weeks_used)}."
            )
        unmatched_usage = st.session_state.get("weekly_usage_unmatched")
        if isinstance(unmatched_usage, pd.DataFrame) and not unmatched_usage.empty:
            with st.expander(
                f"Review {len(unmatched_usage)} players without a usage match"
            ):
                st.dataframe(unmatched_usage, width="stretch", hide_index=True)

    st.markdown("---")
    st.subheader("5. Defensive matchup ratings")
    st.write(
        "Calculate rolling DraftKings PPR points allowed by each defense to "
        "QB, RB, WR, and TE. Only completed weeks before the selected week are used."
    )
    matchup_col_1, matchup_col_2 = st.columns([1, 2])
    with matchup_col_1:
        matchup_lookback = st.selectbox(
            "Matchup weeks to average",
            options=[3, 4, 6, 8, 12],
            index=2,
            key="weekly_matchup_lookback",
        )
    with matchup_col_2:
        st.caption(
            "A rating near 100 is a favorable matchup because that defense has "
            "allowed more fantasy points to the position. A rating near 0 is tough."
        )

    fetch_matchups_clicked = st.button(
        "Fetch and merge defensive matchups",
        use_container_width=True,
    )
    if fetch_matchups_clicked:
        try:
            matchup_result = matchup_service.summarize_for_week(
                season=int(season),
                week=int(week),
                lookback_weeks=int(matchup_lookback),
            )
            enrichment = enrich_player_pool_with_matchups(
                player_pool,
                matchup_result.ratings,
            )
            st.session_state.weekly_matchup_player_pool = enrichment.player_pool
            st.session_state.weekly_matchup_report = enrichment.match_report
            st.session_state.weekly_matchup_unmatched = enrichment.unmatched_players
            st.session_state.weekly_matchup_metadata = {
                "season": int(season),
                "week": int(week),
                "weeks_used": matchup_result.weeks_used,
                "source_rows": matchup_result.source_rows,
            }
            st.session_state.weekly_defensive_ratings = matchup_result.ratings
            st.session_state.pop("weekly_model_player_pool", None)
            st.session_state.pop("weekly_model_summary", None)
            if matchup_result.weeks_used:
                st.success(
                    "Defensive matchups merged from completed weeks "
                    + ", ".join(str(value) for value in matchup_result.weeks_used)
                    + "."
                )
            else:
                st.warning("No completed prior weeks were available for matchup ratings.")
        except Exception as exc:
            st.error(f"Defensive matchup update failed: {exc}")

    matchup_metadata = st.session_state.get("weekly_matchup_metadata")
    if (
        "weekly_matchup_player_pool" in st.session_state
        and matchup_metadata
        and matchup_metadata.get("season") == int(season)
        and matchup_metadata.get("week") == int(week)
    ):
        player_pool = st.session_state.weekly_matchup_player_pool.copy()
        st.dataframe(
            st.session_state.weekly_matchup_report,
            width="stretch",
            hide_index=True,
        )
        unmatched_matchups = st.session_state.get("weekly_matchup_unmatched")
        if isinstance(unmatched_matchups, pd.DataFrame) and not unmatched_matchups.empty:
            with st.expander(
                f"Review {len(unmatched_matchups)} players without a matchup rating"
            ):
                st.dataframe(unmatched_matchups, width="stretch", hide_index=True)

    st.markdown("---")
    st.subheader("6. In-house projection engine")
    st.write(
        "Generate transparent rule-based projections from imported projections "
        "when available, or a salary baseline when they are not. Vegas, home/away, "
        "spread, recent-usage, and defensive-matchup adjustments are shown separately."
    )
    generate_model_clicked = st.button(
        "Generate in-house projections",
        type="primary",
        use_container_width=True,
    )
    if generate_model_clicked:
        try:
            model_result = projection_engine.project(player_pool)
            st.session_state.weekly_model_player_pool = model_result.player_pool
            st.session_state.weekly_model_summary = model_result.summary
            st.success("In-house projections, ceiling, floor, and confidence are ready.")
        except Exception as exc:
            st.error(f"Projection model failed: {exc}")

    if "weekly_model_player_pool" in st.session_state:
        player_pool = st.session_state.weekly_model_player_pool.copy()
        if "weekly_model_summary" in st.session_state:
            st.dataframe(
                st.session_state.weekly_model_summary,
                width="stretch",
                hide_index=True,
            )

    st.markdown("---")
    st.subheader("Updated player pool")
    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    metric_1.metric("Players", len(player_pool))
    metric_2.metric(
        "Positive projections",
        int((player_pool["projection"] > 0).sum()),
    )
    metric_3.metric(
        "Ownership covered",
        int((player_pool["ownership"] > 0).sum()),
    )
    vegas_covered = (
        int(player_pool["game_total"].notna().sum())
        if "game_total" in player_pool
        else 0
    )
    metric_4.metric("Vegas covered", vegas_covered)

    preview_columns = [
        "name",
        "position",
        "team",
        "opponent",
        "salary",
        "projection",
        "ceiling",
        "floor",
        "confidence",
        "ownership",
        "base_projection",
        "vegas_adjustment",
        "home_adjustment",
        "spread_adjustment",
        "usage_games",
        "passing_attempts",
        "carries",
        "targets",
        "receptions",
        "recent_fantasy_points",
        "usage_opportunity",
        "usage_adjustment",
        "matchup_rating",
        "matchup_label",
        "fantasy_points_allowed",
        "matchup_games",
        "matchup_adjustment",
        "model_adjustment",
        "game_total",
        "team_implied_total",
        "team_spread",
        "is_home",
    ]
    preview_columns = [
        column for column in preview_columns if column in player_pool.columns
    ]
    st.dataframe(
        player_pool[preview_columns],
        width="stretch",
        hide_index=True,
    )

    action_1, action_2, action_3 = st.columns(3)
    with action_1:
        use_clicked = st.button(
            "Use as active player pool",
            type="primary",
            use_container_width=True,
        )
    with action_2:
        save_clicked = st.button(
            "Save slate to database",
            use_container_width=True,
        )
    with action_3:
        st.download_button(
            "Download updated CSV",
            data=player_pool.to_csv(index=False).encode("utf-8"),
            file_name=(
                f"{metadata['season']}_week_{metadata['week']}_"
                f"{metadata['slate_name'].replace(' ', '_').lower()}_updated.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )

    if use_clicked:
        active_name = (
            f"{metadata['season']} Week {metadata['week']} — "
            f"{metadata['site']} {metadata['slate_name']}"
        )
        player_pool_service.set_active_pool(
            st.session_state,
            player_pool,
            source="Weekly Update pipeline",
            active_slate_name=active_name,
            active_slate_id=None,
            season=metadata["season"],
            week=metadata["week"],
            site=metadata["site"],
            slate_name=metadata["slate_name"],
        )
        source_names = list(metadata["source_names"])
        if not odds_games.empty:
            source_names.append("The Odds API")
        if "usage_games" in player_pool.columns:
            source_names.append("nflverse prior-week usage")
        if "matchup_rating" in player_pool.columns:
            source_names.append("nflverse defensive matchup ratings")
        source_names.append("In-house projection engine")
        database.record_data_update(
            season=metadata["season"],
            week=metadata["week"],
            site=metadata["site"],
            slate_name=metadata["slate_name"],
            player_count=len(player_pool),
            source_names=source_names,
            aggregation=metadata["aggregation"],
        )
        st.success("The updated player pool is active and ready for the Optimizer.")

    if save_clicked:
        try:
            slate_id = database.save_slate(
                season=metadata["season"],
                week=metadata["week"],
                site=metadata["site"],
                slate_name=metadata["slate_name"],
            )
            saved_count = database.save_player_pool(
                slate_id=slate_id,
                players=player_pool,
            )
            if player_pool_service.has_active_pool(st.session_state):
                player_pool_service.set_active_pool(
                    st.session_state,
                    player_pool_service.get_active_pool(st.session_state),
                    source="Weekly Update saved slate",
                    active_slate_name=(
                        f"{metadata['season']} Week {metadata['week']} — "
                        f"{metadata['site']} {metadata['slate_name']}"
                    ),
                    active_slate_id=slate_id,
                    season=metadata["season"],
                    week=metadata["week"],
                    site=metadata["site"],
                    slate_name=metadata["slate_name"],
                )
            st.success(f"Saved {saved_count} players to the slate database.")
        except Exception as exc:
            st.error(f"Could not save the updated slate: {exc}")
else:
    st.info(
        "Choose a player-pool foundation in Section 1 to reveal the in-house "
        "projection engine."
    )

st.markdown("---")
st.subheader("Recent weekly updates")
recent_updates = database.list_data_updates(limit=20)
if recent_updates.empty:
    st.caption("No weekly updates have been recorded yet.")
else:
    st.dataframe(recent_updates, width="stretch", hide_index=True)
