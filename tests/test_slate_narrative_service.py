from __future__ import annotations

import unittest

import pandas as pd

from services.slate_analysis_service import SlateAnalysisService
from services.slate_narrative_service import SlateNarrativeService


class SlateNarrativeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.players = pd.DataFrame(
            [
                {
                    "player_id": "qb1",
                    "name": "Alpha QB",
                    "position": "QB",
                    "team": "AAA",
                    "opponent": "BBB",
                    "salary": 7500,
                    "projection": 24.0,
                    "ceiling": 36.0,
                    "floor": 16.0,
                    "ownership": 12.0,
                    "confidence": 88.0,
                    "matchup_rating": 82.0,
                    "team_implied_total": 28.0,
                    "game_total": 51.0,
                },
                {
                    "player_id": "wr1",
                    "name": "Alpha WR",
                    "position": "WR",
                    "team": "AAA",
                    "opponent": "BBB",
                    "salary": 6200,
                    "projection": 18.0,
                    "ceiling": 30.0,
                    "floor": 9.0,
                    "ownership": 10.0,
                    "confidence": 80.0,
                    "matchup_rating": 76.0,
                    "team_implied_total": 28.0,
                    "game_total": 51.0,
                },
                {
                    "player_id": "rb1",
                    "name": "Beta RB",
                    "position": "RB",
                    "team": "BBB",
                    "opponent": "AAA",
                    "salary": 5900,
                    "projection": 17.0,
                    "ceiling": 27.0,
                    "floor": 10.0,
                    "ownership": 8.0,
                    "confidence": 78.0,
                    "matchup_rating": 68.0,
                    "team_implied_total": 23.0,
                    "game_total": 51.0,
                },
            ]
        )

    def test_build_creates_evidence_backed_sections(self) -> None:
        analysis = SlateAnalysisService().analyze(
            self.players,
            limit=3,
        )

        narrative = SlateNarrativeService().build(
            analysis,
            slate_name="Test Slate",
            player_limit=3,
            stack_limit=3,
        )

        self.assertEqual(narrative.headline, "Test Slate analysis")
        self.assertIn("Alpha QB", narrative.executive_summary)
        self.assertGreaterEqual(len(narrative.sections), 7)
        self.assertTrue(
            any(
                section.title == "Best value plays"
                for section in narrative.sections
            )
        )
        self.assertTrue(
            any(
                "Alpha" in item or "Beta" in item
                for section in narrative.sections
                for item in section.items
            )
        )

    def test_explain_player_uses_player_metrics(self) -> None:
        analysis = SlateAnalysisService().analyze(
            self.players,
            limit=3,
        )
        player = analysis.ceiling_leaders[0]

        explanation = SlateNarrativeService().explain_player(
            player
        )

        self.assertIn(player.name, explanation.title)
        self.assertIn(f"{player.ceiling:.1f}", explanation.summary)
        self.assertGreaterEqual(len(explanation.items), 1)

    def test_invalid_limits_raise_error(self) -> None:
        analysis = SlateAnalysisService().analyze(
            self.players,
            limit=3,
        )

        with self.assertRaises(ValueError):
            SlateNarrativeService().build(
                analysis,
                player_limit=0,
            )


if __name__ == "__main__":
    unittest.main()
