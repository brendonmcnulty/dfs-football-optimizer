from __future__ import annotations

import re

import pandas as pd


COLUMN_ALIASES = {
    "player_id": [
        "player_id", "player id", "id", "dk id", "draftkings id",
        "dk_player_id", "draftkings_player_id",
    ],
    "name_plus_id": [
        "name + id", "name+id", "player name + id", "draftkings name + id",
    ],
    "name": [
        "name", "player", "player name", "full name", "athlete",
    ],
    "position": [
        "position", "pos", "roster position", "roster_position",
    ],
    "roster_position": [
        "roster position", "roster_position", "eligible positions",
        "position eligibility",
    ],
    "team": [
        "team", "team abbrev", "teamabbrev", "team_abbrev", "team abbreviation",
    ],
    "opponent": [
        "opponent", "opp", "opponent team",
    ],
    "salary": [
        "salary", "dk salary", "draftkings salary",
    ],
    "game_info": [
        "game info", "game_info", "game", "matchup",
    ],
    "projection": [
        "projection", "proj", "fpts", "fantasy points", "projected points",
        "dk projection", "dk points", "proj fpts", "projected fpts", "median", "mean projection",
    ],
    "ceiling": [
        "ceiling", "ceiling projection", "ceiling_projection", "p90",
        "90th percentile", "upside", "max projection",
    ],
    "floor": [
        "floor", "floor projection", "floor_projection", "p10",
        "10th percentile", "downside", "min projection",
    ],
    "ownership": [
        "ownership", "ownership pct", "ownership %", "ownership percentage",
        "projected ownership", "projected_ownership", "proj own", "own%",
    ],
    "confidence": [
        "confidence", "confidence score", "projection confidence",
    ],
}


