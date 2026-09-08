from __future__ import annotations

import math
import hashlib
import random
import statistics
from collections import Counter, defaultdict
from typing import Any, Iterable

from .config import Country, SeriesSpec, load_goals
from .metrics import calculate_metrics, percentile_ranks


FAMILY_BY_GOAL = {item["id"]: item["family"] for item in load_goals()}


def _mean(values: Iterable[float]) -> float:
    materialized = list(values)
    return statistics.mean(materialized) if materialized else math.nan


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _stable_seed(label: str) -> int:
    return int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big")


def bootstrap_mean_interval(
    values: list[float], repetitions: int = 1000, label: str = "mean"
) -> tuple[float, float]:
    if not values:
        return math.nan, math.nan
    if len(values) == 1:
        return values[0], values[0]
    rng = random.Random(_stable_seed(label))
    draws = [statistics.mean(rng.choice(values) for _ in values) for _ in range(repetitions)]
    return _quantile(draws, 0.025), _quantile(draws, 0.975)


def _pearson(left: list[float], right: list[float]) -> float:
    left_mean, right_mean = statistics.mean(left), statistics.mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else 0.0


def _spearman(population: dict[str, float], outcome: dict[str, float]) -> float:
    shared = sorted(population.keys() & outcome.keys())
    population_ranks = percentile_ranks({key: population[key] for key in shared})
    outcome_ranks = percentile_ranks({key: outcome[key] for key in shared})
    return _pearson(
        [population_ranks[key] for key in shared],
        [outcome_ranks[key] for key in shared],
    )


def _spearman_interval(
    population: dict[str, float], outcome: dict[str, float], repetitions: int
) -> tuple[float, float]:
    shared = sorted(population.keys() & outcome.keys())
    rng = random.Random(_stable_seed("population-spearman"))
    draws: list[float] = []
    for _ in range(repetitions):
        sampled = [rng.choice(shared) for _ in shared]
        left = [population[key] for key in sampled]
        right = [outcome[key] for key in sampled]
        left_ranks = percentile_ranks({str(i): value for i, value in enumerate(left)})
        right_ranks = percentile_ranks({str(i): value for i, value in enumerate(right)})
        draws.append(_pearson(list(left_ranks.values()), list(right_ranks.values())))
    return _quantile(draws, 0.025), _quantile(draws, 0.975)


