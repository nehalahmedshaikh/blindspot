from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import CACHE_DIR, Country, SeriesSpec, ensure_directories

UN_BASE = "https://unstats.un.org/SDGAPI/v1/sdg"
WB_BASE = "https://api.worldbank.org/v2"
USER_AGENT = "blindspot/0.1 (+https://github.com/nehalahmedshaikh/blindspot)"
SPI_CSV = "https://raw.githubusercontent.com/worldbank/SPI/master/03_output_data/SPI_index.csv"


class SourceError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def fetch_json(url: str, retries: int = 3, timeout: int = 60) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise SourceError(f"Failed after {retries} attempts: {url}: {error}")


def fetch_text(url: str, retries: int = 3, timeout: int = 120) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv"})
    error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8-sig")
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
            error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise SourceError(f"Failed after {retries} attempts: {url}: {error}")


def query_url(base: str, params: dict[str, Any]) -> str:
    return base + "?" + urllib.parse.urlencode(params, doseq=True)


def _dimensions_summary(dimensions: dict[str, Any] | None) -> dict[str, str]:
    return {str(key): str(value) for key, value in (dimensions or {}).items() if value is not None}


def _normalize_observation(item: dict[str, Any], snapshot_date: str) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    dimensions = _dimensions_summary(item.get("dimensions"))
    year = item.get("timePeriodStart")
    return {
        "snapshot_date": snapshot_date,
        "country_m49": str(int(item["geoAreaCode"])),
        "country_name": item.get("geoAreaName", ""),
        "series_code": item["series"],
        "reference_year": int(float(year)) if year is not None else None,
        "value": item.get("value"),
        "unit": attributes.get("Units"),
        "nature": attributes.get("Nature", "NA"),
        "reporting_type": dimensions.get("Reporting Type"),
        "dimensions": dimensions,
        "source": item.get("source"),
        "lower_bound": item.get("lowerBound"),
        "upper_bound": item.get("upperBound"),
    }


