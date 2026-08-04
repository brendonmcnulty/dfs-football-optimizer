from __future__ import annotations

import pytest

from core.contest_presets import (
    CONTEST_STRATEGY_PRESETS,
    get_contest_strategy_preset,
)


def test_expected_contest_presets_exist() -> None:
    assert set(CONTEST_STRATEGY_PRESETS) == {
        "cash",
        "single_entry_gpp",
        "three_max_gpp",
        "twenty_max_gpp",
        "one_fifty_max_gpp",
    }


def test_lineup_counts_match_contest_types() -> None:
    assert CONTEST_STRATEGY_PRESETS["cash"].lineup_count == 1
    assert CONTEST_STRATEGY_PRESETS["single_entry_gpp"].lineup_count == 1
    assert CONTEST_STRATEGY_PRESETS["three_max_gpp"].lineup_count == 3
    assert CONTEST_STRATEGY_PRESETS["twenty_max_gpp"].lineup_count == 20
    assert CONTEST_STRATEGY_PRESETS["one_fifty_max_gpp"].lineup_count == 150


def test_gpp_presets_require_correlation() -> None:
    for key in (
        "single_entry_gpp",
        "three_max_gpp",
        "twenty_max_gpp",
        "one_fifty_max_gpp",
    ):
        preset = CONTEST_STRATEGY_PRESETS[key]
        assert preset.qb_stack_size >= 1
        assert preset.require_bring_back is True


def test_exposure_caps_tighten_with_portfolio_size() -> None:
    assert CONTEST_STRATEGY_PRESETS["three_max_gpp"].default_player_max_exposure == pytest.approx(0.67)
    assert CONTEST_STRATEGY_PRESETS["twenty_max_gpp"].default_player_max_exposure == pytest.approx(0.50)
    assert CONTEST_STRATEGY_PRESETS["one_fifty_max_gpp"].default_player_max_exposure == pytest.approx(0.35)


def test_unknown_preset_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="Unknown contest strategy preset"):
        get_contest_strategy_preset("not_real")
