"use strict";

const state = { data: null, topology: null, goal: "all", selected: null };
const q = (selector) => document.querySelector(selector);
const totalCodes = new Set(["010", "017", "018", "019", "029", "030", "034", "035", "039", "053", "054", "057", "061", "142", "143", "145", "150", "151", "154", "155", "202", "419"]);
const goalNames = [
  "", "No poverty", "Zero hunger", "Good health and well-being", "Quality education",
  "Gender equality", "Clean water and sanitation", "Affordable and clean energy",
  "Decent work and economic growth", "Industry, innovation and infrastructure",
  "Reduced inequalities", "Sustainable cities and communities",
  "Responsible consumption and production", "Climate action", "Life below water",
  "Life on land", "Peace, justice and strong institutions", "Partnerships for the goals"
];

function countryValue(country) {
  if (!country) return null;
  if (state.goal !== "all") return country.goals[state.goal]?.priority ?? null;
  return country.priority;
}

function color(value) {
  if (value == null || Number.isNaN(value)) return "#cac5b9";
  const stops = ["#e8e1d2", "#e7cf9b", "#f5a56e", "#ef6b47", "#902f26"];
  return stops[Math.min(stops.length - 1, Math.floor(Math.max(0, Math.min(99.99, value)) / 20))];
}

function renderMap() {
  const svg = q("#world-map"), arcs = BlindspotGeo.topologyArcs(state.topology);
  const byM49 = new Map(state.data.countries.map(item => [String(Number(item.m49)), item]));
  svg.innerHTML = "";
  state.topology.objects.countries.geometries.forEach(geometry => {
    const id = String(Number(geometry.id));
    if (totalCodes.has(String(geometry.id).padStart(3, "0"))) return;
    const country = byM49.get(id), path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", BlindspotGeo.pathFor(geometry, arcs));
    path.setAttribute("fill", color(countryValue(country)));
    path.setAttribute("class", `country-shape${state.selected === country?.alpha3 ? " selected" : ""}`);
    path.setAttribute("tabindex", country ? "0" : "-1");
    if (country) path.setAttribute("aria-label", `${country.name}: ${countryValue(country)?.toFixed(1) ?? "no score"}`);
    const show = event => showTooltip(event, country);
    path.addEventListener("mousemove", show); path.addEventListener("focus", show);
    path.addEventListener("mouseleave", hideTooltip); path.addEventListener("blur", hideTooltip);
    path.addEventListener("click", () => selectCountry(country?.alpha3));
    path.addEventListener("keydown", event => { if (event.key === "Enter") selectCountry(country?.alpha3); });
    svg.appendChild(path);
  });
}

function showTooltip(event, country) {
  if (!country) return;
  const tip = q("#tooltip"), rect = q(".map-wrap").getBoundingClientRect();
  tip.innerHTML = `<strong>${country.name}</strong><br>Measurement priority: ${countryValue(country)?.toFixed(1) ?? "n/a"} / 100`;
  tip.style.left = `${Math.min(rect.width - 190, (event.clientX || rect.left + 20) - rect.left + 12)}px`;
  tip.style.top = `${Math.max(10, (event.clientY || rect.top + 20) - rect.top - 45)}px`; tip.hidden = false;
}
function hideTooltip() { q("#tooltip").hidden = true; }

function selectCountry(alpha3) {
  if (!alpha3) return;
  state.selected = alpha3; q("#country-select").value = alpha3; renderMap();
  const country = state.data.countries.find(item => item.alpha3 === alpha3);
  const seriesMap = new Map(state.data.series.map(item => [item.code, item]));
  const allSeries = state.data.country_series
    .filter(item => item.country_alpha3 === alpha3)
    .sort((a,b) => (b.measurement_priority_v1 ?? -1) - (a.measurement_priority_v1 ?? -1));
  const scoredSeries = allSeries.filter(item => item.score_components);
  const averageComponent = key => 100 * scoredSeries.reduce((sum, item) => sum + item.score_components[key], 0) / scoredSeries.length;
  const gaps = allSeries.filter(item => item.measurement_priority_v1 != null).slice(0,3);
  const seriesRows = allSeries.map(item => {
    const series = seriesMap.get(item.series_code);
    const priority = item.measurement_priority_v1 == null ? "Not ranked" : item.measurement_priority_v1.toFixed(1);
    return `<tr><td>${item.goal}. ${goalNames[item.goal]}</td><td><strong>${series?.description || item.series_code}</strong><small>${item.series_code}</small></td><td>${item.latest_year || "None since 2015"}</td><td>${(item.recent_completeness * 100).toFixed(0)}%</td><td>${priority}</td></tr>`;
  }).join("");
  q("#country-profile").innerHTML = `
    <div class="profile-head">
      <div class="profile-identity"><small>${country.region} · ${country.income_group}</small><h3>${country.name}</h3></div>
      <div class="profile-metrics">
        <div class="profile-stat profile-stat-primary"><strong>${country.priority.toFixed(0)}</strong><span>Average measurement priority</span></div>
        <div class="profile-stat"><strong>${averageComponent("staleness").toFixed(0)}</strong><span>Staleness</span></div>
        <div class="profile-stat"><strong>${averageComponent("completeness_deficit").toFixed(0)}</strong><span>Missingness</span></div>
        <div class="profile-stat"><strong>${averageComponent("global_scarcity").toFixed(0)}</strong><span>Global scarcity</span></div>
        <div class="profile-stat"><strong>${averageComponent("population_percentile").toFixed(0)}</strong><span>Population</span></div>
      </div>
    </div>
    <div class="profile-label"><strong>Three indicator series with highest measurement priority</strong></div>
    <div class="profile-gaps">${gaps.map(gap => `<article><small class="gap-goal">Goal ${gap.goal}: ${goalNames[gap.goal]}</small><b>${seriesMap.get(gap.series_code)?.description || gap.series_code}</b><span>Latest year: ${gap.latest_year || "none since 2015"} · Measurement priority: ${gap.measurement_priority_v1.toFixed(1)} / 100</span></article>`).join("")}</div>
    <details class="all-series"><summary>See all ${allSeries.length} selected series for ${country.name}</summary><div class="table-wrap"><table><thead><tr><th>Goal</th><th>Indicator series</th><th>Latest year</th><th>Recent completeness</th><th>Measurement priority / 100</th></tr></thead><tbody>${seriesRows}</tbody></table></div></details>`;
}