def _fetch_one_series(
    spec: SeriesSpec, country_codes: set[str], years: list[int], snapshot_date: str
) -> tuple[str, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        url = query_url(
            f"{UN_BASE}/Series/Data",
            {
                "seriesCode": spec.code,
                # The API currently treats timePeriodStart as an exact
                # filter despite its name. An explicit list is stable.
                "timePeriod": years,
                "page": page,
                "pageSize": 1000,
            },
        )
        payload = fetch_json(url)
        for item in payload.get("data", []):
            code = str(int(item.get("geoAreaCode", -1)))
            if code not in country_codes or item.get("timePeriodStart") is None:
                continue
            rows.append(_normalize_observation(item, snapshot_date))
        if page >= int(payload.get("totalPages", 1)):
            break
        page += 1
    return spec.code, rows


def fetch_un_observations(
    specs: Iterable[SeriesSpec], countries: Iterable[Country], start_year: int = 2015
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    country_codes = {country.m49 for country in countries}
    snapshot_at = utc_now()
    snapshot_date = snapshot_at[:10]
    observations: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}
    failed: dict[str, str] = {}
    years = list(range(start_year, datetime.now(UTC).year + 1))

    spec_list = list(specs)
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="un-sdg") as executor:
        futures = {
            executor.submit(_fetch_one_series, spec, country_codes, years, snapshot_date): spec
            for spec in spec_list
        }
        completed = 0
        for future in as_completed(futures):
            spec = futures[future]
            try:
                code, rows = future.result()
                observations.extend(rows)
                source_counts[code] = len(rows)
            except (SourceError, KeyError, TypeError, ValueError) as exc:
                failed[spec.code] = str(exc)
            completed += 1
            print(
                f"[UN SDG] {completed:02d}/{len(spec_list)} {spec.code}: "
                f"{source_counts.get(spec.code, 0):,} member-state rows",
                file=sys.stderr,
                flush=True,
            )

    if not observations:
        raise SourceError("UN refresh produced no valid observations")
    if failed:
        raise SourceError("UN refresh was partial; refusing to replace cache: " + json.dumps(failed))

    observations.sort(
        key=lambda row: (
            row["series_code"],
            int(row["country_m49"]),
            row["reference_year"],
            json.dumps(row["dimensions"], sort_keys=True),
        )
    )
    ensure_directories()
    target = CACHE_DIR / "observations.jsonl.gz"
    temp = target.with_suffix(".tmp")
    with gzip.open(temp, "wt", encoding="utf-8") as handle:
        for item in observations:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    temp.replace(target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return observations, {
        "source": "UNSD SDG API",
        "retrieved_at": snapshot_at,
        "url": f"{UN_BASE}/Series/Data",
        "sha256": digest,
        "rows": len(observations),
        "series_rows": source_counts,
        "status": "fresh",
    }


def fetch_series_catalog(specs: Iterable[SeriesSpec]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    url = query_url(f"{UN_BASE}/Series/List", {"allreleases": "false"})
    payload = fetch_json(url)
    selected = {spec.code for spec in specs}
    catalog = {item["code"]: item for item in payload if item.get("code") in selected}
    missing = selected - catalog.keys()
    if missing:
        raise SourceError(f"Configured series absent from current UN release: {sorted(missing)}")
    raw = json.dumps(catalog, ensure_ascii=False, sort_keys=True).encode()
    return catalog, {
        "source": "UNSD SDG series catalog",
        "retrieved_at": utc_now(),
        "url": url,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows": len(catalog),
        "status": "fresh",
    }


def fetch_world_bank_context(
    countries: Iterable[Country], start_year: int = 2023
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    members = {country.alpha3 for country in countries}
    metadata_url = query_url(f"{WB_BASE}/country", {"format": "json", "per_page": 400})
    population_url = query_url(
        f"{WB_BASE}/country/all/indicator/SP.POP.TOTL",
        {"date": f"{start_year}:2030", "format": "json", "per_page": 10000},
    )
    metadata_payload = fetch_json(metadata_url)
    population_payload = fetch_json(population_url)
    spi_rows = list(csv.DictReader(io.StringIO(fetch_text(SPI_CSV))))
    context: dict[str, dict[str, Any]] = {}
    for item in metadata_payload[1]:
        code = item.get("id")
        if code in members:
            context[code] = {
                "region": (item.get("region") or {}).get("value") or "Unknown",
                "income_group": (item.get("incomeLevel") or {}).get("value") or "Unknown",
                "population": None,
                "population_year": None,
                "statistical_performance": None,
                "statistical_performance_year": None,
            }
    for item in population_payload[1]:
        code = item.get("countryiso3code")
        value = item.get("value")
        if code in context and value is not None:
            current_year = context[code]["population_year"]
            year = int(item["date"])
            if current_year is None or year > current_year:
                context[code]["population"] = int(value)
                context[code]["population_year"] = year
    for item in spi_rows:
        code = item.get("iso3c")
        value = item.get("SPI.INDEX")
        if code not in context or not value:
            continue
        try:
            score = float(value)
        except ValueError:
            continue
        year = int(item["date"])
        current_year = context[code]["statistical_performance_year"]
        if current_year is None or year > current_year:
            context[code]["statistical_performance"] = round(score, 3)
            context[code]["statistical_performance_year"] = year
    raw = json.dumps(context, sort_keys=True).encode()
    return context, {
        "source": "World Bank population and statistical performance",
        "retrieved_at": utc_now(),
        "url": SPI_CSV,
        "urls": [population_url, SPI_CSV],
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows": len(context),
        "variables": ["population", "region", "income group", "statistical performance"],
        "status": "fresh",
    }


def load_cached_observations() -> list[dict[str, Any]]:
    path = CACHE_DIR / "observations.jsonl.gz"
    if not path.exists():
        raise SourceError("No observation cache. Run `blindspot fetch` first.")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_cache_json(name: str, value: Any) -> None:
    ensure_directories()
    path = CACHE_DIR / name
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def read_cache_json(name: str) -> Any:
    path = CACHE_DIR / name
    if not path.exists():
        raise SourceError(f"Missing cache file {name}. Run `blindspot fetch` first.")
    return json.loads(path.read_text(encoding="utf-8"))
