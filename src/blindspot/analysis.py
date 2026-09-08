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
    """Fit country covariates after absorbing representative-series fixed effects."""
    if include_statistical_performance:
        rows = [row for row in rows if row.get("statistical_performance") is not None]
    incomes = sorted({row["income_group"] for row in rows})
    regions = sorted({row["region"] for row in rows})
    income_reference = "High income" if "High income" in incomes else incomes[0]
    region_reference = "Europe & Central Asia" if "Europe & Central Asia" in regions else regions[0]
    income_levels = [value for value in incomes if value != income_reference]
    region_levels = [value for value in regions if value != region_reference]
    log_population = [math.log(row["population"]) for row in rows]
    population_mean = statistics.mean(log_population)
    population_sd = statistics.pstdev(log_population) or 1.0
    names = ["Log population (1 SD)"]
    names += [f"Income: {value} vs {income_reference}" for value in income_levels]
    names += [f"Region: {value} vs {region_reference}" for value in region_levels]
    if include_statistical_performance:
        names.append("Statistical performance (10 points)")

    raw_design = []
    outcome = []
    clusters = []
    series = []
    for row in rows:
        raw_design.append(
            [(math.log(row["population"]) - population_mean) / population_sd]
            + [float(row["income_group"] == value) for value in income_levels]
            + [float(row["region"] == value) for value in region_levels]
            + ([row["statistical_performance"] / 10] if include_statistical_performance else [])
        )
        outcome.append(row["missingness"])
        clusters.append(row["country_alpha3"])
        series.append(row.get("series_code", row.get("family", "series")))

    by_series: dict[str, list[int]] = defaultdict(list)
    for index, code in enumerate(series):
        by_series[code].append(index)
    design = [[0.0] * len(names) for _ in rows]
    centered_outcome = [0.0] * len(rows)
    for indices in by_series.values():
        means = [
            statistics.mean(raw_design[index][column] for index in indices)
            for column in range(len(names))
        ]
        outcome_mean = statistics.mean(outcome[index] for index in indices)
        for index in indices:
            design[index] = [
                value - mean for value, mean in zip(raw_design[index], means)
            ]
            centered_outcome[index] = outcome[index] - outcome_mean

    columns = len(names)
    xtx = [[0.0] * columns for _ in range(columns)]
    xty = [0.0] * columns
    for x, y in zip(design, centered_outcome):
        for i in range(columns):
            xty[i] += x[i] * y
            for j in range(columns):
                xtx[i][j] += x[i] * x[j]
    inverse = _inverse(xtx)
    coefficients = _matvec(inverse, xty)
    residuals = [
        y - sum(value * beta for value, beta in zip(x, coefficients))
        for x, y in zip(design, centered_outcome)
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
    total_ss = sum(value**2 for value in centered_outcome)
    residual_ss = sum(value**2 for value in residuals)
    return {
        "unit": "country–representative-series pair",
        "outcome": "recent missingness",
        "n": row_count,
        "clusters": cluster_count,
        "clustered_by": "country",
        "indicator_fixed_effects": True,
        "includes_statistical_performance": include_statistical_performance,
        "r_squared_within": round(1 - residual_ss / total_ss, 4) if total_ss else 0.0,
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
        "top_series": ranked[:10],
        "series": ranked,
    }


def _income_gap_interval(
    rows: list[dict[str, Any]],
    repetitions: int,
    label: str,
    population_weighted: bool = False,
) -> tuple[float, float]:
    country_rows = _country_means(rows)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in country_rows:
        grouped[row["income_group"]].append(row)
    high, low = grouped.get("High income", []), grouped.get("Low income", [])
    if not high or not low:
        return math.nan, math.nan
    rng = random.Random(_stable_seed(label))
    estimates = []
    for _ in range(repetitions):
        high_draw = [rng.choice(high) for _ in high]
        low_draw = [rng.choice(low) for _ in low]
        if population_weighted:
            high_mean = _weighted_mean(
                [item["missingness"] for item in high_draw],
                [item["population"] for item in high_draw],
            )
            low_mean = _weighted_mean(
                [item["missingness"] for item in low_draw],
                [item["population"] for item in low_draw],
            )
        else:
            high_mean = _mean(item["missingness"] for item in high_draw)
            low_mean = _mean(item["missingness"] for item in low_draw)
        estimates.append(100 * (low_mean - high_mean))
    return _quantile(estimates, 0.025), _quantile(estimates, 0.975)


def _country_distributions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "country": row["country_name"],
            "country_alpha3": row["country_alpha3"],
            "income_group": row["income_group"],
            "region": row["region"],
            "population": row["population"],
            "missingness_pct": round(100 * row["missingness"], 1),
        }
        for row in _country_means(rows)
    ]


