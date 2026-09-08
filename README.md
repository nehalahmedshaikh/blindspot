# Blindspot

**An open atlas of what humanity has not measured.**

[Explore the observatory](https://nehalahmedshaikh.github.io/blindspot/) for the atlas, research results, methodology, sources, and downloads.

## Quick start

Python 3.11+ is the only runtime requirement.

```bash
git clone https://github.com/nehalahmedshaikh/blindspot.git
cd blindspot
make test
make all
make serve
```

Open <http://localhost:8000>.

## Commands

| Command | Purpose |
|---|---|
| `make fetch` | Transactionally refresh official sources |
| `make build` | Calculate metrics and rankings |
| `make model` | Run temporal continuity evaluation |
| `make analyze` | Estimate gap inequalities and robustness |
| `make validate` | Enforce configuration and score invariants |
| `make export` | Generate site contracts and downloads |
| `make all` | Run the complete pipeline |

## Architecture

```text
UN SDG API ─┐
            ├─ fetch → normalized snapshot → metrics → model + analysis → static site data
World Bank ─┘                 │
                              └─ baseline + append-only revision deltas
```

Refreshes are transactional: every configured series and source must validate before replacing the current snapshot. If a refresh fails, the last validated snapshot remains available unchanged.

The site has no runtime backend. It reads generated JSON and CSV files, so every displayed result can be reproduced from a clean checkout using Python’s standard library.

## Data and licensing

Code is MIT licensed. Generated outputs retain source provenance. Upstream data remain governed by their respective terms. Natural Earth map geometry is public domain through the `world-atlas` package.
