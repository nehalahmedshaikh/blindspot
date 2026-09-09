from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .analysis import run_analysis
from .config import (
    CACHE_DIR,
    DATA_DIR,
    LATEST_COMPLETED_YEAR,
    OBSERVATION_START_YEAR,
    PROJECT_ROOT,
    SITE_DATA_DIR,
    ensure_directories,
    load_countries,
    load_goals,
    load_series,
)
from .metrics import calculate_metrics
from .sources import (
    SourceError,
    fetch_series_catalog,
    fetch_un_observations,
    fetch_world_bank_context,
    load_cached_observations,
    observations_sha256,
    read_cache_json,
    utc_now,
    write_cache_json,
)


def _observation_key(row: dict[str, Any]) -> str:
    dimensions = json.dumps(row.get("dimensions", {}), sort_keys=True, separators=(",", ":"))
    return "|".join(
        [row["country_m49"], row["series_code"], str(row["reference_year"]), dimensions]
    )


def _revision_projection(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": _observation_key(row),
        "value": row.get("value"),
        "nature": row.get("nature"),
        "unit": row.get("unit"),
    }


def _write_gzip_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def record_revision_history(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> dict[str, int]:
    history_dir = DATA_DIR / "history"
    baseline = history_dir / "baseline.jsonl.gz"
    current_map = {_observation_key(row): _revision_projection(row) for row in current}
    if not baseline.exists():
        _write_gzip_jsonl(baseline, sorted(current_map.values(), key=lambda item: item["key"]))
        return {"baseline_cells": len(current_map), "added": 0, "removed": 0, "changed": 0}
    previous_map = {_observation_key(row): _revision_projection(row) for row in previous}
    previous_series = {row["series_code"] for row in previous}
    current_series = {row["series_code"] for row in current}
    shared_series = previous_series & current_series
    comparable_keys = {
        key for key in current_map.keys() | previous_map.keys()
        if key.split("|", 2)[1] in shared_series
    }
    delta: list[dict[str, Any]] = []
    for key in sorted(comparable_keys):
        before = previous_map.get(key)
        after = current_map.get(key)
        if before == after:
            continue
        change = "added" if before is None else "removed" if after is None else "changed"
        delta.append({"key": key, "change": change, "before": before, "after": after})
    if delta:
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
        _write_gzip_jsonl(history_dir / "deltas" / f"{stamp}.jsonl.gz", delta)
    counts = {kind: sum(item["change"] == kind for item in delta) for kind in ("added", "removed", "changed")}
    return {
        "baseline_cells": 0,
        **counts,
        "series_added_to_scope": len(current_series - previous_series),
        "series_removed_from_scope": len(previous_series - current_series),
    }


def refresh() -> bool:
    ensure_directories()
    specs = load_series()
    countries = load_countries()
    previous: list[dict[str, Any]] = []
    try:
        previous = load_cached_observations()
    except SourceError:
        pass
    try:
        catalog, catalog_manifest = fetch_series_catalog(specs)
        context, context_manifest = fetch_world_bank_context(countries)
        observations, observations_manifest = fetch_un_observations(specs, countries)
    except SourceError:
        if not previous:
            raise
        return False

    history = record_revision_history(previous, observations)
    source_manifests = [catalog_manifest, context_manifest, observations_manifest]
    snapshot_id = hashlib.sha256(
        json.dumps(
            [(item["source"], item["sha256"]) for item in source_manifests],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()[:16]
    staging = CACHE_DIR.parent / ".current-next"
    backup = CACHE_DIR.parent / ".current-previous"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    _write_gzip_jsonl(staging / "observations.jsonl.gz", observations)
    observations_manifest["artifact_sha256"] = hashlib.sha256(
        (staging / "observations.jsonl.gz").read_bytes()
    ).hexdigest()
    for name, payload in (("catalog.json", catalog), ("context.json", context)):
        (staging / name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    manifest = {
        "schema_version": "1.0.0",
        "status": "fresh",
        "retrieved_at": utc_now(),
        "snapshot_id": snapshot_id,
        "sources": source_manifests,
        "history": history,
        "last_error": None,
    }
    (staging / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if backup.exists():
        shutil.rmtree(backup)
    if CACHE_DIR.exists():
        CACHE_DIR.replace(backup)
    staging.replace(CACHE_DIR)
    if backup.exists():
        shutil.rmtree(backup)
    return True


def build(completed_year: int | None = None) -> dict[str, Any]:
    metrics = calculate_metrics(
        load_cached_observations(),
        load_series(),
        load_countries(),
        read_cache_json("context.json"),
        read_cache_json("catalog.json"),
        completed_year,
    )
    manifest = read_cache_json("manifest.json")
    metrics["snapshot_id"] = manifest.get("snapshot_id")
    write_cache_json("metrics.json", metrics)
    return metrics


def analyze() -> dict[str, Any]:
    try:
        metrics = read_cache_json("metrics.json")
    except SourceError:
        metrics = build()
    result = run_analysis(
        metrics,
        load_cached_observations(),
        load_series(),
        load_countries(),
        read_cache_json("context.json"),
        read_cache_json("catalog.json"),
        read_cache_json("manifest.json"),
    )
    write_cache_json("analysis.json", result)
    return result


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def export() -> dict[str, Any]:
    ensure_directories()
    output_dir = SITE_DATA_DIR.parent / ".data-next"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    goals = load_goals()
    try:
        metrics = read_cache_json("metrics.json")
    except SourceError:
        metrics = build()
    manifest = read_cache_json("manifest.json")
    try:
        analysis_result = read_cache_json("analysis.json")
        snapshot = analysis_result.get("snapshot", {})
        if (
            snapshot.get("retrieved_at") != manifest["retrieved_at"]
            or snapshot.get("completed_year") != metrics["completed_year"]
            or snapshot.get("snapshot_id") != manifest.get("snapshot_id")
        ):
            analysis_result = analyze()
    except SourceError:
        analysis_result = analyze()
    dashboard = {
        "meta": {
            "schema_version": metrics["schema_version"],
            "completed_year": metrics["completed_year"],
            "recent_window": metrics["recent_window"],
            "retrieved_at": manifest["retrieved_at"],
            "status": manifest["status"],
            "snapshot_id": manifest.get("snapshot_id"),
        },
        "countries": metrics["countries"],
        "series": metrics["series"],
        "country_series": [
            {
                key: item[key]
                for key in (
                    "country_alpha3",
                    "country_name",
                    "series_code",
                    "goal",
                    "goals",
                    "indicators",
                    "applicability",
                    "latest_year",
                    "recent_completeness",
                    "staleness",
                    "measurement_priority_v1",
                    "score_components",
                    "disaggregation",
                    "nature_counts",
                )
            }
            for item in metrics["country_series"]
        ],
        "top_rankings": metrics["rankings"][:500],
    }
    compact_dashboard = json.dumps(
        dashboard, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ) + "\n"
    (CACHE_DIR / "dashboard.json").write_text(compact_dashboard, encoding="utf-8")
    legacy_dashboard = output_dir / "dashboard.json"
    if legacy_dashboard.exists():
        legacy_dashboard.unlink()

    country_rows: dict[str, list[dict[str, Any]]] = {
        country["alpha3"]: [] for country in metrics["countries"]
    }
    for item in dashboard["country_series"]:
        country_rows[item["country_alpha3"]].append(item)

    country_data_dir = output_dir / "countries"
    goal_data_dir = output_dir / "goals"
    for generated_dir in (country_data_dir, goal_data_dir):
        if generated_dir.exists():
            shutil.rmtree(generated_dir)
        generated_dir.mkdir(parents=True)

    site_countries = []
    goal_summaries: dict[str, dict[str, dict[str, float]]] = {
        str(goal["id"]): {} for goal in goals
    }
    for country in metrics["countries"]:
        alpha3 = country["alpha3"]
        data_file = f"countries/{alpha3}.json"
        summary = {key: value for key, value in country.items() if key != "goals"}
        site_countries.append({**summary, "data_file": data_file})
        (output_dir / data_file).write_text(
            json.dumps(country_rows[alpha3], ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for goal, values in country["goals"].items():
            goal_summaries[goal][alpha3] = values
    site_goals = []
    for goal in goals:
        goal_id = str(goal["id"])
        data_file = f"goals/{int(goal_id):02d}.json"
        site_goals.append({**goal, "data_file": data_file})
        (output_dir / data_file).write_text(
            json.dumps(goal_summaries[goal_id], separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )

    catalog = read_cache_json("catalog.json")
    metrics_by_code = {item["code"]: item for item in metrics["series"]}
    representative_by_indicator = {
        indicator: spec
        for spec in load_series()
        for indicator in spec.indicators
    }
    indicator_catalog = []
    indicator_ids = sorted(
        representative_by_indicator,
        key=lambda value: [
            (0, int(token)) if token.isdigit() else (1, token)
            for token in value.replace(".", " ").split()
        ],
    )
    for indicator_id in indicator_ids:
        spec = representative_by_indicator[indicator_id]
        variants = [
            {
                "code": item["code"],
                "description": item.get("description", item["code"]),
            }
            for item in catalog.values()
            if indicator_id in item.get("indicator", [])
        ]
        variants.sort(key=lambda item: item["code"])
        indicator_catalog.append(
            {
                "id": indicator_id,
                "goals": spec.goals or [spec.goal],
                "representative": metrics_by_code[spec.code],
                "variants": variants,
            }
        )

    download_catalog = [
        {"label": "Gap rankings", "format": "CSV", "href": "assets/data/downloads/gap_rankings.csv", "description": "Every ranked country–representative-series pair."},
        {"label": "Indicator selection", "format": "CSV", "href": "assets/data/downloads/indicator_selection.csv", "description": "Representative mappings, cadence, scope, and selection audit."},
        {"label": "Country scores", "format": "CSV", "href": "assets/data/downloads/country_scores.csv", "description": "Country-level atlas summaries."},
        {"label": "Group comparisons", "format": "CSV", "href": "assets/data/downloads/analysis_groups.csv", "description": "Income, region, goal, and SDG-family comparisons."},
        {"label": "Country distribution", "format": "CSV", "href": "assets/data/downloads/analysis_country_distribution.csv", "description": "Country values behind the comparison chart."},
        {"label": "Income by goal", "format": "CSV", "href": "assets/data/downloads/analysis_income_goal.csv", "description": "Values behind the income–goal matrix."},
        {"label": "Reporting status", "format": "CSV", "href": "assets/data/downloads/analysis_reporting_status.csv", "description": "Country-reported, estimated, modelled, other, and missing shares."},
        {"label": "Breakdown visibility", "format": "CSV", "href": "assets/data/downloads/analysis_disaggregation.csv", "description": "Recent sex, age, and location visibility by goal."},
        {"label": "Adjusted model", "format": "CSV", "href": "assets/data/downloads/analysis_model.csv", "description": "Adjusted estimates with representative-series fixed effects."},
        {"label": "Robustness", "format": "CSV", "href": "assets/data/downloads/analysis_sensitivity.csv", "description": "Alternative windows, statuses, and weighting."},
        {"label": "Indicator influence", "format": "CSV", "href": "assets/data/downloads/analysis_leave_one_indicator.csv", "description": "Income gap after removing each representative series."},
        {"label": "Concentration", "format": "CSV", "href": "assets/data/downloads/analysis_concentration.csv", "description": "Ranked contributions to total missingness."},
        {"label": "Full research results", "format": "JSON", "href": "assets/data/analysis.json", "description": "Complete chart and model contract."},
        {"label": "Method contract", "format": "JSON", "href": "assets/data/methodology.json", "description": "Definitions, formulas, and glossary."},
        {"label": "Provenance manifest", "format": "JSON", "href": "assets/data/manifest.json", "description": "Source URLs, retrieval times, hashes, and row counts."},
        {"label": "Checksums", "format": "JSON", "href": "assets/data/checksums.json", "description": "SHA-256 hashes for every published data file."},
    ]
    site_meta = {
        "meta": {
            "completed_year": metrics["completed_year"],
            "recent_window": metrics["recent_window"],
            "observation_window": [
                min(year for item in metrics["country_series"] for year in item["observed_years"]),
                max(year for item in metrics["country_series"] for year in item["observed_years"]),
            ],
            "retrieved_at": manifest["retrieved_at"],
            "status": manifest["status"],
            "snapshot_id": manifest.get("snapshot_id"),
        },
        "counts": {
            "countries": len(metrics["countries"]),
            "series": len(metrics["series"]),
            "indicators": len(indicator_catalog),
            "goals": len(goals),
            "country_series_assessments": len(metrics["country_series"]),
            "universal_series": analysis_result["design"]["universal_series"],
            "statistical_performance_countries": analysis_result["context_model"]["clusters"],
        },
    }
    data_catalog = {
        "downloads": download_catalog,
        "references": [
            {"label": "UN SDG indicator metadata", "href": "https://unstats.un.org/sdgs/metadata/", "description": "Official indicator definitions and methods."},
            {"label": "UN 2030 Agenda", "href": "https://sdgs.un.org/2030agenda", "description": "The goals and five-part SDG framing."},
            {"label": "Open Data Inventory", "href": "https://odin.opendatawatch.com/", "description": "National statistics coverage and openness."},
            {"label": "PARIS21 Statistical Capacity Monitor", "href": "https://www.paris21.org/our-impact/matching-capacity-needs-how-paris21s-statistical-capacity-monitor-helping-put-data-and", "description": "Statistical capacity indicators and resources."},
            {"label": "Sustainable Development Report", "href": "https://dashboards.sdgindex.org/", "description": "SDG outcome reporting and dashboards."},
            {"label": "World Bank Statistical Performance Indicators", "href": "https://www.worldbank.org/en/programs/statistical-performance-indicators", "description": "Country statistical-system context used in the secondary analysis."},
            {"label": "World Bank Missing Evidence", "href": "https://blogs.worldbank.org/en/opendata/missing-evidence-tracking-academic-data-use-around-world", "description": "Related work on gaps in evidence use."},
        ],
    }
    payloads = {
        "meta.json": site_meta,
        "countries.json": site_countries,
        "series.json": metrics["series"],
        "indicators.json": indicator_catalog,
        "goals.json": site_goals,
        "rankings.json": {
            "fields": [
                "country_alpha3",
                "series_code",
                "latest_year",
                "staleness",
                "missingness",
                "global_scarcity",
                "population",
            ],
            "rows": [
                [
                    item["country_alpha3"],
                    item["series_code"],
                    item["latest_year"],
                    item["score_components"]["staleness"],
                    item["score_components"]["completeness_deficit"],
                    item["score_components"]["global_scarcity"],
                    item["score_components"]["population_percentile"],
                ]
                for item in metrics["rankings"]
            ],
        },
        "data-catalog.json": data_catalog,
    }
    old_index = output_dir / "index.json"
    if old_index.exists():
        old_index.unlink()
    for name, payload in payloads.items():
        (output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for name in ("manifest.json", "analysis.json"):
        shutil.copy2(CACHE_DIR / name, output_dir / name)
    downloads = output_dir / "downloads"
    if downloads.exists():
        shutil.rmtree(downloads)
    downloads.mkdir(parents=True)
    _write_csv(
        downloads / "gap_rankings.csv",
        [
            {
                **item,
                "score_components": json.dumps(item.get("score_components"), sort_keys=True),
                "disaggregation": json.dumps(item.get("disaggregation"), sort_keys=True),
                "nature_counts": json.dumps(item.get("nature_counts"), sort_keys=True),
                "observed_years": ";".join(map(str, item.get("observed_years", []))),
            }
            for item in metrics["rankings"]
        ],
        [
            "country_m49",
            "country_alpha3",
            "country_name",
            "series_code",
            "goal",
            "applicability",
            "expected_cadence_years",
            "latest_year",
            "observed_years",
            "recent_completeness",
            "staleness",
            "regularity",
            "has_aggregate_slice",
            "disaggregation",
            "nature_counts",
            "global_scarcity",
            "measurement_priority_v1",
            "score_components",
        ],
    )
    _write_csv(
        downloads / "country_scores.csv",
        metrics["countries"],
        [
            "m49",
            "alpha3",
            "name",
            "region",
            "income_group",
            "population",
            "population_year",
            "statistical_performance",
            "statistical_performance_year",
            "completeness",
            "staleness",
            "priority",
        ],
    )
    group_rows = []
    for dimension, groups in analysis_result["summaries"].items():
        for group in groups:
            group_rows.append({"dimension": dimension, **group})
    _write_csv(
        downloads / "analysis_groups.csv",
        group_rows,
        [
            "dimension",
            "group",
            "countries",
            "mean_missingness_pct",
            "ci_low",
            "ci_high",
            "mean_staleness",
        ],
    )
    _write_csv(
        downloads / "analysis_model.csv",
        analysis_result["pair_model"]["coefficients"],
        [
            "term",
            "estimate_percentage_points",
            "standard_error",
            "ci_low",
            "ci_high",
        ],
    )
    _write_csv(
        downloads / "analysis_context_model.csv",
        analysis_result["context_model"]["coefficients"],
        [
            "term",
            "estimate_percentage_points",
            "standard_error",
            "ci_low",
            "ci_high",
        ],
    )
    _write_csv(
        downloads / "analysis_sensitivity.csv",
        analysis_result["sensitivity"],
        ["specification", "mean_missingness_pct", "low_minus_high_income_pp", "ci_low", "ci_high"],
    )
    _write_csv(
        downloads / "indicator_selection.csv",
        [
            {
                "indicator_ids": ";".join(item["indicator"]),
                "goals": ";".join(map(str, item["goals"])),
                "representative_series": item["code"],
                "description": item["description"],
                "cadence_years": item["cadence"],
                "applicability": item["applicability"],
                "member_countries_at_selection": item["selection"]["member_countries"],
                "observation_rows_2015_2025": item["selection"]["observation_rows_2015_2025"],
                "selection_basis": item["selection"]["basis"],
            }
            for item in metrics["series"]
        ],
        [
            "indicator_ids",
            "goals",
            "representative_series",
            "description",
            "cadence_years",
            "applicability",
            "member_countries_at_selection",
            "observation_rows_2015_2025",
            "selection_basis",
        ],
    )
    _write_csv(
        downloads / "analysis_country_distribution.csv",
        analysis_result["country_distribution"],
        ["country", "country_alpha3", "income_group", "region", "population", "missingness_pct"],
    )
    _write_csv(
        downloads / "analysis_income_goal.csv",
        analysis_result["income_goal_matrix"],
        ["goal", "income_group", "countries", "mean_missingness_pct", "ci_low", "ci_high", "mean_staleness"],
    )
    _write_csv(
        downloads / "analysis_goal_income_effects.csv",
        analysis_result["goal_income_effects"],
        ["goal", "estimate_pp", "ci_low", "ci_high"],
    )
    _write_csv(
        downloads / "analysis_reporting_status.csv",
        [
            {"group": item["group"], "total_expected_slots": item["total_expected_slots"], **item["shares"]}
            for item in analysis_result["reporting_status"]
        ],
        [
            "group",
            "total_expected_slots",
            "country_reported",
            "estimated",
            "modelled_or_global",
            "other_official",
            "missing",
        ],
    )
    _write_csv(
        downloads / "analysis_disaggregation.csv",
        analysis_result["disaggregation_by_goal"],
        ["goal", "dimension", "coverage_pct"],
    )
    _write_csv(
        downloads / "analysis_concentration.csv",
        analysis_result["concentration"]["curve"],
        [
            "rank",
            "series_code",
            "goal",
            "description",
            "mean_missingness_pct",
            "missing_expected_observations",
            "cumulative_share_pct",
        ],
    )
    _write_csv(
        downloads / "analysis_leave_one_indicator.csv",
        analysis_result["leave_one_indicator_out"]["estimates"],
        ["excluded_series", "description", "low_minus_high_income_pp"],
    )
    methodology = {
        "recent_window": metrics["recent_window"],
        "coverage": "The share of countries meeting the expected reporting cadence during the latest five completed years.",
        "applicability": {
            "universal": "Applies to every country.",
            "conditional": "Contextual series remain searchable but are not treated as comparable gaps.",
        },
        "measurement_priority": {
            "scale": "0 to 100; higher means a larger reporting gap under the chosen weights.",
            "formula": "100 × weighted average of staleness, missingness, global scarcity, and population rank",
            "weights": [
                {"id": "staleness", "label": "Staleness", "weight": 0.35, "meaning": "How overdue the latest observation is."},
                {"id": "missingness", "label": "Missingness", "weight": 0.25, "meaning": "How many expected recent reporting years are absent."},
                {"id": "global_scarcity", "label": "Global scarcity", "weight": 0.20, "meaning": "How rarely the series is reported across countries."},
                {"id": "population", "label": "Population", "weight": 0.20, "meaning": "How large the affected population is, using log-population rank."},
            ],
            "scope": "Only universal series receive a measurement-priority score.",
        },
        "research": [
            {"label": "What is compared", "text": "Each country–representative-series pair contributes its share of expected recent observations that are absent."},
            {"label": "Adjusted comparisons", "text": "The model compares income group, region, and population after absorbing representative-series baselines."},
            {"label": "Intervals", "text": "Model uncertainty is clustered by country; descriptive chart intervals come from resampling countries."},
            {"label": "Available context", "text": "The main model uses income group, region, population, and representative-series baselines. A secondary model adds World Bank statistical performance."},
            {"label": "How to read the results", "text": "Associations describe this source and selection of series; they do not establish causes or measure all data a country collects."},
        ],
        "glossary": [
            {"term": "Adjusted comparison", "definition": "A comparison made after accounting for other named characteristics in the model."},
            {"term": "Bootstrap interval", "definition": "A range obtained by repeatedly resampling countries and recalculating the result."},
            {"term": "Breakdown coverage", "definition": "The share of countries where more than one sex, age, or location category is visible."},
            {"term": "Conditional series", "definition": "An indicator series that applies only where the measured subject exists."},
            {"term": "Clustered uncertainty", "definition": "An uncertainty calculation that allows results from the same country to be related."},
            {"term": "Confidence interval", "definition": "A model-based range showing the uncertainty around an estimate."},
            {"term": "Country–indicator pair", "definition": "One country evaluated for one indicator series."},
            {"term": "Coverage", "definition": "The share of countries meeting an indicator's expected recent reporting cadence."},
            {"term": "Global scarcity", "definition": "How rarely an indicator series is reported across countries."},
            {"term": "Indicator series", "definition": "One statistic tracked over time, such as maternal mortality or access to electricity."},
            {"term": "Measurement priority", "definition": "A 0–100 ranking that combines staleness, missingness, global scarcity, and population."},
            {"term": "Representative series", "definition": "The one official series used to represent an SDG indicator without giving split variants extra analytical weight."},
            {"term": "Missingness", "definition": "The share of expected recent observations absent from the selected UN source."},
            {"term": "Percentage point", "definition": "The direct difference between two percentages; 50% minus 40% is 10 percentage points."},
            {"term": "Sensitivity analysis", "definition": "Recalculating a result under reasonable alternative choices to see whether it persists."},
            {"term": "Staleness", "definition": "How overdue the latest observation is relative to its expected reporting cadence."},
            {"term": "Statistical performance", "definition": "The World Bank’s 0–100 assessment of how well a national statistical system serves users."},
            {"term": "Sustainable Development Goal", "definition": "One of the UN's 17 shared development goals."},
            {"term": "Universal series", "definition": "An indicator series intended to apply to every country."},
        ],
    }
    (output_dir / "methodology.json").write_text(
        json.dumps(methodology, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksums = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "checksums.json":
            checksums[str(path.relative_to(output_dir))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output_dir / "checksums.json").write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    backup_dir = SITE_DATA_DIR.parent / ".data-previous"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    if SITE_DATA_DIR.exists():
        SITE_DATA_DIR.replace(backup_dir)
    output_dir.replace(SITE_DATA_DIR)
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    return {"countries": site_countries, "series": metrics["series"]}


def validate() -> list[str]:
    errors: list[str] = []
    specs = load_series()
    goals = load_goals()
    countries = load_countries()
    goal_ids = {goal["id"] for goal in goals}
    configured_goal_ids = {goal for spec in specs for goal in (spec.goals or [spec.goal])}
    if not specs:
        errors.append("At least one series must be configured")
    if configured_goal_ids != goal_ids:
        errors.append(
            f"Series and goal metadata disagree: series={sorted(configured_goal_ids)}, "
            f"goals={sorted(goal_ids)}"
        )
    if len({spec.code for spec in specs}) != len(specs):
        errors.append("Series codes are not unique")
    if not countries:
        errors.append("At least one country must be configured")
    if len({country.m49 for country in countries}) != len(countries):
        errors.append("Country M49 codes are not unique")
    metrics = read_cache_json("metrics.json")
    manifest = read_cache_json("manifest.json")
    analysis_result = read_cache_json("analysis.json")
    observations = load_cached_observations()
    catalog = read_cache_json("catalog.json")
    configured_indicators = [indicator for spec in specs for indicator in spec.indicators]
    official_indicators = {
        indicator for item in catalog.values() for indicator in item.get("indicator", [])
    }
    if len(configured_indicators) != len(set(configured_indicators)):
        errors.append("Official indicators do not map to exactly one representative")
    if set(configured_indicators) != official_indicators:
        errors.append("Representative mapping does not cover the current official indicator catalogue")
    for spec in specs:
        metadata = catalog.get(spec.code, {})
        if not set(spec.indicators) <= set(metadata.get("indicator", [])):
            errors.append(f"Representative mapping disagrees with UN metadata: {spec.code}")
    if manifest.get("status") != "fresh":
        errors.append("Source manifest is not fresh")
    if any(source.get("status") != "fresh" for source in manifest.get("sources", [])):
        errors.append("One or more source manifests are not fresh")
    sources_by_name = {source.get("source"): source for source in manifest.get("sources", [])}
    expected_source_hashes = {
        "UNSD SDG series catalog": hashlib.sha256(
            json.dumps(catalog, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
        "World Bank population and statistical performance": hashlib.sha256(
            json.dumps(read_cache_json("context.json"), sort_keys=True).encode()
        ).hexdigest(),
        "UNSD SDG API": observations_sha256(observations),
    }
    for source_name, expected_hash in expected_source_hashes.items():
        if sources_by_name.get(source_name, {}).get("sha256") != expected_hash:
            errors.append(f"Cached source content does not match its manifest: {source_name}")
    observation_source = sources_by_name.get("UNSD SDG API", {})
    artifact_hash = hashlib.sha256((CACHE_DIR / "observations.jsonl.gz").read_bytes()).hexdigest()
    if observation_source.get("artifact_sha256") != artifact_hash:
        errors.append("Observation artifact does not match its manifest")
    expected_snapshot_id = hashlib.sha256(
        json.dumps(
            [(source.get("source"), source.get("sha256")) for source in manifest.get("sources", [])],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()[:16]
    snapshot_id = manifest.get("snapshot_id")
    if snapshot_id != expected_snapshot_id:
        errors.append("Source snapshot identifier is not reproducible from its manifests")
    if not snapshot_id:
        errors.append("Source manifest has no snapshot identifier")
    if metrics.get("snapshot_id") != snapshot_id:
        errors.append("Metrics and source snapshots do not match")
    if len(metrics.get("countries", [])) != len(countries):
        errors.append("Metrics country count does not match configuration")
    if len(metrics.get("series", [])) != len(specs):
        errors.append("Metrics series count does not match configuration")
    years = {int(item["reference_year"]) for item in observations if item.get("reference_year") is not None}
    if not years or min(years) != OBSERVATION_START_YEAR or max(years) != LATEST_COMPLETED_YEAR:
        errors.append("Observation snapshot does not match the configured year bounds")
    un_source = next(
        (source for source in manifest.get("sources", []) if source.get("source") == "UNSD SDG API"),
        {},
    )
    series_rows = un_source.get("series_rows", {})
    empty_series = [
        spec.code for spec in specs
        if spec.applicability == "universal" and series_rows.get(spec.code, 0) == 0
    ]
    if empty_series:
        errors.append(f"Configured series with no member-state rows: {sorted(empty_series)}")
    design = analysis_result.get("design", {})
    universal_count = sum(spec.applicability == "universal" for spec in specs)
    if design.get("countries") != len(countries):
        errors.append("Analysis does not contain every country")
    if design.get("universal_series") != universal_count:
        errors.append("Analysis universal-series count does not match configuration")
    if design.get("country_series_pairs") != len(countries) * universal_count:
        errors.append("Analysis panel is not rectangular")
    if not analysis_result.get("audit", {}).get("rectangular_panel"):
        errors.append("Analysis rectangular-panel audit failed")
    pair_model = analysis_result.get("pair_model", {})
    if pair_model.get("n") != len(countries) * universal_count:
        errors.append("Country–indicator model does not cover the full research panel")
    if pair_model.get("clusters") != len(countries) or pair_model.get("clustered_by") != "country":
        errors.append("Country–indicator model uncertainty is not clustered by country")
    context_model = analysis_result.get("context_model", {})
    if not 0 < context_model.get("clusters", 0) <= len(countries):
        errors.append("Statistical-performance context model has invalid country coverage")
    sensitivity_labels = {item.get("specification", "") for item in analysis_result.get("sensitivity", [])}
    required_sensitivities = {
        "Primary: all official statuses, 5 years",
        "Short window: 3 years",
        "Long window: 7 years",
        "Country-reported statuses only",
        "Countries weighted by population",
    }
    if sensitivity_labels != required_sensitivities:
        errors.append("Research sensitivity set is incomplete or unexpected")
    if analysis_result.get("snapshot", {}).get("retrieved_at") != manifest.get("retrieved_at"):
        errors.append("Analysis and source timestamps do not match")
    if analysis_result.get("snapshot", {}).get("snapshot_id") != snapshot_id:
        errors.append("Analysis and source snapshots do not match")
    for item in metrics.get("country_series", []):
        for key in ("recent_completeness", "staleness", "global_scarcity"):
            if not 0 <= item[key] <= 1:
                errors.append(f"{key} outside [0,1] for {item['country_alpha3']} {item['series_code']}")
        score = item.get("measurement_priority_v1")
        if score is not None and not 0 <= score <= 100:
            errors.append(f"priority outside [0,100] for {item['country_alpha3']} {item['series_code']}")
    if errors:
        raise ValueError("Validation failed:\n- " + "\n- ".join(errors[:25]))
    return [
        f"{len(specs):,} series across {len(goals)} configured goals",
        f"{len(countries):,} unique countries",
        f"{len(metrics['country_series']):,} country-series assessments",
        f"Observation years {min(years)}–{max(years)}",
        "Every universal series has member-state observations",
        "All normalized scores within declared bounds",
        f"Research panel: {len(countries):,} countries × {universal_count} universal series",
        "Research snapshot, clustered model, sensitivities, and source provenance agree",
        f"Statistical-performance context: {context_model['clusters']:,} countries",
    ]


def clean_generated() -> None:
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
    if SITE_DATA_DIR.exists():
        shutil.rmtree(SITE_DATA_DIR)
