"use strict";
(async () => {
  const { escapeHTML, fetchJSON, metaPromise } = Blindspot;
  const q = selector => document.querySelector(selector);
  const [meta, analysis, goals] = await Promise.all([metaPromise, fetchJSON("assets/data/analysis.json"), fetchJSON("assets/data/goals.json")]);
  const goalMap = new Map(goals.map(item => [String(item.id), item]));
  const period = analysis.snapshot.recent_window.join("–");
  q("#research-scope").textContent = `Recent missingness is the share of expected observations absent from ${period}. Comparisons use ${analysis.design.universal_series} universal representative series covering ${analysis.design.official_indicators} official indicators across ${analysis.design.countries} countries.`;

  const svg = (label, width, height, body) => `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHTML(label)}"><title>${escapeHTML(label)}</title>${body}</svg>`;
  const table = (heads, rows) => `<table><thead><tr>${heads.map(x => `<th>${escapeHTML(x)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(x => `<td>${escapeHTML(String(x))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  const goalLabel = id => `Goal ${id}: ${goalMap.get(String(id))?.label || "Unknown goal"}`;
  const shortTerm = term => term.replace("Income: ", "").replace("Region: ", "").replace(" vs High income", "").replace(" vs Europe & Central Asia", "").replace("Log population (1 SD)", "Population · 1 SD larger").replace("Statistical performance (10 points)", "Statistical performance · 10 points");

  function forest(items, { left = 330, label = x => x.label, aria = "Estimate and interval chart" } = {}) {
    const width = 920, right = 70, rowHeight = 38, top = 30;
    const height = top + items.length * rowHeight + 35;
    let min = Math.min(0, ...items.map(x => x.ci_low));
    let max = Math.max(0, ...items.map(x => x.ci_high));
    const span = Math.max(1, max - min); min -= span * .08; max += span * .08;
    const x = value => left + (value - min) / (max - min) * (width - left - right);
    let body = `<line class="axis-zero" x1="${x(0)}" x2="${x(0)}" y1="12" y2="${height - 25}"></line><text class="axis-label" x="${left}" y="${height - 6}">${min.toFixed(0)} pp</text><text class="axis-label" text-anchor="end" x="${width - right}" y="${height - 6}">${max.toFixed(0)} pp</text>`;
    items.forEach((item, index) => {
      const y = top + index * rowHeight, name = label(item);
      body += `<text class="chart-label" x="0" y="${y + 4}">${escapeHTML(name)}</text><line class="interval" x1="${x(item.ci_low)}" x2="${x(item.ci_high)}" y1="${y}" y2="${y}"></line><circle class="estimate" cx="${x(item.estimate)}" cy="${y}" r="5"><title>${escapeHTML(name)}: ${item.estimate.toFixed(1)} pp; interval ${item.ci_low.toFixed(1)} to ${item.ci_high.toFixed(1)}</title></circle><text class="chart-value" text-anchor="end" x="${width}" y="${y + 4}">${item.estimate.toFixed(1)} pp</text>`;
    });
    return svg(aria, width, height, body);
  }

  const orders = { income: ["High income", "Upper middle income", "Lower middle income", "Low income"], family: ["People", "Prosperity", "Planet", "Peace", "Partnership"] };
  const notes = { income: "Country averages by income group.", region: "Country averages by world region.", goal: "Country averages among universal representatives in each goal.", family: "Country averages across the UN’s five SDG families." };
  function renderComparison() {
    const dimension = q("#comparison-dimension").value;
    const rows = analysis.summaries[dimension], order = orders[dimension] || rows.map(x => x.group);
    const rank = new Map(order.map((name, index) => [String(name), index]));
    const sorted = [...rows].sort((a, b) => (rank.get(String(a.group)) ?? 99) - (rank.get(String(b.group)) ?? 99));
    const width = 920, left = 310, right = 65, rowHeight = 48, top = 28, height = top + sorted.length * rowHeight + 30;
    const x = value => left + value / 100 * (width - left - right);
    let body = `<line class="axis-line" x1="${left}" x2="${width - right}" y1="${height - 24}" y2="${height - 24}"></line>`;
    [0, 25, 50, 75, 100].forEach(tick => { body += `<text class="axis-label" text-anchor="${tick === 0 ? "start" : tick === 100 ? "end" : "middle"}" x="${x(tick)}" y="${height - 7}">${tick}%</text>`; });
    sorted.forEach((item, index) => {
      const y = top + index * rowHeight, group = String(item.group), name = dimension === "goal" ? goalLabel(group) : group;
      if (dimension === "income" || dimension === "region") {
        const field = dimension === "income" ? "income_group" : "region";
        analysis.country_distribution.filter(row => row[field] === group).forEach((row, dotIndex) => {
          body += `<circle class="country-dot" cx="${x(row.missingness_pct)}" cy="${y + ((dotIndex * 7) % 13) - 6}" r="2.4"><title>${escapeHTML(row.country)}: ${row.missingness_pct.toFixed(1)}%</title></circle>`;
        });
      }
      body += `<text class="chart-label" x="0" y="${y + 4}">${escapeHTML(name)}</text><line class="interval" x1="${x(item.ci_low)}" x2="${x(item.ci_high)}" y1="${y}" y2="${y}"></line><circle class="estimate" cx="${x(item.mean_missingness_pct)}" cy="${y}" r="5"></circle><text class="chart-value" text-anchor="end" x="${width}" y="${y + 4}">${item.mean_missingness_pct.toFixed(1)}%</text>`;
    });
    q("#comparison-note").textContent = notes[dimension];
    q("#comparison-chart").innerHTML = svg(`${notes[dimension]} Dots show means and lines show intervals.`, width, height, body);
    q("#comparison-table").innerHTML = table(["Group", "Countries", "Missingness", "Interval"], sorted.map(item => [dimension === "goal" ? goalLabel(item.group) : item.group, item.countries, `${item.mean_missingness_pct.toFixed(1)}%`, `${item.ci_low.toFixed(1)}–${item.ci_high.toFixed(1)}%`]));
  }
  q("#comparison-dimension").addEventListener("change", renderComparison); renderComparison();

  const incomes = ["High income", "Upper middle income", "Lower middle income", "Low income"];
  const matrix = new Map(analysis.income_goal_matrix.map(x => [`${x.goal}|${x.income_group}`, x]));
  q("#goal-income-heatmap").innerHTML = `<table class="heatmap"><thead><tr><th>Goal</th>${incomes.map(x => `<th>${escapeHTML(x.replace(" income", ""))}</th>`).join("")}</tr></thead><tbody>${goals.map(goal => `<tr><th>Goal ${goal.id}<small>${escapeHTML(goal.label)}</small></th>${incomes.map(income => { const value = matrix.get(`${goal.id}|${income}`)?.mean_missingness_pct ?? 0; return `<td class="${value >= 60 ? "high" : ""}" style="--heat:${value.toFixed(1)}%" title="${escapeHTML(goalLabel(goal.id))}, ${escapeHTML(income)}: ${value.toFixed(1)}%">${value.toFixed(1)}%</td>`; }).join("")}</tr>`).join("")}</tbody></table>`;

  const goalEffects = analysis.goal_income_effects.map(item => ({ estimate: item.estimate_pp, ci_low: item.ci_low, ci_high: item.ci_high, label: goalLabel(item.goal) }));
  q("#goal-effects-chart").innerHTML = forest(goalEffects, { left: 310, label: item => item.label, aria: "Low minus high income missingness difference within each goal." });

  const variance = analysis.variance_decomposition;
  const varianceRows = [
    ["Countries", variance.country_percent],
    ["Indicators", variance.indicator_percent],
    ["Country × indicator", variance.interaction_and_residual_percent],
  ];
  q("#variance-chart").innerHTML = `<div>${varianceRows.map((item, index) => `<i class="variance-${index}" style="width:${item[1]}%">${item[1] >= 15 ? `<span>${escapeHTML(item[0])}<b>${item[1].toFixed(1)}%</b></span>` : ""}</i>`).join("")}</div><ul>${varianceRows.map(item => `<li>${escapeHTML(item[0])}: ${item[1].toFixed(1)}%</li>`).join("")}</ul>`;

  const concentration = analysis.concentration.curve.slice(0, 15);
  { const width = 920, left = 390, right = 110, rh = 32, top = 20, height = top + concentration.length * rh + 18;
    let body = "";
    concentration.forEach((item, index) => { const y = top + index * rh, label = item.description.length > 52 ? `${item.description.slice(0, 49)}…` : item.description;
      body += `<text class="chart-label" x="0" y="${y + 4}">${escapeHTML(label)}</text><rect class="rank-bar" x="${left}" y="${y - 7}" width="${item.mean_missingness_pct / 100 * (width - left - right)}" height="14"><title>${escapeHTML(item.description)}: ${item.mean_missingness_pct.toFixed(1)}% missing; cumulative ${item.cumulative_share_pct.toFixed(1)}%</title></rect><text class="chart-value" text-anchor="end" x="${width}" y="${y + 4}">${item.mean_missingness_pct.toFixed(1)}% · Σ ${item.cumulative_share_pct.toFixed(1)}%</text>`;
    });
    q("#concentration-chart").innerHTML = svg("Indicators contributing the most missingness; sigma is cumulative share.", width, height, body);
  }

  const statusLabels = { country_reported: "Country reported", estimated: "Estimated", modelled_or_global: "Modelled or global", other_official: "Other official", missing: "Missing" };
  const statusKeys = Object.keys(statusLabels);
  q("#status-legend").innerHTML = statusKeys.map((key, i) => `<span><i class="status-${i}"></i>${escapeHTML(statusLabels[key])}</span>`).join("");
  q("#status-chart").innerHTML = analysis.reporting_status.map(item => `<div class="stack-row"><span>${escapeHTML(item.group)}</span><div class="stack-track" aria-label="${escapeHTML(item.group)}: ${statusKeys.map(key => `${statusLabels[key]} ${item.shares[key]}%`).join(", ")}">${statusKeys.map((key, i) => item.shares[key] ? `<i class="status-${i}" style="width:${item.shares[key]}%"><title>${escapeHTML(statusLabels[key])}: ${item.shares[key].toFixed(1)}%</title></i>` : "").join("")}</div></div>`).join("");

  const dimensions = ["sex", "age", "location"];
  const breakdowns = new Map(analysis.disaggregation_by_goal.map(x => [`${x.goal}|${x.dimension}`, x.coverage_pct]));
  q("#breakdown-matrix").innerHTML = `<table class="heatmap breakdown-table"><thead><tr><th>Goal</th>${dimensions.map(x => `<th>${x}</th>`).join("")}</tr></thead><tbody>${goals.map(goal => `<tr><th>Goal ${goal.id}<small>${escapeHTML(goal.label)}</small></th>${dimensions.map(dimension => { const value = breakdowns.get(`${goal.id}|${dimension}`) ?? 0; return `<td class="${value >= 60 ? "high" : ""}" style="--heat:${value.toFixed(1)}%">${value.toFixed(1)}%</td>`; }).join("")}</tr>`).join("")}</tbody></table>`;

  const modelItems = analysis.pair_model.coefficients.map(item => ({ estimate: item.estimate_percentage_points, ci_low: item.ci_low, ci_high: item.ci_high, label: shortTerm(item.term) }));
  const performance = analysis.context_model.coefficients.find(item => item.term.startsWith("Statistical performance"));
  if (performance) modelItems.push({ estimate: performance.estimate_percentage_points, ci_low: performance.ci_low, ci_high: performance.ci_high, label: "Statistical performance · secondary model" });
  q("#model-chart").innerHTML = forest(modelItems, { label: x => x.label, aria: "Adjusted differences in recent missingness with confidence intervals." });
  q("#model-table").innerHTML = table(["Comparison", "Difference", "Interval"], modelItems.map(x => [x.label, `${x.estimate.toFixed(1)} pp`, `${x.ci_low.toFixed(1)}–${x.ci_high.toFixed(1)} pp`]));

  const sensitivity = analysis.sensitivity.map(item => ({ estimate: item.low_minus_high_income_pp, ci_low: item.ci_low, ci_high: item.ci_high, label: item.specification }));
  q("#sensitivity-chart").innerHTML = forest(sensitivity, { left: 390, label: x => x.label, aria: "Low minus high income gaps under alternative assumptions." });

  { const leave = analysis.leave_one_indicator_out, values = leave.estimates.map(x => x.low_minus_high_income_pp);
    const lo = Math.min(...values), hi = Math.max(...values), pad = Math.max(1, (hi - lo) * .15), min = lo - pad, max = hi + pad;
    const width = 920, left = 80, right = 80, y = 72, x = value => left + (value - min) / (max - min) * (width - left - right);
    let body = `<line class="axis-line" x1="${left}" x2="${width - right}" y1="${y}" y2="${y}"></line><line class="baseline" x1="${x(leave.baseline_low_minus_high_income_pp)}" x2="${x(leave.baseline_low_minus_high_income_pp)}" y1="22" y2="112"></line><text class="axis-label" x="${left}" y="132">${min.toFixed(1)} pp</text><text class="axis-label" text-anchor="end" x="${width - right}" y="132">${max.toFixed(1)} pp</text>`;
    leave.estimates.forEach((item, index) => { body += `<circle class="influence-dot" cx="${x(item.low_minus_high_income_pp)}" cy="${y + ((index * 11) % 31) - 15}" r="3"><title>Without ${escapeHTML(item.description)}: ${item.low_minus_high_income_pp.toFixed(1)} pp</title></circle>`; });
    body += `<text class="chart-value" text-anchor="middle" x="${x(leave.baseline_low_minus_high_income_pp)}" y="14">All indicators · ${leave.baseline_low_minus_high_income_pp.toFixed(1)} pp</text>`;
    q("#leave-one-chart").innerHTML = svg("Income gap after removing each representative series.", width, 145, body);
  }
})().catch(error => {
  const banner = document.querySelector("#status-banner");
  banner.hidden = false;
  banner.textContent = error.message;
});