def _canonical_column(value: object) -> str:
    text = str(value).strip().lower()
    text = text.replace("%", " pct ")
    text = text.replace("+", " plus ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _alias_lookup(columns: list[object]) -> dict[str, object]:
    return {
        _canonical_column(column): column
        for column in columns
    }


def _find_column(
    columns: list[object],
    aliases: list[str],
) -> object | None:
    lookup = _alias_lookup(columns)
    for alias in aliases:
        found = lookup.get(_canonical_column(alias))
        if found is not None:
            return found
    return None


def _clean_name(value: object) -> str:
    text = str(value).strip()
    return re.sub(r"\s+\(\d+\)$", "", text).strip()


def _clean_player_id(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    match = re.search(r"\((\d+)\)\s*$", text)
    return match.group(1) if match else text


def _opponent_from_game_info(game_info: object, team: object) -> str:
    matchup = str(game_info).split(" ", 1)[0]
    if "@" not in matchup:
        return ""
    away, home = matchup.split("@", 1)
    normalized_team = str(team).upper().strip()
    away = away.upper().strip()
    home = home.upper().strip()
    if normalized_team == away:
        return home
    if normalized_team == home:
        return away
    return ""


def add_derived_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    salary = pd.to_numeric(
        output["salary"],
        errors="coerce",
    ).replace(0, pd.NA)
    projection = pd.to_numeric(
        output["projection"],
        errors="coerce",
    ).fillna(0.0)
    ceiling = pd.to_numeric(
        output["ceiling"],
        errors="coerce",
    ).fillna(projection)
    ownership = pd.to_numeric(
        output["ownership"],
        errors="coerce",
    ).fillna(0.0)

    output["value"] = (
        projection / salary * 1000.0
    ).fillna(0.0)
    output["leverage"] = (
        ceiling / ownership.clip(lower=1.0)
    )
    return output


def normalize_player_pool(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize DraftKings salary files and combined player-pool files."""

    source = frame.copy()
    columns = list(source.columns)
    output = pd.DataFrame(index=source.index)

    for target, aliases in COLUMN_ALIASES.items():
        found = _find_column(columns, aliases)
        if found is not None:
            output[target] = source[found]

    if "name" not in output and "name_plus_id" in output:
        output["name"] = output["name_plus_id"].map(_clean_name)

    required = {"name", "position", "team", "salary"}
    missing = required - set(output.columns)
    if missing:
        raise ValueError(
            "The uploaded file is missing columns that identify "
            f"{sorted(missing)}. Available columns: {columns}"
        )

    output["name"] = output["name"].map(_clean_name)
    output["position"] = (
        output["position"]
        .astype(str)
        .str.upper()
        .str.strip()
        .replace({"D/ST": "DST", "DEF": "DST"})
    )
    output["team"] = (
        output["team"]
        .astype(str)
        .str.upper()
        .str.strip()
    )
    output["salary"] = pd.to_numeric(
        output["salary"],
        errors="coerce",
    )

    if "player_id" in output:
        output["player_id"] = output["player_id"].map(
            _clean_player_id
        )
    elif "name_plus_id" in output:
        output["player_id"] = output["name_plus_id"].map(
            _clean_player_id
        )
    else:
        output["player_id"] = (
            output["name"].astype(str)
            + "_"
            + output["team"].astype(str)
            + "_"
            + output.index.astype(str)
        )

    if "name_plus_id" not in output:
        output["name_plus_id"] = output.apply(
            lambda row: (
                f"{row['name']} ({row['player_id']})"
                if str(row["player_id"]).isdigit()
                else ""
            ),
            axis=1,
        )

    if "roster_position" not in output:
        output["roster_position"] = output["position"]

    if "game_info" not in output:
        output["game_info"] = ""

    if "opponent" not in output:
        output["opponent"] = output.apply(
            lambda row: _opponent_from_game_info(
                row["game_info"],
                row["team"],
            ),
            axis=1,
        )
    else:
        output["opponent"] = (
            output["opponent"]
            .fillna("")
            .astype(str)
            .str.upper()
            .str.strip()
        )

    defaults = {
        "projection": 0.0,
        "ceiling": None,
        "floor": None,
        "ownership": 0.0,
        "confidence": 0.0,
    }
    for column, default in defaults.items():
        if column not in output:
            output[column] = default

    output["projection"] = pd.to_numeric(
        output["projection"],
        errors="coerce",
    ).fillna(0.0)
    output["ceiling"] = pd.to_numeric(
        output["ceiling"],
        errors="coerce",
    ).fillna(output["projection"])
    output["floor"] = pd.to_numeric(
        output["floor"],
        errors="coerce",
    ).fillna(output["projection"])
    output["ownership"] = pd.to_numeric(
        output["ownership"],
        errors="coerce",
    ).fillna(0.0).clip(0.0, 100.0)
    output["confidence"] = pd.to_numeric(
        output["confidence"],
        errors="coerce",
    ).fillna(0.0).clip(0.0, 100.0)

    output = output.dropna(
        subset=["salary"]
    ).copy()
    output["salary"] = output["salary"].astype(int)
    output["locked"] = False
    output["excluded"] = False
    output = add_derived_metrics(output)

    return output[
        [
            "player_id",
            "name_plus_id",
            "name",
            "position",
            "roster_position",
            "team",
            "opponent",
            "salary",
            "game_info",
            "projection",
            "ceiling",
            "floor",
            "value",
            "ownership",
            "leverage",
            "confidence",
            "locked",
            "excluded",
        ]
    ].reset_index(drop=True)


def merge_projections(
    player_pool: pd.DataFrame,
    projections: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge one projection source by DraftKings ID first, then name and team.

    Raises a clear error when the projection file contains duplicate player
    identities that would make matching ambiguous.
    """

    base = player_pool.copy().reset_index(drop=True)
    source = projections.copy().reset_index(drop=True)
    source_columns = list(source.columns)

    id_column = _find_column(
        source_columns,
        COLUMN_ALIASES["player_id"],
    )
    name_column = _find_column(
        source_columns,
        COLUMN_ALIASES["name"],
    )
    team_column = _find_column(
        source_columns,
        COLUMN_ALIASES["team"],
    )
    projection_column = _find_column(
        source_columns,
        COLUMN_ALIASES["projection"],
    )

    if projection_column is None or (
        id_column is None and name_column is None
    ):
        raise ValueError(
            "Projection CSV must contain a projection column and either "
            "a DraftKings player ID or player-name column."
        )

    source["_player_id_key"] = (
        source[id_column].map(_clean_player_id)
        if id_column is not None
        else ""
    )
    source["_name_key"] = (
        source[name_column]
        .map(_clean_name)
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "", regex=True)
        if name_column is not None
        else ""
    )
    source["_team_key"] = (
        source[team_column]
        .astype(str)
        .str.upper()
        .str.strip()
        if team_column is not None
        else ""
    )

    identity = source["_player_id_key"].where(
        source["_player_id_key"].astype(str).ne(""),
        source["_name_key"].astype(str)
        + "|"
        + source["_team_key"].astype(str),
    )
    duplicate_mask = identity.duplicated(keep=False) & identity.ne("|")
    if duplicate_mask.any():
        raise ValueError(
            "Projection CSV contains duplicate player identities. "
            "Remove or consolidate duplicate rows before importing."
        )

    metric_columns: dict[str, object] = {
        "projection": projection_column,
    }
    for metric in ("ceiling", "floor", "ownership"):
        found = _find_column(
            source_columns,
            COLUMN_ALIASES[metric],
        )
        if found is not None:
            metric_columns[metric] = found

    base["_player_id_key"] = base["player_id"].map(
        _clean_player_id
    )
    base["_name_key"] = (
        base["name"]
        .map(_clean_name)
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "", regex=True)
    )
    base["_team_key"] = (
        base["team"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    id_lookup = {
        str(row["_player_id_key"]): index
        for index, row in base.iterrows()
        if str(row["_player_id_key"])
    }
    name_team_lookup: dict[tuple[str, str], list[int]] = {}
    for index, row in base.iterrows():
        key = (
            str(row["_name_key"]),
            str(row["_team_key"]),
        )
        name_team_lookup.setdefault(key, []).append(index)

    for _, source_row in source.iterrows():
        base_index = None
        player_id = str(source_row["_player_id_key"])
        if player_id and player_id in id_lookup:
            base_index = id_lookup[player_id]
        else:
            key = (
                str(source_row["_name_key"]),
                str(source_row["_team_key"]),
            )
            candidates = name_team_lookup.get(key, [])
            if len(candidates) == 1:
                base_index = candidates[0]

        if base_index is None:
            continue

        for metric, source_column in metric_columns.items():
            value = pd.to_numeric(
                pd.Series([source_row[source_column]]),
                errors="coerce",
            ).iloc[0]
            if pd.notna(value):
                base.at[base_index, metric] = float(value)

    base["ceiling"] = pd.to_numeric(
        base["ceiling"],
        errors="coerce",
    ).fillna(base["projection"])
    base["floor"] = pd.to_numeric(
        base["floor"],
        errors="coerce",
    ).fillna(base["projection"])
    base["ownership"] = pd.to_numeric(
        base["ownership"],
        errors="coerce",
    ).fillna(0.0).clip(0.0, 100.0)

    return add_derived_metrics(
        base.drop(
            columns=[
                "_player_id_key",
                "_name_key",
                "_team_key",
            ]
        )
    )
