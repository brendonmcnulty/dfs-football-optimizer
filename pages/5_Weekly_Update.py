from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from core.local_settings import get_odds_api_key
from data_pipeline import DataSourceInput, WeeklyDataPipeline
from database import DatabaseManager
from services.odds_api_service import OddsApiService, enrich_player_pool_with_vegas
from projection_engine import ProjectionEngine


st.set_page_config(page_title='Weekly Update', page_icon='🔄', layout='wide')


def _read_csv(uploaded_file) -> pd.DataFrame:
    uploaded_file.seek(0)
    return pd.read_csv(uploaded_file)


database = DatabaseManager()
pipeline = WeeklyDataPipeline()
projection_engine = ProjectionEngine()

st.title('🔄 Weekly Data Update')
st.caption('Build the weekly player pool and enrich it with live NFL betting markets.')

with st.sidebar:
    st.header('Slate information')
    current_year = datetime.now().year
    season = st.number_input(
        'NFL season', min_value=2000, max_value=current_year + 1,
        value=int(st.session_state.get('season', current_year)), step=1,
    )
    week = st.number_input(
        'NFL week', min_value=1, max_value=22,
        value=int(st.session_state.get('week', 1)), step=1,
    )
    site = st.selectbox('DFS site', options=['DraftKings'])
    slate_name = st.text_input(
        'Slate name', value=str(st.session_state.get('slate_name', 'Main')),
    )
    st.markdown('---')
    aggregation_label = st.selectbox(
        'Combine matching sources using',
        options=['Average', 'Median', 'First source'],
    )
    aggregation = {'Average': 'mean', 'Median': 'median', 'First source': 'first'}[
        aggregation_label
    ]

st.subheader('1. DraftKings salary file')
st.write('Upload the salary CSV downloaded from the DraftKings contest lobby.')
salary_file = st.file_uploader('DraftKings salary CSV', type=['csv'], key='weekly_salary_file')

st.subheader('2. Optional projection and ownership sources')
st.write('Upload up to three provider CSVs. Players match by ID first, then name and team.')
source_columns = st.columns(3)
source_uploads = []
for index, column in enumerate(source_columns, start=1):
    with column:
        source_name = st.text_input(
            f'Source {index} name', value=f'Source {index}',
            key=f'weekly_source_name_{index}',
        )
        source_file = st.file_uploader(
            f'Source {index} CSV', type=['csv'], key=f'weekly_source_file_{index}',
        )
        source_uploads.append((source_name, source_file))

build_clicked = st.button('Build weekly player pool', type='primary', use_container_width=True)
if build_clicked:
    if salary_file is None:
        st.error('Upload a DraftKings salary CSV before building the player pool.')
    else:
        try:
            sources = [
                DataSourceInput(name=name.strip() or file.name, frame=_read_csv(file))
                for name, file in source_uploads if file is not None
            ]
            result = pipeline.run(
                salary_frame=_read_csv(salary_file),
                data_sources=sources,
                aggregation=aggregation,
            )
            st.session_state.weekly_pipeline_result = result
            st.session_state.weekly_pipeline_metadata = {
                'season': int(season), 'week': int(week), 'site': site,
                'slate_name': slate_name.strip() or 'Main',
                'source_names': [source.name for source in sources],
                'aggregation': aggregation,
            }
            st.success('Player pool built. Add Vegas data below.')
        except Exception as exc:
            st.error(f'Weekly update failed: {exc}')

st.markdown('---')
st.subheader('3. Live Vegas data')
api_key = get_odds_api_key()
if api_key:
    st.caption('The Odds API key is configured. Fetching odds uses plan credits.')
else:
    st.warning('Configure your key on the Settings page before fetching Vegas data.')

fetch_col, cache_col = st.columns(2)
with fetch_col:
    fetch_odds_clicked = st.button(
        'Fetch current NFL odds', disabled=not bool(api_key), use_container_width=True,
    )
with cache_col:
    load_cached_clicked = st.button('Load cached odds for this week', use_container_width=True)

if fetch_odds_clicked:
    try:
        odds_result = OddsApiService(api_key).fetch_nfl_odds()
        st.session_state.weekly_odds_result = odds_result
        saved = database.save_games(int(season), int(week), odds_result.games, odds_result.fetched_at)
        st.success(f'Fetched and cached {saved} upcoming NFL games.')
    except Exception as exc:
        st.error(f'Vegas update failed: {exc}')

if load_cached_clicked:
    cached = database.load_games(int(season), int(week))
    if cached.empty:
        st.warning('No cached Vegas games were found for this season and week.')
    else:
        st.session_state.weekly_cached_games = cached
        st.success(f'Loaded {len(cached)} cached games.')

odds_games = pd.DataFrame()
odds_meta = None
if 'weekly_odds_result' in st.session_state:
    odds_meta = st.session_state.weekly_odds_result
    odds_games = odds_meta.games
elif 'weekly_cached_games' in st.session_state:
    odds_games = st.session_state.weekly_cached_games

