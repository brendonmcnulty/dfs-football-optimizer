from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from statistics import mean
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


API_BASE_URL = 'https://api.the-odds-api.com/v4'
NFL_SPORT_KEY = 'americanfootball_nfl'

NFL_TEAM_ABBREVIATIONS = {
    'Arizona Cardinals': 'ARI', 'Atlanta Falcons': 'ATL',
    'Baltimore Ravens': 'BAL', 'Buffalo Bills': 'BUF',
    'Carolina Panthers': 'CAR', 'Chicago Bears': 'CHI',
    'Cincinnati Bengals': 'CIN', 'Cleveland Browns': 'CLE',
    'Dallas Cowboys': 'DAL', 'Denver Broncos': 'DEN',
    'Detroit Lions': 'DET', 'Green Bay Packers': 'GB',
    'Houston Texans': 'HOU', 'Indianapolis Colts': 'IND',
    'Jacksonville Jaguars': 'JAX', 'Kansas City Chiefs': 'KC',
    'Las Vegas Raiders': 'LV', 'Los Angeles Chargers': 'LAC',
    'Los Angeles Rams': 'LAR', 'Miami Dolphins': 'MIA',
    'Minnesota Vikings': 'MIN', 'New England Patriots': 'NE',
    'New Orleans Saints': 'NO', 'New York Giants': 'NYG',
    'New York Jets': 'NYJ', 'Philadelphia Eagles': 'PHI',
    'Pittsburgh Steelers': 'PIT', 'San Francisco 49ers': 'SF',
    'Seattle Seahawks': 'SEA', 'Tampa Bay Buccaneers': 'TB',
    'Tennessee Titans': 'TEN', 'Washington Commanders': 'WAS',
}


@dataclass(frozen=True)
class OddsApiResult:
    games: pd.DataFrame
    requests_remaining: int | None
    requests_used: int | None
    request_cost: int | None
    fetched_at: str


class OddsApiError(RuntimeError):
    """Raised when The Odds API cannot return usable data."""


