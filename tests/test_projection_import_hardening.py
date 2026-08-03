from __future__ import annotations

import pandas as pd

from data_pipeline.service import (
    DataSourceInput,
    WeeklyDataPipeline,
)


def test_projection_import_matches_draftkings_id_before_name():
    salary = pd.DataFrame(
        {
            "Position": ["QB", "RB"],
            "Name + ID": ["Player One (101)", "Player Two (202)"],
            "Name": ["Player One", "Player Two"],
            "ID": [101, 202],
            "Roster Position": ["QB", "RB/FLEX"],
            "Salary": [7000, 6000],
            "Game Info": ["AAA@BBB 09/01/2026", "AAA@BBB 09/01/2026"],
            "TeamAbbrev": ["AAA", "BBB"],
        }
    )
    projections = pd.DataFrame(
        {
            "DK Player ID": [202, 101],
            "Player Name": ["Wrong Name", "Also Wrong"],
            "Proj FPTS": [18.5, 24.0],
            "Own%": [12.0, 20.0],
        }
    )

    result = WeeklyDataPipeline().run(
        salary,
        [DataSourceInput("Test", projections)],
    )

    values = result.player_pool.set_index("player_id")
    assert values.loc["101", "projection"] == 24.0
    assert values.loc["202", "projection"] == 18.5
    assert result.source_report.iloc[0]["id_matches"] == 2


def test_duplicate_projection_rows_are_reported_and_excluded():
    salary = pd.DataFrame(
        {
            "Position": ["QB"],
            "Name": ["Player One"],
            "ID": [101],
            "Salary": [7000],
            "TeamAbbrev": ["AAA"],
        }
    )
    projections = pd.DataFrame(
        {
            "ID": [101, 101],
            "Projection": [20.0, 22.0],
        }
    )

    result = WeeklyDataPipeline().run(
        salary,
        [DataSourceInput("Duplicate source", projections)],
    )

    assert len(result.duplicate_report) == 2
    assert result.player_pool.iloc[0]["projection"] == 0.0
