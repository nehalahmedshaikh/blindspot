"use strict";

const Blindspot = (() => {
  const pages = [
    ["overview", "./", "Overview"], ["explore", "explore/", "Explore"],
    ["indicators", "indicators/", "Indicators"], ["research", "research/", "Research"],
    ["methods", "methods/", "Methods"], ["data", "data/", "Data"]
  ];
  const page = document.body.dataset.page;
  const header = document.querySelector("#site-header");
  const footer = document.querySelector("#site-footer");
  const escapeHTML = value => String(value ?? "").replace(/[&<>'"]/g, character => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"})[character]);
  const fetchJSON = async path => {
    const response = await fetch(path);
    if (!response.ok) throw new Error(`Could not load ${path}.`);
    return response.json();
  };
  const signed = (value, digits = 1) => {
    const number = Number(value);
    return `${number > 0 ? "+" : number < 0 ? "−" : ""}${Math.abs(number).toFixed(digits)}`;
  };
  header.innerHTML = `<a class="brand" href="./">BLINDSPOT</a><nav aria-label="Primary">${pages.map(([id, href, label]) => `<a href="${href}"${id === page ? ' aria-current="page"' : ""}>${label}</a>`).join("")}</nav>`;
  footer.innerHTML = `<strong>BLINDSPOT</strong><span>Evidence about the evidence.</span><a href="https://github.com/nehalahmedshaikh/blindspot">Source and documentation ↗</a><span id="freshness">Loading source status…</span>`;
  const metaPromise = fetchJSON("assets/data/meta.json").then(index => {
    document.querySelectorAll("[data-count]").forEach(node => { node.textContent = Number(index.counts[node.dataset.count]).toLocaleString(); });
    document.querySelectorAll("[data-window]").forEach(node => { node.textContent = index.meta.recent_window.join("—"); });
    document.querySelector("#freshness").textContent = `Source snapshot ${new Date(index.meta.retrieved_at).toLocaleDateString()}`;
    if (index.meta.status !== "fresh") {
      const banner = document.querySelector("#status-banner");
      banner.hidden = false;
      banner.textContent = "The latest refresh failed. Blindspot is showing the last validated snapshot.";
    }
    return index;
  }).catch(error => {
    const banner = document.querySelector("#status-banner");
    banner.hidden = false;
    banner.textContent = error.message;
    throw error;
  });
  return { escapeHTML, fetchJSON, metaPromise, signed };
})();
window.Blindspot = Blindspot;
