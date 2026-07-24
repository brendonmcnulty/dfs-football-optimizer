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
    "ceiling": [
        "ceiling", "Ceiling", "ceiling_projection", "Ceiling Projection",
        "p90", "P90", "90th Percentile",
    ],
    "floor": [
        "floor", "Floor", "floor_projection", "Floor Projection",
        "p10", "P10", "10th Percentile",
    ],
    "ownership": [
        "ownership", "Ownership", "ownership_pct", "Ownership %",
        "Projected Ownership", "projected_ownership",
    ],
}


def _find_column(columns: list[str], aliases: list[str]) -> str | None:
    for alias in aliases:
        if alias in columns:
            return alias
    return None


def _clean_name(value: object) -> str:
    text = str(value).strip()
    return re.sub(r"\s+\(\d+\)$", "", text).strip()


def add_derived_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    salary = pd.to_numeric(output["salary"], errors="coerce").replace(0, pd.NA)
    projection = pd.to_numeric(output["projection"], errors="coerce").fillna(0.0)
    ceiling = pd.to_numeric(output["ceiling"], errors="coerce").fillna(projection)
    ownership = pd.to_numeric(output["ownership"], errors="coerce").fillna(0.0)

    output["value"] = (projection / salary * 1000.0).fillna(0.0)
    output["leverage"] = ceiling / ownership.clip(lower=1.0)
    return output


def normalize_player_pool(frame: pd.DataFrame) -> pd.DataFrame:
    source = frame.copy()
    columns = list(source.columns)
    output = pd.DataFrame(index=source.index)

    for target, aliases in COLUMN_ALIASES.items():
        found = _find_column(columns, aliases)
        if found is not None:
            output[target] = source[found]

    required_without_projection = {"name", "position", "team", "salary"}
    missing = required_without_projection - set(output.columns)
    if missing:
        raise ValueError(
            "The uploaded file is missing columns that identify "
            f"{sorted(missing)}. Available columns: {columns}"
        )

    output["name"] = output["name"].map(_clean_name)
    output["position"] = output["position"].astype(str).str.upper().str.strip()
    output["position"] = output["position"].replace({"D/ST": "DST", "DEF": "DST"})
    output["team"] = output["team"].astype(str).str.upper().str.strip()
    output["salary"] = pd.to_numeric(output["salary"], errors="coerce")

    if "player_id" not in output:
        output["player_id"] = (
            output["name"].astype(str) + "_" + output["team"].astype(str)
            + "_" + output.index.astype(str)
        )
    if "opponent" not in output:
        output["opponent"] = ""
    if "projection" not in output:
        output["projection"] = 0.0

    output["projection"] = pd.to_numeric(output["projection"], errors="coerce").fillna(0.0)

    if "ceiling" not in output:
        output["ceiling"] = output["projection"]
    if "floor" not in output:
        output["floor"] = output["projection"]
    if "ownership" not in output:
        output["ownership"] = 0.0

    output["ceiling"] = pd.to_numeric(output["ceiling"], errors="coerce").fillna(output["projection"])
    output["floor"] = pd.to_numeric(output["floor"], errors="coerce").fillna(output["projection"])
    output["ownership"] = pd.to_numeric(output["ownership"], errors="coerce").fillna(0.0).clip(0.0, 100.0)

    output = output.dropna(subset=["salary"]).copy()
    output["salary"] = output["salary"].astype(int)
    output["locked"] = False
    output["excluded"] = False
    output = add_derived_metrics(output)

    return output[[
        "player_id", "name", "position", "team", "opponent", "salary",
        "projection", "ceiling", "floor", "value", "ownership", "leverage",
        "locked", "excluded",
    ]].reset_index(drop=True)


def merge_projections(player_pool: pd.DataFrame, projections: pd.DataFrame) -> pd.DataFrame:
    projection_columns = list(projections.columns)
    name_column = _find_column(projection_columns, COLUMN_ALIASES["name"])
    projection_column = _find_column(projection_columns, COLUMN_ALIASES["projection"])
    if name_column is None or projection_column is None:
        raise ValueError(
            "Projection CSV must contain a player-name column and a projection column."
        )

    optional = {}
    for target in ("ceiling", "floor", "ownership"):
        found = _find_column(projection_columns, COLUMN_ALIASES[target])
        if found is not None:
            optional[target] = found

    selected = [name_column, projection_column, *optional.values()]
    table = projections[selected].copy()
    table.columns = ["name", "uploaded_projection", *[f"uploaded_{k}" for k in optional]]
    table["name"] = table["name"].map(_clean_name)
    for column in table.columns:
        if column != "name":
            table[column] = pd.to_numeric(table[column], errors="coerce")

    drop_columns = [c for c in ("projection", "ceiling", "floor", "ownership", "value", "leverage") if c in player_pool.columns]
    merged = player_pool.drop(columns=drop_columns).merge(table, on="name", how="left")
    merged["projection"] = merged["uploaded_projection"].fillna(0.0)
    merged["ceiling"] = merged.get("uploaded_ceiling", merged["projection"]).fillna(merged["projection"])
    merged["floor"] = merged.get("uploaded_floor", merged["projection"]).fillna(merged["projection"])
    merged["ownership"] = merged.get("uploaded_ownership", pd.Series(0.0, index=merged.index)).fillna(0.0).clip(0.0, 100.0)
    merged = merged.drop(columns=[c for c in merged.columns if c.startswith("uploaded_")])
    return add_derived_metrics(merged)
