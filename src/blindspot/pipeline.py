from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import CACHE_DIR, DATA_DIR, PROJECT_ROOT, SITE_DATA_DIR, ensure_directories, load_countries, load_series
from .metrics import calculate_metrics
from .model import train_continuity_model
from .sources import (
    SourceError,
    fetch_series_catalog,
    fetch_un_observations,
    fetch_world_bank_context,
    load_cached_observations,
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
    delta: list[dict[str, Any]] = []
    for key in sorted(current_map.keys() | previous_map.keys()):
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
    return {"baseline_cells": 0, **counts}


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
    except SourceError as exc:
        if not previous:
            raise
        old_manifest = read_cache_json("manifest.json")
        old_manifest["status"] = "stale"
        old_manifest["last_attempt_at"] = utc_now()
        old_manifest["last_error"] = str(exc)
        write_cache_json("manifest.json", old_manifest)
        return False
    history = record_revision_history(previous, observations)
    write_cache_json("catalog.json", catalog)
    write_cache_json("context.json", context)
    write_cache_json(
        "manifest.json",
        {
            "schema_version": "1.0.0",
            "status": "fresh",
            "retrieved_at": utc_now(),
            "sources": [catalog_manifest, context_manifest, observations_manifest],
            "history": history,
            "last_error": None,
        },
    )
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
    write_cache_json("metrics.json", metrics)
    return metrics


def model() -> dict[str, Any]:
    try:
        metrics = read_cache_json("metrics.json")
    except SourceError:
        metrics = build()
    result = train_continuity_model(
        load_cached_observations(),
        load_series(),
        load_countries(),
        read_cache_json("context.json"),
        metrics["completed_year"],
    )
    write_cache_json("model.json", result)
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
    try:
        metrics = read_cache_json("metrics.json")
    except SourceError:
        metrics = build()
    try:
        model_result = read_cache_json("model.json")
    except SourceError:
        model_result = model()
    manifest = read_cache_json("manifest.json")
    dashboard = {
        "meta": {
            "schema_version": metrics["schema_version"],
            "completed_year": metrics["completed_year"],
            "recent_window": metrics["recent_window"],
            "retrieved_at": manifest["retrieved_at"],
            "status": manifest["status"],
            "model_selected": model_result["selected"],
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
        "model": model_result,
    }
    compact_dashboard = json.dumps(
        dashboard, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ) + "\n"
    (CACHE_DIR / "dashboard.json").write_text(compact_dashboard, encoding="utf-8")
    (SITE_DATA_DIR / "dashboard.json").write_text(compact_dashboard, encoding="utf-8")
    for name in ("manifest.json", "model.json"):
        shutil.copy2(CACHE_DIR / name, SITE_DATA_DIR / name)
    downloads = SITE_DATA_DIR / "downloads"
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
            "completeness",
            "staleness",
            "priority",
        ],
    )
    methodology = {
        "method": "measurement_priority",
        "recent_window": metrics["recent_window"],
        "weights": {
            "staleness": 0.35,
            "completeness_deficit": 0.25,
            "global_scarcity": 0.20,
            "population_percentile": 0.20,
        },
        "exclusions": "Conditional-applicability series are descriptive and excluded from priority rankings.",
        "warning": "Priority is a transparent heuristic, not a causal estimate or funding recommendation.",
    }
    (SITE_DATA_DIR / "methodology.json").write_text(
        json.dumps(methodology, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksums = {}
    for path in sorted(SITE_DATA_DIR.rglob("*")):
        if path.is_file() and path.name != "checksums.json":
            checksums[str(path.relative_to(SITE_DATA_DIR))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (SITE_DATA_DIR / "checksums.json").write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return dashboard


def validate() -> list[str]:
    errors: list[str] = []
    specs = load_series()
    countries = load_countries()
    if len(specs) != 51:
        errors.append(f"Expected 51 series, found {len(specs)}")
    goal_counts = {goal: sum(spec.goal == goal for spec in specs) for goal in range(1, 18)}
    if any(count != 3 for count in goal_counts.values()):
        errors.append(f"Each goal must have three series: {goal_counts}")
    if len({spec.code for spec in specs}) != len(specs):
        errors.append("Series codes are not unique")
    if len(countries) != 193:
        errors.append(f"Expected 193 UN members, found {len(countries)}")
    if len({country.m49 for country in countries}) != len(countries):
        errors.append("Country M49 codes are not unique")
    metrics = read_cache_json("metrics.json")
    manifest = read_cache_json("manifest.json")
    observations = load_cached_observations()
    if len(metrics.get("countries", [])) != 193:
        errors.append("Metrics do not contain 193 countries")
    if len(metrics.get("series", [])) != 51:
        errors.append("Metrics do not contain 51 series")
    years = {int(item["reference_year"]) for item in observations if item.get("reference_year") is not None}
    if not years or max(years) <= 2015:
        errors.append("Observation snapshot does not span beyond the 2015 start year")
    un_source = next(
        (source for source in manifest.get("sources", []) if source.get("source") == "UNSD SDG API"),
        {},
    )
    empty_series = [code for code, count in un_source.get("series_rows", {}).items() if count == 0]
    if empty_series:
        errors.append(f"Configured series with no member-state rows: {sorted(empty_series)}")
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
        "51 series: three for every SDG",
        "193 unique UN member states",
        f"{len(metrics['country_series']):,} country-series assessments",
        f"Observation years {min(years)}–{max(years)}",
        "Every configured series has member-state observations",
        "All normalized scores within declared bounds",
    ]


def clean_generated() -> None:
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
    if SITE_DATA_DIR.exists():
        shutil.rmtree(SITE_DATA_DIR)
