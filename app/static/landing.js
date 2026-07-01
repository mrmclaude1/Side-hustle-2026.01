"use strict";

// A short, human description for each Pro-only feature flag.
const PRO_FEATURES = {
  pro_signals: "Premium signals (full-depth + percentiles)",
  export: "CSV export",
  alerts_unlimited: "Unlimited alert rules",
};

function fmtCompact(n) {
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(1) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(Math.round(n));
}

async function loadLiveStat() {
  try {
    const d = await (await fetch("/api/scan?limit=1")).json();
    const s = d.summary;
    const top = d.assets[0];
    const el = document.getElementById("live-stat");
    if (s && top) {
      el.textContent =
        `Live: ${s.assets} assets scanned · top signal ${top.base} ` +
        `(score ${top.radar_score}) · $${fmtCompact(s.total_volume_usd)} 24h volume`;
    }
  } catch (e) {
    document.getElementById("live-stat").textContent =
      "Open the scanner for a live view of the market.";
  }
}

function planCard(name, p, checkoutUrl) {
  const isPro = name === "pro";
  const feats = [
    `Up to ${p.max_scan_limit}-deep scans`,
    `${p.rate_per_min}/min API rate`,
    isPro ? "Unlimited alert rules" : `${p.max_alert_rules} alert rules`,
  ];
  if (isPro) {
    for (const f of p.features) if (PRO_FEATURES[f]) feats.push(PRO_FEATURES[f]);
  }
  const cta = isPro
    ? `<a class="btn btn-primary cta" href="${checkoutUrl || "#"}" ${checkoutUrl ? 'target="_blank" rel="noopener"' : ""}>${checkoutUrl ? "Get Pro" : "Get Pro (configure checkout)"}</a>`
    : `<a class="btn btn-ghost cta" href="/app">Open free scanner</a>`;
  return `<div class="plan-card ${isPro ? "pro-card" : ""}">
    <h3>${name.toUpperCase()}</h3>
    <div class="muted">${isPro ? "Everything in Free, plus:" : "Full dashboard, free forever"}</div>
    <ul>${feats.map((f) => `<li>${f}</li>`).join("")}</ul>
    ${cta}
  </div>`;
}

async function loadPricing() {
  try {
    const data = await (await fetch("/api/pricing")).json();
    const url = data.checkout_url || "";
    const order = ["free", "pro"];
    document.getElementById("lp-pricing").innerHTML = order
      .filter((n) => data.plans[n])
      .map((n) => planCard(n, data.plans[n], url))
      .join("");
    if (url) document.getElementById("hero-pro").setAttribute("href", url);
  } catch (e) {
    document.getElementById("lp-pricing").innerHTML =
      '<p class="muted">Pricing unavailable. <a href="/app">Open the scanner →</a></p>';
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadLiveStat();
  loadPricing();
});
