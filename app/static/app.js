"use strict";

const state = {
  rows: [],
  sortKey: "radar_score",
  sortDir: -1, // -1 desc, 1 asc
  query: "",
};

const $ = (s) => document.querySelector(s);

// Friendly labels for API feature flags / metrics (raw values stay in the API).
const FEATURE_LABELS = {
  scan: "Full market scan",
  cross: "Cross-exchange view",
  history: "Score history & sparklines",
  alerts: "Alert rules",
  alerts_unlimited: "Unlimited alert rules",
  export: "CSV export",
  pro_signals: "Premium signals (full-depth + percentiles)",
};
const METRIC_LABELS = {
  radar_score: "Radar score",
  score_delta: "Score Δ",
  basis_bps: "Basis (bps)",
  abs_basis_bps: "|Basis| (bps)",
  change_pct: "24h change %",
  abs_change_pct: "|24h change| %",
  range_pct: "Range %",
  volume_usd: "Volume (USD)",
};

function fmtNum(v, opts = {}) {
  if (v === null || v === undefined) return "—";
  const { dp = 2, pct = false, sign = false } = opts;
  const n = Number(v);
  let s = n.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
  if (sign && n > 0) s = "+" + s;
  return pct ? s + "%" : s;
}

function fmtCompact(v) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n.toFixed(0);
}

function fmtPrice(v) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (n >= 1) {
    const dp = n >= 100 ? 2 : 3;
    return n.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
  }
  // Sub-$1 assets keep 4 significant digits so micro-price moves stay visible.
  return n.toLocaleString(undefined, { minimumSignificantDigits: 4, maximumSignificantDigits: 4 });
}

function signedClass(v) {
  if (v === null || v === undefined) return "";
  return Number(v) > 0 ? "pos" : Number(v) < 0 ? "neg" : "";
}

function scoreColor(s) {
  // Legible grey floor -> accent. Every step stays readable on --panel-2;
  // sign/magnitude never relies on this color alone (bar width + text carry it).
  const t = Math.max(0, Math.min(1, s / 100));
  const r = Math.round(139 + t * (57 - 139));
  const g = Math.round(151 + t * (135 - 151));
  const b = Math.round(168 + t * (229 - 168));
  return `rgb(${r},${g},${b})`;
}

function scoreGauge(score) {
  // Mini bar-gauge: fill width encodes magnitude, text stays high-contrast.
  return `<span class="score"><i class="score-fill" style="width:${Math.max(0, Math.min(100, score))}%"></i><b>${score.toFixed(1)}</b></span>`;
}

function renderSummary(s, meta, topAsset) {
  const breadth = s.breadth_pct;
  const cards = [
    ["Assets scanned", s.assets, ""],
    ["Breadth", breadth === null ? "—" : `${breadth}% advancing`, breadth === null ? "" : breadth >= 50 ? "pos" : "neg"],
    ["Advancers / Decliners",
      `${s.advancers} / ${s.decliners}` +
      `<div class="split"><i style="flex:${s.advancers || 0}"></i><i class="d" style="flex:${s.decliners || 0}"></i></div>`, ""],
    ["Avg 24h change", s.avg_change_pct === null ? "—" : fmtNum(s.avg_change_pct, { pct: true, sign: true }), signedClass(s.avg_change_pct)],
    ["Avg perp basis", s.avg_basis_bps === null ? "—" : fmtNum(s.avg_basis_bps, { sign: true }) + " bps", signedClass(s.avg_basis_bps)],
    ["Total volume", "$" + fmtCompact(s.total_volume_usd), ""],
  ];
  if (topAsset) {
    cards.unshift(["Top signal",
      `<a href="#scan" class="plain">${topAsset.base} · ${topAsset.radar_score.toFixed(1)}</a>`, ""]);
  }
  $("#summary").innerHTML =
    cards.map(([k, v, cls]) =>
      `<div class="card"><div class="k">${k}</div><div class="v ${cls}">${v}</div></div>`
    ).join("") +
    `<div class="card" id="top-arb" hidden><div class="k">Best arb edge</div><div class="v"></div></div>`;

  const pill = $("#source-pill");
  pill.textContent = meta.data_source === "live" ? "● LIVE" : "● DEMO SNAPSHOT";
  pill.className = "pill " + (meta.data_source === "live" ? "live" : "fixture");
}

