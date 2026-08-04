from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from config import SALARY_CAP
from core.contest_presets import (
    CONTEST_STRATEGY_PRESETS,
    get_contest_strategy_preset,
)
from core.settings import OptimizerSettings
from database import DatabaseManager
from data_loader import add_derived_metrics
from services import OptimizerService, PlayerPoolService


def _apply_contest_preset(
    preset_key: str,
    player_ids: list[str],
    teams: list[str],
) -> None:
    """Apply one contest preset to editable Streamlit state."""

    preset = get_contest_strategy_preset(preset_key)

    settings = {
        "minimum_salary": preset.minimum_salary,
        "lineup_count": preset.lineup_count,
        "minimum_unique_players": preset.minimum_unique_players,
        "qb_stack_size": preset.qb_stack_size,
        "require_bring_back": preset.require_bring_back,
        "maximum_players_per_team": preset.maximum_players_per_team,
        "minimum_players_from_primary_game": (
            preset.minimum_players_from_primary_game
        ),
        "maximum_players_per_game": preset.maximum_players_per_game,
        "optimization_target": preset.optimization_target,
        "limit_total_ownership": preset.limit_total_ownership,
        "maximum_total_ownership": (
            preset.maximum_total_ownership
            if preset.maximum_total_ownership is not None
            else 150.0
        ),
        "block_dst_opposing_qb": True,
        "block_dst_opposing_wr": True,
        "block_dst_opposing_rb": False,
        "block_dst_opposing_te": False,
    }

    for key, value in settings.items():
        st.session_state[key] = value

    st.session_state.player_max_exposures = {
        str(player_id): preset.default_player_max_exposure
        for player_id in player_ids
    }
    st.session_state.team_max_exposures = {
        str(team).upper(): 1.0
        for team in teams
    }

    for editor_key in (
        "maximum_exposure_editor",
        "team_exposure_editor",
    ):
        st.session_state.pop(editor_key, None)

    for generated_key in tuple(st.session_state):
        if str(generated_key).startswith("generated_"):
            st.session_state.pop(generated_key, None)

    st.session_state.applied_contest_preset = preset.key
    st.session_state.applied_contest_preset_label = preset.label



st.set_page_config(
    page_title="Optimizer",
    page_icon="⚙️",
    layout="wide",
)

database = DatabaseManager()
optimizer_service = OptimizerService()
player_pool_service = PlayerPoolService()

st.title("⚙️ Lineup Optimizer")
st.caption(
    "Generate unique DraftKings NFL Classic lineups "
    "with exposure, correlation, and ownership controls"
)

if not player_pool_service.has_active_pool(st.session_state):
    st.warning(
        "No player pool is currently loaded. Import a CSV from the "
        "**Player Pool** page or load a slate from **Saved Slates**."
    )
    st.stop()

players = player_pool_service.get_active_pool(st.session_state)
if "ceiling" not in players.columns:
    players["ceiling"] = players["projection"]
if "floor" not in players.columns:
    players["floor"] = players["projection"]
if "ownership" not in players.columns:
    players["ownership"] = 0.0
players = add_derived_metrics(players)
player_pool_service.update_active_pool(
    st.session_state,
    players,
    source="Optimizer normalization",
)

active_metadata = player_pool_service.get_metadata(st.session_state)
active_slate_name = active_metadata.active_slate_name
active_slate_id = active_metadata.active_slate_id

st.subheader("Active slate")
st.write(f"**{active_slate_name}**")

if active_slate_id is None:
    st.warning(
        "This player pool has not been saved to the database. "
        "You may generate lineups, but the slate must be saved "
        "before a lineup can be stored."
    )

