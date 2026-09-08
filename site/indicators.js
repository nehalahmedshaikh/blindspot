"use strict";
(async () => {
  const { escapeHTML, fetchJSON, metaPromise } = Blindspot;
  const q = selector => document.querySelector(selector);
  const [meta, indicators, goals] = await Promise.all([metaPromise, fetchJSON("assets/data/indicators.json"), fetchJSON("assets/data/goals.json")]);
  const goalMap = new Map(goals.map(item => [String(item.id), item]));
  const pageSize = 30;
  let page = 1;
  goals.forEach(goal => q("#series-goal").insertAdjacentHTML("beforeend", `<option value="${goal.id}">Goal ${goal.id}: ${escapeHTML(goal.label)}</option>`));
  const params = new URL(location.href).searchParams;
  q("#series-search").value = params.get("q") || "";
  q("#series-goal").value = params.get("goal") || "all";
  q("#series-scope").value = params.get("scope") || "all";

  function filteredRows() {
    const needle = q("#series-search").value.toLowerCase().trim();
    const goal = q("#series-goal").value, scope = q("#series-scope").value;
    return indicators.filter(item => {
      const representative = item.representative;
      const searchable = `${item.id} ${item.goals.join(" ")} ${representative.code} ${representative.description} ${item.variants.map(x => `${x.code} ${x.description}`).join(" ")}`.toLowerCase();
      return (!needle || searchable.includes(needle)) &&
        (goal === "all" || item.goals.map(String).includes(goal)) &&
        (scope === "all" || representative.applicability === scope);
    });
  }
  function updateURL() {
    const url = new URL(location.href);
    const values = { q: q("#series-search").value.trim(), goal: q("#series-goal").value, scope: q("#series-scope").value };
    Object.entries(values).forEach(([key, value]) => value && value !== "all" ? url.searchParams.set(key, value) : url.searchParams.delete(key));
    history.replaceState(null, "", url);
  }
  function render() {
    const rows = filteredRows(), pages = Math.max(1, Math.ceil(rows.length / pageSize));
    page = Math.min(page, pages);
    const visible = rows.slice((page - 1) * pageSize, page * pageSize);
    q("#series-count").textContent = `${rows.length} official indicators`;
    q("#series-grid").innerHTML = visible.map(item => {
      const series = item.representative;
      const goalsText = item.goals.map(id => `Goal ${id}: ${goalMap.get(String(id))?.label || "Unknown goal"}`).join(" · ");
      const coverage = series.applicability === "universal"
        ? `${series.coverage.toFixed(1)}% recent coverage`
        : `Visible in ${series.visible_countries} countries · contextual`;
      const variants = item.variants.filter(variant => variant.code !== series.code);
      const details = variants.length
        ? `<details><summary>${variants.length} other official series</summary><ul>${variants.map(variant => `<li><code>${escapeHTML(variant.code)}</code> ${escapeHTML(variant.description)}</li>`).join("")}</ul></details>`
        : "";
      return `<article class="indicator-row"><div><span class="goal">${escapeHTML(goalsText)}</span><strong>${escapeHTML(item.id)}</strong></div><div><h3>${escapeHTML(series.description)}</h3><p><code>${escapeHTML(series.code)}</code> · Expected every ${series.cadence} year${series.cadence === 1 ? "" : "s"} · ${escapeHTML(coverage)}</p>${details}</div></article>`;
    }).join("");
    q("#series-page").textContent = `Page ${page} of ${pages}`;
    q("#series-prev").disabled = page === 1;
    q("#series-next").disabled = page === pages;
    updateURL();
  }
  ["#series-search", "#series-goal", "#series-scope"].forEach(selector => q(selector).addEventListener("input", () => { page = 1; render(); }));
  q("#series-prev").addEventListener("click", () => { page--; render(); scrollTo({ top: q(".catalogue-panel").offsetTop - 80, behavior: "smooth" }); });
  q("#series-next").addEventListener("click", () => { page++; render(); scrollTo({ top: q(".catalogue-panel").offsetTop - 80, behavior: "smooth" }); });
  render();
})().catch(error => {
  const banner = document.querySelector("#status-banner");
  banner.hidden = false;
  banner.textContent = error.message;
});
