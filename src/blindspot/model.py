from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from .config import Country, SeriesSpec


def _sigmoid(value: float) -> float:
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _fit_logistic(features: list[list[float]], targets: list[int], steps: int = 350) -> list[float]:
    if not features:
        return []
    weights = [0.0] * (len(features[0]) + 1)
    learning_rate = 0.15
    for _ in range(steps):
        gradients = [0.0] * len(weights)
        for row, target in zip(features, targets):
            prediction = _sigmoid(weights[0] + sum(w * x for w, x in zip(weights[1:], row)))
            error = prediction - target
            gradients[0] += error
            for index, value in enumerate(row, 1):
                gradients[index] += error * value
        scale = 1 / len(features)
        for index in range(len(weights)):
            penalty = 0.001 * weights[index] if index else 0.0
            weights[index] -= learning_rate * (gradients[index] * scale + penalty)
    return weights


def _predict(weights: list[float], row: list[float]) -> float:
    return _sigmoid(weights[0] + sum(w * x for w, x in zip(weights[1:], row)))


def _auc(targets: list[int], predictions: list[float]) -> float | None:
    positives = sum(targets)
    negatives = len(targets) - positives
    if positives == 0 or negatives == 0:
        return None
    ranked = sorted(zip(predictions, targets), key=lambda item: item[0])
    rank_sum = 0.0
    index = 0
    while index < len(ranked):
        end = index + 1
        while end < len(ranked) and ranked[end][0] == ranked[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2
        rank_sum += average_rank * sum(target for _, target in ranked[index:end])
        index = end
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def _average_precision(targets: list[int], predictions: list[float]) -> float | None:
    positives = sum(targets)
    if positives == 0:
        return None
    ranked = sorted(zip(predictions, targets), reverse=True)
    hits = 0
    total = 0.0
    for index, (_, target) in enumerate(ranked, 1):
        if target:
            hits += 1
            total += hits / index
    return total / positives


def _scores(targets: list[int], predictions: list[float]) -> dict[str, float | None]:
    if not targets:
        return {"n": 0, "auroc": None, "average_precision": None, "brier": None}
    return {
        "n": len(targets),
        "auroc": round(_auc(targets, predictions), 4) if _auc(targets, predictions) is not None else None,
        "average_precision": round(_average_precision(targets, predictions), 4)
        if _average_precision(targets, predictions) is not None
        else None,
        "brier": round(sum((p - y) ** 2 for p, y in zip(predictions, targets)) / len(targets), 4),
    }


def train_continuity_model(
    observations: list[dict[str, Any]],
    specs: list[SeriesSpec],
    countries: list[Country],
    context: dict[str, dict[str, Any]],
    completed_year: int,
) -> dict[str, Any]:
    observed: dict[tuple[str, str], set[int]] = defaultdict(set)
    for row in observations:
        year = row.get("reference_year")
        if year is not None and int(year) <= completed_year:
            observed[(row["country_m49"], row["series_code"])].add(int(year))
    populations = [
        context.get(country.alpha3, {}).get("population") or 0 for country in countries
    ]
    max_log_population = max((math.log1p(value) for value in populations), default=1.0)
    series_rate: dict[str, float] = {}
    for spec in specs:
        cells = len(countries) * max(1, completed_year - 2015 + 1)
        present = sum(len(observed[(country.m49, spec.code)]) for country in countries)
        series_rate[spec.code] = min(1.0, present / cells)

    feature_names = [
        "normalized_gap",
        "historical_presence_rate",
        "series_presence_rate",
        "log_population",
        "cadence",
        "goal",
    ]
    samples: list[tuple[int, list[float], int, float]] = []
    for spec in specs:
        if spec.applicability != "universal":
            continue
        for country in countries:
            years = observed[(country.m49, spec.code)]
            population = context.get(country.alpha3, {}).get("population") or 0
            for prediction_year in range(2020, completed_year + 1):
                if prediction_year + spec.cadence - 1 > completed_year:
                    continue
                history = [year for year in years if 2015 <= year < prediction_year]
                latest = max(history) if history else None
                gap = prediction_year - latest if latest is not None else prediction_year - 2015
                history_span = max(1, prediction_year - 2015)
                row = [
                    min(1.0, gap / max(1, spec.cadence * 4)),
                    len(history) / history_span,
                    series_rate[spec.code],
                    math.log1p(population) / max_log_population if max_log_population else 0.0,
                    spec.cadence / 5,
                    spec.goal / 17,
                ]
                target_window = range(prediction_year, min(completed_year + 1, prediction_year + spec.cadence))
                target = int(not any(year in years for year in target_window))
                samples.append((prediction_year, row, target, 1 - series_rate[spec.code]))

    test_start = max(2021, completed_year - 3)
    train = [sample for sample in samples if sample[0] < test_start]
    test = [sample for sample in samples if sample[0] >= test_start]
    weights = _fit_logistic([x[1] for x in train], [x[2] for x in train])
    targets = [x[2] for x in test]
    predictions = [_predict(weights, x[1]) for x in test]
    baseline_predictions = [x[3] for x in test]
    model_scores = _scores(targets, predictions)
    baseline_scores = _scores(targets, baseline_predictions)
    selected = "logistic_regression"
    if model_scores["auroc"] is None:
        selected = "descriptive_only"
    elif model_scores["brier"] is None or (
        baseline_scores["brier"] is not None and baseline_scores["brier"] <= model_scores["brier"]
    ):
        selected = "series_rate_baseline"
    return {
        "schema_version": "1.0.0",
        "target": "No observation in the next configured reporting window",
        "experimental": True,
        "feature_names": feature_names,
        "split": {
            "training_through": test_start - 1,
            "testing_from": test_start,
            "temporal": True,
        },
        "candidates": {
            "logistic_regression": {"metrics": model_scores, "weights": [round(x, 6) for x in weights]},
            "series_rate_baseline": {"metrics": baseline_scores},
        },
        "selected": selected,
        "limitations": [
            "Publication-year vintages are unavailable before Blindspot launch.",
            "A missing reference-year observation may be published later and is not proof of collection failure.",
            "Features describe associations and must not be interpreted causally.",
        ],
    }
