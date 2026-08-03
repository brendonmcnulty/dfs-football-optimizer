from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from statistics import mean
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


API_BASE_URL = "https://api.the-odds-api.com/v4"
NFL_SPORT_KEY = "americanfootball_nfl"

FEATURED_MARKETS = (
    "h2h",
    "spreads",
    "totals",
)

DEFAULT_PROP_MARKET = "player_pass_yds"

NFL_TEAM_ABBREVIATIONS = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}


@dataclass(frozen=True)
class OddsApiResult:
    games: pd.DataFrame
    requests_remaining: int | None
    requests_used: int | None
    request_cost: int | None
    fetched_at: str


@dataclass(frozen=True)
class OddsApiCapabilityReport:
    """Results from testing the capabilities of one API key."""

    nfl_listed: bool
    nfl_active: bool
    event_count: int
    tested_event_id: str | None
    tested_event: str | None
    featured_markets_status: str
    featured_markets_detail: str
    player_props_status: str
    player_props_detail: str
    player_prop_market: str
    requests_remaining: int | None
    requests_used: int | None
    credits_spent: int
    tested_at: str

    def as_rows(self) -> list[dict[str, str]]:
        """Return Streamlit-friendly capability rows."""

        return [
            {
                "Capability": "API key authentication",
                "Status": "AVAILABLE" if self.nfl_listed else "UNAVAILABLE",
                "Detail": (
                    "The API key authenticated and the NFL sport key was found."
                    if self.nfl_listed
                    else "The NFL sport key was not returned for this account."
                ),
            },
            {
                "Capability": "NFL currently active",
                "Status": "AVAILABLE" if self.nfl_active else "INACTIVE",
                "Detail": (
                    "The API currently marks NFL as active."
                    if self.nfl_active
                    else (
                        "The key authenticated, but NFL is currently marked "
                        "inactive. This can happen during parts of the offseason."
                    )
                ),
            },
            {
                "Capability": "NFL event list",
                "Status": "AVAILABLE" if self.event_count > 0 else "NO EVENTS",
                "Detail": f"{self.event_count} current or upcoming NFL event(s) returned.",
            },
            {
                "Capability": "Featured NFL markets",
                "Status": self.featured_markets_status,
                "Detail": self.featured_markets_detail,
            },
            {
                "Capability": "NFL player props",
                "Status": self.player_props_status,
                "Detail": self.player_props_detail,
            },
        ]


class OddsApiError(RuntimeError):
    """Raised when The Odds API cannot return usable data."""


