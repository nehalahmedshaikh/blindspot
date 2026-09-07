from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from .config import Country, SeriesSpec

TOTAL_DIMENSION_VALUES = {
    "ALL",
    "ALLAGE",
    "ALLAREA",
    "BOTHSEX",
    "_T",
    "TOTAL",
    "NAT",
    "NATIONAL",
}
STATUS_LABELS = {
    "C": "country",
    "CA": "country_adjusted",
    "E": "estimated",
    "G": "global_monitoring",
    "M": "modeled",
    "N": "non_relevant",
    "NA": "unavailable",
}


def percentile_ranks(values: dict[str, float | int | None]) -> dict[str, float]:
    present = sorted((float(value), key) for key, value in values.items() if value is not None)
    if not present:
        return {key: 0.5 for key in values}
    denominator = max(1, len(present) - 1)
    ranks: dict[str, float] = {}
    index = 0
    while index < len(present):
        end = index + 1
        while end < len(present) and present[end][0] == present[index][0]:
            end += 1
        average_index = (index + end - 1) / 2
        for _, key in present[index:end]:
            ranks[key] = average_index / denominator
        index = end
    return {key: round(ranks.get(key, 0.5), 6) for key in values}


def is_aggregate(dimensions: dict[str, str]) -> bool:
    relevant = {key: value for key, value in dimensions.items() if key != "Reporting Type"}
    return bool(relevant) and all(value.upper() in TOTAL_DIMENSION_VALUES for value in relevant.values())


def _regularity(years: list[int]) -> float | None:
    if len(years) < 3:
        return None
    gaps = [right - left for left, right in zip(years, years[1:]) if right > left]
    if len(gaps) < 2 or statistics.mean(gaps) == 0:
        return 1.0
    return round(1 / (1 + statistics.pstdev(gaps) / statistics.mean(gaps)), 4)


def _dimension_coverage(rows: list[dict[str, Any]]) -> dict[str, bool]:
    output: dict[str, bool] = {}
    for dimension in ("Sex", "Age", "Location"):
        values = {
            row.get("dimensions", {}).get(dimension)
            for row in rows
            if row.get("dimensions", {}).get(dimension)
        }
        output[dimension.lower()] = len({v for v in values if v.upper() not in TOTAL_DIMENSION_VALUES}) > 1
    return output


