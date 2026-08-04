from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping

import pandas as pd

from services.draftkings_contest_service import DraftKingsContestService
from services.player_pool_service import PlayerPoolService


@dataclass(frozen=True)
class ReadinessCheck:
    """One Week 1 workflow readiness check."""

    category: str
    label: str
    status: str
    detail: str
    destination: str | None = None
    critical: bool = True


@dataclass(frozen=True)
class PortfolioHealthReport:
    """Portfolio-level diagnostics for generated lineups."""

    lineup_count: int
    average_salary: float
    average_projection: float
    average_ceiling: float
    average_ownership: float
    average_salary_remaining: float
    duplicate_lineup_count: int
    unique_player_count: int
    qb_exposure: pd.DataFrame
    player_exposure: pd.DataFrame
    team_exposure: pd.DataFrame
    game_exposure: pd.DataFrame
    stack_summary: pd.DataFrame
    salary_distribution: pd.DataFrame
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WeekOneReadinessReport:
    """Complete pre-lock readiness and portfolio-health report."""

    overall_status: str
    checks: tuple[ReadinessCheck, ...]
    critical_failures: int
    warnings: int
    portfolio: PortfolioHealthReport | None


class WeekOneReadinessService:
    """Assess whether the active slate is ready for DraftKings upload."""

    READY = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"

    def __init__(
        self,
        player_pool_service: PlayerPoolService | None = None,
        contest_service: DraftKingsContestService | None = None,
    ) -> None:
        self.player_pool_service = player_pool_service or PlayerPoolService()
        self.contest_service = contest_service or DraftKingsContestService()

    def assess(
        self,
        state: MutableMapping[str, Any],
    ) -> WeekOneReadinessReport:
        """Build a deterministic pre-lock checklist from shared app state."""

        checks: list[ReadinessCheck] = []
        pool = self.player_pool_service.get_active_pool(state)
        pool_metadata = self.player_pool_service.get_metadata(state)
        contest_metadata = self.contest_service.get_metadata(state)

        checks.append(
            ReadinessCheck(
                category="DraftKings",
                label="DKEntries loaded",
                status=(self.READY if contest_metadata else self.FAIL),
                detail=(
                    f"{contest_metadata.entry_count} reserved entry row(s) loaded "
                    f"from {contest_metadata.source_name}."
                    if contest_metadata
                    else "Upload DKEntries.csv on Weekly Update."
                ),
                destination="pages/5_Weekly_Update.py",
            )
        )

        checks.append(
            ReadinessCheck(
                category="DraftKings",
                label="Player pool loaded",
                status=(self.READY if not pool.empty else self.FAIL),
                detail=(
                    f"{len(pool)} players are active from {pool_metadata.source}."
                    if not pool.empty
                    else "No active player pool is available."
                ),
                destination="pages/5_Weekly_Update.py",
            )
        )

        if pool.empty:
            checks.extend(
                [
                    self._missing_pool_check("Projections", "Projection coverage"),
                    self._missing_pool_check("Ownership", "Ownership coverage", critical=False),
                    self._missing_pool_check("Data sources", "Vegas coverage", critical=False),
                    self._missing_pool_check("Data sources", "Usage coverage", critical=False),
                    self._missing_pool_check("Data sources", "Matchup coverage", critical=False),
                ]
            )
        else:
            checks.extend(self._pool_checks(pool))

        generated_lineups = state.get("generated_lineups", [])
        requested_count = int(
            state.get("generated_lineup_settings", {}).get(
                "lineup_count",
                len(generated_lineups),
            )
        )
        generated_count = len(generated_lineups)

        if generated_count == 0:
            checks.append(
                ReadinessCheck(
                    category="Portfolio",
                    label="Lineups generated",
                    status=self.FAIL,
                    detail="No lineups have been generated for the active session.",
                    destination="pages/3_Optimizer.py",
                )
            )
        elif generated_count < requested_count:
            checks.append(
                ReadinessCheck(
                    category="Portfolio",
                    label="Lineups generated",
                    status=self.WARNING,
                    detail=(
                        f"Generated {generated_count} of {requested_count} requested lineups."
                    ),
                    destination="pages/3_Optimizer.py",
                    critical=False,
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    category="Portfolio",
                    label="Lineups generated",
                    status=self.READY,
                    detail=f"Generated all {generated_count} requested lineups.",
                    destination="pages/3_Optimizer.py",
                )
            )

        portfolio = (
            self.build_portfolio_health(generated_lineups, state)
            if generated_count
            else None
        )

        if contest_metadata and generated_count:
            if generated_count < contest_metadata.entry_count:
                entry_status = self.WARNING
                entry_detail = (
                    f"{generated_count} lineups are available for "
                    f"{contest_metadata.entry_count} reserved entries."
                )
                entry_critical = False
            else:
                entry_status = self.READY
                entry_detail = (
                    f"At least one lineup is available for each of the "
                    f"{contest_metadata.entry_count} reserved entries."
                )
                entry_critical = True
        elif contest_metadata:
            entry_status = self.FAIL
            entry_detail = "Reserved entries exist, but no lineups are available."
            entry_critical = True
        else:
            entry_status = self.FAIL
            entry_detail = "No reserved-entry template is loaded."
            entry_critical = True

        checks.append(
            ReadinessCheck(
                category="Export",
                label="Entry count coverage",
                status=entry_status,
                detail=entry_detail,
                destination="pages/16_DraftKings_Export.py",
                critical=entry_critical,
            )
        )

        export_result = state.get("dk_export_result")
        if export_result is None:
            export_status = self.WARNING if generated_count else self.FAIL
            export_detail = (
                "Build and validate the DraftKings export after selecting final lineups."
                if generated_count
                else "Generate lineups before building a DraftKings export."
            )
            export_critical = False if generated_count else True
        elif bool(getattr(export_result, "is_valid", False)):
            export_status = self.READY
            export_detail = "DraftKings export validation passed with no critical errors."
            export_critical = True
        else:
            critical_errors = getattr(export_result, "critical_errors", ())
            export_status = self.FAIL
            export_detail = (
                f"DraftKings export has {len(critical_errors)} critical error(s)."
            )
            export_critical = True

        checks.append(
            ReadinessCheck(
                category="Export",
                label="DraftKings export validated",
                status=export_status,
                detail=export_detail,
                destination="pages/16_DraftKings_Export.py",
                critical=export_critical,
            )
        )

        critical_failures = sum(
            check.status == self.FAIL and check.critical
            for check in checks
        )
        warning_count = sum(
            check.status == self.WARNING
            for check in checks
        )

        if critical_failures:
            overall_status = "NOT READY"
        elif warning_count:
            overall_status = "READY WITH WARNINGS"
        else:
            overall_status = "READY FOR UPLOAD"

        return WeekOneReadinessReport(
            overall_status=overall_status,
            checks=tuple(checks),
            critical_failures=int(critical_failures),
            warnings=int(warning_count),
            portfolio=portfolio,
        )

    def _pool_checks(self, pool: pd.DataFrame) -> list[ReadinessCheck]:
        checks: list[ReadinessCheck] = []
        total = len(pool)

        player_ids = pool.get("player_id", pd.Series("", index=pool.index)).astype(str)
        duplicate_ids = int(player_ids.duplicated(keep=False).sum())
        missing_ids = int(player_ids.str.strip().eq("").sum())
        id_status = self.READY if duplicate_ids == 0 and missing_ids == 0 else self.FAIL
        checks.append(
            ReadinessCheck(
                category="DraftKings",
                label="Player IDs valid",
                status=id_status,
                detail=(
                    "All active players have unique DraftKings IDs."
                    if id_status == self.READY
                    else f"Found {missing_ids} missing and {duplicate_ids} duplicated ID rows."
                ),
                destination="pages/1_Player_Pool.py",
            )
        )

        metric_specs = [
            ("Projections", "Projection coverage", "projection", 0.80, True),
            ("Ownership", "Ownership coverage", "ownership", 0.50, False),
            ("Data sources", "Vegas coverage", "game_total", 0.80, False),
            ("Data sources", "Usage coverage", "usage_games", 0.50, False),
        ]

        for category, label, column, threshold, critical in metric_specs:
            coverage = self._positive_coverage(pool, column)
            if coverage >= threshold:
                status = self.READY
            elif coverage > 0:
                status = self.WARNING
            else:
                status = self.FAIL if critical else self.WARNING
            checks.append(
                ReadinessCheck(
                    category=category,
                    label=label,
                    status=status,
                    detail=f"{coverage:.0%} of {total} players are covered.",
                    destination="pages/5_Weekly_Update.py",
                    critical=critical,
                )
            )

        matchup_coverage = self._matchup_coverage(pool)
        matchup_status = self.READY if matchup_coverage >= 0.50 else self.WARNING
        checks.append(
            ReadinessCheck(
                category="Data sources",
                label="Matchup coverage",
                status=matchup_status,
                detail=f"{matchup_coverage:.0%} of {total} players have non-default matchup ratings.",
                destination="pages/5_Weekly_Update.py",
                critical=False,
            )
        )

        return checks

    def build_portfolio_health(
        self,
        lineups: list[pd.DataFrame],
        state: Mapping[str, Any] | None = None,
    ) -> PortfolioHealthReport:
        """Calculate portfolio health, exposures, correlations, and warnings."""

        if not lineups:
            raise ValueError("At least one lineup is required.")

        state = state or {}
        salary_cap = int(
            state.get("generated_lineup_settings", {}).get("salary_cap", 50000)
        )

        lineup_records: list[dict[str, Any]] = []
        player_records: list[dict[str, Any]] = []
        team_records: list[dict[str, Any]] = []
        game_records: list[dict[str, Any]] = []
        stack_records: list[dict[str, Any]] = []
        signatures: list[tuple[str, ...]] = []

        for lineup_number, lineup in enumerate(lineups, start=1):
            normalized = lineup.copy()
            normalized["player_id"] = normalized["player_id"].astype(str)
            signatures.append(tuple(sorted(normalized["player_id"].tolist())))

            salary = float(pd.to_numeric(normalized.get("salary"), errors="coerce").fillna(0).sum())
            projection = float(pd.to_numeric(normalized.get("projection"), errors="coerce").fillna(0).sum())
            ceiling = float(pd.to_numeric(normalized.get("ceiling"), errors="coerce").fillna(0).sum()) if "ceiling" in normalized else 0.0
            ownership = float(pd.to_numeric(normalized.get("ownership"), errors="coerce").fillna(0).sum()) if "ownership" in normalized else 0.0

            lineup_records.append(
                {
                    "lineup_number": lineup_number,
                    "salary": salary,
                    "salary_remaining": salary_cap - salary,
                    "projection": projection,
                    "ceiling": ceiling,
                    "ownership": ownership,
                }
            )

            for _, player in normalized.drop_duplicates("player_id").iterrows():
                player_records.append(
                    {
                        "lineup_number": lineup_number,
                        "player_id": str(player.get("player_id", "")),
                        "name": str(player.get("name", "")),
                        "position": str(player.get("position", "")),
                        "team": str(player.get("team", "")),
                    }
                )

            teams = sorted(set(normalized.get("team", pd.Series(dtype=str)).astype(str)))
            for team in teams:
                team_records.append({"lineup_number": lineup_number, "team": team})

            games = sorted(set(self._game_key(row) for _, row in normalized.iterrows()))
            for game in games:
                game_records.append({"lineup_number": lineup_number, "game": game})

            stack_records.append(self._stack_record(lineup_number, normalized))

        lineup_frame = pd.DataFrame(lineup_records)
        player_frame = pd.DataFrame(player_records)
        team_frame = pd.DataFrame(team_records)
        game_frame = pd.DataFrame(game_records)
        stack_frame = pd.DataFrame(stack_records)

        player_exposure = (
            player_frame.groupby(["player_id", "name", "position", "team"], as_index=False)
            .agg(lineups=("lineup_number", "nunique"))
        )
        player_exposure["exposure"] = player_exposure["lineups"] / len(lineups)
        player_exposure = player_exposure.sort_values(
            ["exposure", "position", "name"], ascending=[False, True, True]
        ).reset_index(drop=True)

        qb_exposure = player_exposure.loc[
            player_exposure["position"].astype(str).str.upper().eq("QB")
        ].reset_index(drop=True)

        team_exposure = team_frame.groupby("team", as_index=False).agg(
            lineups=("lineup_number", "nunique")
        )
        team_exposure["exposure"] = team_exposure["lineups"] / len(lineups)
        team_exposure = team_exposure.sort_values("exposure", ascending=False).reset_index(drop=True)

        game_exposure = game_frame.groupby("game", as_index=False).agg(
            lineups=("lineup_number", "nunique")
        )
        game_exposure["exposure"] = game_exposure["lineups"] / len(lineups)
        game_exposure = game_exposure.sort_values("exposure", ascending=False).reset_index(drop=True)

        duplicate_count = len(signatures) - len(set(signatures))
        warnings: list[str] = []
        low_salary_count = int((lineup_frame["salary_remaining"] > 2000).sum())
        if low_salary_count:
            warnings.append(
                f"{low_salary_count} lineup(s) leave more than $2,000 of salary unused."
            )
        if duplicate_count:
            warnings.append(f"Found {duplicate_count} duplicate lineup(s).")
        if not qb_exposure.empty and float(qb_exposure.iloc[0]["exposure"]) > 0.60:
            warnings.append(
                f"{qb_exposure.iloc[0]['name']} appears in "
                f"{float(qb_exposure.iloc[0]['exposure']):.0%} of lineups."
            )
        if not player_exposure.empty and float(player_exposure.iloc[0]["exposure"]) > 0.75:
            warnings.append(
                f"{player_exposure.iloc[0]['name']} is the highest-exposed player at "
                f"{float(player_exposure.iloc[0]['exposure']):.0%}."
            )
        no_stack_count = int((~stack_frame["has_qb_stack"]).sum())
        if no_stack_count:
            warnings.append(f"{no_stack_count} lineup(s) have no same-team QB pass catcher.")
        no_bringback_count = int(
            (stack_frame["has_qb_stack"] & ~stack_frame["has_bring_back"]).sum()
        )
        if no_bringback_count:
            warnings.append(
                f"{no_bringback_count} QB-stacked lineup(s) do not include an opponent bring-back."
            )

        salary_distribution = lineup_frame[[
            "lineup_number", "salary", "salary_remaining", "projection", "ceiling", "ownership"
        ]].copy()

        return PortfolioHealthReport(
            lineup_count=len(lineups),
            average_salary=float(lineup_frame["salary"].mean()),
            average_projection=float(lineup_frame["projection"].mean()),
            average_ceiling=float(lineup_frame["ceiling"].mean()),
            average_ownership=float(lineup_frame["ownership"].mean()),
            average_salary_remaining=float(lineup_frame["salary_remaining"].mean()),
            duplicate_lineup_count=int(duplicate_count),
            unique_player_count=int(player_frame["player_id"].nunique()),
            qb_exposure=qb_exposure,
            player_exposure=player_exposure,
            team_exposure=team_exposure,
            game_exposure=game_exposure,
            stack_summary=stack_frame,
            salary_distribution=salary_distribution,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _positive_coverage(pool: pd.DataFrame, column: str) -> float:
        if column not in pool.columns or pool.empty:
            return 0.0
        values = pd.to_numeric(pool[column], errors="coerce").fillna(0.0)
        return float((values > 0).mean())

    @staticmethod
    def _matchup_coverage(pool: pd.DataFrame) -> float:
        if "matchup_rating" not in pool.columns or pool.empty:
            return 0.0
        values = pd.to_numeric(pool["matchup_rating"], errors="coerce")
        return float((values.notna() & (values != 50)).mean())

    @classmethod
    def _missing_pool_check(
        cls,
        category: str,
        label: str,
        *,
        critical: bool = True,
    ) -> ReadinessCheck:
        return ReadinessCheck(
            category=category,
            label=label,
            status=cls.FAIL if critical else cls.WARNING,
            detail="No active player pool is available for this check.",
            destination="pages/5_Weekly_Update.py",
            critical=critical,
        )

    @staticmethod
    def _game_key(player: pd.Series) -> str:
        team = str(player.get("team", "")).upper().strip()
        opponent = str(player.get("opponent", "")).upper().strip()
        if not opponent:
            return team
        return " @ ".join(sorted({team, opponent}))

    @staticmethod
    def _stack_record(lineup_number: int, lineup: pd.DataFrame) -> dict[str, Any]:
        positions = lineup.get("position", pd.Series("", index=lineup.index)).astype(str).str.upper()
        quarterbacks = lineup.loc[positions.eq("QB")]
        if quarterbacks.empty:
            return {
                "lineup_number": lineup_number,
                "quarterback": "",
                "qb_team": "",
                "opponent": "",
                "same_team_pass_catchers": 0,
                "opponent_bring_backs": 0,
                "has_qb_stack": False,
                "has_bring_back": False,
            }

        qb = quarterbacks.iloc[0]
        qb_team = str(qb.get("team", "")).upper().strip()
        opponent = str(qb.get("opponent", "")).upper().strip()
        skill_mask = positions.isin(["WR", "TE"])
        bringback_mask = positions.isin(["RB", "WR", "TE"])
        same_team = int((skill_mask & lineup["team"].astype(str).str.upper().eq(qb_team)).sum())
        bring_backs = int((bringback_mask & lineup["team"].astype(str).str.upper().eq(opponent)).sum())
        return {
            "lineup_number": lineup_number,
            "quarterback": str(qb.get("name", "")),
            "qb_team": qb_team,
            "opponent": opponent,
            "same_team_pass_catchers": same_team,
            "opponent_bring_backs": bring_backs,
            "has_qb_stack": same_team >= 1,
            "has_bring_back": bring_backs >= 1,
        }
