"use strict";

(async () => {
  const { escapeHTML, fetchJSON, metaPromise } = Blindspot;
  const q = selector => document.querySelector(selector);
  const totalCodes = new Set(["010", "017", "018", "019", "029", "030", "034", "035", "039", "053", "054", "057", "061", "142", "143", "145", "150", "151", "154", "155", "202", "419"]);
  const [meta, countries, series, goals, topology, rankings] = await Promise.all([metaPromise, fetchJSON("assets/data/countries.json"), fetchJSON("assets/data/series.json"), fetchJSON("assets/data/goals.json"), fetchJSON("assets/countries-110m.json"), fetchJSON("assets/data/rankings.json")]);
  const state = { meta, countries, series, goals, topology, rankings: rankings.rows, goal: "all", selected: null, goalData: new Map(), countryData: new Map() };
  const seriesMap = new Map(state.series.map(item => [item.code, item]));
  const countryMap = new Map(state.countries.map(item => [item.alpha3, item]));
  const goalMap = new Map(state.goals.map(item => [String(item.id), item]));

  function countryValue(country) {
    if (!country) return null;
    return state.goal === "all" ? country.priority : state.goalData.get(state.goal)?.[country.alpha3]?.priority ?? null;
  }
  function color(value) {
    if (value == null || Number.isNaN(value)) return "#cac5b9";
    const stops = ["#e8e1d2", "#e7cf9b", "#f5a56e", "#ef6b47", "#902f26"];
    return stops[Math.min(4, Math.floor(Math.max(0, Math.min(99.99, value)) / 20))];
  }
  function updateURL() {
    const url = new URL(location.href);
    state.selected ? url.searchParams.set("country", state.selected) : url.searchParams.delete("country");
    state.goal !== "all" ? url.searchParams.set("goal", state.goal) : url.searchParams.delete("goal");
    history.replaceState(null, "", url);
  }
  function renderMap() {
    const svg = q("#world-map");
    const arcs = BlindspotGeo.topologyArcs(state.topology);
    const byM49 = new Map(state.countries.map(item => [String(Number(item.m49)), item]));
    svg.innerHTML = "";
    state.topology.objects.countries.geometries.forEach(geometry => {
      if (totalCodes.has(String(geometry.id).padStart(3, "0"))) return;
      const country = byM49.get(String(Number(geometry.id)));
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
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
    tip.innerHTML = `<strong>${escapeHTML(country.name)}</strong><br>Measurement priority: ${countryValue(country)?.toFixed(1) ?? "n/a"}`;
    tip.style.left = `${Math.min(rect.width - 190, (event.clientX || rect.left + 20) - rect.left + 12)}px`;
    tip.style.top = `${Math.max(10, (event.clientY || rect.top + 20) - rect.top - 45)}px`;
    tip.hidden = false;
  }
  function hideTooltip() { q("#tooltip").hidden = true; }
  async function countrySeries(country) {
    if (!state.countryData.has(country.alpha3)) {
      state.countryData.set(country.alpha3, fetchJSON(`assets/data/${country.data_file}`));
    }
    return state.countryData.get(country.alpha3);
  }
  async function setGoal(goal, writeURL = true) {
    state.goal = goal;
    if (goal !== "all" && !state.goalData.has(goal)) {
      state.goalData.set(goal, await fetchJSON(`assets/data/${goalMap.get(String(goal)).data_file}`));
    }
    if (writeURL) updateURL();
    renderMap();
    if (state.selected) await selectCountry(state.selected, false);
  }
  async function selectCountry(alpha3, writeURL = true) {
    if (!alpha3) return;
    state.selected = alpha3;
    q("#country-select").value = alpha3;
    if (writeURL) updateURL();
    renderMap();
    const country = state.countries.find(item => item.alpha3 === alpha3);
    const countryRows = [...(await countrySeries(country))].sort((a, b) => (b.measurement_priority_v1 ?? -1) - (a.measurement_priority_v1 ?? -1));
    if (state.selected !== alpha3) return;
    const allSeries = state.goal === "all" ? countryRows : countryRows.filter(item => String(item.goal) === state.goal);
    const scored = allSeries.filter(item => item.score_components);
    const average = key => scored.length ? 100 * scored.reduce((sum, item) => sum + item.score_components[key], 0) / scored.length : null;
    const averagePriority = scored.length ? scored.reduce((sum, item) => sum + item.measurement_priority_v1, 0) / scored.length : null;
    const display = value => value == null ? "—" : value.toFixed(0);
    const gaps = scored.slice(0, 3);
    const tableRows = allSeries.map(item => {
      const series = seriesMap.get(item.series_code), priority = item.measurement_priority_v1 == null ? "Not ranked" : item.measurement_priority_v1.toFixed(1);
      const breakdowns = Object.entries(item.disaggregation).filter(([, visible]) => visible).map(([name]) => name).join(", ");
      return `<tr><td>${item.goal}. ${goalMap.get(String(item.goal))?.label || "Unknown goal"}</td><td><strong>${escapeHTML(series?.description || item.series_code)}</strong><small>${escapeHTML(item.series_code)}</small></td><td>${item.latest_year || "None since 2015"}</td><td>${(item.recent_completeness * 100).toFixed(0)}%</td><td>${breakdowns || "—"}</td><td>${priority}</td></tr>`;
    }).join("");
    const scope = state.goal === "all" ? "all goals" : `Goal ${state.goal}: ${goalMap.get(state.goal)?.label || "Unknown goal"}`;
    const gapCards = gaps.length ? gaps.map(gap => `<article><small class="gap-goal">Goal ${gap.goal}: ${goalMap.get(String(gap.goal))?.label || "Unknown goal"}</small><b>${escapeHTML(seriesMap.get(gap.series_code)?.description || gap.series_code)}</b><span>Latest year: ${gap.latest_year || "none since 2015"} · Measurement priority: ${gap.measurement_priority_v1.toFixed(1)}</span></article>`).join("") : `<div class="empty-state">No measurement-priority scores are available for ${escapeHTML(scope)}.</div>`;
    q("#country-profile").innerHTML = `<div class="profile-head"><div class="profile-identity"><small>${escapeHTML(country.region)} · ${escapeHTML(country.income_group)}</small><h3>${escapeHTML(country.name)}</h3></div><div class="profile-metrics"><div class="profile-stat profile-stat-primary"><strong>${display(averagePriority)}</strong><span>Average measurement priority</span></div><div class="profile-stat"><strong>${display(average("staleness"))}</strong><span>Staleness</span></div><div class="profile-stat"><strong>${display(average("completeness_deficit"))}</strong><span>Missingness</span></div><div class="profile-stat"><strong>${display(average("global_scarcity"))}</strong><span>Global scarcity</span></div><div class="profile-stat"><strong>${display(average("population_percentile"))}</strong><span>Population</span></div></div></div><div class="profile-label"><strong>Highest measurement priority · ${escapeHTML(scope)}</strong></div><div class="profile-gaps">${gapCards}</div><details class="all-series"><summary>See all ${allSeries.length} selected series for ${escapeHTML(country.name)} · ${escapeHTML(scope)}</summary><div class="table-wrap"><table><thead><tr><th>Goal</th><th>Indicator series</th><th>Latest year</th><th>Recent completeness</th><th>Breakdowns</th><th>Measurement priority</th></tr></thead><tbody>${tableRows}</tbody></table></div></details>`;
  }
  function adjustedRank(row) {
    const keys = ["staleness", "completeness_deficit", "global_scarcity", "population_percentile"];
    const weights = keys.map(key => Number(q(`#weight-${key}`).value));
    const total = weights.reduce((left, right) => left + right, 0) || 1;
    return 100 * weights.reduce((sum, weight, index) => sum + row[index + 3] * weight / total, 0);
  }
  function renderRankings() {
    const ranked = state.rankings.map(row => ({ row, adjusted: adjustedRank(row) })).sort((a, b) => b.adjusted - a.adjusted).slice(0, 15);
    q("#ranking-body").innerHTML = ranked.map((item, index) => {
      const [alpha3, seriesCode, latestYear] = item.row;
      const country = countryMap.get(alpha3), series = seriesMap.get(seriesCode);
      return `<tr><td>${String(index + 1).padStart(2, "0")}</td><td>${escapeHTML(country?.name || alpha3)}</td><td>${series?.goal}: ${goalMap.get(String(series?.goal))?.label || "Unknown goal"}</td><td>${escapeHTML(series?.description || seriesCode)}</td><td>${latestYear || "—"}</td><td>${item.adjusted.toFixed(1)}</td></tr>`;
    }).join("");
  }
  state.goals.forEach(goal => q("#goal-select").insertAdjacentHTML("beforeend", `<option value="${goal.id}">Goal ${goal.id}: ${escapeHTML(goal.label)}</option>`));
  state.countries.forEach(country => q("#country-select").insertAdjacentHTML("beforeend", `<option value="${country.alpha3}">${escapeHTML(country.name)}</option>`));
  q("#goal-select").addEventListener("change", event => setGoal(event.target.value));
  q("#country-select").addEventListener("change", event => selectCountry(event.target.value));
  ["staleness", "completeness_deficit", "global_scarcity", "population_percentile"].forEach(key => q(`#weight-${key}`).addEventListener("input", event => { q(`#out-${key}`).textContent = `${event.target.value}%`; renderRankings(); }));
  const params = new URL(location.href).searchParams;
  const initialGoal = params.get("goal");
  if (initialGoal && goalMap.has(initialGoal)) {
    q("#goal-select").value = initialGoal;
    await setGoal(initialGoal, false);
  } else {
    renderMap();
  }
  renderRankings();
  const initialCountry = params.get("country")?.toUpperCase();
  if (state.countries.some(item => item.alpha3 === initialCountry)) selectCountry(initialCountry, false);
})().catch(error => { const banner = document.querySelector("#status-banner"); banner.hidden = false; banner.textContent = error.message; });