function adjustedRank(item) {
  const components = item.score_components, keys = ["staleness", "completeness_deficit", "global_scarcity", "population_percentile"];
  const weights = keys.map(key => Number(q(`#weight-${key}`).value));
  const total = weights.reduce((a,b) => a+b, 0) || 1;
  return 100 * keys.reduce((sum, key, index) => sum + components[key] * weights[index] / total, 0);
}

function renderRankings() {
  const seriesMap = new Map(state.data.series.map(item => [item.code, item]));
  const ranked = state.data.top_rankings.map(item => ({...item, adjusted: adjustedRank(item)})).sort((a,b) => b.adjusted-a.adjusted).slice(0,15);
  q("#ranking-body").innerHTML = ranked.map((item,index) => `<tr><td>${String(index+1).padStart(2,"0")}</td><td>${item.country_name}</td><td>${item.goal}: ${goalNames[item.goal]}</td><td>${seriesMap.get(item.series_code)?.description || item.series_code}</td><td>${item.latest_year || "—"}</td><td>${item.adjusted.toFixed(1)}</td></tr>`).join("");
}

function renderSeries(filter="") {
  const needle = filter.toLowerCase().trim();
  const rows = state.data.series.filter(item => `${item.goal} ${goalNames[item.goal]} ${item.code} ${item.description}`.toLowerCase().includes(needle));
  q("#series-grid").innerHTML = rows.map(item => `<article class="series-card"><span class="goal">Goal ${item.goal}: ${goalNames[item.goal]}</span><h3>${item.description}</h3><p>${item.rationale} · Expected every ${item.cadence} year${item.cadence === 1 ? "" : "s"}.</p><div class="coverage-bar"><i style="width:${item.coverage}%"></i></div><span class="coverage-label">${item.coverage.toFixed(1)}% recent coverage · ${item.applicability}</span><a href="https://unstats.un.org/sdgs/metadata/?Goal=${item.goal}" rel="noreferrer">Official goal metadata ↗</a></article>`).join("");
}

function populateControls() {
  for (let goal=1; goal<=17; goal++) q("#goal-select").insertAdjacentHTML("beforeend", `<option value="${goal}">Goal ${goal}: ${goalNames[goal]}</option>`);
  state.data.countries.forEach(country => q("#country-select").insertAdjacentHTML("beforeend", `<option value="${country.alpha3}">${country.name}</option>`));
  q("#goal-select").addEventListener("change", event => { state.goal=event.target.value; renderMap(); });
  q("#country-select").addEventListener("change", event => selectCountry(event.target.value));
  q("#series-search").addEventListener("input", event => renderSeries(event.target.value));
  ["staleness","completeness_deficit","global_scarcity","population_percentile"].forEach(key => q(`#weight-${key}`).addEventListener("input", event => { q(`#out-${key}`).textContent=`${event.target.value}%`; renderRankings(); }));
}

async function init() {
  try {
    const [dataResponse, topologyResponse] = await Promise.all([fetch("data/dashboard.json"), fetch("assets/countries-110m.json")]);
    if (!dataResponse.ok || !topologyResponse.ok) throw new Error("Generated data is unavailable. Run the Blindspot pipeline first.");
    state.data = await dataResponse.json(); state.topology = await topologyResponse.json();
    q("#country-count").textContent=state.data.countries.length;
    q("#window-label").textContent=state.data.meta.recent_window.join("—");
    q("#freshness").textContent=`Source snapshot ${new Date(state.data.meta.retrieved_at).toLocaleDateString()}`;
    if (state.data.meta.status !== "fresh") { const banner=q("#status-banner"); banner.hidden=false; banner.textContent="Latest source refresh failed. The atlas is showing the last validated snapshot; inspect the provenance manifest for details."; }
    populateControls(); renderMap(); renderRankings(); renderSeries();
  } catch (error) {
    const banner=q("#status-banner"); banner.hidden=false; banner.textContent=error.message;
  }
}
init();
