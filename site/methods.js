"use strict";

(async () => {
  const { escapeHTML, fetchJSON, metaPromise } = Blindspot;
  const q = selector => document.querySelector(selector);
  const [meta, method] = await Promise.all([metaPromise, fetchJSON("assets/data/methodology.json")]);
  const priority = method.measurement_priority;
  q("#priority-method").innerHTML = `<p class="method-summary"><strong>${escapeHTML(priority.scale)}</strong> ${escapeHTML(priority.scope)}</p><div class="formula"><span>Default formula</span><strong>${escapeHTML(priority.formula)}</strong></div><div class="component-grid">${priority.weights.map(item => `<article><strong>${Math.round(item.weight * 100)}%</strong><h3>${escapeHTML(item.label)}</h3><p>${escapeHTML(item.meaning)}</p></article>`).join("")}</div>`;
  q("#research-method-grid").innerHTML = method.research.map(item => `<article><h3>${escapeHTML(item.label)}</h3><p>${escapeHTML(item.text)}</p></article>`).join("");
  function slug(term) { return term.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, ""); }
  function renderGlossary() {
    const needle = q("#glossary-search").value.toLowerCase().trim();
    q("#glossary-list").innerHTML = method.glossary.filter(item => `${item.term} ${item.definition}`.toLowerCase().includes(needle)).map(item => `<article id="${slug(item.term)}"><h3>${escapeHTML(item.term)}</h3><p>${escapeHTML(item.definition)}</p></article>`).join("");
  }
  q("#glossary-search").addEventListener("input", renderGlossary);
  renderGlossary();
})().catch(error => { const banner = document.querySelector("#status-banner"); banner.hidden = false; banner.textContent = error.message; });
