# Contributing

Blindspot welcomes reproducibility checks, source corrections, accessibility improvements, and evidence about indicator applicability.

1. Create a branch from the default branch.
2. Run `make test`.
3. If generated metrics change, run the full pipeline and explain the source or methodology change.
4. Open a pull request with a concise before/after description.

Do not add an indicator merely because its coverage is high. Changes to representative-series mappings must document relevance, country applicability, cadence, and the effect on historical comparability.

Good first issues include validating a series cadence against custodian metadata, reviewing country-name presentation, checking a country profile against an official national source, and testing keyboard navigation.
