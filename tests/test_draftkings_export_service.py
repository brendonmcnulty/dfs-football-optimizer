from __future__ import annotations

from io import StringIO
import csv

import pandas as pd

from services.draftkings_export_service import (
    DraftKingsExportService,
)


def _fixture_bytes() -> bytes:
    players = [
        ("QB", "Quarterback", "101", "QB", 7000, "AAA@BBB 09/01/2026", "AAA"),
        ("RB", "Running Back One", "201", "RB/FLEX", 6500, "AAA@BBB 09/01/2026", "AAA"),
        ("RB", "Running Back Two", "202", "RB/FLEX", 6200, "CCC@DDD 09/01/2026", "CCC"),
        ("WR", "Receiver One", "301", "WR/FLEX", 6000, "AAA@BBB 09/01/2026", "AAA"),
        ("WR", "Receiver Two", "302", "WR/FLEX", 5600, "CCC@DDD 09/01/2026", "DDD"),
        ("WR", "Receiver Three", "303", "WR/FLEX", 5000, "EEE@FFF 09/01/2026", "EEE"),
        ("TE", "Tight End", "401", "TE/FLEX", 4200, "EEE@FFF 09/01/2026", "FFF"),
        ("RB", "Flex Player", "203", "RB/FLEX", 4800, "GGG@HHH 09/01/2026", "GGG"),
        ("DST", "Defense", "501", "DST", 2700, "GGG@HHH 09/01/2026", "HHH"),
    ]

    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "Entry ID", "Contest Name", "Contest ID", "Entry Fee",
        "QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST",
        "", "Instructions",
    ])
    writer.writerow([
        "1", "Test Contest", "2", "$0",
        *[f"{name} ({player_id})" for _, name, player_id, *_ in players],
        "", "",
    ])
    writer.writerow([""] * 14 + ["Instructions"])
    writer.writerow(
        [""] * 14
        + [
            "Position", "Name + ID", "Name", "ID", "Roster Position",
            "Salary", "Game Info", "TeamAbbrev", "AvgPointsPerGame",
        ]
    )
    for position, name, player_id, roster_position, salary, game, team in players:
        writer.writerow(
            [""] * 14
            + [
                position,
                f"{name} ({player_id})",
                name,
                player_id,
                roster_position,
                salary,
                game,
                team,
                10.0,
            ]
        )
    return output.getvalue().encode("utf-8")


def _lineup(template):
    records = []
    for slot, player_id in zip(
        ("QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"),
        ("101", "201", "202", "301", "302", "303", "401", "203", "501"),
    ):
        player = template.players.loc[
            template.players["player_id"] == player_id
        ].iloc[0]
        records.append(
            {
                "roster_slot": slot,
                "player_id": player_id,
                "name": player["name"],
                "position": player["position"],
                "salary": player["salary"],
            }
        )
    return pd.DataFrame(records)


def test_parse_and_export_entry_template():
    service = DraftKingsExportService()
    template = service.parse_template(_fixture_bytes())

    assert len(template.entries) == 1
    assert len(template.players) == 9

    result = service.export_lineups(template, [_lineup(template)])

    assert result.is_valid
    decoded = result.csv_bytes.decode("utf-8-sig")
    assert decoded.startswith("Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB")
    assert "Quarterback (101)" in decoded


def test_unknown_player_id_blocks_export():
    service = DraftKingsExportService()
    template = service.parse_template(_fixture_bytes())
    lineup = _lineup(template)
    lineup.loc[0, "player_id"] = "999999999"

    result = service.export_lineups(template, [lineup])

    assert not result.is_valid
    assert any(
        "failed validation" in error
        for error in result.critical_errors
    )
