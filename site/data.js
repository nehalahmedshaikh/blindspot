"use strict";

(async () => {
  const { escapeHTML, fetchJSON, metaPromise } = Blindspot;
  const q = selector => document.querySelector(selector);
  const [meta, catalog, manifest] = await Promise.all([metaPromise, fetchJSON("assets/data/data-catalog.json"), fetchJSON("assets/data/manifest.json")]);
  q("#snapshot-grid").innerHTML = `<article><strong>${manifest.status}</strong><span>Status</span></article><article><strong>${new Date(manifest.retrieved_at).toLocaleDateString()}</strong><span>Retrieved</span></article><article><strong>${meta.counts.country_series_assessments.toLocaleString()}</strong><span>Country–series assessments</span></article><article><strong>${manifest.history.changed + manifest.history.added + manifest.history.removed}</strong><span>Changes from prior snapshot</span></article>`;
  q("#primary-sources").innerHTML = manifest.sources.map(source => `<a href="${source.url}" rel="noreferrer"><span><strong>${escapeHTML(source.source)}</strong><small>${Number(source.rows).toLocaleString()} source rows · ${escapeHTML(source.status)}</small></span><b>↗</b></a>`).join("");
  q("#download-list").innerHTML = catalog.downloads.map(item => `<a href="${item.href}"><span><strong>${escapeHTML(item.label)}</strong><small>${escapeHTML(item.description)}</small></span><b>${escapeHTML(item.format)} ↗</b></a>`).join("");
  q("#reference-list").innerHTML = catalog.references.map(item => `<a href="${item.href}" rel="noreferrer"><span><strong>${escapeHTML(item.label)}</strong><small>${escapeHTML(item.description)}</small></span><b>↗</b></a>`).join("");
})().catch(error => { const banner = document.querySelector("#status-banner"); banner.hidden = false; banner.textContent = error.message; });