function stateRow(msg, cls = "") {
  return `<tr class="state-row ${cls}"><td colspan="10">${msg}</td></tr>`;
}

function renderRows() {
  // Remember an open sparkline so the 60s auto-refresh doesn't swallow it.
  const openBase = document.querySelector(".detail-row")?.previousElementSibling?.dataset?.base;

  let rows = state.rows.slice();
  if ($("#perps-only").checked) rows = rows.filter((r) => r.has_perp);
  if (state.query) {
    const q = state.query.toUpperCase();
    rows = rows.filter((r) => r.base.includes(q));
  }

  const k = state.sortKey;
  rows.sort((a, b) => {
    const av = a[k], bv = b[k];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    if (av < bv) return -1 * state.sortDir;
    if (av > bv) return 1 * state.sortDir;
    return 0;
  });

  if (!rows.length) {
    $("#rows").innerHTML = stateRow(
      state.rows.length ? "No assets match your filters." : "No data yet.");
  } else {
    $("#rows").innerHTML = rows
      .map((r) => {
        const badge = r.has_perp ? '<span class="badge">PERP</span>' : "";
        const d = r.score_delta;
        const delta =
          d === null || d === undefined
            ? '<span class="muted">—</span>'
            : Math.abs(d) < 0.05
              ? '<span class="delta-flat">·</span>'
              : `<span class="${signedClass(d)}">${d > 0 ? "▲" : "▼"} ${Math.abs(d).toFixed(1)}</span>`;
        return `<tr data-base="${r.base}" class="data-row" tabindex="0" aria-label="${r.base}: show score history">
          <td class="num">${scoreGauge(r.radar_score)}</td>
          <td class="num">${delta}</td>
          <td><span class="asset">${r.base}</span>${badge}</td>
          <td class="num">${fmtPrice(r.price)}</td>
          <td class="num ${signedClass(r.change_pct)}">${fmtNum(r.change_pct, { pct: true, sign: true })}</td>
          <td class="num ${signedClass(r.basis_bps)}">${fmtNum(r.basis_bps, { dp: 1, sign: true })}</td>
          <td class="num">${fmtNum(r.range_pct, { dp: 1, pct: true })}</td>
          <td class="num">${fmtNum(r.spread_bps, { dp: 1 })}</td>
          <td class="num">${fmtCompact(r.open_interest)}</td>
          <td class="num">$${fmtCompact(r.volume_usd)}</td>
        </tr>`;
      })
      .join("");
  }

  // Sort indicators on the scanner grid only.
  document.querySelectorAll("#grid thead th").forEach((th) => {
    const sorted = th.dataset.k === state.sortKey;
    th.classList.toggle("sorted", sorted);
    th.classList.toggle("asc", sorted && state.sortDir === 1);
    th.setAttribute("aria-sort", sorted ? (state.sortDir === 1 ? "ascending" : "descending") : "none");
  });

  // Restore the sparkline the user had open.
  if (openBase) {
    const tr = document.querySelector(`tr.data-row[data-base="${openBase}"]`);
    if (tr) toggleDetail(tr);
  }
}

async function load() {
  const minVol = $("#min-volume").value || 0;
  const limit = $("#limit").value || 50;
  const btn = $("#refresh");
  btn.disabled = true;
  try {
    const res = await fetch(`/api/scan?min_volume_usd=${minVol}&limit=${limit}`);
    const data = await res.json();
    state.rows = data.assets;
    renderSummary(data.summary, data.meta, data.assets[0]);
    renderRows();
    loadCross(); // refresh top-arb card against the new summary DOM
    const age = data.meta.cache_age_s ? ` · cached ${data.meta.cache_age_s}s` : "";
    $("#updated").textContent = `Updated ${new Date().toLocaleTimeString()}${age}`;
  } catch (e) {
    $("#rows").innerHTML = stateRow("Couldn’t load market data — check your connection and hit ↻ Refresh.", "error");
    $("#updated").textContent = "Failed to load data.";
  } finally {
    btn.disabled = false;
  }
}

