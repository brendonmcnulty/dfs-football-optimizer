from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, MutableMapping

import pandas as pd


@dataclass(frozen=True)
class ActivePlayerPoolMetadata:
    """Metadata describing the player pool currently active in the app."""

    source: str
    active_slate_name: str
    active_slate_id: int | None
    season: int | None
    week: int | None
    site: str | None
    slate_name: str | None
    player_count: int
    loaded_at: str
    revision: int


class PlayerPoolService:
    """
    Manage the active DFS player pool through one shared state interface.

    The service accepts any mutable mapping, including Streamlit's
    ``st.session_state``. It keeps legacy session keys synchronized so current
    pages remain compatible while new pages can use this service directly.
    """

    PLAYER_POOL_KEY = "player_pool"
    METADATA_KEY = "_active_player_pool_metadata"
    REVISION_KEY = "_active_player_pool_revision"

    def has_active_pool(self, state: MutableMapping[str, Any]) -> bool:
        """Return whether a non-empty active player pool exists."""

        pool = state.get(self.PLAYER_POOL_KEY)
        return isinstance(pool, pd.DataFrame) and not pool.empty

    def get_active_pool(
        self,
        state: MutableMapping[str, Any],
        *,
        copy: bool = True,
    ) -> pd.DataFrame:
        """Return the active player pool or an empty DataFrame."""

        pool = state.get(self.PLAYER_POOL_KEY)
        if not isinstance(pool, pd.DataFrame):
            return pd.DataFrame()
        return pool.copy() if copy else pool

    def set_active_pool(
        self,
        state: MutableMapping[str, Any],
        players: pd.DataFrame,
        *,
        source: str,
        active_slate_name: str,
        active_slate_id: int | None = None,
        season: int | None = None,
        week: int | None = None,
        site: str | None = None,
        slate_name: str | None = None,
    ) -> ActivePlayerPoolMetadata:
        """Set the active pool and synchronize all legacy session keys."""

        if not isinstance(players, pd.DataFrame):
            raise TypeError("players must be a pandas DataFrame.")
        if players.empty:
            raise ValueError("The active player pool cannot be empty.")
        if not str(source).strip():
            raise ValueError("The player-pool source cannot be blank.")
        if not str(active_slate_name).strip():
            raise ValueError("The active slate name cannot be blank.")

        normalized = players.copy().reset_index(drop=True)
        revision = int(state.get(self.REVISION_KEY, 0)) + 1
        loaded_at = datetime.now(timezone.utc).isoformat()

        metadata = ActivePlayerPoolMetadata(
            source=str(source).strip(),
            active_slate_name=str(active_slate_name).strip(),
            active_slate_id=(
                int(active_slate_id) if active_slate_id is not None else None
            ),
            season=int(season) if season is not None else None,
            week=int(week) if week is not None else None,
            site=str(site).strip() if site is not None else None,
            slate_name=(
                str(slate_name).strip() if slate_name is not None else None
            ),
            player_count=len(normalized),
            loaded_at=loaded_at,
            revision=revision,
        )

        state[self.PLAYER_POOL_KEY] = normalized
        state[self.METADATA_KEY] = asdict(metadata)
        state[self.REVISION_KEY] = revision

        # Keep existing pages and saved workflows compatible.
        state["active_slate_id"] = metadata.active_slate_id
        state["active_slate_name"] = metadata.active_slate_name
        if metadata.season is not None:
            state["season"] = metadata.season
        if metadata.week is not None:
            state["week"] = metadata.week
        if metadata.site is not None:
            state["site"] = metadata.site
        if metadata.slate_name is not None:
            state["slate_name"] = metadata.slate_name

        return metadata

    def update_active_pool(
        self,
        state: MutableMapping[str, Any],
        players: pd.DataFrame,
        *,
        source: str | None = None,
    ) -> ActivePlayerPoolMetadata:
        """Replace player rows while preserving the current slate metadata."""

        current = self.get_metadata(state)
        return self.set_active_pool(
            state,
            players,
            source=source or current.source,
            active_slate_name=current.active_slate_name,
            active_slate_id=current.active_slate_id,
            season=current.season,
            week=current.week,
            site=current.site,
            slate_name=current.slate_name,
        )

    def clear_active_pool(self, state: MutableMapping[str, Any]) -> None:
        """Remove the active player pool and its metadata."""

        for key in (
            self.PLAYER_POOL_KEY,
            self.METADATA_KEY,
            "active_slate_id",
            "active_slate_name",
        ):
            state.pop(key, None)

    def get_metadata(
        self,
        state: MutableMapping[str, Any],
    ) -> ActivePlayerPoolMetadata:
        """Return active-pool metadata, including legacy-state fallback."""

        raw = state.get(self.METADATA_KEY)
        if isinstance(raw, ActivePlayerPoolMetadata):
            return raw
        if isinstance(raw, dict):
            try:
                return ActivePlayerPoolMetadata(**raw)
            except TypeError:
                pass

        pool = self.get_active_pool(state)
        return ActivePlayerPoolMetadata(
            source="Legacy session state" if not pool.empty else "None",
            active_slate_name=str(
                state.get("active_slate_name", "No active slate")
            ),
            active_slate_id=state.get("active_slate_id"),
            season=self._optional_int(state.get("season")),
            week=self._optional_int(state.get("week")),
            site=self._optional_text(state.get("site")),
            slate_name=self._optional_text(state.get("slate_name")),
            player_count=len(pool),
            loaded_at="Unknown",
            revision=int(state.get(self.REVISION_KEY, 0)),
        )

    def build_coverage_report(
        self,
        players: pd.DataFrame,
    ) -> pd.DataFrame:
        """Return a standard data-coverage report for an active player pool."""

        fields = {
            "Projection": ("projection", "positive"),
            "Ceiling": ("ceiling", "positive"),
            "Floor": ("floor", "positive"),
            "Ownership": ("ownership", "positive"),
            "Confidence": ("confidence", "positive"),
            "Vegas total": ("game_total", "positive"),
            "Team implied total": ("team_implied_total", "positive"),
            "Usage": ("usage_games", "positive"),
            "Matchup rating": ("matchup_rating", "non_default_matchup"),
        }

        total = len(players)
        records: list[dict[str, object]] = []
        for label, (column, rule) in fields.items():
            if column not in players.columns:
                covered = 0
            else:
                values = pd.to_numeric(players[column], errors="coerce")
                if rule == "non_default_matchup":
                    covered = int((values.notna() & (values != 50)).sum())
                else:
                    covered = int((values.notna() & (values > 0)).sum())

            records.append(
                {
                    "Metric": label,
                    "Rows covered": covered,
                    "Total players": total,
                    "Coverage": covered / total if total else 0.0,
                }
            )

        return pd.DataFrame(records)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