with st.sidebar:
    st.header("Optimizer settings")

    st.subheader("Contest strategy preset")

    preset_options = ["custom", *CONTEST_STRATEGY_PRESETS.keys()]
    selected_preset = st.selectbox(
        "Contest strategy",
        options=preset_options,
        key="contest_strategy_preset_selector",
        format_func=lambda value: (
            "Custom"
            if value == "custom"
            else CONTEST_STRATEGY_PRESETS[value].label
        ),
        help=(
            "Choose a contest type, review the recommended defaults, then "
            "apply them. Every setting remains editable afterward."
        ),
    )

    if selected_preset == "custom":
        st.caption(
            "Custom leaves the current optimizer settings unchanged."
        )
    else:
        preset_preview = CONTEST_STRATEGY_PRESETS[selected_preset]
        st.info(preset_preview.description)

        with st.expander("Preview preset settings", expanded=False):
            for setting_name, setting_value in preset_preview.summary_rows:
                st.write(f"**{setting_name}:** {setting_value}")

        if st.button(
            "Apply contest preset",
            type="primary",
            use_container_width=True,
            key="apply_contest_preset",
        ):
            _apply_contest_preset(
                selected_preset,
                players["player_id"].astype(str).tolist(),
                players["team"].astype(str).unique().tolist(),
            )
            st.rerun()

    applied_preset_label = st.session_state.get(
        "applied_contest_preset_label"
    )
    if applied_preset_label:
        st.success(
            f"Applied preset: {applied_preset_label}. "
            "Any control can now be customized."
        )

    st.markdown("---")

    salary_cap = st.number_input(
        "Salary cap",
        min_value=1,
        value=int(
            st.session_state.get(
                "salary_cap",
                SALARY_CAP,
            )
        ),
        step=500,
        key="salary_cap",
    )

    saved_minimum_salary = int(
        st.session_state.get(
            "minimum_salary",
            max(int(salary_cap) - 1000, 0),
        )
    )

    minimum_salary = st.number_input(
        "Minimum salary to use",
        min_value=0,
        max_value=int(salary_cap),
        value=min(
            saved_minimum_salary,
            int(salary_cap),
        ),
        step=100,
        key="minimum_salary",
    )

    lineup_count = st.number_input(
        "Number of lineups",
        min_value=1,
        max_value=150,
        value=int(
            st.session_state.get(
                "lineup_count",
                5,
            )
        ),
        step=1,
        key="lineup_count",
    )

    minimum_unique_players = st.slider(
        "Minimum unique players",
        min_value=1,
        max_value=9,
        value=int(
            st.session_state.get(
                "minimum_unique_players",
                1,
            )
        ),
        help=(
            "Each generated lineup must differ from every earlier "
            "lineup by at least this many players."
        ),
        key="minimum_unique_players",
    )

    qb_stack_size = st.selectbox(
        "QB stacking",
        options=[
            0,
            1,
            2,
        ],
        index=[
            0,
            1,
            2,
        ].index(
            int(
                st.session_state.get(
                    "qb_stack_size",
                    0,
                )
            )
        ),
        format_func=lambda stack_size: (
            "Off"
            if stack_size == 0
            else f"QB +{stack_size}"
        ),
        help=(
            "Require the selected quarterback to be paired with "
            "one or two same-team WR/TE pass catchers."
        ),
        key="qb_stack_size",
    )

    require_bring_back = st.checkbox(
        "Require opponent bring-back",
        value=bool(
            st.session_state.get(
                "require_bring_back",
                False,
            )
        ),
        help=(
            "Require at least one opposing RB, WR, or TE "
            "for the selected quarterback."
        ),
        key="require_bring_back",
    )

    maximum_players_per_team = st.selectbox(
        "Maximum players per team",
        options=[None, 3, 4, 5],
        index=[None, 3, 4, 5].index(
            st.session_state.get(
                "maximum_players_per_team",
                None,
            )
        ),
        format_func=lambda value: (
            "No limit" if value is None else str(value)
        ),
        help=(
            "Limit how many players from the same NFL team may "
            "appear in one lineup."
        ),
        key="maximum_players_per_team",
    )

    st.subheader("Defense correlation")

    block_opposing_qb = st.checkbox(
        "Block opposing QB",
        value=bool(
            st.session_state.get(
                "block_dst_opposing_qb",
                True,
            )
        ),
        key="block_dst_opposing_qb",
    )

    block_opposing_wr = st.checkbox(
        "Block opposing WR",
        value=bool(
            st.session_state.get(
                "block_dst_opposing_wr",
                True,
            )
        ),
        key="block_dst_opposing_wr",
    )

    block_opposing_rb = st.checkbox(
        "Block opposing RB",
        value=bool(
            st.session_state.get(
                "block_dst_opposing_rb",
                False,
            )
        ),
        key="block_dst_opposing_rb",
    )

    block_opposing_te = st.checkbox(
        "Block opposing TE",
        value=bool(
            st.session_state.get(
                "block_dst_opposing_te",
                False,
            )
        ),
        key="block_dst_opposing_te",
    )

    st.subheader("Game stacking")

    minimum_players_from_primary_game = st.selectbox(
        "Minimum players from primary game",
        options=[None, 3, 4, 5],
        index=[None, 3, 4, 5].index(
            st.session_state.get(
                "minimum_players_from_primary_game",
                None,
            )
        ),
        format_func=lambda value: (
            "Off" if value is None else str(value)
        ),
        help=(
            "Require at least one game to supply this many players "
            "to every generated lineup."
        ),
        key="minimum_players_from_primary_game",
    )

    maximum_players_per_game = st.selectbox(
        "Maximum players from one game",
        options=[None, 5, 6],
        index=[None, 5, 6].index(
            st.session_state.get(
                "maximum_players_per_game",
                None,
            )
        ),
        format_func=lambda value: (
            "No limit" if value is None else str(value)
        ),
        help=(
            "Limit the total players drawn from either side of the "
            "same NFL game."
        ),
        key="maximum_players_per_game",
    )

    st.subheader("Optimization strategy")

    optimization_options = [
        "projection",
        "ceiling",
        "floor",
        "balanced",
        "cash",
        "single_entry",
        "large_field_gpp",
        "custom",
    ]
    optimization_target = st.selectbox(
        "Strategy",
        options=optimization_options,
        index=optimization_options.index(
            st.session_state.get("optimization_target", "projection")
        ),
        format_func=lambda value: {
            "projection": "Projection",
            "ceiling": "Ceiling",
            "floor": "Floor",
            "balanced": "Balanced",
            "cash": "Cash",
            "single_entry": "Single Entry",
            "large_field_gpp": "Large-Field GPP",
            "custom": "Custom Formula",
        }[value],
        help=(
            "Choose a ready-made contest strategy or build your own "
            "weighted optimization formula."
        ),
        key="optimization_target",
    )
    preset_weights = {
        "projection": (100, 0, 0, 0, 0),
        "ceiling": (0, 100, 0, 0, 0),
        "floor": (0, 0, 100, 0, 0),
        "balanced": (40, 40, 0, 20, 0),
        "cash": (55, 0, 35, 10, 0),
        "single_entry": (40, 35, 5, 10, 10),
        "large_field_gpp": (20, 45, 0, 10, 25),
    }

    if optimization_target == "custom":
        st.caption("Custom weights must total exactly 100%.")
        projection_weight = st.slider(
            "Projection weight",
            0,
            100,
            int(st.session_state.get("projection_weight", 35)),
        )
        ceiling_weight = st.slider(
            "Ceiling weight",
            0,
            100,
            int(st.session_state.get("ceiling_weight", 35)),
        )
        floor_weight = st.slider(
            "Floor weight",
            0,
            100,
            int(st.session_state.get("floor_weight", 10)),
        )
        value_weight = st.slider(
            "Value weight",
            0,
            100,
            int(st.session_state.get("value_weight", 10)),
        )
        leverage_weight = st.slider(
            "Leverage weight",
            0,
            100,
            int(st.session_state.get("leverage_weight", 10)),
        )
        custom_weight_total = (
            projection_weight
            + ceiling_weight
            + floor_weight
            + value_weight
            + leverage_weight
        )
        if custom_weight_total == 100:
            st.success("Custom weight total: 100%")
        else:
            st.error(f"Custom weight total: {custom_weight_total}%")
    else:
        (
            projection_weight,
            ceiling_weight,
            floor_weight,
            value_weight,
            leverage_weight,
        ) = preset_weights[optimization_target]
        st.caption(
            "Weights: "
            f"Projection {projection_weight}% · "
            f"Ceiling {ceiling_weight}% · "
            f"Floor {floor_weight}% · "
            f"Value {value_weight}% · "
            f"Leverage {leverage_weight}%"
        )

    st.session_state.projection_weight = int(projection_weight)
    st.session_state.ceiling_weight = int(ceiling_weight)
    st.session_state.floor_weight = int(floor_weight)
    st.session_state.value_weight = int(value_weight)
    st.session_state.leverage_weight = int(leverage_weight)

    st.subheader("Ownership")

    limit_total_ownership = st.checkbox(
        "Limit total projected ownership",
        value=bool(
            st.session_state.get(
                "limit_total_ownership",
                False,
            )
        ),
        help=(
            "Cap the sum of projected ownership percentages across "
            "the nine selected players."
        ),
        key="limit_total_ownership",
    )

    maximum_total_ownership = None
    if limit_total_ownership:
        maximum_total_ownership = st.number_input(
            "Maximum total ownership",
            min_value=0.0,
            max_value=900.0,
            value=float(
                st.session_state.get(
                    "maximum_total_ownership",
                    150.0,
                )
            ),
            step=5.0,
            format="%.1f",
            help=(
                "Example: 150 means the nine-player lineup may sum "
                "to no more than 150% projected ownership."
            ),
            key="maximum_total_ownership",
        )

