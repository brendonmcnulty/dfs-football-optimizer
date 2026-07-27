from __future__ import annotations

import os
from pathlib import Path


ENV_PATH = Path('.env')
ODDS_API_KEY_NAME = 'ODDS_API_KEY'


def _read_env_file(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_odds_api_key() -> str:
    """Return the API key from the process environment or local .env file."""
    environment_value = os.getenv(ODDS_API_KEY_NAME, '').strip()
    if environment_value:
        return environment_value
    return _read_env_file().get(ODDS_API_KEY_NAME, '').strip()


def save_odds_api_key(api_key: str, path: Path = ENV_PATH) -> None:
    """Save the API key locally without changing unrelated .env entries."""
    clean_key = api_key.strip()
    if not clean_key:
        raise ValueError('The Odds API key cannot be blank.')

    values = _read_env_file(path)
    values[ODDS_API_KEY_NAME] = clean_key
    lines = [
        '# Local secrets. Do not commit this file.',
        *[f'{key}={value}' for key, value in sorted(values.items())],
        '',
    ]
    path.write_text('\n'.join(lines), encoding='utf-8')
    os.environ[ODDS_API_KEY_NAME] = clean_key
