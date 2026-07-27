from __future__ import annotations

import streamlit as st

from core.local_settings import get_odds_api_key, save_odds_api_key
from services.odds_api_service import OddsApiService


st.set_page_config(page_title='Settings', page_icon='⚙️', layout='wide')
st.title('⚙️ Settings')
st.caption('Configure local integrations. Secrets remain on this computer.')

st.subheader('The Odds API')
configured_key = get_odds_api_key()
st.write(
    'The key is saved in a local `.env` file. That file is excluded from Git and '
    'is not included in project ZIP releases.'
)
api_key = st.text_input(
    'API key',
    value='',
    type='password',
    placeholder='Paste your key here to save or test it',
    help='Leave blank to use the key that is already saved locally.',
)

col1, col2 = st.columns(2)
with col1:
    save_clicked = st.button('Save API key', type='primary', use_container_width=True)
with col2:
    test_clicked = st.button('Test connection', use_container_width=True)

if configured_key:
    st.success('An Odds API key is configured locally.')
else:
    st.warning('No Odds API key is configured yet.')

if save_clicked:
    try:
        save_odds_api_key(api_key)
        st.success('The API key was saved locally in `.env`.')
        configured_key = api_key.strip()
    except Exception as exc:
        st.error(f'Could not save the API key: {exc}')

if test_clicked:
    key_to_test = api_key.strip() or get_odds_api_key()
    try:
        result = OddsApiService(key_to_test).test_connection()
        st.success('Connection successful. NFL is available from The Odds API.')
        if result.requests_remaining is not None:
            st.metric('Requests remaining', result.requests_remaining)
    except Exception as exc:
        st.error(f'Connection test failed: {exc}')
