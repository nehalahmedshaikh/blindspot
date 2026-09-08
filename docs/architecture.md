# Architecture

```text
UN SDG API ─┐
            ├─ fetch → normalized current snapshot → metrics → model + analysis → static contracts
World Bank ─┘                 │                                │
                             └─ baseline + append-only deltas  └─ GitHub Pages
```

The source refresh is transactional. All 51 series and both sources must validate before the current snapshot is replaced. If a later refresh fails and a prior snapshot exists, the prior snapshot is retained and marked stale.

The website has no runtime backend. It reads generated JSON and CSV files, so every visible claim is reproducible from a clean checkout using only Python's standard library.
