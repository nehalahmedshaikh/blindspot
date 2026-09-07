# Methodology

## Unit of analysis

Blindspot evaluates a country–series–reference-year cell. The first release covers 193 UN member states, 51 configured headline series (three per SDG), and reference years from 2015 onward.

“Observed” means that the current official UN SDG Global Database contains at least one observation for the cell. It does **not** prove that a national aggregate was collected, nor does “unobserved” prove that a country failed to collect data. Aggregate-slice availability and disaggregation are reported separately.

## Descriptive measures

- Recent completeness is observed distinct years divided by the number expected during the latest five completed reference years, capped at one.
- Staleness is elapsed expected reporting periods since the last observation, capped after three periods.
- Regularity is `1 / (1 + coefficient of variation)` for observed reporting gaps; it is omitted with fewer than three years.
- Disaggregation is present when more than one non-total category is observed for sex, age, or location.

Cadences are curated in `config/series.json`. They are methodological assumptions, not properties inferred from how often a source happens to contain data.

## Measurement priority v1

`100 × (0.35 × staleness + 0.25 × completeness deficit + 0.20 × global scarcity + 0.20 × population percentile)`

All components are bounded to `[0,1]`. Population uses a percentile of the latest available `log1p(population)`, so very large countries do not dominate linearly. Conditional-applicability series are excluded. The interface lets readers vary every weight.

This is a triage heuristic, not an estimate of social welfare, causal benefit, collection cost, or the optimal allocation of funding.

## Reporting-continuity model

The experimental model predicts absence during the next configured reporting window from information available before that window. Features cover prior gap, historical presence, series presence, population, cadence, and goal. Evaluation is temporal. Logistic regression must beat the series-rate baseline on Brier score and have both target classes; otherwise Blindspot publishes the baseline or a descriptive-only result.

## Revisions

Blindspot stores a compact baseline and append-only cell deltas. Revision history begins with the project's first retrieval and does not reconstruct earlier publication vintages.
