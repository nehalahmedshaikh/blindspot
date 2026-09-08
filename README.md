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

Open <http://localhost:8000>. A full source refresh currently takes roughly 10–15 minutes; subsequent local builds take seconds.

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

## Data and licensing

Code is MIT licensed. Generated outputs retain source provenance. Upstream data remain governed by their respective terms. Natural Earth map geometry is public domain through the `world-atlas` package.