class OddsApiService:
    def __init__(self, api_key: str, timeout_seconds: int = 20) -> None:
        self.api_key = api_key.strip()
        self.timeout_seconds = int(timeout_seconds)
        if not self.api_key:
            raise ValueError('The Odds API key is not configured.')

    def test_connection(self) -> OddsApiResult:
        """Test the key with the quota-free sports endpoint."""
        payload, headers = self._request('/sports', {'all': 'false'})
        active = any(
            item.get('key') == NFL_SPORT_KEY and item.get('active', False)
            for item in payload
        )
        if not active:
            raise OddsApiError(
                'The API connection worked, but NFL odds are not currently active.'
            )
        return OddsApiResult(
            games=pd.DataFrame(),
            requests_remaining=_header_int(headers, 'x-requests-remaining'),
            requests_used=_header_int(headers, 'x-requests-used'),
            request_cost=_header_int(headers, 'x-requests-last'),
            fetched_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        )

    def fetch_nfl_odds(self) -> OddsApiResult:
        """Fetch upcoming NFL moneylines, spreads, and totals and build consensus lines."""
        payload, headers = self._request(
            f'/sports/{NFL_SPORT_KEY}/odds',
            {
                'regions': 'us',
                'markets': 'h2h,spreads,totals',
                'oddsFormat': 'american',
                'dateFormat': 'iso',
            },
        )
        records = [self._consensus_game(event) for event in payload]
        games = pd.DataFrame(records)
        if not games.empty:
            games = games.sort_values('commence_time').reset_index(drop=True)
        return OddsApiResult(
            games=games,
            requests_remaining=_header_int(headers, 'x-requests-remaining'),
            requests_used=_header_int(headers, 'x-requests-used'),
            request_cost=_header_int(headers, 'x-requests-last'),
            fetched_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        )

    def _request(self, endpoint: str, parameters: dict[str, str]) -> tuple[Any, Any]:
        query = urlencode({**parameters, 'apiKey': self.api_key})
        request = Request(
            f'{API_BASE_URL}{endpoint}?{query}',
            headers={'User-Agent': 'DFS-Football-Optimizer/1.4'},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode('utf-8')), response.headers
        except HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            try:
                detail = json.loads(body).get('message', body)
            except json.JSONDecodeError:
                detail = body
            raise OddsApiError(f'The Odds API returned HTTP {exc.code}: {detail}') from exc
        except URLError as exc:
            raise OddsApiError(f'Could not connect to The Odds API: {exc.reason}') from exc
        except json.JSONDecodeError as exc:
            raise OddsApiError('The Odds API returned invalid JSON.') from exc

    def _consensus_game(self, event: dict[str, Any]) -> dict[str, Any]:
        home_name = str(event.get('home_team', ''))
        away_name = str(event.get('away_team', ''))
        home_spreads: list[float] = []
        totals: list[float] = []
        home_moneylines: list[float] = []
        away_moneylines: list[float] = []

        for bookmaker in event.get('bookmakers', []):
            for market in bookmaker.get('markets', []):
                key = market.get('key')
                outcomes = market.get('outcomes', [])
                if key == 'spreads':
                    for outcome in outcomes:
                        if outcome.get('name') == home_name and outcome.get('point') is not None:
                            home_spreads.append(float(outcome['point']))
                elif key == 'totals':
                    over = next((o for o in outcomes if o.get('name') == 'Over'), None)
                    if over and over.get('point') is not None:
                        totals.append(float(over['point']))
                elif key == 'h2h':
                    for outcome in outcomes:
                        if outcome.get('price') is None:
                            continue
                        if outcome.get('name') == home_name:
                            home_moneylines.append(float(outcome['price']))
                        elif outcome.get('name') == away_name:
                            away_moneylines.append(float(outcome['price']))

        spread = mean(home_spreads) if home_spreads else None
        total = mean(totals) if totals else None
        home_implied = None
        away_implied = None
        if spread is not None and total is not None:
            home_implied = (total - spread) / 2.0
            away_implied = (total + spread) / 2.0

        return {
            'event_id': str(event.get('id', '')),
            'commence_time': str(event.get('commence_time', '')),
            'home_team_name': home_name,
            'away_team_name': away_name,
            'home_team': NFL_TEAM_ABBREVIATIONS.get(home_name, home_name),
            'away_team': NFL_TEAM_ABBREVIATIONS.get(away_name, away_name),
            'home_spread': round(spread, 2) if spread is not None else None,
            'game_total': round(total, 2) if total is not None else None,
            'home_implied_total': round(home_implied, 2) if home_implied is not None else None,
            'away_implied_total': round(away_implied, 2) if away_implied is not None else None,
            'home_moneyline': round(mean(home_moneylines), 0) if home_moneylines else None,
            'away_moneyline': round(mean(away_moneylines), 0) if away_moneylines else None,
            'bookmaker_count': int(len(event.get('bookmakers', []))),
        }


def enrich_player_pool_with_vegas(player_pool: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Attach game environment fields to every player by team abbreviation."""
    output = player_pool.copy()
    fields = [
        'game_total', 'team_implied_total', 'opponent_implied_total',
        'team_spread', 'moneyline', 'is_home', 'commence_time',
    ]
    for field in fields:
        output[field] = pd.NA

    if games.empty:
        return output

    team_lookup: dict[str, dict[str, Any]] = {}
    for _, game in games.iterrows():
        home = str(game['home_team']).upper().strip()
        away = str(game['away_team']).upper().strip()
        spread = game.get('home_spread')
        team_lookup[home] = {
            'game_total': game.get('game_total'),
            'team_implied_total': game.get('home_implied_total'),
            'opponent_implied_total': game.get('away_implied_total'),
            'team_spread': spread,
            'moneyline': game.get('home_moneyline'),
            'is_home': True,
            'commence_time': game.get('commence_time'),
        }
        team_lookup[away] = {
            'game_total': game.get('game_total'),
            'team_implied_total': game.get('away_implied_total'),
            'opponent_implied_total': game.get('home_implied_total'),
            'team_spread': -spread if pd.notna(spread) else None,
            'moneyline': game.get('away_moneyline'),
            'is_home': False,
            'commence_time': game.get('commence_time'),
        }

    for index, player in output.iterrows():
        data = team_lookup.get(str(player['team']).upper().strip())
        if data:
            for field, value in data.items():
                output.at[index, field] = value
    return output


def _header_int(headers: Any, name: str) -> int | None:
    value = headers.get(name)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
