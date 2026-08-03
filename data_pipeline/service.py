from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

import pandas as pd

from data_loader import (
    COLUMN_ALIASES,
    _find_column,
    add_derived_metrics,
    normalize_player_pool,
)


METRIC_COLUMNS = (
    "projection",
    "ceiling",
    "floor",
    "ownership",
)

IDENTITY_ALIASES = {
    "player_id": COLUMN_ALIASES["player_id"],
    "name": COLUMN_ALIASES["name"],
    "team": COLUMN_ALIASES["team"],
}


@dataclass(frozen=True)
class DataSourceInput:
    """One projection or ownership source used during a weekly update."""

    name: str
    frame: pd.DataFrame


@dataclass(frozen=True)
class PipelineResult:
    """Output from one weekly data-pipeline run."""

    player_pool: pd.DataFrame
    coverage_report: pd.DataFrame
    source_report: pd.DataFrame
    unmatched_report: pd.DataFrame
    duplicate_report: pd.DataFrame


def _clean_player_id(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    match = re.search(r"\((\d+)\)\s*$", text)
    return match.group(1) if match else text


def _clean_player_name(value: object) -> str:
    text = str(value).strip()
    text = re.sub(r"\s+\(\d+\)$", "", text)
    text = re.sub(r"[^a-zA-Z0-9 ]+", " ", text)
    return " ".join(text.lower().split())


def _clean_team(value: object) -> str:
    return str(value).upper().strip()


def _normalize_source(
    source: DataSourceInput,
) -> pd.DataFrame:
    frame = source.frame.copy().reset_index(drop=True)
    columns = list(frame.columns)

    output = pd.DataFrame(index=frame.index)

    for target, aliases in IDENTITY_ALIASES.items():
        found = _find_column(columns, aliases)
        if found is not None:
            output[target] = frame[found]

    if "name" not in output.columns and "player_id" not in output.columns:
        raise ValueError(
            f"{source.name} must contain a player-name or player-ID column."
        )

    found_metrics: list[str] = []
    for metric in METRIC_COLUMNS:
        found = _find_column(columns, COLUMN_ALIASES[metric])
        if found is not None:
            output[metric] = pd.to_numeric(
                frame[found],
                errors="coerce",
            )
            found_metrics.append(metric)

    if not found_metrics:
        raise ValueError(
            f"{source.name} does not contain projection, ceiling, floor, "
            "or ownership data."
        )

    output["player_id"] = (
        output["player_id"].map(_clean_player_id)
        if "player_id" in output.columns
        else ""
    )
    output["original_name"] = (
        output["name"].astype(str).str.strip()
        if "name" in output.columns
        else ""
    )
    output["name_key"] = (
        output["name"].map(_clean_player_name)
        if "name" in output.columns
        else ""
    )
    output["team_key"] = (
        output["team"].map(_clean_team)
        if "team" in output.columns
        else ""
    )
    output["source_name"] = source.name.strip() or "Unnamed source"
    output["source_row"] = output.index.astype(int) + 2

    output["identity_key"] = output["player_id"].where(
        output["player_id"].astype(str).ne(""),
        output["name_key"].astype(str)
        + "|"
        + output["team_key"].astype(str),
    )

    return output.reset_index(drop=True)


def _build_base_match_keys(
    player_pool: pd.DataFrame,
) -> pd.DataFrame:
    keyed = player_pool.copy().reset_index(drop=True)
    keyed["_base_index"] = keyed.index
    keyed["_player_id_key"] = keyed["player_id"].map(
        _clean_player_id
    )
    keyed["_name_key"] = keyed["name"].map(
        _clean_player_name
    )
    keyed["_team_key"] = keyed["team"].map(
        _clean_team
    )
    return keyed


def _match_source_row(
    row: pd.Series,
    base: pd.DataFrame,
) -> tuple[int | None, str]:
    player_id = str(row.get("player_id", "")).strip()
    name_key = str(row.get("name_key", "")).strip()
    team_key = str(row.get("team_key", "")).strip()

    if player_id:
        candidates = base.loc[
            base["_player_id_key"] == player_id,
            "_base_index",
        ]
        if len(candidates) == 1:
            return int(candidates.iloc[0]), "player_id"
        if len(candidates) > 1:
            return None, "duplicate_base_id"

    if name_key and team_key:
        candidates = base.loc[
            (base["_name_key"] == name_key)
            & (base["_team_key"] == team_key),
            "_base_index",
        ]
        if len(candidates) == 1:
            return int(candidates.iloc[0]), "name_team"
        if len(candidates) > 1:
            return None, "duplicate_base_name_team"

    if name_key:
        candidates = base.loc[
            base["_name_key"] == name_key,
            "_base_index",
        ]
        if len(candidates) == 1:
            return int(candidates.iloc[0]), "unique_name"
        if len(candidates) > 1:
            return None, "ambiguous_name"

    return None, "unmatched"


class WeeklyDataPipeline:
    """Combine a DraftKings salary file with projection and ownership sources."""

    def run(
        self,
        salary_frame: pd.DataFrame,
        data_sources: Iterable[DataSourceInput],
        aggregation: str = "mean",
    ) -> PipelineResult:
        if aggregation not in {"mean", "median", "first"}:
            raise ValueError(
                "Aggregation must be mean, median, or first."
            )

        player_pool = normalize_player_pool(
            salary_frame
        )
        base = _build_base_match_keys(
            player_pool
        )
        sources = list(data_sources)

        contributions: list[dict[str, object]] = []
        source_summary: list[dict[str, object]] = []
        unmatched_rows: list[dict[str, object]] = []
        duplicate_rows: list[dict[str, object]] = []

        for source in sources:
            normalized = _normalize_source(source)

            duplicate_mask = (
                normalized["identity_key"].duplicated(
                    keep=False
                )
                & normalized["identity_key"].astype(str).ne("|")
                & normalized["identity_key"].astype(str).ne("")
            )
            for _, duplicate in normalized.loc[
                duplicate_mask
            ].iterrows():
                duplicate_rows.append(
                    {
                        "source": duplicate["source_name"],
                        "source_row": int(duplicate["source_row"]),
                        "player_id": duplicate["player_id"],
                        "name": duplicate["original_name"],
                        "team": duplicate["team_key"],
                        "identity_key": duplicate["identity_key"],
                        "reason": "Duplicate source identity",
                    }
                )

            normalized = normalized.loc[
                ~duplicate_mask
            ].copy()

            matched_count = 0
            id_matches = 0
            name_team_matches = 0
            unique_name_matches = 0

            for _, row in normalized.iterrows():
                base_index, match_method = _match_source_row(
                    row,
                    base,
                )

                if base_index is None:
                    unmatched_rows.append(
                        {
                            "source": row["source_name"],
                            "source_row": int(row["source_row"]),
                            "player_id": row.get("player_id", ""),
                            "name": row.get("original_name", ""),
                            "team": row.get("team_key", ""),
                            "reason": match_method.replace("_", " "),
                        }
                    )
                    continue

                matched_count += 1
                if match_method == "player_id":
                    id_matches += 1
                elif match_method == "name_team":
                    name_team_matches += 1
                elif match_method == "unique_name":
                    unique_name_matches += 1

                for metric in METRIC_COLUMNS:
                    value = row.get(metric)
                    if pd.notna(value):
                        contributions.append(
                            {
                                "base_index": int(base_index),
                                "metric": metric,
                                "value": float(value),
                                "source": row["source_name"],
                                "match_method": match_method,
                            }
                        )

            original_rows = len(source.frame)
            duplicate_count = int(duplicate_mask.sum())

            source_summary.append(
                {
                    "source": source.name,
                    "rows": original_rows,
                    "usable_rows": len(normalized),
                    "matched_rows": matched_count,
                    "unmatched_rows": len(normalized) - matched_count,
                    "duplicate_rows": duplicate_count,
                    "id_matches": id_matches,
                    "name_team_matches": name_team_matches,
                    "unique_name_matches": unique_name_matches,
                    "match_rate": (
                        matched_count / len(normalized)
                        if len(normalized)
                        else 0.0
                    ),
                }
            )

        contribution_frame = pd.DataFrame(
            contributions
        )

        if not contribution_frame.empty:
            if aggregation == "mean":
                aggregated = contribution_frame.groupby(
                    ["base_index", "metric"],
                    as_index=False,
                )["value"].mean()
            elif aggregation == "median":
                aggregated = contribution_frame.groupby(
                    ["base_index", "metric"],
                    as_index=False,
                )["value"].median()
            else:
                aggregated = contribution_frame.drop_duplicates(
                    subset=["base_index", "metric"],
                    keep="first",
                )[
                    ["base_index", "metric", "value"]
                ]

            metric_table = aggregated.pivot(
                index="base_index",
                columns="metric",
                values="value",
            )

            for metric in METRIC_COLUMNS:
                if metric in metric_table.columns:
                    player_pool.loc[
                        metric_table.index,
                        metric,
                    ] = metric_table[metric]

        player_pool["projection"] = pd.to_numeric(
            player_pool["projection"],
            errors="coerce",
        ).fillna(0.0)
        player_pool["ceiling"] = pd.to_numeric(
            player_pool["ceiling"],
            errors="coerce",
        ).fillna(player_pool["projection"])
        player_pool["floor"] = pd.to_numeric(
            player_pool["floor"],
            errors="coerce",
        ).fillna(player_pool["projection"])
        player_pool["ownership"] = pd.to_numeric(
            player_pool["ownership"],
            errors="coerce",
        ).fillna(0.0).clip(0.0, 100.0)
        player_pool = add_derived_metrics(
            player_pool
        )

        coverage_records: list[dict[str, object]] = []
        for metric in METRIC_COLUMNS:
            if contribution_frame.empty:
                covered_indexes: set[int] = set()
            else:
                covered_indexes = set(
                    contribution_frame.loc[
                        contribution_frame["metric"] == metric,
                        "base_index",
                    ].astype(int)
                )

            covered = len(covered_indexes)
            coverage_records.append(
                {
                    "metric": metric.title(),
                    "players_covered": covered,
                    "total_players": len(player_pool),
                    "coverage": (
                        covered / len(player_pool)
                        if len(player_pool)
                        else 0.0
                    ),
                }
            )

        return PipelineResult(
            player_pool=player_pool,
            coverage_report=pd.DataFrame(
                coverage_records
            ),
            source_report=pd.DataFrame(
                source_summary
            ),
            unmatched_report=pd.DataFrame(
                unmatched_rows
            ),
            duplicate_report=pd.DataFrame(
                duplicate_rows
            ),
        )