def _income_goal_matrix(
    rows: list[dict[str, Any]], repetitions: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cells = []
    effects = []
    goals = sorted({row["goal"] for row in rows})
    incomes = ["High income", "Upper middle income", "Lower middle income", "Low income"]
    for goal in goals:
        goal_rows = [row for row in rows if row["goal"] == goal]
        summary = {item["group"]: item for item in _group_summary(goal_rows, "income_group", repetitions)}
        for income in incomes:
            if income in summary:
                cells.append({"goal": goal, "income_group": income, **summary[income]})
        low, high = _income_gap_interval(goal_rows, repetitions, f"goal-income:{goal}")
        if "Low income" in summary and "High income" in summary:
            effects.append(
                {
                    "goal": goal,
                    "estimate_pp": round(
                        summary["Low income"]["mean_missingness_pct"]
                        - summary["High income"]["mean_missingness_pct"],
                        1,
                    ),
                    "ci_low": round(low, 1),
                    "ci_high": round(high, 1),
                }
            )
    return cells, effects


def _status_composition(
    observations: list[dict[str, Any]],
    specs: list[SeriesSpec],
    countries: list[Country],
    completed_year: int,
) -> list[dict[str, Any]]:
    recent_start = completed_year - 4
    universal = {spec.code: spec for spec in specs if spec.applicability == "universal"}
    member_codes = {country.m49 for country in countries}
    by_cell: dict[tuple[str, str, int], set[str]] = defaultdict(set)
    for row in observations:
        year = row.get("reference_year")
        if (
            row.get("series_code") in universal
            and row.get("country_m49") in member_codes
            and year is not None
            and recent_start <= int(year) <= completed_year
        ):
            by_cell[(row["country_m49"], row["series_code"], int(year))].add(row.get("nature", "NA"))
    precedence = (
        ("country_reported", {"C", "CA"}),
        ("estimated", {"E"}),
        ("modelled_or_global", {"M", "G"}),
        ("other_official", {"N", "NA"}),
    )
    totals: dict[str, Counter[str]] = defaultdict(Counter)
    years_by_pair: dict[tuple[str, str], list[int]] = defaultdict(list)
    for country_code, series_code, year in by_cell:
        years_by_pair[(country_code, series_code)].append(year)
    for spec in universal.values():
        family = FAMILY_BY_GOAL[spec.goal]
        expected = max(1, math.ceil(5 / spec.cadence))
        for country in countries:
            years = sorted(set(years_by_pair[(country.m49, spec.code)]), reverse=True)[:expected]
            for year in years:
                natures = by_cell[(country.m49, spec.code, year)]
                category = next(
                    (label for label, values in precedence if natures & values),
                    "other_official",
                )
                totals[family][category] += 1
                totals["All indicators"][category] += 1
            missing = expected - len(years)
            totals[family]["missing"] += missing
            totals["All indicators"]["missing"] += missing
    output = []
    categories = ["country_reported", "estimated", "modelled_or_global", "other_official", "missing"]
    for group, counts in sorted(totals.items()):
        total = sum(counts.values())
        output.append(
            {
                "group": group,
                "total_expected_slots": total,
                "shares": {
                    category: round(100 * counts[category] / total, 1) if total else 0.0
                    for category in categories
                },
            }
        )
    return output


def _disaggregation_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["goal"]].append(row)
    output = []
    for goal, items in sorted(grouped.items()):
        for dimension in ("sex", "age", "location"):
            output.append(
                {
                    "goal": goal,
                    "dimension": dimension,
                    "coverage_pct": round(
                        100 * _mean(float(item["disaggregation"][dimension]) for item in items),
                        1,
                    ),
                }
            )
    return output


