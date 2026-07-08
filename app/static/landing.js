"use strict";

// Human descriptions for Pro-only feature flags. alerts_unlimited is covered
// by the hardcoded bullet in planCard, so it is deliberately absent here.
const PRO_FEATURES = {
  pro_signals: "Premium signals (full-depth + percentiles)",
  export: "CSV export",
};

// Escape API-derived strings before innerHTML interpolation.
const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function fmtCompact(n) {
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(1) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(Math.round(n));
}

function fmtPct(v) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  return (n > 0 ? "+" : "") + n.toFixed(2) + "%";
}

function signedClass(v) {
  if (v === null || v === undefined) return "";
  return Number(v) > 0 ? "pos" : Number(v) < 0 ? "neg" : "";
}

async function loadLiveStat() {
  const statEl = document.getElementById("live-stat");
  try {
    const d = await (await fetch("/api/scan?limit=5")).json();
    const s = d.summary;
    const top = d.assets && d.assets[0];
    if (s && top) {
      const prefix = d.meta && d.meta.data_source === "live" ? "Live" : "Snapshot";
      statEl.textContent =
        `${prefix}: ${s.assets} assets scanned · top signal ${top.base} ` +
        `(score ${top.radar_score}) · $${fmtCompact(s.total_volume_usd)} 24h volume`;
      renderPreview(d.assets);
    } else {
      statEl.textContent = "Open the scanner for a live view of the market.";
    }
  } catch (e) {
    statEl.textContent = "Open the scanner for a live view of the market.";
  }
}

function renderPreview(assets) {
  const tbody = document.getElementById("preview-rows");
  if (!tbody || !assets || !assets.length) return;
  tbody.innerHTML = assets.slice(0, 5).map((a) => `
    <tr>
      <td class="num"><span class="p-score"><i style="width:${Math.max(0, Math.min(100, a.radar_score))}%"></i><b>${a.radar_score.toFixed(1)}</b></span></td>
      <td><strong>${esc(a.base)}</strong>${a.has_perp ? ' <span class="p-badge">PERP</span>' : ""}</td>
      <td class="num ${signedClass(a.change_pct)}">${fmtPct(a.change_pct)}</td>
      <td class="num ${signedClass(a.basis_bps)}">${a.basis_bps === null || a.basis_bps === undefined ? "—" : (a.basis_bps > 0 ? "+" : "") + a.basis_bps.toFixed(1)}</td>
    </tr>`).join("");
}

function planCard(name, p, checkoutUrl) {
  const isPro = name === "pro";
  const feats = [
    `Up to ${p.max_scan_limit}-deep scans`,
    `${p.rate_per_min}/min API rate`,
    isPro ? "Unlimited alert rules" : `${p.max_alert_rules} alert rules`,
  ];
  if (isPro) {
    for (const f of p.features) {
      const label = PRO_FEATURES[f];
      if (label && !feats.includes(label)) feats.push(label);
    }
  }
  const price = isPro
    ? `<div class="price">$${esc(p.price_usd_month || "—")}<span>/mo</span></div>`
    : `<div class="price">$0<span> forever</span></div>`;
  const cta = isPro
    ? (checkoutUrl
        ? `<a class="btn btn-primary cta" href="${esc(checkoutUrl)}" target="_blank" rel="noopener">Get Pro</a>`
        : `<a class="btn btn-ghost cta" href="/app">Pro checkout opens soon — try the free scanner</a>`)
    : `<a class="btn btn-ghost cta" href="/app">Open free scanner</a>`;
  return `<div class="plan-card ${isPro ? "pro-card" : ""}">
    ${isPro ? '<span class="pop">MOST POPULAR</span>' : ""}
    <h3>${name.toUpperCase()}</h3>
    ${price}
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
    // The hero "Get Pro" always scrolls to pricing first, so the price is seen
    // before any checkout — the card CTA carries the actual checkout link.
  } catch (e) {
    document.getElementById("lp-pricing").innerHTML =
      '<p class="muted">Pricing unavailable. <a href="/app">Open the scanner →</a></p>';
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadLiveStat();
  loadPricing();
});