function sparkline(points, w = 240, h = 40) {
  const vals = points.map((p) => p.radar_score).filter((v) => v !== null);
  if (vals.length < 2) return '<span class="muted">Not enough history yet — snapshots build over time.</span>';
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const step = w / (vals.length - 1);
  const coords = vals.map((v, i) => [i * step, h - 4 - ((v - min) / span) * (h - 8)]);
  const pts = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const [lx, ly] = coords[coords.length - 1];
  return `<svg width="${w}" height="${h}" class="spark" role="img" aria-label="Score ${min.toFixed(1)} to ${max.toFixed(1)} over ${vals.length} snapshots">
      <polygon points="0,${h} ${pts} ${w},${h}" fill="rgba(57,135,229,.14)"/>
      <polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="1.5"/>
      <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="2.5" fill="var(--accent)"/>
    </svg> <span class="muted">score ${min.toFixed(1)}–${max.toFixed(1)} over ${vals.length} snapshots</span>`;
}

async function toggleDetail(tr) {
  const base = tr.dataset.base;
  const next = tr.nextElementSibling;
  if (next && next.classList.contains("detail-row")) {
    next.remove();
    return;
  }
  // Close any other open detail row.
  document.querySelectorAll(".detail-row").forEach((el) => el.remove());
  const dr = document.createElement("tr");
  dr.className = "detail-row";
  dr.innerHTML = `<td colspan="10" class="detail">Loading ${base} history…</td>`;
  tr.after(dr);
  try {
    const res = await fetch(`/api/history/${encodeURIComponent(base)}`);
    const data = await res.json();
    dr.querySelector(".detail").innerHTML =
      `<strong>${base}</strong> &nbsp; ` + sparkline(data.points);
  } catch (e) {
    dr.querySelector(".detail").textContent = "Failed to load history.";
  }
}

async function loadPlan() {
  try {
    const me = await (await fetch("/api/me")).json();
    const pill = $("#plan-pill");
    pill.textContent = "plan: " + me.plan.toUpperCase();
    pill.className = "pill " + (me.plan === "pro" ? "live" : "");
  } catch (e) { /* optional */ }
}

async function loadPricing() {
  try {
    const data = await (await fetch("/api/pricing")).json();
    const url = data.checkout_url || "";
    const grid = $("#pricing-grid");
    grid.innerHTML = ["free", "pro"]
      .filter((n) => data.plans[n])
      .map((name) => {
        const p = data.plans[name];
        const isPro = name === "pro";
        const feats = p.features.map((f) => `<li>${FEATURE_LABELS[f] || f}</li>`).join("");
        const price = isPro
          ? `<div class="price">$${p.price_usd_month || "—"}<span>/mo</span></div>`
          : `<div class="price">$0</div>`;
        const cta = isPro
          ? (url
              ? `<a class="btn-cta primary" href="${url}" target="_blank" rel="noopener">Get Pro</a>`
              : `<span class="btn-cta ghost" title="Pro checkout opens soon">Coming soon</span>`)
          : "";
        return `<div class="plan-card ${isPro ? "pro-card" : ""}">
          ${isPro ? '<span class="pop">MOST POPULAR</span>' : ""}
          <h3>${name.toUpperCase()}</h3>
          ${price}
          <div class="muted">${p.rate_per_min}/min · scan ≤ ${p.max_scan_limit} · ${isPro ? "unlimited" : p.max_alert_rules} alert rules</div>
          <ul>${feats}</ul>
          ${cta}
        </div>`;
      })
      .join("");
  } catch (e) { /* optional */ }
}

async function loadCross() {
  try {
    const data = await (await fetch("/api/cross?limit=25")).json();
    const s = data.summary;
    $("#cross-venues").textContent =
      s.venues.length ? s.venues.join(", ") : "multiple venues";
    $("#cross-rows").innerHTML = data.assets
      .map((a) => {
        const arb = a.arb;
        const edge = arb ? arb.edge_bps : null;
        const edgeCls = edge !== null && edge > 0 ? "pos" : "muted";
        const dir = arb ? `${arb.buy_at} → ${arb.sell_at}` : "—";
        return `<tr>
          <td class="num"><span class="spread-pill" style="color:${scoreColor(Math.min(100, (a.price_spread_bps || 0) * 4))}">${fmtNum(a.price_spread_bps, { dp: 1 })}</span></td>
          <td><span class="asset">${a.base}</span></td>
          <td class="muted">${a.venues.join(" · ")}</td>
          <td class="num">${fmtPrice(a.reference_price)}</td>
          <td class="num ${edgeCls}">${edge === null ? "—" : fmtNum(edge, { dp: 1, sign: true })}</td>
          <td class="muted">${dir}</td>
          <td class="num">$${fmtCompact(a.total_volume_usd)}</td>
        </tr>`;
      })
      .join("");

    // Surface the best positive arb edge as an above-the-fold card.
    const best = data.assets
      .filter((a) => a.arb && a.arb.edge_bps > 0)
      .sort((a, b) => b.arb.edge_bps - a.arb.edge_bps)[0];
    const card = $("#top-arb");
    if (card) {
      if (best) {
        card.hidden = false;
        card.querySelector(".v").innerHTML =
          `<a href="#cross" class="plain">${best.base} · ${best.arb.edge_bps.toFixed(1)} bps</a>`;
      } else {
        card.hidden = true;
      }
    }
  } catch (e) { /* cross-exchange view is optional */ }
}

