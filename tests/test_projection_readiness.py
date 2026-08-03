from __future__ import annotations

import pandas as pd

from core.settings import OptimizerSettings
from services.optimizer_service import OptimizerService


def _players(projection: float = 10.0) -> pd.DataFrame:
    rows = []
    positions = [
        "QB",
        "RB",
        "RB",
        "RB",
        "WR",
        "WR",
        "WR",
        "WR",
        "TE",
        "TE",
        "DST",
    ]
    for index, position in enumerate(positions):
        rows.append(
            {
                "player_id": str(index),
                "name": f"Player {index}",
                "position": position,
                "team": f"T{index}",
                "opponent": f"O{index}",
                "salary": 5000,
                "projection": projection,
                "ceiling": projection + 5,
                "floor": max(projection - 5, 0),
                "ownership": 10.0,
                "locked": False,
                "excluded": False,
            }
        )
    return pd.DataFrame(rows)


def test_zero_projection_pool_is_blocked() -> None:
    report = OptimizerService().assess_projection_readiness(
        _players(0.0),
        OptimizerSettings(),
    )

    assert not report.is_ready
    assert any(
        "No eligible players have positive projections" in error
        for error in report.critical_errors
    )


def test_usable_projection_pool_is_ready() -> None:
    report = OptimizerService().assess_projection_readiness(
        _players(10.0),
        OptimizerSettings(),
    )

    assert report.is_ready
    assert report.positive_projection_count == 11


def test_leverage_strategy_requires_ownership_coverage() -> None:
    players = _players(10.0)
    players["ownership"] = 0.0

    report = OptimizerService().assess_projection_readiness(
        players,
        OptimizerSettings(
            optimization_target="large_field_gpp",
        ),
    )

    assert not report.is_ready
    assert any(
        "projected ownership" in error
        for error in report.critical_errors
    )
