"use strict";

(async () => {
  const { escapeHTML, fetchJSON, metaPromise } = Blindspot;
  const q = selector => document.querySelector(selector);
  const [meta, series, goals] = await Promise.all([metaPromise, fetchJSON("assets/data/series.json"), fetchJSON("assets/data/goals.json")]);
  const goalMap = new Map(goals.map(item => [String(item.id), item]));
  const pageSize = 24;
  let page = 1;
  goals.forEach(goal => q("#series-goal").insertAdjacentHTML("beforeend", `<option value="${goal.id}">Goal ${goal.id}: ${escapeHTML(goal.label)}</option>`));
  const params = new URL(location.href).searchParams;
  q("#series-search").value = params.get("q") || "";
  q("#series-goal").value = params.get("goal") || "all";
  q("#series-scope").value = params.get("scope") || "all";
  function filteredRows() {
    const needle = q("#series-search").value.toLowerCase().trim();
    const goal = q("#series-goal").value, scope = q("#series-scope").value;
    return series.filter(item => (!needle || `${item.goal} ${goalMap.get(String(item.goal))?.label || "Unknown goal"} ${item.code} ${item.description} ${item.rationale}`.toLowerCase().includes(needle)) && (goal === "all" || String(item.goal) === goal) && (scope === "all" || item.applicability === scope));
  }
  function updateURL() {
    const url = new URL(location.href), values = { q: q("#series-search").value.trim(), goal: q("#series-goal").value, scope: q("#series-scope").value };
    Object.entries(values).forEach(([key, value]) => value && value !== "all" ? url.searchParams.set(key, value) : url.searchParams.delete(key));
    history.replaceState(null, "", url);
  }
  function render() {
    const rows = filteredRows(), pages = Math.max(1, Math.ceil(rows.length / pageSize));
    page = Math.min(page, pages);
    const visible = rows.slice((page - 1) * pageSize, page * pageSize);
    q("#series-count").textContent = `${rows.length} indicator series`;
    q("#series-grid").innerHTML = visible.map(item => `<article class="series-card"><span class="goal">Goal ${item.goal}: ${goalMap.get(String(item.goal))?.label || "Unknown goal"}</span><h3>${escapeHTML(item.description)}</h3><p>${escapeHTML(item.rationale)} · Expected every ${item.cadence} year${item.cadence === 1 ? "" : "s"}.</p><div class="coverage-bar"><i style="width:${item.coverage}%"></i></div><span class="coverage-label">${item.coverage.toFixed(1)}% recent coverage · ${item.applicability}</span><a href="https://unstats.un.org/sdgs/metadata/?Goal=${item.goal}" rel="noreferrer">Official goal metadata ↗</a></article>`).join("");
    q("#series-page").textContent = `Page ${page} of ${pages}`;
    q("#series-prev").disabled = page === 1; q("#series-next").disabled = page === pages;
    updateURL();
  }
  ["#series-search", "#series-goal", "#series-scope"].forEach(selector => q(selector).addEventListener("input", () => { page = 1; render(); }));
  q("#series-prev").addEventListener("click", () => { page--; render(); scrollTo({ top: q(".catalogue-panel").offsetTop - 80, behavior: "smooth" }); });
  q("#series-next").addEventListener("click", () => { page++; render(); scrollTo({ top: q(".catalogue-panel").offsetTop - 80, behavior: "smooth" }); });
  render();
})().catch(error => { const banner = document.querySelector("#status-banner"); banner.hidden = false; banner.textContent = error.message; });