if not odds_games.empty:
    if odds_meta is not None:
        m1, m2, m3 = st.columns(3)
        m1.metric('Games returned', len(odds_games))
        m2.metric('Requests remaining', odds_meta.requests_remaining or 'Unknown')
        m3.metric('Last request cost', odds_meta.request_cost or 'Unknown')
    st.dataframe(
        odds_games[[
            'commence_time', 'away_team', 'home_team', 'home_spread', 'game_total',
            'away_implied_total', 'home_implied_total', 'bookmaker_count',
        ]],
        width='stretch', hide_index=True,
    )

if 'weekly_pipeline_result' in st.session_state:
    result = st.session_state.weekly_pipeline_result
    metadata = st.session_state.weekly_pipeline_metadata
    player_pool = result.player_pool.copy()
    if not odds_games.empty:
        player_pool = enrich_player_pool_with_vegas(player_pool, odds_games)

    st.markdown('---')
    st.subheader('4. In-house projection engine')
    st.write(
        'Generate transparent rule-based projections from imported projections '
        'when available, or a salary baseline when they are not. Vegas, home/away, '
        'and spread adjustments are shown separately.'
    )
    generate_model_clicked = st.button(
        'Generate in-house projections',
        use_container_width=True,
    )
    if generate_model_clicked:
        try:
            model_result = projection_engine.project(player_pool)
            st.session_state.weekly_model_player_pool = model_result.player_pool
            st.session_state.weekly_model_summary = model_result.summary
            st.success('In-house projections, ceiling, floor, and confidence are ready.')
        except Exception as exc:
            st.error(f'Projection model failed: {exc}')

    if 'weekly_model_player_pool' in st.session_state:
        player_pool = st.session_state.weekly_model_player_pool.copy()
        if 'weekly_model_summary' in st.session_state:
            st.dataframe(
                st.session_state.weekly_model_summary,
                width='stretch',
                hide_index=True,
            )

    st.markdown('---')
    st.subheader('Updated player pool')
    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    metric_1.metric('Players', len(player_pool))
    metric_2.metric('Positive projections', int((player_pool['projection'] > 0).sum()))
    metric_3.metric('Ownership covered', int((player_pool['ownership'] > 0).sum()))
    vegas_covered = int(player_pool['game_total'].notna().sum()) if 'game_total' in player_pool else 0
    metric_4.metric('Vegas covered', vegas_covered)

    preview_columns = [
        'name', 'position', 'team', 'opponent', 'salary', 'projection', 'ceiling',
        'floor', 'confidence', 'ownership', 'base_projection', 'vegas_adjustment',
        'home_adjustment', 'spread_adjustment', 'model_adjustment', 'game_total',
        'team_implied_total', 'team_spread', 'is_home',
    ]
    preview_columns = [column for column in preview_columns if column in player_pool.columns]
    st.dataframe(player_pool[preview_columns], width='stretch', hide_index=True)

    action_1, action_2, action_3 = st.columns(3)
    with action_1:
        use_clicked = st.button('Use as active player pool', type='primary', use_container_width=True)
    with action_2:
        save_clicked = st.button('Save slate to database', use_container_width=True)
    with action_3:
        st.download_button(
            'Download updated CSV', data=player_pool.to_csv(index=False).encode('utf-8'),
            file_name=(
                f"{metadata['season']}_week_{metadata['week']}_"
                f"{metadata['slate_name'].replace(' ', '_').lower()}_updated.csv"
            ), mime='text/csv', use_container_width=True,
        )

    if use_clicked:
        st.session_state.player_pool = player_pool.copy()
        st.session_state.season = metadata['season']
        st.session_state.week = metadata['week']
        st.session_state.site = metadata['site']
        st.session_state.slate_name = metadata['slate_name']
        st.session_state.active_slate_id = None
        st.session_state.active_slate_name = (
            f"{metadata['season']} Week {metadata['week']} — "
            f"{metadata['site']} {metadata['slate_name']}"
        )
        source_names = list(metadata['source_names'])
        if not odds_games.empty:
            source_names.append('The Odds API')
        database.record_data_update(
            season=metadata['season'], week=metadata['week'], site=metadata['site'],
            slate_name=metadata['slate_name'], player_count=len(player_pool),
            source_names=source_names, aggregation=metadata['aggregation'],
        )
        st.success('The updated player pool is active and ready for the Optimizer.')

    if save_clicked:
        try:
            slate_id = database.save_slate(
                season=metadata['season'], week=metadata['week'], site=metadata['site'],
                slate_name=metadata['slate_name'],
            )
            saved_count = database.save_player_pool(slate_id=slate_id, players=player_pool)
            st.session_state.active_slate_id = slate_id
            st.success(f'Saved {saved_count} players to the slate database.')
        except Exception as exc:
            st.error(f'Could not save the updated slate: {exc}')

st.markdown('---')
st.subheader('Recent weekly updates')
recent_updates = database.list_data_updates(limit=20)
if recent_updates.empty:
    st.caption('No weekly updates have been recorded yet.')
else:
    st.dataframe(recent_updates, width='stretch', hide_index=True)