async function loadAlerts() {
  try {
    const meta = await (await fetch("/api/alerts")).json();
    const mSel = $("#rule-metric"), oSel = $("#rule-op");
    if (mSel && !mSel.options.length) {
      mSel.innerHTML = meta.metrics
        .map((m) => `<option value="${m}">${METRIC_LABELS[m] || m}</option>`).join("");
      oSel.innerHTML = meta.ops.map((o) => `<option>${o}</option>`).join("");
    }
    const rl = $("#rule-list");
    rl.innerHTML = meta.rules.length
      ? meta.rules.map((r) =>
          `<li><span>${r.enabled ? "" : "(off) "}<strong>${r.name}</strong>: ${METRIC_LABELS[r.metric] || r.metric} ${r.op} ${r.threshold}</span>
           <button class="link del-rule" data-id="${r.id}" aria-label="Delete rule ${r.name}">✕</button></li>`).join("")
      : '<li class="muted">None yet — add your first rule above.</li>';

    const ev = await (await fetch("/api/alerts/events?limit=20")).json();
    const el = $("#event-list");
    el.innerHTML = ev.events.length
      ? ev.events.map((e) =>
          `<li><strong>${e.base}</strong> ${METRIC_LABELS[e.metric] || e.metric} ${e.op} ${e.threshold}
           <span class="muted">= ${e.value} · ${new Date(e.ts).toLocaleString()}</span></li>`).join("")
      : '<li class="muted">None yet — triggers appear when a rule fires.</li>';
  } catch (e) { /* alerts are optional; ignore load errors */ }
}

async function addRule(e) {
  e.preventDefault();
  const body = {
    name: $("#rule-name").value,
    metric: $("#rule-metric").value,
    op: $("#rule-op").value,
    threshold: parseFloat($("#rule-threshold").value),
  };
  const res = await fetch("/api/alerts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) { $("#rule-name").value = ""; $("#rule-threshold").value = ""; loadAlerts(); }
  else {
    const err = await res.json().catch(() => ({}));
    alert(err.error || err.detail || "Failed to add rule");
  }
}

function wire() {
  $("#refresh").addEventListener("click", load);
  $("#rule-form").addEventListener("submit", addRule);
  $("#rule-list").addEventListener("click", async (e) => {
    const b = e.target.closest(".del-rule");
    if (b) { await fetch(`/api/alerts/${b.dataset.id}`, { method: "DELETE" }); loadAlerts(); }
  });
  $("#search").addEventListener("input", (e) => {
    state.query = e.target.value.trim();
    renderRows();
  });
  $("#min-volume").addEventListener("change", load);
  $("#limit").addEventListener("change", load);
  $("#perps-only").addEventListener("change", renderRows);
  $("#rows").addEventListener("click", (e) => {
    const tr = e.target.closest("tr.data-row");
    if (tr) toggleDetail(tr);
  });
  $("#rows").addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const tr = e.target.closest("tr.data-row");
    if (tr) { e.preventDefault(); toggleDetail(tr); }
  });
  // Sorting is scoped to the scanner grid; the cross-exchange table is static.
  document.querySelectorAll("#grid thead th[data-k]").forEach((th) => {
    th.addEventListener("click", () => {
      const k = th.dataset.k;
      if (state.sortKey === k) state.sortDir *= -1;
      else { state.sortKey = k; state.sortDir = k === "base" ? 1 : -1; }
      renderRows();
    });
  });
  load();
  loadPlan();
  loadPricing();
  loadAlerts();
  setInterval(load, 60000); // auto-refresh every 60s (loadCross piggybacks)
  setInterval(loadAlerts, 60000);
}

document.addEventListener("DOMContentLoaded", wire);