blocked_dst_opposing_positions = tuple(
    position
    for position, is_blocked in {
        "QB": block_opposing_qb,
        "WR": block_opposing_wr,
        "RB": block_opposing_rb,
        "TE": block_opposing_te,
    }.items()
    if is_blocked
)

optimizer_settings = OptimizerSettings(
    salary_cap=int(salary_cap),
    minimum_salary=int(minimum_salary),
    lineup_count=int(lineup_count),
    minimum_unique_players=int(
        minimum_unique_players
    ),
    qb_stack_size=int(
        qb_stack_size
    ),
    require_bring_back=bool(
        require_bring_back
    ),
    maximum_players_per_team=(
        maximum_players_per_team
    ),
    blocked_dst_opposing_positions=(
        blocked_dst_opposing_positions
    ),
    minimum_players_from_primary_game=(
        minimum_players_from_primary_game
    ),
    maximum_players_per_game=maximum_players_per_game,
    maximum_total_ownership=maximum_total_ownership,
    optimization_target=optimization_target,
    projection_weight=float(projection_weight),
    ceiling_weight=float(ceiling_weight),
    floor_weight=float(floor_weight),
    value_weight=float(value_weight),
    leverage_weight=float(leverage_weight),
)

st.subheader("Player-pool summary")

metric_column_1, metric_column_2, metric_column_3, metric_column_4 = (
    st.columns(4)
)

