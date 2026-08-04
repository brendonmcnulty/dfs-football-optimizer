from __future__ import annotations

import pandas as pd

from services.week_one_readiness_service import WeekOneReadinessService


def _lineup(qb_name: str = "QB One") -> pd.DataFrame:
    records = [
        ("1", qb_name, "QB", "AAA", "BBB", 7000, 22.0, 32.0, 12.0),
        ("2", "RB One", "RB", "AAA", "BBB", 6500, 18.0, 28.0, 15.0),
        ("3", "RB Two", "RB", "CCC", "DDD", 6100, 16.0, 25.0, 11.0),
        ("4", "WR One", "WR", "AAA", "BBB", 6200, 17.0, 27.0, 13.0),
        ("5", "WR Two", "WR", "BBB", "AAA", 5900, 15.0, 24.0, 10.0),
        ("6", "WR Three", "WR", "EEE", "FFF", 5600, 14.0, 23.0, 9.0),
        ("7", "TE One", "TE", "GGG", "HHH", 4300, 11.0, 19.0, 8.0),
        ("8", "Flex One", "RB", "III", "JJJ", 5400, 13.0, 22.0, 7.0),
        ("9", "DST One", "DST", "KKK", "LLL", 3000, 8.0, 14.0, 5.0),
    ]
    frame = pd.DataFrame(
        records,
        columns=[
            "player_id", "name", "position", "team", "opponent",
            "salary", "projection", "ceiling", "ownership",
        ],
    )
    return frame


def test_portfolio_health_detects_stack_and_bringback() -> None:
    service = WeekOneReadinessService()
    report = service.build_portfolio_health(
        [_lineup()],
        {"generated_lineup_settings": {"salary_cap": 50000}},
    )

    assert report.lineup_count == 1
    assert report.stack_summary.iloc[0]["has_qb_stack"]
    assert report.stack_summary.iloc[0]["has_bring_back"]
    assert report.duplicate_lineup_count == 0


def test_portfolio_health_detects_duplicates() -> None:
    service = WeekOneReadinessService()
    lineup = _lineup()
    report = service.build_portfolio_health(
        [lineup, lineup.copy()],
        {"generated_lineup_settings": {"salary_cap": 50000}},
    )

    assert report.duplicate_lineup_count == 1
    assert any("duplicate" in warning.lower() for warning in report.warnings)
