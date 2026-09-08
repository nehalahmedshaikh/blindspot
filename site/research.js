"use strict";

(async () => {
  const { escapeHTML, fetchJSON, metaPromise, signed } = Blindspot;
  const q = selector => document.querySelector(selector);
  const [meta, analysis, goals] = await Promise.all([metaPromise, fetchJSON("assets/data/analysis.json"), fetchJSON("assets/data/goals.json")]);
  const goalMap = new Map(goals.map(item => [String(item.id), item]));
  q("#research-scope").textContent = `Recent missingness is the share of expected observations absent from ${analysis.snapshot.recent_window.join("–")}. Every comparison uses the same ${analysis.design.universal_series} universal series across ${analysis.design.countries} countries.`;
  function findingValue(item) {
    if (item.value_low != null) return `${item.value_low.toFixed(1)}–${item.value_high.toFixed(1)} pp`;
    if (item.unit === "percent") return `${item.value.toFixed(1)}%`;
    return `${signed(item.value)} pp`;
  }
  q("#finding-strip").innerHTML = analysis.findings.map(item => `<article id="${item.id}"><strong>${findingValue(item)}</strong><div><span>${escapeHTML(item.label)}</span><p>${escapeHTML(item.plain_language)}</p></div></article>`).join("");
  const comparisonOrder = {
    income: ["High income", "Upper middle income", "Lower middle income", "Low income"],
    family: ["People", "Prosperity", "Planet", "Peace", "Partnership"],
  };
  const comparisonNotes = {
    income: "Average recent missingness by country income group.",
    region: "Average recent missingness by world region.",
    goal: "Average recent missingness among universal series in each goal.",
    family: "Average recent missingness across the UN’s five SDG families.",
  };
  function groupLabel(dimension, group) {
    return dimension === "goal" ? `Goal ${group}: ${goalMap.get(String(group))?.label || "Unknown goal"}` : group;
  }
  function renderComparison() {
    const dimension = q("#comparison-dimension").value;
    const order = comparisonOrder[dimension] || analysis.summaries[dimension].map(item => item.group);
    const rank = new Map(order.map((name, position) => [String(name), position]));
    const sorted = [...analysis.summaries[dimension]].sort((left, right) => (rank.get(String(left.group)) ?? 99) - (rank.get(String(right.group)) ?? 99));
    q("#comparison-note").textContent = comparisonNotes[dimension];
    q("#comparison-bars").innerHTML = sorted.map(item => {
      const label = groupLabel(dimension, item.group);
      return `<div class="bar-row"><span class="bar-name">${escapeHTML(label)}</span><div class="bar-track" aria-label="${escapeHTML(label)}: ${item.mean_missingness_pct}% recent missingness; interval ${item.ci_low}% to ${item.ci_high}%"><i class="bar-fill" style="width:${item.mean_missingness_pct}%"></i><i class="bar-interval" style="left:${item.ci_low}%;width:${Math.max(0, item.ci_high - item.ci_low)}%"></i></div><strong>${item.mean_missingness_pct.toFixed(1)}%</strong></div>`;
    }).join("");
  }
  q("#comparison-dimension").addEventListener("change", renderComparison);
  renderComparison();
  q("#supporting-results").innerHTML = analysis.supporting_results.map(item => {
    const value = item.unit === "percent" ? `${item.value.toFixed(1)}%` : `${signed(item.value)} pp`;
    const detail = item.ci_low != null ? `Model interval: ${signed(item.ci_low)} to ${signed(item.ci_high)} points.` : `${item.count} series produce this share.`;
    return `<article id="${item.id}"><strong>${value}</strong><div><h3>${escapeHTML(item.label)}</h3><p>${escapeHTML(item.plain_language)}</p><small>${detail}</small></div></article>`;
  }).join("");
  const gaps = analysis.sensitivity.map(item => item.low_minus_high_income_pp);
  const leave = analysis.leave_one_series_out;
  const contextIncome = analysis.context_model.coefficients.find(item => item.term.startsWith("Income: Low income"));
  q("#robustness-results").innerHTML = `<article><strong>${Math.min(...gaps).toFixed(1)}–${Math.max(...gaps).toFixed(1)} pp</strong><div><h3>Change assumptions</h3><p>The unadjusted low–high income gap across alternative windows, statuses, weighting, and applicability assumptions.</p></div></article><article><strong>${leave.minimum_pp.toFixed(1)}–${leave.maximum_pp.toFixed(1)} pp</strong><div><h3>Remove indicators one at a time</h3><p>The unadjusted income gap after excluding each series in turn.</p></div></article><article><strong>${signed(contextIncome.estimate_percentage_points)} pp</strong><div><h3>Add statistical performance</h3><p>Adjusted low-income difference after adding World Bank statistical performance; interval ${signed(contextIncome.ci_low)} to ${signed(contextIncome.ci_high)}.</p></div></article>`;
})().catch(error => { const banner = document.querySelector("#status-banner"); banner.hidden = false; banner.textContent = error.message; });