class OddsApiService:
    def __init__(self, api_key: str, timeout_seconds: int = 20) -> None:
        self.api_key = api_key.strip()
        self.timeout_seconds = int(timeout_seconds)

        if not self.api_key:
            raise ValueError("The Odds API key is not configured.")

    def test_connection(self) -> OddsApiResult:
        """Test the key with the quota-free sports endpoint."""

        payload, headers = self._request(
            "/sports",
            {
                "all": "false",
            },
        )

        active = any(
            item.get("key") == NFL_SPORT_KEY
            and item.get("active", False)
            for item in payload
        )

        if not active:
            raise OddsApiError(
                "The API connection worked, but NFL odds are not currently active."
            )

        return OddsApiResult(
            games=pd.DataFrame(),
            requests_remaining=_header_int(
                headers,
                "x-requests-remaining",
            ),
            requests_used=_header_int(
                headers,
                "x-requests-used",
            ),
            request_cost=_header_int(
                headers,
                "x-requests-last",
            ),
            fetched_at=datetime.now(
                timezone.utc
            ).isoformat(
                timespec="seconds"
            ),
        )

    def test_capabilities(
        self,
        test_featured_markets: bool = False,
        test_player_props: bool = False,
        player_prop_market: str = DEFAULT_PROP_MARKET,
    ) -> OddsApiCapabilityReport:
        """
        Inspect the capabilities of the configured API key.

        The sports and events checks are quota-free. Featured-market testing
        can cost up to three credits. A one-market player-prop test can cost
        up to one credit when data is returned.
        """

        credits_spent = 0
        latest_headers: Any = {}

        sports_payload, sports_headers = self._request(
            "/sports",
            {
                "all": "true",
            },
        )
        latest_headers = sports_headers

        nfl_sport = next(
            (
                item
                for item in sports_payload
                if item.get("key") == NFL_SPORT_KEY
            ),
            None,
        )

        nfl_listed = nfl_sport is not None
        nfl_active = bool(
            nfl_sport
            and nfl_sport.get(
                "active",
                False,
            )
        )

        events_payload: list[dict[str, Any]] = []

        if nfl_listed:
            events_result, events_headers = self._request(
                f"/sports/{NFL_SPORT_KEY}/events",
                {
                    "dateFormat": "iso",
                },
            )
            latest_headers = events_headers

            if isinstance(
                events_result,
                list,
            ):
                events_payload = events_result

        events_payload = sorted(
            events_payload,
            key=lambda event: str(
                event.get(
                    "commence_time",
                    "",
                )
            ),
        )

        tested_event = (
            events_payload[0]
            if events_payload
            else None
        )

        tested_event_id = (
            str(
                tested_event.get(
                    "id",
                    "",
                )
            )
            if tested_event
            else None
        ) or None

        tested_event_name = None

        if tested_event:
            away_team = str(
                tested_event.get(
                    "away_team",
                    "",
                )
            )
            home_team = str(
                tested_event.get(
                    "home_team",
                    "",
                )
            )
            tested_event_name = (
                f"{away_team} at {home_team}"
            ).strip()

        featured_status = "NOT TESTED"
        featured_detail = (
            "Enable the featured-market test to verify moneyline, spread, "
            "and total access. This test can cost up to three credits."
        )

        if test_featured_markets:
            try:
                featured_payload, featured_headers = self._request(
                    f"/sports/{NFL_SPORT_KEY}/odds",
                    {
                        "regions": "us",
                        "markets": ",".join(
                            FEATURED_MARKETS
                        ),
                        "oddsFormat": "american",
                        "dateFormat": "iso",
                    },
                )
                latest_headers = featured_headers
                credits_spent += (
                    _header_int(
                        featured_headers,
                        "x-requests-last",
                    )
                    or 0
                )

                returned_markets = _collect_market_keys(
                    featured_payload
                )

                if returned_markets:
                    featured_status = "AVAILABLE"
                    featured_detail = (
                        "Returned market data for: "
                        + ", ".join(
                            sorted(
                                returned_markets
                            )
                        )
                        + "."
                    )
                elif featured_payload:
                    featured_status = "NO MARKET DATA"
                    featured_detail = (
                        "NFL events were returned, but no requested featured "
                        "markets were present."
                    )
                else:
                    featured_status = "NO CURRENT EVENTS"
                    featured_detail = (
                        "The request succeeded but returned no current NFL "
                        "odds. Empty responses do not normally consume quota."
                    )
            except OddsApiError as error:
                featured_status = "ERROR"
                featured_detail = str(error)

        prop_market = (
            player_prop_market.strip()
            or DEFAULT_PROP_MARKET
        )

        props_status = "NOT TESTED"
        props_detail = (
            "Enable the player-prop test to check one market on one current "
            "NFL event. The result depends on both account access and whether "
            "bookmakers currently offer the selected market."
        )

        if test_player_props:
            if not tested_event_id:
                props_status = "NOT CURRENTLY TESTABLE"
                props_detail = (
                    "No current or upcoming NFL event was available, so the "
                    "event-level player-prop endpoint could not be tested."
                )
            else:
                try:
                    props_payload, props_headers = self._request(
                        (
                            f"/sports/{NFL_SPORT_KEY}/events/"
                            f"{tested_event_id}/odds"
                        ),
                        {
                            "regions": "us",
                            "markets": prop_market,
                            "oddsFormat": "american",
                            "dateFormat": "iso",
                        },
                    )
                    latest_headers = props_headers
                    credits_spent += (
                        _header_int(
                            props_headers,
                            "x-requests-last",
                        )
                        or 0
                    )

                    returned_markets = _collect_market_keys(
                        props_payload
                    )

                    if prop_market in returned_markets:
                        props_status = "AVAILABLE"
                        props_detail = (
                            f"The market `{prop_market}` was returned for "
                            f"{tested_event_name or tested_event_id}."
                        )
                    else:
                        props_status = "NO CURRENT DATA"
                        props_detail = (
                            f"The request was accepted, but `{prop_market}` "
                            "was not returned for the tested event. This does "
                            "not prove the account lacks all player-prop access; "
                            "the market may simply be unavailable for that game."
                        )
                except OddsApiError as error:
                    props_status = "RESTRICTED OR ERROR"
                    props_detail = (
                        f"The event-level prop request failed: {error}"
                    )

        return OddsApiCapabilityReport(
            nfl_listed=nfl_listed,
            nfl_active=nfl_active,
            event_count=len(
                events_payload
            ),
            tested_event_id=tested_event_id,
            tested_event=tested_event_name,
            featured_markets_status=featured_status,
            featured_markets_detail=featured_detail,
            player_props_status=props_status,
            player_props_detail=props_detail,
            player_prop_market=prop_market,
            requests_remaining=_header_int(
                latest_headers,
                "x-requests-remaining",
            ),
            requests_used=_header_int(
                latest_headers,
                "x-requests-used",
            ),
            credits_spent=int(
                credits_spent
            ),
            tested_at=datetime.now(
                timezone.utc
            ).isoformat(
                timespec="seconds"
            ),
        )

    def fetch_nfl_odds(self) -> OddsApiResult:
        """Fetch upcoming NFL moneylines, spreads, and totals."""

        payload, headers = self._request(
            f"/sports/{NFL_SPORT_KEY}/odds",
            {
                "regions": "us",
                "markets": "h2h,spreads,totals",
                "oddsFormat": "american",
                "dateFormat": "iso",
            },
        )

        records = [
            self._consensus_game(
                event
            )
            for event in payload
        ]

        games = pd.DataFrame(
            records
        )

        if not games.empty:
            games = (
                games.sort_values(
                    "commence_time"
                )
                .reset_index(
                    drop=True
                )
            )

        return OddsApiResult(
            games=games,
            requests_remaining=_header_int(
                headers,
                "x-requests-remaining",
            ),
            requests_used=_header_int(
                headers,
                "x-requests-used",
            ),
            request_cost=_header_int(
                headers,
                "x-requests-last",
            ),
            fetched_at=datetime.now(
                timezone.utc
            ).isoformat(
                timespec="seconds"
            ),
        )

    def _request(
        self,
        endpoint: str,
        parameters: dict[str, str],
    ) -> tuple[Any, Any]:
        query = urlencode(
            {
                **parameters,
                "apiKey": self.api_key,
            }
        )

        request = Request(
            f"{API_BASE_URL}{endpoint}?{query}",
            headers={
                "User-Agent": (
                    "DFS-Football-Optimizer/4.3"
                ),
            },
        )

        try:
            with urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                return (
                    json.loads(
                        response.read().decode(
                            "utf-8"
                        )
                    ),
                    response.headers,
                )
        except HTTPError as error:
            body = error.read().decode(
                "utf-8",
                errors="replace",
            )

            try:
                parsed_body = json.loads(
                    body
                )
                error_code = parsed_body.get(
                    "error_code",
                    parsed_body.get(
                        "code",
                        "",
                    ),
                )
                message = parsed_body.get(
                    "message",
                    body,
                )
                detail = (
                    f"{error_code}: {message}"
                    if error_code
                    else str(message)
                )
            except json.JSONDecodeError:
                detail = body

            raise OddsApiError(
                "The Odds API returned "
                f"HTTP {error.code}: {detail}"
            ) from error
        except URLError as error:
            raise OddsApiError(
                "Could not connect to The Odds API: "
                f"{error.reason}"
            ) from error
        except json.JSONDecodeError as error:
            raise OddsApiError(
                "The Odds API returned invalid JSON."
            ) from error

    def _consensus_game(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        home_name = str(
            event.get(
                "home_team",
                "",
            )
        )
        away_name = str(
            event.get(
                "away_team",
                "",
            )
        )

        home_spreads: list[float] = []
        totals: list[float] = []
        home_moneylines: list[float] = []
        away_moneylines: list[float] = []

        for bookmaker in event.get(
            "bookmakers",
            [],
        ):
            for market in bookmaker.get(
                "markets",
                [],
            ):
                key = market.get(
                    "key"
                )
                outcomes = market.get(
                    "outcomes",
                    [],
                )

                if key == "spreads":
                    for outcome in outcomes:
                        if (
                            outcome.get(
                                "name"
                            )
                            == home_name
                            and outcome.get(
                                "point"
                            )
                            is not None
                        ):
                            home_spreads.append(
                                float(
                                    outcome[
                                        "point"
                                    ]
                                )
                            )
                elif key == "totals":
                    over = next(
                        (
                            outcome
                            for outcome in outcomes
                            if outcome.get(
                                "name"
                            )
                            == "Over"
                        ),
                        None,
                    )

                    if (
                        over
                        and over.get(
                            "point"
                        )
                        is not None
                    ):
                        totals.append(
                            float(
                                over[
                                    "point"
                                ]
                            )
                        )
                elif key == "h2h":
                    for outcome in outcomes:
                        if outcome.get(
                            "price"
                        ) is None:
                            continue

                        if outcome.get(
                            "name"
                        ) == home_name:
                            home_moneylines.append(
                                float(
                                    outcome[
                                        "price"
                                    ]
                                )
                            )
                        elif outcome.get(
                            "name"
                        ) == away_name:
                            away_moneylines.append(
                                float(
                                    outcome[
                                        "price"
                                    ]
                                )
                            )

        spread = (
            mean(
                home_spreads
            )
            if home_spreads
            else None
        )
        total = (
            mean(
                totals
            )
            if totals
            else None
        )

        home_implied = None
        away_implied = None

        if (
            spread is not None
            and total is not None
        ):
            home_implied = (
                total - spread
            ) / 2.0
            away_implied = (
                total + spread
            ) / 2.0

        return {
            "event_id": str(
                event.get(
                    "id",
                    "",
                )
            ),
            "commence_time": str(
                event.get(
                    "commence_time",
                    "",
                )
            ),
            "home_team_name": home_name,
            "away_team_name": away_name,
            "home_team": NFL_TEAM_ABBREVIATIONS.get(
                home_name,
                home_name,
            ),
            "away_team": NFL_TEAM_ABBREVIATIONS.get(
                away_name,
                away_name,
            ),
            "home_spread": (
                round(
                    spread,
                    2,
                )
                if spread is not None
                else None
            ),
            "game_total": (
                round(
                    total,
                    2,
                )
                if total is not None
                else None
            ),
            "home_implied_total": (
                round(
                    home_implied,
                    2,
                )
                if home_implied is not None
                else None
            ),
            "away_implied_total": (
                round(
                    away_implied,
                    2,
                )
                if away_implied is not None
                else None
            ),
            "home_moneyline": (
                round(
                    mean(
                        home_moneylines
                    ),
                    0,
                )
                if home_moneylines
                else None
            ),
            "away_moneyline": (
                round(
                    mean(
                        away_moneylines
                    ),
                    0,
                )
                if away_moneylines
                else None
            ),
            "bookmaker_count": int(
                len(
                    event.get(
                        "bookmakers",
                        [],
                    )
                )
            ),
        }


def nfl_week_bounds(
    season: int,
    week: int,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return approximate UTC boundaries for an NFL regular-season week."""

    season = int(
        season
    )
    week = int(
        week
    )

    if week < 1 or week > 22:
        raise ValueError(
            "NFL week must be between 1 and 22."
        )

    september_first = datetime(
        season,
        9,
        1,
        tzinfo=timezone.utc,
    )
    days_until_monday = (
        7 - september_first.weekday()
    ) % 7
    labor_day = (
        september_first
        + timedelta(
            days=days_until_monday
        )
    )

    week_one_start = (
        labor_day
        + timedelta(
            days=2
        )
    )
    start = (
        week_one_start
        + timedelta(
            days=7
            * (
                week - 1
            )
        )
    )
    end = (
        start
        + timedelta(
            days=7
        )
    )

    return (
        pd.Timestamp(
            start
        ),
        pd.Timestamp(
            end
        ),
    )


def filter_games_for_week(
    games: pd.DataFrame,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Return games whose kickoff falls in the selected NFL week."""

    if games.empty:
        return games.copy()

    if "commence_time" not in games.columns:
        raise ValueError(
            "Vegas games are missing the commence_time column."
        )

    start, end = nfl_week_bounds(
        season,
        week,
    )
    kickoff = pd.to_datetime(
        games[
            "commence_time"
        ],
        utc=True,
        errors="coerce",
    )
    mask = (
        kickoff.ge(
            start
        )
        & kickoff.lt(
            end
        )
    )

    filtered = games.loc[
        mask
    ].copy()

    return (
        filtered.sort_values(
            "commence_time"
        )
        .reset_index(
            drop=True
        )
    )


def enrich_player_pool_with_vegas(
    player_pool: pd.DataFrame,
    games: pd.DataFrame,
) -> pd.DataFrame:
    """Attach game-environment fields to every player."""

    output = player_pool.copy()

    fields = [
        "game_total",
        "team_implied_total",
        "opponent_implied_total",
        "team_spread",
        "moneyline",
        "is_home",
        "commence_time",
    ]

    for field in fields:
        output[field] = pd.NA

    if games.empty:
        return output

    team_lookup: dict[
        str,
        dict[str, Any],
    ] = {}

    for _, game in games.iterrows():
        home = str(
            game[
                "home_team"
            ]
        )
        away = str(
            game[
                "away_team"
            ]
        )

        team_lookup[home] = {
            "game_total": game[
                "game_total"
            ],
            "team_implied_total": game[
                "home_implied_total"
            ],
            "opponent_implied_total": game[
                "away_implied_total"
            ],
            "team_spread": game[
                "home_spread"
            ],
            "moneyline": game[
                "home_moneyline"
            ],
            "is_home": True,
            "commence_time": game[
                "commence_time"
            ],
        }

        away_spread = (
            -float(
                game[
                    "home_spread"
                ]
            )
            if pd.notna(
                game[
                    "home_spread"
                ]
            )
            else None
        )

        team_lookup[away] = {
            "game_total": game[
                "game_total"
            ],
            "team_implied_total": game[
                "away_implied_total"
            ],
            "opponent_implied_total": game[
                "home_implied_total"
            ],
            "team_spread": away_spread,
            "moneyline": game[
                "away_moneyline"
            ],
            "is_home": False,
            "commence_time": game[
                "commence_time"
            ],
        }

    normalized_teams = (
        output[
            "team"
        ]
        .astype(
            str
        )
        .str.upper()
        .str.strip()
    )

    for row_index, team in normalized_teams.items():
        game_values = team_lookup.get(
            team
        )

        if not game_values:
            continue

        for field, value in game_values.items():
            output.at[
                row_index,
                field,
            ] = value

    return output


def _collect_market_keys(
    payload: Any,
) -> set[str]:
    """Collect market keys from sport-odds or event-odds responses."""

    events = (
        payload
        if isinstance(
            payload,
            list,
        )
        else [
            payload
        ]
    )

    market_keys: set[str] = set()

    for event in events:
        if not isinstance(
            event,
            dict,
        ):
            continue

        for bookmaker in event.get(
            "bookmakers",
            [],
        ):
            for market in bookmaker.get(
                "markets",
                [],
            ):
                key = market.get(
                    "key"
                )

                if key:
                    market_keys.add(
                        str(
                            key
                        )
                    )

    return market_keys


def _header_int(
    headers: Any,
    name: str,
) -> int | None:
    value = headers.get(
        name
    )

    try:
        return (
            int(
                value
            )
            if value is not None
            else None
        )
    except (
        TypeError,
        ValueError,
    ):
        return None