metric_column_1.metric(
    "Players",
    len(players),
)

metric_column_2.metric(
    "Positive projections",
    int(
        (
            players["projection"] > 0
        ).sum()
    ),
)

metric_column_3.metric(
    "Locked",
    int(
        players["locked"].sum()
    ),
)

metric_column_4.metric(
    "Excluded",
    int(
        players["excluded"].sum()
    ),
)

readiness_report = optimizer_service.assess_projection_readiness(
    players=players,
    settings=optimizer_settings,
)

if readiness_report.is_ready:
    st.success(
        "Projection readiness passed: "
        f"{readiness_report.positive_projection_count} of "
        f"{readiness_report.eligible_player_count} eligible players "
        "have positive projections."
    )
else:
    st.error(
        "Optimization is blocked until the projection issues below are fixed."
    )
    for issue in readiness_report.critical_errors:
        st.write(f"- {issue}")
    st.page_link(
        "pages/5_Weekly_Update.py",
        label="Open Weekly Update to import or generate projections",
        icon="🔄",
    )

for warning in readiness_report.warnings:
    st.warning(warning)

with st.expander(
    "Review active player pool"
):
    st.dataframe(
        players[
            [
                "name",
                "position",
                "team",
                "opponent",
                "salary",
                "projection",
                "ceiling",
                "floor",
                "value",
                "ownership",
                "leverage",
                "locked",
                "excluded",
            ]
        ],
        width="stretch",
        hide_index=True,
    )

st.markdown("---")
st.subheader("Maximum player exposure")

st.caption(
    "Set the maximum percentage of generated lineups in which each "
    "player may appear. Locked players must remain at 100%."
)

default_exposure_table = players[
    [
        "player_id",
        "name",
        "position",
        "team",
        "salary",
        "projection",
        "ceiling",
        "floor",
        "value",
        "ownership",
        "leverage",
        "locked",
        "excluded",
    ]
].copy()

saved_exposures = st.session_state.get(
    "player_max_exposures",
    {},
)

default_exposure_table[
    "maximum_exposure"
] = (
    default_exposure_table["player_id"]
    .astype(str)
    .map(saved_exposures)
    .fillna(1.0)
)

edited_exposure_table = st.data_editor(
    default_exposure_table,
    width="stretch",
    hide_index=True,
    disabled=[
        "player_id",
        "name",
        "position",
        "team",
        "salary",
        "projection",
        "ceiling",
        "floor",
        "value",
        "ownership",
        "leverage",
    ],
    column_config={
        "player_id": None,
        "name": st.column_config.TextColumn(
            "Player",
        ),
        "position": st.column_config.TextColumn(
            "Position",
        ),
        "team": st.column_config.TextColumn(
            "Team",
        ),
        "salary": st.column_config.NumberColumn(
            "Salary",
            format="$%d",
        ),
        "projection": st.column_config.NumberColumn(
            "Projection",
            format="%.2f",
        ),
        "ceiling": st.column_config.NumberColumn(
            "Ceiling",
            format="%.2f",
        ),
        "floor": st.column_config.NumberColumn(
            "Floor",
            format="%.2f",
        ),
        "value": st.column_config.NumberColumn(
            "Value",
            format="%.2f",
        ),
        "leverage": st.column_config.NumberColumn(
            "Leverage",
            format="%.2f",
        ),
        "ownership": st.column_config.NumberColumn(
            "Ownership %",
            format="%.1f%%",
        ),
        "locked": st.column_config.CheckboxColumn(
            "Locked",
        ),
        "excluded": st.column_config.CheckboxColumn(
            "Excluded",
        ),
        "maximum_exposure": (
            st.column_config.NumberColumn(
                "Maximum exposure",
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                format="percent",
                help=(
                    "1.00 = 100%, 0.50 = 50%, "
                    "0.25 = 25%"
                ),
            )
        ),
    },
    key="maximum_exposure_editor",
)

players["locked"] = (
    edited_exposure_table["locked"]
    .fillna(False)
    .astype(bool)
)

players["excluded"] = (
    edited_exposure_table["excluded"]
    .fillna(False)
    .astype(bool)
)