def calculate_metrics(
    observations: list[dict[str, Any]],
    specs: list[SeriesSpec],
    countries: list[Country],
    context: dict[str, dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    completed_year: int | None = None,
) -> dict[str, Any]:
    completed_year = completed_year or datetime.now(UTC).year - 1
    recent_start = completed_year - 4
    country_by_m49 = {country.m49: country for country in countries}
    spec_by_code = {spec.code: spec for spec in specs}
    rows_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        if row["country_m49"] in country_by_m49 and row["series_code"] in spec_by_code:
            rows_by_pair[(row["country_m49"], row["series_code"])].append(row)

    population_ranks = percentile_ranks(
        {country.alpha3: context.get(country.alpha3, {}).get("population") for country in countries}
    )
    intermediate: list[dict[str, Any]] = []
    scarcity_counts: Counter[str] = Counter()

    for country in countries:
        for spec in specs:
            pair_rows = rows_by_pair.get((country.m49, spec.code), [])
            years = sorted(
                {
                    int(row["reference_year"])
                    for row in pair_rows
                    if row.get("reference_year") is not None and int(row["reference_year"]) <= completed_year
                }
            )
            recent_years = [year for year in years if recent_start <= year <= completed_year]
            expected = max(1, math.ceil(5 / spec.cadence))
            completeness = min(1.0, len(recent_years) / expected)
            latest = max(years) if years else None
            if latest is None:
                staleness = 1.0
                periods_since = None
            else:
                periods_since = max(0.0, (completed_year - latest) / spec.cadence)
                staleness = min(1.0, periods_since / 3)
            if completeness < 1:
                scarcity_counts[spec.code] += 1
            nature_counts = Counter(row.get("nature", "NA") for row in pair_rows)
            dimensions = _dimension_coverage(pair_rows)
            intermediate.append(
                {
                    "country_m49": country.m49,
                    "country_alpha3": country.alpha3,
                    "country_name": country.name,
                    "series_code": spec.code,
                    "goal": spec.goal,
                    "applicability": spec.applicability,
                    "expected_cadence_years": spec.cadence,
                    "cadence_confidence": "curated",
                    "latest_year": latest,
                    "observed_years": years,
                    "recent_completeness": round(completeness, 4),
                    "staleness": round(staleness, 4),
                    "periods_since_latest": round(periods_since, 3) if periods_since is not None else None,
                    "regularity": _regularity(years),
                    "has_aggregate_slice": any(is_aggregate(row.get("dimensions", {})) for row in pair_rows),
                    "disaggregation": dimensions,
                    "nature_counts": {STATUS_LABELS.get(key, key): value for key, value in sorted(nature_counts.items())},
                }
            )

    applicable_count = sum(1 for country in countries for spec in specs if spec.applicability == "universal")
    if applicable_count == 0:
        raise ValueError("No universally applicable series configured")
    country_accumulator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in intermediate:
        spec = spec_by_code[item["series_code"]]
        scarcity = scarcity_counts[spec.code] / len(countries)
        item["global_scarcity"] = round(scarcity, 4)
        if spec.applicability != "universal":
            item["measurement_priority_v1"] = None
            item["score_components"] = None
        else:
            components = {
                "staleness": item["staleness"],
                "completeness_deficit": round(1 - item["recent_completeness"], 4),
                "global_scarcity": round(scarcity, 4),
                "population_percentile": population_ranks[item["country_alpha3"]],
            }
            score = (
                0.35 * components["staleness"]
                + 0.25 * components["completeness_deficit"]
                + 0.20 * components["global_scarcity"]
                + 0.20 * components["population_percentile"]
            )
            item["measurement_priority_v1"] = round(100 * score, 2)
            item["score_components"] = components
            country_accumulator[item["country_alpha3"]].append(item)

    country_metrics: list[dict[str, Any]] = []
    for country in countries:
        items = country_accumulator[country.alpha3]
        ctx = context.get(country.alpha3, {})
        by_goal: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            by_goal[item["goal"]].append(item)
        country_metrics.append(
            {
                "m49": country.m49,
                "alpha3": country.alpha3,
                "name": country.name,
                "region": ctx.get("region", "Unknown"),
                "income_group": ctx.get("income_group", "Unknown"),
                "population": ctx.get("population"),
                "population_year": ctx.get("population_year"),
                "completeness": round(100 * statistics.mean(x["recent_completeness"] for x in items), 2),
                "staleness": round(100 * statistics.mean(x["staleness"] for x in items), 2),
                "priority": round(statistics.mean(x["measurement_priority_v1"] for x in items), 2),
                "goals": {
                    str(goal): {
                        "completeness": round(100 * statistics.mean(x["recent_completeness"] for x in goal_items), 2),
                        "priority": round(statistics.mean(x["measurement_priority_v1"] for x in goal_items), 2),
                    }
                    for goal, goal_items in sorted(by_goal.items())
                },
            }
        )

    series_metrics = []
    for spec in specs:
        relevant = [item for item in intermediate if item["series_code"] == spec.code]
        metadata = catalog.get(spec.code, {})
        series_metrics.append(
            {
                "code": spec.code,
                "goal": spec.goal,
                "description": metadata.get("description", spec.code),
                "indicator": metadata.get("indicator", []),
                "rationale": spec.rationale,
                "cadence": spec.cadence,
                "applicability": spec.applicability,
                "coverage": round(100 * (1 - scarcity_counts[spec.code] / len(countries)), 2),
                "latest_year": max((x["latest_year"] for x in relevant if x["latest_year"]), default=None),
            }
        )

    rankings = sorted(
        (item for item in intermediate if item["measurement_priority_v1"] is not None),
        key=lambda item: (-item["measurement_priority_v1"], item["country_name"], item["series_code"]),
    )
    return {
        "schema_version": "1.0.0",
        "completed_year": completed_year,
        "recent_window": [recent_start, completed_year],
        "countries": sorted(country_metrics, key=lambda item: item["name"]),
        "series": sorted(series_metrics, key=lambda item: (item["goal"], item["code"])),
        "country_series": intermediate,
        "rankings": rankings,
    }
