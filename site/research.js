"use strict";

(async () => {
  const { escapeHTML, fetchJSON, metaPromise, signed } = Blindspot;
  const q = selector => document.querySelector(selector);
  const [meta, analysis] = await Promise.all([metaPromise, fetchJSON("assets/data/analysis.json")]);
  q("#research-scope").textContent = `Recent missingness is the share of expected observations absent from ${analysis.snapshot.recent_window.join("–")}. Every comparison uses the same ${analysis.design.universal_series} universal series across ${analysis.design.countries} countries.`;
  function findingValue(item) {
    if (item.value_low != null) return `${item.value_low.toFixed(1)}–${item.value_high.toFixed(1)} pp`;
    if (item.unit === "percent") return `${item.value.toFixed(1)}%`;
    return `${signed(item.value)} pp`;
  }
  q("#finding-strip").innerHTML = analysis.findings.map(item => `<article id="${item.id}"><strong>${findingValue(item)}</strong><span>${escapeHTML(item.label)}</span><p>${escapeHTML(item.plain_language)}</p></article>`).join("");
  function renderBars(selector, rows, order) {
    const rank = new Map(order.map((name, position) => [name, position]));
    const sorted = [...rows].sort((left, right) => (rank.get(left.group) ?? 99) - (rank.get(right.group) ?? 99));
    q(selector).innerHTML = sorted.map(item => `<div class="bar-row"><span class="bar-name">${escapeHTML(item.group)}</span><div class="bar-track" aria-label="${escapeHTML(item.group)}: ${item.mean_missingness_pct}% recent missingness; interval ${item.ci_low}% to ${item.ci_high}%"><i class="bar-fill" style="width:${item.mean_missingness_pct}%"></i><i class="bar-interval" style="left:${item.ci_low}%;width:${Math.max(0, item.ci_high - item.ci_low)}%"></i></div><strong>${item.mean_missingness_pct.toFixed(1)}%</strong></div>`).join("");
  }
  renderBars("#income-bars", analysis.summaries.income, ["High income", "Upper middle income", "Lower middle income", "Low income"]);
  renderBars("#family-bars", analysis.summaries.family, ["People", "Prosperity", "Planet", "Peace", "Partnership"]);
  q("#supporting-results").innerHTML = analysis.supporting_results.map(item => {
    const value = item.unit === "percent" ? `${item.value.toFixed(1)}%` : `${signed(item.value)} pp`;
    const detail = item.id === "population" ? `Model interval: ${signed(item.ci_low)} to ${signed(item.ci_high)} points.` : `${item.count} series produce this share.`;
    return `<article id="${item.id}"><strong>${value}</strong><h3>${escapeHTML(item.label)}</h3><p>${escapeHTML(item.plain_language)}</p><small>${detail}</small></article>`;
  }).join("");
  const gaps = analysis.sensitivity.map(item => item.low_minus_high_income_pp);
  const leave = analysis.leave_one_series_out;
  q("#robustness-results").innerHTML = `<article><h3>Change the data window</h3><strong>${Math.min(...gaps).toFixed(1)}–${Math.max(...gaps).toFixed(1)} pp</strong><p>The unadjusted low–high income gap remains in this range across 3-, 5-, and 7-year windows and a country-reported-status-only calculation.</p></article><article><h3>Remove indicators one at a time</h3><strong>${leave.minimum_pp.toFixed(1)}–${leave.maximum_pp.toFixed(1)} pp</strong><p>Removing a series changes each country's average when that series has a different gap pattern. No single series removes the income difference.</p></article>`;
})().catch(error => { const banner = document.querySelector("#status-banner"); banner.hidden = false; banner.textContent = error.message; });