def _concentration_curve(concentration: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = concentration.get("series", concentration.get("top_series", []))
    total = sum(item["missing_expected_observations"] for item in ranked)
    cumulative = 0.0
    output = []
    for rank, item in enumerate(ranked, 1):
        cumulative += item["missing_expected_observations"]
        output.append(
            {
                **item,
                "rank": rank,
                "cumulative_share_pct": round(100 * cumulative / total, 1) if total else 0.0,
            }
        )
    return output


def run_analysis(
    metrics: dict[str, Any], observations: list[dict[str, Any]], specs: list[SeriesSpec],
    countries: list[Country], context: dict[str, dict[str, Any]], catalog: dict[str, dict[str, Any]],
    manifest: dict[str, Any], bootstrap_repetitions: int = 1000,
) -> dict[str, Any]:
    rows = _analysis_rows(metrics)
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
    country_model = fit_country_model(country_rows)
    pair_model = fit_pair_model(rows)
    context_model = fit_pair_model(rows, include_statistical_performance=True)
    variance = variance_decomposition(rows)
    concentration = missingness_concentration(rows, catalog)
    leave_one_out = leave_one_series_out(rows, catalog)

    sensitivity_inputs = [
        ("Primary: all official statuses, 5 years", rows, False),
        ("Short window: 3 years", _window_rows(rows, metrics["completed_year"], 3), False),
        ("Long window: 7 years", _window_rows(rows, metrics["completed_year"], 7), False),
        ("Country-reported statuses only", reported_rows, False),
        ("Countries weighted by population", rows, True),
    ]
    sensitivity = []
    for label, sensitivity_rows, weighted in sensitivity_inputs:
        entry = _sensitivity_entry(label, sensitivity_rows, population_weighted=weighted)
        low, high = _income_gap_interval(
            sensitivity_rows,
            bootstrap_repetitions,
            f"sensitivity:{label}",
            population_weighted=weighted,
        )
        entry.update({"ci_low": round(low, 1), "ci_high": round(high, 1)})
        sensitivity.append(entry)

    income_goal, goal_income_effects = _income_goal_matrix(rows, bootstrap_repetitions)
    status_counts = Counter(row.get("nature", "NA") for row in observations)
    analysis = {
        "snapshot": {
            "retrieved_at": manifest["retrieved_at"],
            "completed_year": metrics["completed_year"],
            "recent_window": metrics["recent_window"],
            "snapshot_id": manifest.get("snapshot_id"),
        },
        "design": {
            "primary_outcome": "recent missingness",
            "unit": "country, averaged equally across universal representative series",
            "countries": len(country_rows),
            "official_indicators": len({indicator for spec in specs for indicator in spec.indicators}),
            "representative_series": len(specs),
            "universal_series": universal_series,
            "country_series_pairs": len(rows),
            "bootstrap_repetitions": bootstrap_repetitions,
            "interpretation": "descriptive associations, not causal effects",
        },
        "audit": {
            "manifest_status": manifest["status"],
            "rectangular_panel": len(rows) == len(country_rows) * universal_series,
            "countries_with_complete_context": sum(
                row["population"] is not None
                and row["region"] != "Unknown"
                and row["income_group"] != "Unknown"
                for row in country_rows
            ),
            "future_observations_excluded": sum(
                int(row["reference_year"]) > metrics["completed_year"]
                for row in observations
                if row.get("reference_year") is not None
            ),
            "observation_status_counts": dict(sorted(status_counts.items())),
        },
        "summaries": {
            "income": _group_summary(rows, "income_group", bootstrap_repetitions),
            "region": _group_summary(rows, "region", bootstrap_repetitions),
            "goal": _group_summary(rows, "goal", bootstrap_repetitions),
            "family": _group_summary(rows, "family", bootstrap_repetitions),
        },
        "country_distribution": _country_distributions(rows),
        "income_goal_matrix": income_goal,
        "goal_income_effects": goal_income_effects,
        "reporting_status": _status_composition(
            observations, specs, countries, metrics["completed_year"]
        ),
        "disaggregation_by_goal": _disaggregation_summary(rows),
        "population_association": {
            "spearman_rho": round(rho, 3),
            "ci_low": round(rho_low, 3),
            "ci_high": round(rho_high, 3),
        },
        "pair_model": pair_model,
        "context_model": context_model,
        "country_model": country_model,
        "variance_decomposition": variance,
        "concentration": {
            **concentration,
            "curve": _concentration_curve(concentration),
        },
        "leave_one_indicator_out": leave_one_out,
        "sensitivity": sensitivity,
    }
    if not analysis["audit"]["rectangular_panel"]:
        raise ValueError("Research analysis requires a rectangular country-series panel")
    if analysis["audit"]["countries_with_complete_context"] != len(country_rows):
        raise ValueError("Research analysis requires complete country context")
    return analysis