def _inverse(matrix: list[list[float]]) -> list[list[float]]:
    size = len(matrix)
    augmented = [row[:] + [float(i == j) for j in range(size)] for i, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-10:
            raise ValueError("Analysis design matrix is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column])
            ]
    return [row[size:] for row in augmented]


def _matvec(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [sum(value * weight for value, weight in zip(row, vector)) for row in matrix]


def _sandwich(inverse: list[list[float]], meat: list[list[float]]) -> list[list[float]]:
    size = len(inverse)
    left = [
        [sum(inverse[i][k] * meat[k][j] for k in range(size)) for j in range(size)]
        for i in range(size)
    ]
    return [
        [sum(left[i][k] * inverse[j][k] for k in range(size)) for j in range(size)]
        for i in range(size)
    ]


def fit_country_model(rows: list[dict[str, Any]]) -> dict[str, Any]:
    incomes = sorted({row["income_group"] for row in rows})
    regions = sorted({row["region"] for row in rows})
    income_reference = "High income" if "High income" in incomes else incomes[0]
    region_reference = "Europe & Central Asia" if "Europe & Central Asia" in regions else regions[0]
    income_levels = [value for value in incomes if value != income_reference]
    region_levels = [value for value in regions if value != region_reference]
    log_population = [math.log(row["population"]) for row in rows]
    population_mean = statistics.mean(log_population)
    population_sd = statistics.pstdev(log_population) or 1.0
    names = ["Intercept", "Log population (1 SD)"]
    names += [f"Income: {value} vs {income_reference}" for value in income_levels]
    names += [f"Region: {value} vs {region_reference}" for value in region_levels]
    design, outcome = [], []
    for row in rows:
        design.append(
            [1.0, (math.log(row["population"]) - population_mean) / population_sd]
            + [float(row["income_group"] == value) for value in income_levels]
            + [float(row["region"] == value) for value in region_levels]
        )
        outcome.append(row["missingness"])
    columns = len(names)
    xtx = [[0.0] * columns for _ in range(columns)]
    xty = [0.0] * columns
    for x, y in zip(design, outcome):
        for i in range(columns):
            xty[i] += x[i] * y
            for j in range(columns):
                xtx[i][j] += x[i] * x[j]
    inverse = _inverse(xtx)
    coefficients = _matvec(inverse, xty)
    residuals = [
        y - sum(value * beta for value, beta in zip(x, coefficients))
        for x, y in zip(design, outcome)
    ]
    meat = [[0.0] * columns for _ in range(columns)]
    for x, residual in zip(design, residuals):
        leverage = sum(
            x[i] * inverse[i][j] * x[j]
            for i in range(columns)
            for j in range(columns)
        )
        adjusted = residual / max(1e-6, 1 - leverage)
        for i in range(columns):
            for j in range(columns):
                meat[i][j] += x[i] * x[j] * adjusted**2
    covariance = _sandwich(inverse, meat)
    standard_errors = [math.sqrt(max(0.0, covariance[i][i])) for i in range(columns)]
    total_ss = sum((value - statistics.mean(outcome)) ** 2 for value in outcome)
    residual_ss = sum(value**2 for value in residuals)
    return {
        "unit": "country mean across the same universally applicable series",
        "outcome": "recent missingness",
        "n": len(rows),
        "r_squared": round(1 - residual_ss / total_ss, 4) if total_ss else 0.0,
        "income_reference": income_reference,
        "region_reference": region_reference,
        "coefficients": [
            {
                "term": name,
                "estimate_percentage_points": round(100 * estimate, 2),
                "standard_error": round(100 * error, 2),
                "ci_low": round(100 * (estimate - 1.96 * error), 2),
                "ci_high": round(100 * (estimate + 1.96 * error), 2),
            }
            for name, estimate, error in zip(names, coefficients, standard_errors)
        ],
    }


def fit_pair_model(
    rows: list[dict[str, Any]], include_statistical_performance: bool = False
) -> dict[str, Any]:
    """Fit the preregistered country-series model with country-clustered errors."""
    if include_statistical_performance:
        rows = [row for row in rows if row.get("statistical_performance") is not None]
    incomes = sorted({row["income_group"] for row in rows})
    regions = sorted({row["region"] for row in rows})
    families = sorted({row["family"] for row in rows})
    income_reference = "High income" if "High income" in incomes else incomes[0]
    region_reference = "Europe & Central Asia" if "Europe & Central Asia" in regions else regions[0]
    family_reference = "People" if "People" in families else families[0]
    income_levels = [value for value in incomes if value != income_reference]
    region_levels = [value for value in regions if value != region_reference]
    family_levels = [value for value in families if value != family_reference]
    log_population = [math.log(row["population"]) for row in rows]
    population_mean = statistics.mean(log_population)
    population_sd = statistics.pstdev(log_population) or 1.0
    names = ["Intercept", "Log population (1 SD)"]
    names += [f"Income: {value} vs {income_reference}" for value in income_levels]
    names += [f"Region: {value} vs {region_reference}" for value in region_levels]
    names += [f"SDG family: {value} vs {family_reference}" for value in family_levels]
    if include_statistical_performance:
        names.append("Statistical performance (10 points)")
    design, outcome, clusters = [], [], []
    for row in rows:
        design.append(
            [1.0, (math.log(row["population"]) - population_mean) / population_sd]
            + [float(row["income_group"] == value) for value in income_levels]
            + [float(row["region"] == value) for value in region_levels]
            + [float(row["family"] == value) for value in family_levels]
            + ([row["statistical_performance"] / 10] if include_statistical_performance else [])
        )
        outcome.append(row["missingness"])
        clusters.append(row["country_alpha3"])
    columns = len(names)
    xtx = [[0.0] * columns for _ in range(columns)]
    xty = [0.0] * columns
    for x, y in zip(design, outcome):
        for i in range(columns):
            xty[i] += x[i] * y
            for j in range(columns):
                xtx[i][j] += x[i] * x[j]
    inverse = _inverse(xtx)
    coefficients = _matvec(inverse, xty)
    residuals = [
        y - sum(value * beta for value, beta in zip(x, coefficients))
        for x, y in zip(design, outcome)
    ]
    cluster_scores: dict[str, list[float]] = defaultdict(lambda: [0.0] * columns)
    for cluster, x, residual in zip(clusters, design, residuals):
        for index in range(columns):
            cluster_scores[cluster][index] += x[index] * residual
    meat = [[0.0] * columns for _ in range(columns)]
    for score in cluster_scores.values():
        for i in range(columns):
            for j in range(columns):
                meat[i][j] += score[i] * score[j]
    cluster_count = len(cluster_scores)
    row_count = len(rows)
    correction = (cluster_count / (cluster_count - 1)) * ((row_count - 1) / (row_count - columns))
    covariance = _sandwich(inverse, [[value * correction for value in row] for row in meat])
    standard_errors = [math.sqrt(max(0.0, covariance[i][i])) for i in range(columns)]
    total_ss = sum((value - statistics.mean(outcome)) ** 2 for value in outcome)
    residual_ss = sum(value**2 for value in residuals)
    return {
        "unit": "country–indicator pair",
        "outcome": "recent missingness",
        "n": row_count,
        "clusters": cluster_count,
        "clustered_by": "country",
        "includes_statistical_performance": include_statistical_performance,
        "r_squared": round(1 - residual_ss / total_ss, 4) if total_ss else 0.0,
        "income_reference": income_reference,
        "region_reference": region_reference,
        "family_reference": family_reference,
        "coefficients": [
            {
                "term": name,
                "estimate_percentage_points": round(100 * estimate, 2),
                "standard_error": round(100 * error, 2),
                "ci_low": round(100 * (estimate - 1.96 * error), 2),
                "ci_high": round(100 * (estimate + 1.96 * error), 2),
            }
            for name, estimate, error in zip(names, coefficients, standard_errors)
        ],
    }


def variance_decomposition(rows: list[dict[str, Any]]) -> dict[str, float]:
    by_country: dict[str, list[float]] = defaultdict(list)
    by_series: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_country[row["country_alpha3"]].append(row["missingness"])
        by_series[row["series_code"]].append(row["missingness"])
    overall = _mean(row["missingness"] for row in rows)
    total = sum((row["missingness"] - overall) ** 2 for row in rows)
    if not total:
        return {
            "country_percent": 0.0,
            "indicator_percent": 0.0,
            "interaction_and_residual_percent": 0.0,
        }
    country = len(by_series) * sum((statistics.mean(v) - overall) ** 2 for v in by_country.values())
    series = len(by_country) * sum((statistics.mean(v) - overall) ** 2 for v in by_series.values())
    residual = max(0.0, total - country - series)
    return {
        "country_percent": round(100 * country / total, 1),
        "indicator_percent": round(100 * series / total, 1),
        "interaction_and_residual_percent": round(100 * residual / total, 1),
    }


def _analysis_rows(
    metrics: dict[str, Any], include_conditional: bool = False
) -> list[dict[str, Any]]:
    countries = {item["alpha3"]: item for item in metrics["countries"]}
    rows = []
    for item in metrics["country_series"]:
        if item["applicability"] != "universal" and not include_conditional:
            continue
        country = countries[item["country_alpha3"]]
        rows.append(
            {
                **item,
                "region": country["region"].strip(),
                "income_group": country["income_group"].strip(),
                "population": country["population"],
                "statistical_performance": country.get("statistical_performance"),
                "family": FAMILY_BY_GOAL[item["goal"]],
                "missingness": 1 - item["recent_completeness"],
            }
        )
    return rows


def _country_means(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["country_alpha3"]].append(row)
    return [
        {
            "country_alpha3": code,
            "country_name": items[0]["country_name"],
            "region": items[0]["region"],
            "income_group": items[0]["income_group"],
            "population": items[0]["population"],
            "missingness": _mean(item["missingness"] for item in items),
            "staleness": _mean(item["staleness"] for item in items),
        }
        for code, items in sorted(grouped.items())
    ]


def _group_summary(rows: list[dict[str, Any]], group_key: str, repetitions: int) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[str(row[group_key])][row["country_alpha3"]].append(row)
    summaries = []
    for group, country_items in sorted(grouped.items()):
        missingness = [_mean(item["missingness"] for item in items) for items in country_items.values()]
        staleness = [_mean(item["staleness"] for item in items) for items in country_items.values()]
        low, high = bootstrap_mean_interval(missingness, repetitions, f"{group_key}:{group}")
        summaries.append(
            {
                "group": group,
                "countries": len(country_items),
                "mean_missingness_pct": round(100 * statistics.mean(missingness), 1),
                "ci_low": round(100 * low, 1),
                "ci_high": round(100 * high, 1),
                "mean_staleness": round(100 * statistics.mean(staleness), 1),
            }
        )
    return summaries


def _window_rows(rows: list[dict[str, Any]], completed_year: int, width: int) -> list[dict[str, Any]]:
    start = completed_year - width + 1
    output = []
    for row in rows:
        recent = [year for year in row["observed_years"] if start <= year <= completed_year]
        expected = max(1, math.ceil(width / row["expected_cadence_years"]))
        output.append({**row, "missingness": 1 - min(1.0, len(recent) / expected)})
    return output


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    total = sum(weights)
    return sum(value * weight for value, weight in zip(values, weights)) / total if total else math.nan


def _sensitivity_entry(
    label: str, rows: list[dict[str, Any]], population_weighted: bool = False
) -> dict[str, Any]:
    country_rows = _country_means(rows)
    if population_weighted:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in country_rows:
            grouped[row["income_group"]].append(row)
        means = {
            group: 100 * _weighted_mean(
                [item["missingness"] for item in items],
                [item["population"] for item in items],
            )
            for group, items in grouped.items()
        }
        low_high = means["Low income"] - means["High income"]
        overall = 100 * _weighted_mean(
            [item["missingness"] for item in country_rows],
            [item["population"] for item in country_rows],
        )
    else:
        income = {item["group"]: item for item in _group_summary(rows, "income_group", 250)}
        low_high = income["Low income"]["mean_missingness_pct"] - income["High income"]["mean_missingness_pct"]
        overall = 100 * _mean(item["missingness"] for item in country_rows)
    return {
        "specification": label,
        "mean_missingness_pct": round(overall, 1),
        "low_minus_high_income_pp": round(low_high, 1),
    }


def _income_gap(rows: list[dict[str, Any]]) -> float:
    country_rows = _country_means(rows)
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in country_rows:
        grouped[row["income_group"]].append(row["missingness"])
    return 100 * (
        statistics.mean(grouped["Low income"])
        - statistics.mean(grouped["High income"])
    )


def leave_one_series_out(
    rows: list[dict[str, Any]], catalog: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    estimates = []
    for code in sorted({row["series_code"] for row in rows}):
        estimate = _income_gap([row for row in rows if row["series_code"] != code])
        metadata = catalog.get(code, {})
        estimates.append(
            {
                "excluded_series": code,
                "description": metadata.get("description", code),
                "low_minus_high_income_pp": round(estimate, 2),
            }
        )
    return {
        "baseline_low_minus_high_income_pp": round(_income_gap(rows), 2),
        "minimum_pp": round(
            min(item["low_minus_high_income_pp"] for item in estimates), 2
        ),
        "maximum_pp": round(
            max(item["low_minus_high_income_pp"] for item in estimates), 2
        ),
        "most_attenuating": min(
            estimates, key=lambda item: item["low_minus_high_income_pp"]
        ),
        "most_amplifying": max(
            estimates, key=lambda item: item["low_minus_high_income_pp"]
        ),
        "estimates": estimates,
    }


def missingness_concentration(
    rows: list[dict[str, Any]], catalog: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["series_code"]].append(row)
    ranked = []
    for code, items in grouped.items():
        metadata = catalog.get(code, {})
        ranked.append(
            {
                "series_code": code,
                "goal": items[0]["goal"],
                "description": metadata.get("description", code),
                "mean_missingness_pct": round(
                    100 * _mean(item["missingness"] for item in items), 1
                ),
                "missing_expected_observations": round(
                    sum(item["missingness"] for item in items), 2
                ),
            }
        )
    ranked.sort(
        key=lambda item: (
            -item["missing_expected_observations"], item["series_code"]
        )
    )
    top_count = max(1, math.ceil(0.2 * len(ranked)))
    total = sum(item["missing_expected_observations"] for item in ranked)
    top_total = sum(
        item["missing_expected_observations"] for item in ranked[:top_count]
    )
    return {
        "top_quintile_series": top_count,
        "top_quintile_share_of_missingness_pct": (
            round(100 * top_total / total, 1) if total else 0.0
        ),
        "top_series": ranked[:5],
    }


def run_analysis(
    metrics: dict[str, Any], observations: list[dict[str, Any]], specs: list[SeriesSpec],
    countries: list[Country], context: dict[str, dict[str, Any]], catalog: dict[str, dict[str, Any]],
    manifest: dict[str, Any], bootstrap_repetitions: int = 1000,
) -> dict[str, Any]:
    rows = _analysis_rows(metrics)
    all_series_rows = _analysis_rows(metrics, include_conditional=True)
    country_rows = _country_means(rows)
    population = {row["country_alpha3"]: float(row["population"]) for row in country_rows}
    missingness = {row["country_alpha3"]: row["missingness"] for row in country_rows}
    rho = _spearman(population, missingness)
    rho_low, rho_high = _spearman_interval(population, missingness, bootstrap_repetitions)
    reported_metrics = calculate_metrics(
        [row for row in observations if row.get("nature") in {"C", "CA"}],
        specs, countries, context, catalog, metrics["completed_year"],
    )
    reported_rows = _analysis_rows(reported_metrics)
    universal_series = len({row["series_code"] for row in rows})
    status_counts = Counter(row.get("nature", "NA") for row in observations)
    country_model = fit_country_model(country_rows)
    pair_model = fit_pair_model(rows)
    context_model = fit_pair_model(rows, include_statistical_performance=True)
    variance = variance_decomposition(rows)
    concentration = missingness_concentration(rows, catalog)
    leave_one_out = leave_one_series_out(rows, catalog)
    sensitivity = [
        _sensitivity_entry("All official statuses, 5-year window", rows),
        _sensitivity_entry(
            "All official statuses, 3-year window",
            _window_rows(rows, metrics["completed_year"], 3),
        ),
        _sensitivity_entry(
            "All official statuses, 7-year window",
            _window_rows(rows, metrics["completed_year"], 7),
        ),
        _sensitivity_entry(
            "Country and country-adjusted statuses only, 5-year window",
            reported_rows,
        ),
        _sensitivity_entry(
            "Population-weighted countries, all official statuses, 5-year window",
            rows,
            population_weighted=True,
        ),
        _sensitivity_entry(
            "All selected series, treating conditional series as applicable",
            all_series_rows,
        ),
    ]
    income_effect = next(
        item
        for item in pair_model["coefficients"]
        if item["term"].startswith("Income: Low income")
    )
    population_effect = next(
        item
        for item in pair_model["coefficients"]
        if item["term"] == "Log population (1 SD)"
    )
    statistical_performance_effect = next(
        item
        for item in context_model["coefficients"]
        if item["term"] == "Statistical performance (10 points)"
    )
    analysis = {
        "snapshot": {"retrieved_at": manifest["retrieved_at"], "completed_year": metrics["completed_year"], "recent_window": metrics["recent_window"]},
        "design": {
            "primary_outcome": "recent missingness",
            "unit": "country, averaged equally across the same universally applicable series",
            "countries": len(country_rows), "universal_series": universal_series,
            "country_series_pairs": len(rows), "bootstrap_repetitions": bootstrap_repetitions,
            "interpretation": "descriptive associations, not causal effects",
            "included_context": ["income group", "region", "population", "SDG family"],
            "unavailable_context": ["collection cost", "conflict exposure"],
        },
        "audit": {
            "manifest_status": manifest["status"],
            "rectangular_panel": len(rows) == len(country_rows) * universal_series,
            "countries_with_complete_context": sum(
                row["population"] is not None and row["region"] != "Unknown" and row["income_group"] != "Unknown"
                for row in country_rows
            ),
            "future_observations_excluded": sum(
                int(row["reference_year"]) > metrics["completed_year"]
                for row in observations if row.get("reference_year") is not None
            ),
            "observation_status_counts": dict(sorted(status_counts.items())),
        },
        "summaries": {
            "income": _group_summary(rows, "income_group", bootstrap_repetitions),
            "region": _group_summary(rows, "region", bootstrap_repetitions),
            "goal": _group_summary(rows, "goal", bootstrap_repetitions),
            "family": _group_summary(rows, "family", bootstrap_repetitions),
        },
        "population_association": {"spearman_rho": round(rho, 3), "ci_low": round(rho_low, 3), "ci_high": round(rho_high, 3)},
        "pair_model": pair_model,
        "context_model": context_model,
        "country_model": country_model,
        "variance_decomposition": variance,
        "concentration": concentration,
        "leave_one_series_out": leave_one_out,
        "sensitivity": sensitivity,
        "findings": [
            {
                "id": "income-gap",
                "value": income_effect["estimate_percentage_points"],
                "unit": "percentage points",
                "label": "Adjusted low-income gap",
                "plain_language": (
                    "After accounting for region and population, low-income "
                    "countries have more recent missingness than high-income countries."
                ),
                "ci_low": income_effect["ci_low"],
                "ci_high": income_effect["ci_high"],
            },
            {
                "id": "indicator-variation",
                "value": variance["indicator_percent"],
                "unit": "percent",
                "label": "Variation between indicators",
                "plain_language": (
                    "Missingness differs much more from indicator to indicator "
                    "than from country to country."
                ),
                "comparison_value": variance["country_percent"],
            },
        ],
        "supporting_results": [
            {
                "id": "population",
                "label": "Population",
                "value": population_effect["estimate_percentage_points"],
                "unit": "percentage points per standard deviation",
                "plain_language": (
                    "Larger populations are associated with less recent missingness "
                    "after accounting for region and income."
                ),
                "ci_low": population_effect["ci_low"],
                "ci_high": population_effect["ci_high"],
            },
            {
                "id": "statistical-performance",
                "label": "Statistical performance",
                "value": statistical_performance_effect["estimate_percentage_points"],
                "unit": "percentage points per 10-point score increase",
                "plain_language": (
                    "Higher World Bank statistical-performance scores are associated "
                    "with less recent missingness after the other adjustments."
                ),
                "ci_low": statistical_performance_effect["ci_low"],
                "ci_high": statistical_performance_effect["ci_high"],
            },
            {
                "id": "concentration",
                "label": "Concentration",
                "value": concentration["top_quintile_share_of_missingness_pct"],
                "unit": "percent",
                "count": concentration["top_quintile_series"],
                "plain_language": (
                    "A small group of high-gap indicator series accounts for a "
                    "disproportionate share of total missingness."
                ),
            },
        ],
    }
    if not analysis["audit"]["rectangular_panel"]:
        raise ValueError("Research analysis requires a rectangular country-series panel")
    if analysis["audit"]["countries_with_complete_context"] != len(country_rows):
        raise ValueError("Research analysis requires complete country context")
    return analysis
