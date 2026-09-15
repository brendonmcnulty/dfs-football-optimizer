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


def test_leverage_uses_positive_projection_candidates_for_ownership_coverage() -> None:
    projected = _players(10.0)

    # Mimic a real provider feed: the relevant players have projections and
    # ownership, while DraftKings also lists hundreds of deep reserves with
    # neither metric.
    reserve_rows = []
    for index in range(400):
        reserve_rows.append(
            {
                "player_id": f"reserve-{index}",
                "name": f"Reserve {index}",
                "position": "WR",
                "team": "RES",
                "opponent": "OPP",
                "salary": 3000,
                "projection": 0.0,
                "ceiling": 0.0,
                "floor": 0.0,
                "ownership": 0.0,
                "locked": False,
                "excluded": False,
            }
        )

    players = pd.concat(
        [projected, pd.DataFrame(reserve_rows)],
        ignore_index=True,
    )

    report = OptimizerService().assess_projection_readiness(
        players,
        OptimizerSettings(
            optimization_target="large_field_gpp",
        ),
    )

    assert report.is_ready
    assert report.positive_projection_count == len(projected)
    assert any(
        "full DraftKings player pool" in warning
        for warning in report.warnings
    )


def test_leverage_still_blocks_when_projected_candidates_lack_ownership() -> None:
    players = _players(10.0)
    players.loc[players.index[:6], "ownership"] = 0.0

    report = OptimizerService().assess_projection_readiness(
        players,
        OptimizerSettings(
            optimization_target="large_field_gpp",
        ),
    )

    assert not report.is_ready
    assert any(
        "positive projections" in error
        for error in report.critical_errors
    )


def test_zero_percent_imported_ownership_counts_as_populated() -> None:
    players = _players(10.0)
    players["ownership"] = 0.0
    players["ownership_imported"] = True

    report = OptimizerService().assess_projection_readiness(
        players,
        OptimizerSettings(
            optimization_target="large_field_gpp",
        ),
    )

    assert report.is_ready


def test_missing_imported_ownership_marker_still_blocks_candidates() -> None:
    players = _players(10.0)
    players["ownership"] = 0.0
    players["ownership_imported"] = True
    players.loc[players.index[:6], "ownership_imported"] = False

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

def test_negative_floor_is_valid_model_input() -> None:
    players = _players(10.0)
    players.loc[players.index[0], "floor"] = -2.5

    service = OptimizerService()

    # Negative floors are legitimate downside estimates and should not
    # invalidate an otherwise usable player pool.
    service.validate_player_pool(players)


def test_negative_ceiling_is_still_invalid() -> None:
    players = _players(10.0)
    players.loc[players.index[0], "ceiling"] = -1.0

    service = OptimizerService()

    try:
        service.validate_player_pool(players)
    except ValueError as exc:
        assert "ceiling values cannot be negative" in str(exc)
    else:
        raise AssertionError("Negative ceiling should fail validation.")