st.session_state.player_pool = (
    players.copy()
)

player_max_exposures = {
    str(row["player_id"]): (
        1.0
        if bool(row["locked"])
        else float(row["maximum_exposure"])
    )
    for _, row in (
        edited_exposure_table.iterrows()
    )
}

st.session_state.player_max_exposures = (
    player_max_exposures
)

limited_player_count = sum(
    exposure < 1.0
    for exposure in (
        player_max_exposures.values()
    )
)

st.write(
    f"**Players with exposure limits:** "
    f"{limited_player_count}"
)

reset_exposures_clicked = st.button(
    "Reset all maximum exposures to 100%"
)

if reset_exposures_clicked:
    st.session_state.player_max_exposures = {
        str(player_id): 1.0
        for player_id in players[
            "player_id"
        ].astype(str)
    }

    if "maximum_exposure_editor" in (
        st.session_state
    ):
        del st.session_state[
            "maximum_exposure_editor"
        ]

    st.rerun()

st.markdown("---")
st.subheader("Maximum team exposure")
st.caption(
    "A team counts once when any player from that NFL team appears in a "
    "lineup. Teams with locked players must remain at 100%."
)

team_exposure_table = pd.DataFrame(
    {"team": sorted(players["team"].astype(str).str.upper().unique())}
)
saved_team_exposures = st.session_state.get("team_max_exposures", {})
team_exposure_table["maximum_exposure"] = (
    team_exposure_table["team"]
    .map(saved_team_exposures)
    .fillna(1.0)
)

edited_team_exposure_table = st.data_editor(
    team_exposure_table,
    width="stretch",
    hide_index=True,
    disabled=["team"],
    column_config={
        "team": st.column_config.TextColumn("Team"),
        "maximum_exposure": st.column_config.NumberColumn(
            "Maximum exposure",
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            format="percent",
            help="1.00 = 100%, 0.50 = 50%, 0.25 = 25%",
        ),
    },
    key="team_exposure_editor",
)

team_max_exposures = {
    str(row["team"]).upper(): float(row["maximum_exposure"])
    for _, row in edited_team_exposure_table.iterrows()
}
st.session_state.team_max_exposures = team_max_exposures

st.write(
    "**Teams with exposure limits:** "
    f"{sum(exposure < 1.0 for exposure in team_max_exposures.values())}"
)

if st.button("Reset all maximum team exposures to 100%"):
    st.session_state.team_max_exposures = {
        str(team).upper(): 1.0
        for team in players["team"].astype(str).unique()
    }
    if "team_exposure_editor" in st.session_state:
        del st.session_state["team_exposure_editor"]
    st.rerun()

st.markdown("---")

generate_clicked = st.button(
    "Generate lineups",
    type="primary",
    use_container_width=True,
    disabled=not readiness_report.is_ready,
    help=(
        None
        if readiness_report.is_ready
        else "Import or generate usable projections before optimizing."
    ),
)

if generate_clicked:
    try:
        results = (
            optimizer_service.generate_lineups(
                players=players,
                settings=optimizer_settings,
                player_max_exposures=(
                    player_max_exposures
                ),
                team_max_exposures=team_max_exposures,
            )
        )

        generated_lineups = [
            result.lineup.copy()
            for result in results
        ]

        st.session_state.generated_lineups = (
            generated_lineups
        )

        st.session_state.generated_lineup_metadata = [
            {
                "total_salary": result.total_salary,
                "total_projection": result.total_projection,
                "total_ceiling": result.total_ceiling,
                "total_floor": result.total_floor,
                "total_optimization_score": result.total_optimization_score,
                "total_ownership": (
                    result.total_ownership
                ),
                "status": result.status,
            }
            for result in results
        ]

        st.session_state.generated_exposure_rules = (
            player_max_exposures.copy()
        )
        st.session_state.generated_team_exposure_rules = (
            team_max_exposures.copy()
        )

        st.session_state.generated_exposure_report = (
            optimizer_service.build_exposure_report(
                lineups=generated_lineups,
                player_max_exposures=(
                    player_max_exposures
                ),
            )
        )

        st.session_state.generated_team_exposure_report = (
            optimizer_service.build_team_exposure_report(
                lineups=generated_lineups,
                team_max_exposures=team_max_exposures,
            )
        )

        st.session_state.generated_lineup_settings = {
            "contest_preset": st.session_state.get(
                "applied_contest_preset",
                "custom",
            ),
            "contest_preset_label": st.session_state.get(
                "applied_contest_preset_label",
                "Custom",
            ),
            "salary_cap": int(
                optimizer_settings.salary_cap
            ),
            "minimum_salary": int(
                optimizer_settings.minimum_salary
            ),
            "lineup_count": int(
                optimizer_settings.lineup_count
            ),
            "minimum_unique_players": int(
                optimizer_settings.minimum_unique_players
            ),
            "qb_stack_size": int(
                optimizer_settings.qb_stack_size
            ),
            "require_bring_back": bool(
                optimizer_settings.require_bring_back
            ),
            "maximum_players_per_team": (
                optimizer_settings.maximum_players_per_team
            ),
            "blocked_dst_opposing_positions": list(
                optimizer_settings.blocked_dst_opposing_positions
            ),
            "minimum_players_from_primary_game": (
                optimizer_settings.minimum_players_from_primary_game
            ),
            "maximum_players_per_game": (
                optimizer_settings.maximum_players_per_game
            ),
            "maximum_total_ownership": (
                optimizer_settings.maximum_total_ownership
            ),
            "optimization_target": optimizer_settings.optimization_target,
            "objective_weights": optimizer_settings.objective_weights,
        }

        st.session_state.saved_generated_lineups = {}

    except Exception as exc:
        st.error(
            f"Optimizer error: {exc}"
        )

