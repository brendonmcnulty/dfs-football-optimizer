from __future__ import annotations

import re

import pandas as pd


COLUMN_ALIASES = {
    "player_id": ["player_id", "id", "ID"],
    "name": ["name", "Name", "player", "Player", "Name + ID"],
    "position": ["position", "Position", "pos", "Pos"],
    "team": ["team", "Team", "team_abbrev", "TeamAbbrev"],
    "opponent": ["opponent", "Opponent", "opp", "Opp"],
    "salary": ["salary", "Salary"],
    "projection": ["projection", "Projection", "proj", "Proj", "fpts", "FPTS"],
}


def _find_column(columns: list[str], aliases: list[str]) -> str | None:
    for alias in aliases:
        if alias in columns:
            return alias
    return None


def _clean_name(value: object) -> str:
    text = str(value).strip()
    # DraftKings "Name + ID" values often look like "Player Name (12345678)".
    return re.sub(r"\s+\(\d+\)$", "", text).strip()


def normalize_player_pool(frame: pd.DataFrame) -> pd.DataFrame:
    source = frame.copy()
    columns = list(source.columns)
    output = pd.DataFrame(index=source.index)

    for target, aliases in COLUMN_ALIASES.items():
        found = _find_column(columns, aliases)
        if found is not None:
            output[target] = source[found]

    required_without_projection = {
        "name",
        "position",
        "team",
        "salary",
    }
    missing = required_without_projection - set(output.columns)
    if missing:
        raise ValueError(
            "The uploaded file is missing columns that identify "
            f"{sorted(missing)}. Available columns: {columns}"
        )

    output["name"] = output["name"].map(_clean_name)
    output["position"] = output["position"].astype(str).str.upper().str.strip()
    output["position"] = output["position"].replace(
        {"D/ST": "DST", "DEF": "DST"}
    )
    output["team"] = output["team"].astype(str).str.upper().str.strip()
    output["salary"] = pd.to_numeric(output["salary"], errors="coerce")

    if "player_id" not in output:
        output["player_id"] = (
            output["name"].astype(str)
            + "_"
            + output["team"].astype(str)
            + "_"
            + output.index.astype(str)
        )

    if "opponent" not in output:
        output["opponent"] = ""

    if "projection" not in output:
        output["projection"] = 0.0

    output["projection"] = pd.to_numeric(
        output["projection"], errors="coerce"
    ).fillna(0.0)

    output = output.dropna(subset=["salary"]).copy()
    output["salary"] = output["salary"].astype(int)
    output["locked"] = False
    output["excluded"] = False

    return output[
        [
            "player_id",
            "name",
            "position",
            "team",
            "opponent",
            "salary",
            "projection",
            "locked",
            "excluded",
        ]
    ].reset_index(drop=True)


def merge_projections(
    player_pool: pd.DataFrame,
    projections: pd.DataFrame,
) -> pd.DataFrame:
    projection_columns = list(projections.columns)
    name_column = _find_column(
        projection_columns, COLUMN_ALIASES["name"]
    )
    projection_column = _find_column(
        projection_columns, COLUMN_ALIASES["projection"]
    )

    if name_column is None or projection_column is None:
        raise ValueError(
            "Projection CSV must contain a player-name column and a "
            "projection column."
        )

    projection_table = projections[[name_column, projection_column]].copy()
    projection_table.columns = ["name", "uploaded_projection"]
    projection_table["name"] = projection_table["name"].map(_clean_name)
    projection_table["uploaded_projection"] = pd.to_numeric(
        projection_table["uploaded_projection"], errors="coerce"
    )

    merged = player_pool.drop(columns=["projection"]).merge(
        projection_table,
        on="name",
        how="left",
    )
    merged["projection"] = merged["uploaded_projection"].fillna(0.0)
    merged = merged.drop(columns=["uploaded_projection"])
    return merged
