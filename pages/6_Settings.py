from __future__ import annotations

import pandas as pd
import streamlit as st

from core.local_settings import (
    get_odds_api_key,
    save_odds_api_key,
)
from services.odds_api_service import (
    DEFAULT_PROP_MARKET,
    OddsApiCapabilityReport,
    OddsApiService,
)


st.set_page_config(
    page_title="Settings",
    page_icon="⚙️",
    layout="wide",
)

st.title("⚙️ Settings")
st.caption(
    "Configure local integrations and verify exactly what your API key can access."
)

st.subheader("The Odds API")

configured_key = get_odds_api_key()

st.write(
    "The key is saved in a local `.env` file. That file is excluded "
    "from Git and is not included in project ZIP releases."
)

api_key = st.text_input(
    "API key",
    value="",
    type="password",
    placeholder="Paste your key here to save or test it",
    help="Leave blank to use the key that is already saved locally.",
)

button_columns = st.columns(2)

with button_columns[0]:
    save_clicked = st.button(
        "Save API key",
        type="primary",
        use_container_width=True,
    )

with button_columns[1]:
    test_clicked = st.button(
        "Test basic connection",
        use_container_width=True,
    )

if configured_key:
    st.success(
        "An Odds API key is configured locally."
    )
else:
    st.warning(
        "No Odds API key is configured yet."
    )

if save_clicked:
    try:
        save_odds_api_key(
            api_key
        )
        configured_key = api_key.strip()
        st.success(
            "The API key was saved locally in `.env`."
        )
    except Exception as error:  # noqa: BLE001
        st.error(
            f"Could not save the API key: {error}"
        )

if test_clicked:
    key_to_test = (
        api_key.strip()
        or get_odds_api_key()
    )

    try:
        result = OddsApiService(
            key_to_test
        ).test_connection()
        st.success(
            "Connection successful. NFL is currently available "
            "from The Odds API."
        )

        metric_columns = st.columns(3)

        metric_columns[0].metric(
            "Requests remaining",
            (
                result.requests_remaining
                if result.requests_remaining
                is not None
                else "Unknown"
            ),
        )
        metric_columns[1].metric(
            "Requests used",
            (
                result.requests_used
                if result.requests_used
                is not None
                else "Unknown"
            ),
        )
        metric_columns[2].metric(
            "Last request cost",
            (
                result.request_cost
                if result.request_cost
                is not None
                else "Unknown"
            ),
        )
    except Exception as error:  # noqa: BLE001
        st.error(
            f"Connection test failed: {error}"
        )

st.markdown("---")
st.subheader("API capability tester")

st.write(
    "The free checks verify authentication, NFL availability, and the "
    "current NFL event list. Those endpoints do not consume usage credits."
)

st.info(
    "Optional market checks make real odds requests. Featured markets can "
    "cost up to 3 credits. The single player-prop check can cost up to "
    "1 credit when the selected market is returned."
)

option_columns = st.columns(2)

with option_columns[0]:
    test_featured_markets = st.checkbox(
        "Test moneyline, spreads, and totals",
        value=False,
        help=(
            "Makes one NFL odds request for h2h, spreads, and totals. "
            "Maximum expected cost: 3 credits."
        ),
    )

with option_columns[1]:
    test_player_props = st.checkbox(
        "Test one NFL player-prop market",
        value=False,
        help=(
            "Uses the first current NFL event and requests one player-prop "
            "market. Maximum expected cost: 1 credit if data is returned."
        ),
    )

prop_market = st.text_input(
    "Player-prop market key",
    value=DEFAULT_PROP_MARKET,
    disabled=not test_player_props,
    help=(
        "The default checks passing-yards props. A successful empty response "
        "may mean the market is not yet posted for the tested game."
    ),
)

estimated_maximum_cost = (
    (3 if test_featured_markets else 0)
    + (1 if test_player_props else 0)
)

st.caption(
    f"Maximum expected credit cost for this capability run: "
    f"{estimated_maximum_cost}"
)

run_capability_test = st.button(
    "Run API capability test",
    type="primary",
    use_container_width=True,
)

if run_capability_test:
    key_to_test = (
        api_key.strip()
        or get_odds_api_key()
    )

    if not key_to_test:
        st.error(
            "Save or enter an API key before running the capability test."
        )
    else:
        try:
            report = OddsApiService(
                key_to_test
            ).test_capabilities(
                test_featured_markets=(
                    test_featured_markets
                ),
                test_player_props=(
                    test_player_props
                ),
                player_prop_market=(
                    prop_market
                ),
            )
        except Exception as error:  # noqa: BLE001
            st.error(
                "Capability test failed: "
                f"{type(error).__name__}: {error}"
            )
        else:
            st.session_state[
                "odds_api_capability_report"
            ] = report
            st.success(
                "Capability test completed."
            )

report = st.session_state.get(
    "odds_api_capability_report"
)

if isinstance(
    report,
    OddsApiCapabilityReport,
):
    capability_frame = pd.DataFrame(
        report.as_rows()
    )

    st.dataframe(
        capability_frame,
        hide_index=True,
        width="stretch",
        column_config={
            "Capability": st.column_config.TextColumn(
                "Capability"
            ),
            "Status": st.column_config.TextColumn(
                "Status"
            ),
            "Detail": st.column_config.TextColumn(
                "Detail",
                width="large",
            ),
        },
    )

    metric_columns = st.columns(4)

    metric_columns[0].metric(
        "NFL events found",
        report.event_count,
    )
    metric_columns[1].metric(
        "Credits spent by test",
        report.credits_spent,
    )
    metric_columns[2].metric(
        "Requests remaining",
        (
            report.requests_remaining
            if report.requests_remaining
            is not None
            else "Unknown"
        ),
    )
    metric_columns[3].metric(
        "Requests used",
        (
            report.requests_used
            if report.requests_used
            is not None
            else "Unknown"
        ),
    )

    if report.tested_event:
        st.write(
            f"**Event used for the player-prop check:** "
            f"{report.tested_event}"
        )

    st.caption(
        f"Capability test completed at {report.tested_at} UTC."
    )

    if (
        report.player_props_status
        == "NO CURRENT DATA"
    ):
        st.warning(
            "A no-data result is inconclusive. The account may support "
            "player props even when the selected market is not posted for "
            "the first available event."
        )

    if (
        report.player_props_status
        == "AVAILABLE"
    ):
        st.success(
            "Player-prop data was returned. Your key can access at least "
            f"the tested market: {report.player_prop_market}."
        )

st.markdown("---")
st.caption(
    "The `/sports` and `/events` checks are quota-free. The application "
    "does not display or transmit your API key anywhere except directly "
    "to The Odds API."
)