if "generated_lineups" not in st.session_state:
    st.info(
        "Configure the optimizer and generate one or more lineups."
    )
    st.stop()

generated_lineups = (
    st.session_state.generated_lineups
)

generated_metadata = (
    st.session_state.generated_lineup_metadata
)

generated_settings = (
    st.session_state.get(
        "generated_lineup_settings",
        {
            "salary_cap": int(salary_cap),
            "minimum_salary": int(
                minimum_salary
            ),
            "lineup_count": len(
                generated_lineups
            ),
            "minimum_unique_players": int(
                minimum_unique_players
            ),
            "qb_stack_size": int(
                qb_stack_size
            ),
            "require_bring_back": bool(
                require_bring_back
            ),
            "maximum_players_per_team": (
                maximum_players_per_team
            ),
            "blocked_dst_opposing_positions": list(
                blocked_dst_opposing_positions
            ),
            "minimum_players_from_primary_game": (
                minimum_players_from_primary_game
            ),
            "maximum_players_per_game": (
                maximum_players_per_game
            ),
            "maximum_total_ownership": (
                maximum_total_ownership
            ),
            "optimization_target": optimization_target,
            "objective_weights": optimizer_settings.objective_weights,
        },
    )
)

generated_salary_cap = int(
    generated_settings["salary_cap"]
)

requested_lineup_count = int(
    generated_settings["lineup_count"]
)

generated_count = len(
    generated_lineups
)

if generated_count < requested_lineup_count:
    st.warning(
        f"The optimizer generated {generated_count} of the "
        f"{requested_lineup_count} requested lineups. The current "
        "salary, uniqueness, lock, exclusion, exposure, or stacking rules "
        "prevented additional valid lineups."
    )
else:
    st.success(
        f"Generated {generated_count} unique lineups."
    )

strategy_label = {
    "projection": "Projection",
    "ceiling": "Ceiling",
    "floor": "Floor",
    "balanced": "Balanced",
    "cash": "Cash",
    "single_entry": "Single Entry",
    "large_field_gpp": "Large-Field GPP",
    "custom": "Custom Formula",
}.get(
    generated_settings.get("optimization_target", "projection"),
    "Projection",
)
strategy_weights = generated_settings.get(
    "objective_weights",
    optimizer_settings.objective_weights,
)
st.caption(
    f"Optimization strategy: **{strategy_label}** · "
    f"Projection {strategy_weights['projection']:.0%} · "
    f"Ceiling {strategy_weights['ceiling']:.0%} · "
    f"Floor {strategy_weights['floor']:.0%} · "
    f"Value {strategy_weights['value']:.0%} · "
    f"Leverage {strategy_weights['leverage']:.0%}"
)

summary_records: list[dict] = []

for lineup_index, metadata in enumerate(
    generated_metadata,
    start=1,
):
    summary_records.append(
        {
            "lineup_number": lineup_index,
            "total_salary": int(
                metadata["total_salary"]
            ),
            "salary_remaining": (
                generated_salary_cap
                - int(
                    metadata["total_salary"]
                )
            ),
            "total_projection": float(metadata["total_projection"]),
            "total_ceiling": float(metadata.get("total_ceiling", 0.0)),
            "total_floor": float(metadata.get("total_floor", 0.0)),
            "optimization_score": float(metadata.get("total_optimization_score", metadata["total_projection"])),
            "total_ownership": float(
                metadata.get("total_ownership", 0.0)
            ),
            "average_ownership": float(
                metadata.get("total_ownership", 0.0)
            ) / 9.0,
            "status": str(
                metadata["status"]
            ),
        }
    )

summary_frame = pd.DataFrame(
    summary_records
)

st.subheader("Generated lineup summary")

