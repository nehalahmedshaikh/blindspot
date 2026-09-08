# Blindspot

**An open atlas of what humanity has not measured.**

Blindspot maps missing, stale, irregular, and fragile evidence across 51 selected indicator series—three for each UN Sustainable Development Goal—and all 193 UN member states. It asks a different question from most development dashboards: not “how is a country performing?” but “where is the evidence too weak to know?”

## What is already implemented

- Official UN SDG and World Bank ingestion with pagination, retries, provenance, and transactional refreshes.
- Exactly three configured series for every SDG, with curated cadence and applicability.
- Country–series completeness, staleness, regularity, status, aggregate-slice, and disaggregation metrics.
- A transparent measurement-priority score with interactive weight sensitivity.
- An experimental reporting-continuity model with temporal testing and a mandatory baseline.
- Compact snapshot and append-only revision tracking.
- A dependency-free static atlas with CSV and JSON downloads.
- Weekly GitHub Pages deployment and offline unit tests.

## Research status

The reproducible observatory is complete as a v0.1; the broader research program is not. Next comes peer review of the first frozen snapshot and the preregistered analysis of how reporting gaps vary by region, income group, population, and indicator family. Later phases expand country-level applicability, disaggregation, indicator and national-source coverage, and longitudinal revision analysis. The public site presents this roadmap alongside the methodology and novelty boundary.

## Quick start

Python 3.11+ is the only runtime requirement.

```bash
git clone https://github.com/nehalahmedshaikh/blindspot.git
cd blindspot
make test
make all
make serve
```

Open <http://localhost:8000>. A full source refresh currently takes roughly 10–15 minutes; subsequent local builds take seconds.

For an editable installation:

```bash
make bootstrap
.venv/bin/blindspot --help
```

## Commands

| Command | Purpose |
|---|---|
| `blindspot fetch` | Transactionally refresh official sources |
| `blindspot build` | Calculate metrics and rankings |
| `blindspot model` | Run temporal continuity evaluation |
| `blindspot validate` | Enforce configuration and score invariants |
| `blindspot export` | Generate site contracts and downloads |
| `blindspot all` | Run the complete pipeline |

## Interpretation

“Not observed” means absent from the selected official source under Blindspot's declared unit of analysis. It does not prove that a country collected nothing. Priority is a challengeable heuristic, not a causal estimate or funding recommendation. Read the [methodology](docs/methodology.md) and [novelty boundary](docs/related-work.md) before using rankings.

## Data and licensing

Code is MIT licensed. Derived outputs retain source provenance and are regenerated from the UN SDG Global Database and World Bank Indicators API. Upstream data remain governed by their respective terms. Natural Earth map geometry is public domain through the `world-atlas` package.
