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


def test_cpenn_columns_are_detected_and_percent_ownership_is_parsed():
    salary = pd.DataFrame(
        {
            "Position": ["RB", "WR"],
            "Name": ["Jahmyr Gibbs", "Ja'Marr Chase"],
            "ID": [43727325, 43727631],
            "Roster Position": ["RB/FLEX", "WR/FLEX"],
            "Salary": [8000, 7800],
            "Game Info": ["NO@DET 09/13/2026", "TB@CIN 09/13/2026"],
            "TeamAbbrev": ["DET", "CIN"],
        }
    )
    cpenn = pd.DataFrame(
        {
            "Player": ["Jahmyr Gibbs", "Ja'Marr Chase"],
            "Pos": ["RB", "WR"],
            "Team": ["DET", "CIN"],
            "Opp": ["NO", "TB"],
            "DK Sal": ["8,000", "7,800"],
            "DK Proj": [23.9, 21.6],
            "DK pOWN%": ["33.9%", "24.0%"],
            "DK Floor": [13.9, 11.2],
            "DK Ceil": [34.9, 33.1],
        }
    )

    result = WeeklyDataPipeline().run(
        salary,
        [DataSourceInput("CPenn", cpenn)],
    )

    values = result.player_pool.set_index("player_id")
    assert values.loc["43727325", "projection"] == 23.9
    assert values.loc["43727325", "floor"] == 13.9
    assert values.loc["43727325", "ceiling"] == 34.9
    assert values.loc["43727325", "ownership"] == 33.9
    assert values.loc["43727631", "ownership"] == 24.0
    assert result.source_report.iloc[0]["name_team_matches"] == 2
    assert result.source_report.iloc[0]["metrics_detected"] == (
        "projection, ceiling, floor, ownership"
    )


def test_cpenn_raw_export_matches_draftkings_by_name_and_team():
    salary = pd.DataFrame(
        {
            "Position": ["QB"],
            "Name + ID": ["Joe Burrow (999)"],
            "Name": ["Joe Burrow"],
            "ID": [999],
            "Roster Position": ["QB"],
            "Salary": [6900],
            "Game Info": ["TB@CIN 09/13/2026"],
            "TeamAbbrev": ["CIN"],
        }
    )
    cpenn = pd.DataFrame(
        {
            "Player": ["Joe Burrow"],
            "Pos": ["QB"],
            "Team": ["CIN"],
            "Opp": ["TB"],
            "DK Proj": [20.7],
            "DK Floor": [13.6],
            "DK Ceil": [27.9],
            "DK pOWN%": ["8.7%"],
        }
    )

    result = WeeklyDataPipeline().run(
        salary,
        [DataSourceInput("CPenn", cpenn)],
    )

    assert result.source_report.iloc[0]["matched_rows"] == 1
    assert result.source_report.iloc[0]["name_team_matches"] == 1
    assert result.player_pool.iloc[0]["projection"] == 20.7