st.dataframe(
    summary_frame,
    width="stretch",
    hide_index=True,
    column_config={
        "lineup_number": (
            st.column_config.NumberColumn(
                "Lineup",
                format="%d",
            )
        ),
        "total_salary": (
            st.column_config.NumberColumn(
                "Salary",
                format="$%d",
            )
        ),
        "salary_remaining": (
            st.column_config.NumberColumn(
                "Remaining",
                format="$%d",
            )
        ),
        "total_projection": st.column_config.NumberColumn(
            "Projection",
            format="%.2f",
        ),
        "total_ceiling": st.column_config.NumberColumn(
            "Ceiling",
            format="%.2f",
        ),
        "total_floor": st.column_config.NumberColumn(
            "Floor",
            format="%.2f",
        ),
        "optimization_score": st.column_config.NumberColumn(
            "Target score",
            format="%.2f",
        ),
        "total_ownership": st.column_config.NumberColumn(
            "Total ownership",
            format="%.1f%%",
        ),
        "average_ownership": st.column_config.NumberColumn(
            "Average ownership",
            format="%.1f%%",
        ),
        "status": st.column_config.TextColumn(
            "Status",
        ),
    },
)

st.markdown("---")
st.subheader("Team exposure")

team_exposure_report = st.session_state.get(
    "generated_team_exposure_report"
)
if team_exposure_report is None:
    team_exposure_report = optimizer_service.build_team_exposure_report(
        lineups=generated_lineups,
        team_max_exposures=st.session_state.get(
            "generated_team_exposure_rules",
            {},
        ),
    )

st.dataframe(
    team_exposure_report,
    width="stretch",
    hide_index=True,
    column_config={
        "team": st.column_config.TextColumn("Team"),
        "lineup_count": st.column_config.NumberColumn(
            "Lineups",
            format="%d",
        ),
        "exposure": st.column_config.NumberColumn(
            "Actual exposure",
            format="percent",
        ),
        "maximum_exposure": st.column_config.NumberColumn(
            "Maximum exposure",
            format="percent",
        ),
    },
)

st.markdown("---")
st.subheader("Portfolio exposure")

exposure_report = st.session_state.get(
    "generated_exposure_report"
)

if exposure_report is None:
    exposure_report = (
        optimizer_service.build_exposure_report(
            lineups=generated_lineups,
            player_max_exposures=(
                st.session_state.get(
                    "generated_exposure_rules",
                    {},
                )
            ),
        )
    )

if exposure_report.empty:
    st.info(
        "No exposure data is available."
    )
else:
    exposure_metric_1, exposure_metric_2, exposure_metric_3 = (
        st.columns(3)
    )

    exposure_metric_1.metric(
        "Players used",
        len(exposure_report),
    )

    exposure_metric_2.metric(
        "100% exposed players",
        int(
            (
                exposure_report["exposure"]
                == 1.0
            ).sum()
        ),
    )

    exposure_metric_3.metric(
        "Highest exposure",
        (
            f"{float(exposure_report['exposure'].max()):.0%}"
        ),
    )

    selected_position = st.selectbox(
        "Filter exposure by position",
        options=[
            "All",
            "QB",
            "RB",
            "WR",
            "TE",
            "DST",
        ],
    )

    minimum_exposure_percentage = st.slider(
        "Minimum displayed exposure",
        min_value=0,
        max_value=100,
        value=0,
        step=5,
    )

    filtered_exposure = (
        exposure_report.copy()
    )

    if selected_position != "All":
        filtered_exposure = (
            filtered_exposure.loc[
                filtered_exposure["position"]
                == selected_position
            ]
        )

    filtered_exposure = (
        filtered_exposure.loc[
            filtered_exposure["exposure"]
            >= (
                minimum_exposure_percentage
                / 100
            )
        ]
        .reset_index(drop=True)
    )

    st.dataframe(
        filtered_exposure[
            [
                "name",
                "position",
                "team",
                "salary",
                "projection",
                "lineup_count",
                "exposure",
                "maximum_exposure",
            ]
        ],
        width="stretch",
        hide_index=True,
        column_config={
            "name": st.column_config.TextColumn(
                "Player",
            ),
            "salary": (
                st.column_config.NumberColumn(
                    "Salary",
                    format="$%d",
                )
            ),
            "projection": (
                st.column_config.NumberColumn(
                    "Projection",
                    format="%.2f",
                )
            ),
            "lineup_count": (
                st.column_config.NumberColumn(
                    "Lineups",
                    format="%d",
                )
            ),
            "exposure": (
                st.column_config.ProgressColumn(
                    "Actual exposure",
                    min_value=0.0,
                    max_value=1.0,
                    format="percent",
                )
            ),
            "maximum_exposure": (
                st.column_config.ProgressColumn(
                    "Maximum exposure",
                    min_value=0.0,
                    max_value=1.0,
                    format="percent",
                )
            ),
        },
    )

    exposure_export = (
        exposure_report.copy()
    )

    exposure_export["exposure_percentage"] = (
        exposure_export["exposure"] * 100
    )

    exposure_export[
        "maximum_exposure_percentage"
    ] = (
        exposure_export["maximum_exposure"]
        * 100
    )

    st.download_button(
        "Download exposure report CSV",
        data=exposure_export.to_csv(
            index=False
        ).encode("utf-8"),
        file_name="lineup_exposure_report.csv",
        mime="text/csv",
    )

