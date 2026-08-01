from __future__ import annotations

import unittest

import pandas as pd

from services.player_pool_service import PlayerPoolService


class PlayerPoolServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PlayerPoolService()
        self.state: dict[str, object] = {}
        self.players = pd.DataFrame(
            [
                {
                    "player_id": "1",
                    "name": "Test Player",
                    "position": "QB",
                    "team": "AAA",
                    "opponent": "BBB",
                    "salary": 7000,
                    "projection": 20.0,
                }
            ]
        )

    def test_set_active_pool_synchronizes_legacy_keys(self) -> None:
        metadata = self.service.set_active_pool(
            self.state,
            self.players,
            source="Unit test",
            active_slate_name="2026 Week 1 — DraftKings Main",
            season=2026,
            week=1,
            site="DraftKings",
            slate_name="Main",
        )

        self.assertTrue(self.service.has_active_pool(self.state))
        self.assertEqual(metadata.player_count, 1)
        self.assertEqual(self.state["season"], 2026)
        self.assertEqual(self.state["week"], 1)
        self.assertEqual(self.state["active_slate_name"], metadata.active_slate_name)

    def test_update_preserves_metadata(self) -> None:
        original = self.service.set_active_pool(
            self.state,
            self.players,
            source="Original",
            active_slate_name="Test Slate",
        )
        updated_players = self.players.copy()
        updated_players.loc[0, "projection"] = 21.0

        updated = self.service.update_active_pool(
            self.state,
            updated_players,
            source="Edited",
        )

        self.assertEqual(updated.active_slate_name, original.active_slate_name)
        self.assertEqual(updated.source, "Edited")
        self.assertEqual(
            self.service.get_active_pool(self.state).loc[0, "projection"],
            21.0,
        )

    def test_clear_removes_active_pool(self) -> None:
        self.service.set_active_pool(
            self.state,
            self.players,
            source="Unit test",
            active_slate_name="Test Slate",
        )
        self.service.clear_active_pool(self.state)
        self.assertFalse(self.service.has_active_pool(self.state))


if __name__ == "__main__":
    unittest.main()
