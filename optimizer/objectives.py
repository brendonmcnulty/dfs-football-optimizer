from __future__ import annotations

from collections.abc import Mapping


OBJECTIVE_COMPONENTS = {
    "projection",
    "ceiling",
    "floor",
    "value",
    "leverage",
}


def validate_objective_weights(
    objective_weights: Mapping[str, float],
) -> dict[str, float]:
    """Validate and normalize objective weights."""

    normalized = {
        str(component): float(weight)
        for component, weight in objective_weights.items()
    }

    if set(normalized) != OBJECTIVE_COMPONENTS:
        raise ValueError(
            "Objective weights must include projection, ceiling, "
            "floor, value, and leverage."
        )

    if any(weight < 0.0 or weight > 1.0 for weight in normalized.values()):
        raise ValueError("Objective weights must be between 0% and 100%.")

    if abs(sum(normalized.values()) - 1.0) > 0.0001:
        raise ValueError("Objective weights must total exactly 100%.")

    return normalized


def calculate_player_objective_score(
    *,
    projection: float,
    ceiling: float,
    floor: float,
    salary: int,
    ownership: float,
    objective_weights: Mapping[str, float],
) -> float:
    """Calculate a comparable weighted optimization score for one player."""

    weights = validate_objective_weights(objective_weights)
    normalized_salary = max(int(salary), 1)
    normalized_ownership = min(max(float(ownership), 0.0), 100.0)

    # Scale value and leverage into fantasy-point-like units so the
    # percentages remain intuitive when all five components are blended.
    value_equivalent = float(projection) * 6000.0 / normalized_salary
    leverage_equivalent = float(ceiling) * (
        1.0 - normalized_ownership / 100.0
    )

    return (
        weights["projection"] * float(projection)
        + weights["ceiling"] * float(ceiling)
        + weights["floor"] * float(floor)
        + weights["value"] * value_equivalent
        + weights["leverage"] * leverage_equivalent
    )