st.markdown("---")
st.subheader("Lineup review")

selected_lineup_number = st.selectbox(
    "Select a lineup to review",
    options=list(
        range(
            1,
            generated_count + 1,
        )
    ),
    format_func=lambda number: (
        f"Lineup {number}"
    ),
)

selected_index = (
    int(selected_lineup_number) - 1
)

selected_lineup = (
    generated_lineups[
        selected_index
    ].copy()
)

selected_metadata = (
    generated_metadata[
        selected_index
    ]
)

total_salary = int(
    selected_metadata["total_salary"]
)

total_projection = float(
    selected_metadata["total_projection"]
)

status = str(
    selected_metadata["status"]
)

metric_column_1, metric_column_2, metric_column_3 = (
    st.columns(3)
)

metric_column_1.metric(
    "Projected points",
    f"{total_projection:.2f}",
)

metric_column_2.metric(
    "Salary used",
    f"${total_salary:,}",
)

metric_column_3.metric(
    "Salary remaining",
    f"${generated_salary_cap - total_salary:,}",
)

st.dataframe(
    selected_lineup[
        [
            "roster_slot",
            "name",
            "position",
            "team",
            "opponent",
            "salary",
            "projection",
        ]
    ],
    width="stretch",
    hide_index=True,
)

st.markdown("---")
st.subheader("Save selected lineup")

saved_generated_lineups = (
    st.session_state.get(
        "saved_generated_lineups",
        {},
    )
)

selected_lineup_saved = (
    selected_index
    in saved_generated_lineups
)

default_lineup_name = (
    f"Lineup {selected_lineup_number} - "
    + datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )
)

lineup_name = st.text_input(
    "Lineup name",
    value=default_lineup_name,
    key=(
        "lineup_name_"
        f"{selected_lineup_number}"
    ),
    disabled=selected_lineup_saved,
)

save_lineup_clicked = st.button(
    "Save selected lineup to database",
    use_container_width=True,
    disabled=(
        active_slate_id is None
        or selected_lineup_saved
    ),
)

if save_lineup_clicked:
    try:
        lineup_id = database.save_lineup(
            slate_id=int(
                active_slate_id
            ),
            lineup=selected_lineup,
            lineup_name=lineup_name,
            total_salary=total_salary,
            total_projection=total_projection,
            solver_status=status,
            salary_cap=generated_salary_cap,
            minimum_salary=int(
                generated_settings[
                    "minimum_salary"
                ]
            ),
        )

        saved_generated_lineups[
            selected_index
        ] = lineup_id

        st.session_state.saved_generated_lineups = (
            saved_generated_lineups
        )

        st.rerun()

    except Exception as exc:
        st.error(
            f"Could not save lineup: {exc}"
        )

if selected_lineup_saved:
    saved_lineup_id = (
        saved_generated_lineups[
            selected_index
        ]
    )

    st.success(
        "This lineup is saved in the database as "
        f"lineup #{saved_lineup_id}."
    )

selected_export = selected_lineup[
    [
        "roster_slot",
        "player_id",
        "name",
        "position",
        "team",
        "salary",
    ]
].copy()

st.download_button(
    "Download selected lineup CSV",
    data=selected_export.to_csv(
        index=False
    ).encode("utf-8"),
    file_name=(
        f"optimized_lineup_"
        f"{selected_lineup_number}.csv"
    ),
    mime="text/csv",
)

portfolio_export_records: list[dict] = []

for lineup_index, lineup in enumerate(
    generated_lineups,
    start=1,
):
    for _, player in lineup.iterrows():
        portfolio_export_records.append(
            {
                "lineup_number": lineup_index,
                "roster_slot": (
                    player["roster_slot"]
                ),
                "player_id": (
                    player["player_id"]
                ),
                "name": player["name"],
                "position": (
                    player["position"]
                ),
                "team": player["team"],
                "salary": player["salary"],
                "projection": (
                    player["projection"]
                ),
            }
        )

portfolio_export = pd.DataFrame(
    portfolio_export_records
)

st.download_button(
    "Download all generated lineups CSV",
    data=portfolio_export.to_csv(
        index=False
    ).encode("utf-8"),
    file_name="generated_lineups.csv",
    mime="text/csv",
)