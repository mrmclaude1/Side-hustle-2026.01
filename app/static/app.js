"use strict";

const state = {
  rows: [],
  sortKey: "radar_score",
  sortDir: -1, // -1 desc, 1 asc
  query: "",
  loaded: false,
  loadSeq: 0,
  plan: "free",
  bestArb: null,
};
const detailCache = new Map(); // base -> rendered detail HTML

const $ = (s) => document.querySelector(s);

// Escape every API-derived string before innerHTML interpolation.
const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const KEY_STORAGE = "basispulse_key";

// All API calls go through here so a saved key upgrades the whole dashboard.
function apiFetch(url, opts = {}) {
  const key = localStorage.getItem(KEY_STORAGE);
  if (key) opts.headers = Object.assign({}, opts.headers, { "X-API-Key": key });
  return fetch(url, opts);
}

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
const METRIC_HINTS = {
  radar_score: "e.g. 80 (score 0–100)",
  score_delta: "e.g. 5 (score points)",
  basis_bps: "e.g. -50 (bps)",
  abs_basis_bps: "e.g. 50 (bps)",
  change_pct: "e.g. -10 (%)",
  abs_change_pct: "e.g. 10 (%)",
  range_pct: "e.g. 20 (%)",
  volume_usd: "e.g. 1000000 (USD)",
};
// Plain-English explainer + a sensible starting threshold for each metric,
// shown under the alert form as the user picks a metric.
const METRIC_INFO = {
  radar_score:
    "How unusual an asset looks right now, 0–100. Typical alert: ≥ 80 catches only the hottest handful; ≥ 60 is a looser net.",
  score_delta:
    "How much the score changed since the previous snapshot — a rising score is something heating up. Typical alert: ≥ 10.",
  basis_bps:
    "Perp price minus spot price, in basis points (1 bp = 0.01%). Positive = longs paying a premium (crowded long); negative = perp at a discount (crowded short). Typical alerts: ≤ −50 or ≥ 50.",
  abs_basis_bps:
    "Size of the perp/spot gap in either direction — stretched positioning regardless of side. Typical alert: ≥ 50.",
  change_pct:
    "24-hour price change in percent, with direction. Typical alerts: ≤ −10 (dumping) or ≥ 10 (pumping).",
  abs_change_pct:
    "Size of the 24-hour move in either direction — big movers, up or down. Typical alert: ≥ 10.",
  range_pct:
    "Today's high-to-low range as % of price — a volatility gauge. Typical alert: ≥ 20 (a wild day).",
  volume_usd:
    "24-hour traded volume in US dollars. Typical alert: ≥ 1000000 to only watch liquid markets ($1M+).",
};

const DASH = '<span class="dim">—</span>';

function fmtNum(v, opts = {}) {
  if (v === null || v === undefined) return DASH;
  const { dp = 2, pct = false, sign = false } = opts;
  const n = Number(v);
  let s = n.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
  if (sign && n > 0) s = "+" + s;
  return pct ? s + "%" : s;
}

function fmtCompact(v) {
  if (v === null || v === undefined) return DASH;
  const n = Number(v);
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n.toFixed(0);
}

function fmtMoney(v) {
  return v === null || v === undefined ? DASH : "$" + fmtCompact(v);
}

function fmtPrice(v) {
  if (v === null || v === undefined) return DASH;
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
  // Legible grey floor -> accent; magnitude is also carried by bar width/text.
  const t = Math.max(0, Math.min(1, s / 100));
  const r = Math.round(139 + t * (57 - 139));
  const g = Math.round(151 + t * (135 - 151));
  const b = Math.round(168 + t * (229 - 168));
  return `rgb(${r},${g},${b})`;
}

function scoreGauge(score) {
  return `<span class="score"><i class="score-fill" style="width:${Math.max(0, Math.min(100, score))}%"></i><b>${score.toFixed(1)}</b></span>`;
}

function renderSummary(s, meta, topAsset) {
  const breadth = s.breadth_pct;
  const cards = [];
  if (topAsset) {
    cards.push(["Top signal",
      `<a href="#scan" class="plain locate" data-base="${esc(topAsset.base)}">${esc(topAsset.base)} · ${topAsset.radar_score.toFixed(1)}</a>`, ""]);
  }
  if (state.bestArb) {
    cards.push(["Best arb edge",
      `<a href="#cross" class="plain">${esc(state.bestArb.base)} · ${state.bestArb.edge_bps.toFixed(1)} bps</a>`, ""]);
  }
  cards.push(
    ["Assets scanned", s.assets, ""],
    ["Breadth", breadth === null ? DASH : `${breadth}% advancing`, breadth === null ? "" : breadth >= 50 ? "pos" : "neg"],
    ["Advancers / Decliners",
      `${s.advancers} / ${s.decliners}` +
      `<div class="split"><i style="flex:${s.advancers || 0}"></i><i class="d" style="flex:${s.decliners || 0}"></i></div>`, ""],
    ["Avg 24h change", s.avg_change_pct === null ? DASH : fmtNum(s.avg_change_pct, { pct: true, sign: true }), signedClass(s.avg_change_pct)],
    ["Avg perp basis", s.avg_basis_bps === null ? DASH : fmtNum(s.avg_basis_bps, { sign: true }) + " bps", signedClass(s.avg_basis_bps)],
    ["Total volume", fmtMoney(s.total_volume_usd), ""],
  );
  $("#summary").innerHTML = cards.map(([k, v, cls]) =>
    `<div class="card"><div class="k">${k}</div><div class="v ${cls}">${v}</div></div>`
  ).join("");

  const pill = $("#source-pill");
  pill.textContent = meta.data_source === "live" ? "● LIVE" : "● DEMO SNAPSHOT";
  pill.className = "pill " + (meta.data_source === "live" ? "live" : "fixture");
}

function stateRow(msg, colspan = 10, cls = "") {
  return `<tr class="state-row ${cls}"><td colspan="${colspan}">${msg}</td></tr>`;
}

function renderRows() {
  // Preserve an open sparkline and keyboard focus across rebuilds.
  const openBase = document.querySelector(".detail-row")?.previousElementSibling?.dataset?.base;
  const focusBase = document.activeElement?.closest?.("tr.data-row")?.dataset?.base;

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
    let msg = "Loading market data…";
    if (state.loaded) {
      msg = state.rows.length
        ? "No assets match your filters."
        : "No assets above this volume floor — try lowering Min 24h volume.";
    }
    $("#rows").innerHTML = stateRow(msg);
  } else {
    $("#rows").innerHTML = rows
      .map((r) => {
        const base = esc(r.base);
        const badge = r.has_perp ? '<span class="badge">PERP</span>' : "";
        const d = r.score_delta;
        const delta =
          d === null || d === undefined
            ? DASH
            : Math.abs(d) < 0.05
              ? '<span class="delta-flat">·</span>'
              : `<span class="${signedClass(d)}">${d > 0 ? "▲" : "▼"} ${Math.abs(d).toFixed(1)}</span>`;
        return `<tr data-base="${base}" class="data-row" tabindex="0" role="button" aria-expanded="false" aria-label="${base}: show history">
          <td><span class="asset">${base}</span>${badge}</td>
          <td class="num">${scoreGauge(r.radar_score)}</td>
          <td class="num">${delta}</td>
          <td class="num">${fmtPrice(r.price)}</td>
          <td class="num ${signedClass(r.change_pct)}">${fmtNum(r.change_pct, { pct: true, sign: true })}</td>
          <td class="num ${signedClass(r.basis_bps)}">${fmtNum(r.basis_bps, { dp: 1, sign: true })}</td>
          <td class="num">${fmtNum(r.range_pct, { dp: 1, pct: true })}</td>
          <td class="num">${fmtNum(r.spread_bps, { dp: 1 })}</td>
          <td class="num">${fmtCompact(r.open_interest)}</td>
          <td class="num">${fmtMoney(r.volume_usd)}</td>
        </tr>`;
      })
      .join("");
  }

  document.querySelectorAll("#grid thead th[data-k]").forEach((th) => {
    const sorted = th.dataset.k === state.sortKey;
    th.classList.toggle("sorted", sorted);
    th.classList.toggle("asc", sorted && state.sortDir === 1);
    th.setAttribute("aria-sort", sorted ? (state.sortDir === 1 ? "ascending" : "descending") : "none");
  });

  if (openBase) {
    const tr = document.querySelector(`tr.data-row[data-base="${CSS.escape(openBase)}"]`);
    if (tr) toggleDetail(tr, { restore: true });
  }
  if (focusBase) {
    const tr = document.querySelector(`tr.data-row[data-base="${CSS.escape(focusBase)}"]`);
    if (tr) tr.focus({ preventScroll: true });
  }
}

async function load() {
  const seq = ++state.loadSeq;
  const minVol = $("#min-volume").value || 0;
  const limit = $("#limit").value || 50;
  const btn = $("#refresh");
  btn.disabled = true;
  const btnLabel = btn.textContent;
  btn.textContent = "↻ Refreshing…";
  try {
    const res = await apiFetch(`/api/scan?min_volume_usd=${minVol}&limit=${limit}`);
    if (seq !== state.loadSeq) return; // a newer request superseded this one
    if (!res.ok) throw new Error(res.status === 429 ? "rate" : `scan ${res.status}`);
    const data = await res.json();
    if (seq !== state.loadSeq) return;
    if (!Array.isArray(data.assets)) throw new Error("bad payload");
    state.rows = data.assets;
    state.loaded = true;
    detailCache.clear(); // fresh scan -> stale sparklines
    renderSummary(data.summary, data.meta, data.assets[0]);
    renderRows();
    let updated = `Updated ${new Date().toLocaleTimeString()}`;
    if (data.meta.cache_age_s) updated += ` · cached ${data.meta.cache_age_s}s`;
    if (data.meta.limit_capped_to) {
      updated += ` · capped at ${data.meta.limit_capped_to} on ${(data.meta.plan || "free").toUpperCase()}`;
    }
    $("#updated").textContent = updated;
  } catch (e) {
    if (seq !== state.loadSeq) return;
    const msg = e.message === "rate"
      ? "Rate limited — auto-retrying within 60s."
      : "Couldn’t load market data — check your connection and hit ↻ Refresh.";
    if (!state.loaded) $("#rows").innerHTML = stateRow(msg, 10, "error");
    $("#updated").textContent = msg;
  } finally {
    if (seq === state.loadSeq) {
      btn.disabled = false;
      btn.textContent = btnLabel;
    }
    loadCross(); // cross section refreshes regardless of scan outcome
  }
}

// --- Detail row: score / price / basis mini-charts ------------------------

function humanizeSpan(ms) {
  const m = ms / 60000;
  if (m < 90) return `${Math.max(1, Math.round(m))}m`;
  const h = m / 60;
  if (h < 48) return `${Math.round(h)}h`;
  return `${Math.round(h / 24)}d`;
}

function miniChart(points, key, label, color, lastFmt, zeroLine = false) {
  const vals = points.map((p) => p[key]).filter((v) => v !== null && v !== undefined);
  if (vals.length < 2) return "";
  const w = 180, h = 40;
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const step = w / (vals.length - 1);
  const y = (v) => h - 4 - ((v - min) / span) * (h - 8);
  const coords = vals.map((v, i) => [i * step, y(v)]);
  const pts = coords.map(([x, yy]) => `${x.toFixed(1)},${yy.toFixed(1)}`).join(" ");
  const [lx, ly] = coords[coords.length - 1];
  const zero = zeroLine && min < 0 && max > 0
    ? `<line x1="0" x2="${w}" y1="${y(0).toFixed(1)}" y2="${y(0).toFixed(1)}" stroke="var(--muted)" stroke-width="1" stroke-dasharray="3 3" opacity=".6"/>`
    : "";
  return `<div class="mini-chart">
    <div class="mc-label">${label} <b>${lastFmt(vals[vals.length - 1])}</b></div>
    <svg width="${w}" height="${h}" class="spark" role="img" aria-label="${label} trend">
      <polygon points="0,${h} ${pts} ${w},${h}" fill="${color}" fill-opacity=".14"/>
      ${zero}
      <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5"/>
      <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="2.5" fill="${color}"/>
    </svg>
  </div>`;
}

function detailHTML(base, points) {
  if (!points || points.length < 2) {
    return `<strong>${esc(base)}</strong> &nbsp; <span class="muted">Not enough history yet — snapshots build over time.</span>`;
  }
  const lastBasis = [...points].reverse().find((p) => p.basis_bps !== null && p.basis_bps !== undefined);
  const basisColor = lastBasis && lastBasis.basis_bps < 0 ? "#e66767" : "#199e70";
  const charts = [
    miniChart(points, "radar_score", "Score", "#3987e5", (v) => v.toFixed(1)),
    miniChart(points, "price", "Price", "#8b97a8", (v) => fmtPrice(v)),
    miniChart(points, "basis_bps", "Basis", basisColor, (v) => (v > 0 ? "+" : "") + v.toFixed(1) + " bps", true),
  ].filter(Boolean).join("");
  let span = "";
  const t0 = Date.parse(points[0].ts), t1 = Date.parse(points[points.length - 1].ts);
  if (!isNaN(t0) && !isNaN(t1) && t1 > t0) span = ` · last ${humanizeSpan(t1 - t0)}`;
  const lastScore = points[points.length - 1].radar_score;
  const alertLink = lastScore !== null && lastScore !== undefined
    ? ` · <a href="#alerts" class="mk-alert" data-base="${esc(base)}" data-score="${Math.round(lastScore)}">+ Alert when score ≥ ${Math.round(lastScore)}</a>`
    : "";
  return `<strong>${esc(base)}</strong>
    <div class="detail-charts">${charts}</div>
    <div class="muted">${points.length} snapshots${span}${alertLink}</div>`;
}

async function toggleDetail(tr, { restore = false } = {}) {
  const base = tr.dataset.base;
  const next = tr.nextElementSibling;
  if (!restore && next && next.classList.contains("detail-row")) {
    next.remove();
    tr.classList.remove("open");
    tr.setAttribute("aria-expanded", "false");
    return;
  }
  document.querySelectorAll(".detail-row").forEach((el) => el.remove());
  document.querySelectorAll("tr.data-row.open").forEach((el) => {
    el.classList.remove("open");
    el.setAttribute("aria-expanded", "false");
  });
  tr.classList.add("open");
  tr.setAttribute("aria-expanded", "true");
  const dr = document.createElement("tr");
  dr.className = "detail-row";
  const cached = detailCache.get(base);
  dr.innerHTML = `<td colspan="10" class="detail">${cached || `Loading ${esc(base)} history…`}</td>`;
  tr.after(dr);
  if (cached) return; // no flash, no refetch — cache invalidates on fresh scans
  try {
    const res = await apiFetch(`/api/history/${encodeURIComponent(base)}`);
    const data = await res.json();
    const html = detailHTML(base, data.points);
    detailCache.set(base, html);
    dr.querySelector(".detail").innerHTML = html;
  } catch (e) {
    dr.querySelector(".detail").textContent = "Failed to load history.";
  }
}

// --- Plan / pricing / key -------------------------------------------------

async function loadPlan() {
  try {
    const res = await apiFetch("/api/me");
    if (res.status === 401) {
      localStorage.removeItem(KEY_STORAGE);
      setKeyStatus("That key was rejected — cleared it.", true);
      return;
    }
    const me = await res.json();
    state.plan = me.plan;
    const pill = $("#plan-pill");
    pill.textContent = "plan: " + me.plan.toUpperCase();
    pill.className = "pill " + (me.plan === "pro" ? "live" : "");
    if (me.authenticated) setKeyStatus(`Key active — ${me.plan.toUpperCase()} plan.`);
  } catch (e) { /* optional */ }
}

function setKeyStatus(msg, isError = false) {
  const el = $("#key-status");
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle("neg", isError);
  const clear = $("#key-clear");
  if (clear) clear.hidden = !localStorage.getItem(KEY_STORAGE);
}

async function loadPricing() {
  try {
    const data = await (await apiFetch("/api/pricing")).json();
    const url = data.checkout_url || "";
    const grid = $("#pricing-grid");
    grid.innerHTML = ["free", "pro"]
      .filter((n) => data.plans[n])
      .map((name) => {
        const p = data.plans[name];
        const isPro = name === "pro";
        const feats = p.features.map((f) => `<li>${FEATURE_LABELS[f] || esc(f)}</li>`).join("");
        const price = isPro
          ? `<div class="price">$${esc(p.price_usd_month || "—")}<span>/mo</span></div>`
          : `<div class="price">$0</div>`;
        const current = state.plan === name ? '<span class="pop current">CURRENT PLAN</span>' : "";
        const popular = isPro && state.plan !== "pro" ? '<span class="pop">MOST POPULAR</span>' : "";
        const cta = isPro && state.plan !== "pro"
          ? (url
              ? `<a class="btn-cta primary" href="${esc(url)}" target="_blank" rel="noopener">Get Pro</a>`
              : `<span class="btn-cta ghost" title="Pro checkout opens soon">Coming soon</span>`)
          : "";
        return `<div class="plan-card ${isPro ? "pro-card" : ""}">
          ${current || popular}
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

// --- Cross-exchange --------------------------------------------------------

async function loadCross() {
  try {
    const res = await apiFetch("/api/cross?limit=25");
    if (!res.ok) throw new Error("cross " + res.status);
    const data = await res.json();
    const s = data.summary;
    $("#cross-venues").textContent =
      s.venues.length ? s.venues.join(", ") : "multiple venues";
    $("#cross-rows").innerHTML = data.assets.length
      ? data.assets
          .map((a) => {
            const arb = a.arb;
            const edge = arb ? arb.edge_bps : null;
            const edgeCls = edge !== null && edge > 0 ? "pos" : "muted";
            const dir = arb ? `${esc(arb.buy_at)} → ${esc(arb.sell_at)}` : DASH;
            return `<tr>
              <td class="num"><span class="spread-pill" style="color:${scoreColor(Math.min(100, (a.price_spread_bps || 0) * 4))}">${fmtNum(a.price_spread_bps, { dp: 1 })}</span></td>
              <td><span class="asset">${esc(a.base)}</span></td>
              <td class="muted">${a.venues.map(esc).join(" · ")}</td>
              <td class="num">${fmtPrice(a.reference_price)}</td>
              <td class="num ${edgeCls}">${edge === null ? DASH : fmtNum(edge, { dp: 1, sign: true })}</td>
              <td class="muted">${dir}</td>
              <td class="num">${fmtMoney(a.total_volume_usd)}</td>
            </tr>`;
          })
          .join("")
      : stateRow("No cross-venue dislocations right now.", 7);

    const best = data.assets
      .filter((a) => a.arb && a.arb.edge_bps > 0)
      .sort((a, b) => b.arb.edge_bps - a.arb.edge_bps)[0];
    state.bestArb = best ? { base: best.base, edge_bps: best.arb.edge_bps } : null;
    // Patch the summary card in place — or insert it on first paint, when
    // renderSummary ran before this data arrived.
    if (state.bestArb) {
      const cards = document.querySelectorAll("#summary .card");
      let arbCard = [...cards].find((c) => c.querySelector(".k")?.textContent === "Best arb edge");
      if (!arbCard && cards.length) {
        arbCard = document.createElement("div");
        arbCard.className = "card";
        arbCard.innerHTML = '<div class="k">Best arb edge</div><div class="v"></div>';
        cards[0].after(arbCard);
      }
      if (arbCard) {
        arbCard.querySelector(".v").innerHTML =
          `<a href="#cross" class="plain">${esc(state.bestArb.base)} · ${state.bestArb.edge_bps.toFixed(1)} bps</a>`;
      }
    }
  } catch (e) {
    if (!$("#cross-rows").children.length || $("#cross-rows").querySelector(".state-row")) {
      $("#cross-rows").innerHTML = stateRow("Couldn’t load cross-exchange data.", 7, "error");
    }
  }
}

// --- Alerts -----------------------------------------------------------------

function showRuleError(msg, isHTML = false) {
  const el = $("#rule-error");
  if (!el) return;
  if (isHTML) el.innerHTML = msg; else el.textContent = msg;
  el.hidden = !msg;
}

async function loadAlerts() {
  try {
    const meta = await (await apiFetch("/api/alerts")).json();
    const mSel = $("#rule-metric"), oSel = $("#rule-op");
    if (mSel && !mSel.options.length) {
      mSel.innerHTML = meta.metrics
        .map((m) => `<option value="${esc(m)}" title="${esc(METRIC_INFO[m] || "")}">${METRIC_LABELS[m] || esc(m)}</option>`).join("");
      oSel.innerHTML = meta.ops.map((o) => `<option>${esc(o)}</option>`).join("");
      updateThresholdHint();
    }
    const rl = $("#rule-list");
    rl.innerHTML = meta.rules.length
      ? meta.rules.map((r) =>
          `<li>${r.enabled ? "" : '<span class="badge">OFF</span> '}<span><strong>${esc(r.name)}</strong>: ${METRIC_LABELS[r.metric] || esc(r.metric)} ${esc(r.op)} ${r.threshold}</span>
           <button class="link del-rule" data-id="${r.id}" aria-label="Delete rule">✕</button></li>`).join("")
      : '<li class="muted">None yet — add your first rule above.</li>';

    const ev = await (await apiFetch("/api/alerts/events?limit=20")).json();
    const el = $("#event-list");
    el.innerHTML = ev.events.length
      ? ev.events.map((e) =>
          `<li><a href="#scan" class="locate asset" data-base="${esc(e.base)}">${esc(e.base)}</a> ${METRIC_LABELS[e.metric] || esc(e.metric)} ${esc(e.op)} ${e.threshold}
           <span class="muted">= ${e.value} · ${new Date(e.ts).toLocaleString()}</span></li>`).join("")
      : '<li class="muted">None yet — triggers appear when a rule fires.</li>';
  } catch (e) { /* alerts are optional; ignore load errors */ }
}

function updateThresholdHint() {
  const m = $("#rule-metric")?.value;
  const t = $("#rule-threshold");
  if (m && t) t.placeholder = METRIC_HINTS[m] || "Threshold";
  const help = $("#metric-help");
  if (m && help) help.textContent = METRIC_INFO[m] || "";
}

async function addRule(e) {
  e.preventDefault();
  showRuleError("");
  const body = {
    name: $("#rule-name").value,
    metric: $("#rule-metric").value,
    op: $("#rule-op").value,
    threshold: parseFloat($("#rule-threshold").value),
  };
  try {
    const res = await apiFetch("/api/alerts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      $("#rule-name").value = "";
      $("#rule-threshold").value = "";
      loadAlerts();
      return;
    }
    const err = await res.json().catch(() => ({}));
    const msg = esc(err.error || err.detail || "Failed to add rule");
    if (res.status === 402) {
      showRuleError(`${msg} <a href="#pro">Upgrade to Pro →</a>`, true);
    } else {
      showRuleError(msg);
    }
  } catch (err) {
    showRuleError("Network error — rule not saved. Try again.");
  }
}

function locateAsset(base) {
  const search = $("#search");
  search.value = base;
  state.query = base;
  renderRows();
  document.querySelector("#scan")?.scrollIntoView();
  const tr = document.querySelector(`tr.data-row[data-base="${CSS.escape(base)}"]`);
  if (tr) {
    tr.classList.add("flash");
    setTimeout(() => tr.classList.remove("flash"), 1600);
  }
}

function saveKey(e) {
  e.preventDefault();
  const input = $("#api-key");
  const key = input.value.trim();
  if (!key) return;
  localStorage.setItem(KEY_STORAGE, key);
  input.value = "";
  setKeyStatus("Checking key…");
  loadPlan().then(loadPricing).then(load);
}

function clearKey() {
  localStorage.removeItem(KEY_STORAGE);
  state.plan = "free";
  setKeyStatus("Key cleared — back to the free plan.");
  loadPlan().then(loadPricing).then(load);
}

// --- "Start here" tour -------------------------------------------------------

const TOUR_KEY = "basispulse_tour_seen";

function openTour() {
  const t = $("#tour");
  if (!t) return;
  t.hidden = false;
  $("#tour-close")?.focus();
}

function closeTour() {
  const t = $("#tour");
  if (!t || t.hidden) return;
  t.hidden = true;
  localStorage.setItem(TOUR_KEY, "1");
  $("#help")?.focus();
}

function setHeaderVar() {
  const h = document.querySelector("header.app-header");
  if (!h) return;
  const sticky = getComputedStyle(h).position === "sticky";
  document.documentElement.style.setProperty("--header-h", (sticky ? h.offsetHeight : 0) + "px");
}

function watchSections() {
  const links = [...document.querySelectorAll(".section-nav a")];
  if (!("IntersectionObserver" in window) || !links.length) return;
  const byId = Object.fromEntries(links.map((a) => [a.getAttribute("href").slice(1), a]));
  const obs = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (en.isIntersecting) {
        links.forEach((a) => a.classList.remove("active"));
        byId[en.target.id]?.classList.add("active");
      }
    });
  }, { rootMargin: "-20% 0px -70% 0px" });
  ["scan", "cross", "alerts", "pro"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) obs.observe(el);
  });
}

function wire() {
  $("#refresh").addEventListener("click", load);
  $("#rule-form").addEventListener("submit", addRule);
  $("#rule-form").addEventListener("input", () => showRuleError(""));
  $("#rule-metric").addEventListener("change", updateThresholdHint);
  // Preset chips prefill the form (teaching it), rather than adding blindly.
  document.querySelectorAll("button.preset").forEach((b) => {
    b.addEventListener("click", () => {
      $("#rule-name").value = b.dataset.name;
      $("#rule-metric").value = b.dataset.metric;
      $("#rule-op").value = b.dataset.op;
      $("#rule-threshold").value = b.dataset.threshold;
      updateThresholdHint();
      $("#rule-form button[type=submit]").focus();
    });
  });
  const keyForm = $("#key-form");
  if (keyForm) {
    keyForm.addEventListener("submit", saveKey);
    $("#key-clear").addEventListener("click", clearKey);
  }
  $("#rule-list").addEventListener("click", async (e) => {
    const b = e.target.closest(".del-rule");
    if (!b) return;
    if (!b.classList.contains("confirm")) {
      // Two-step delete: first click arms, second click within 3s deletes.
      b.classList.add("confirm");
      b.textContent = "delete?";
      setTimeout(() => { b.classList.remove("confirm"); b.textContent = "✕"; }, 3000);
      return;
    }
    try {
      const res = await apiFetch(`/api/alerts/${b.dataset.id}`, { method: "DELETE" });
      if (!res.ok) showRuleError("Couldn’t delete that rule — try again.");
    } catch (err) {
      showRuleError("Network error — rule not deleted.");
    }
    loadAlerts();
  });
  document.body.addEventListener("click", (e) => {
    const loc = e.target.closest("a.locate");
    if (loc) { e.preventDefault(); locateAsset(loc.dataset.base); return; }
    const mk = e.target.closest("a.mk-alert");
    if (mk) {
      $("#rule-name").value = `${mk.dataset.base} watch`;
      $("#rule-metric").value = "radar_score";
      $("#rule-op").value = ">=";
      $("#rule-threshold").value = mk.dataset.score;
      updateThresholdHint();
      setTimeout(() => $("#rule-threshold").focus(), 300);
    }
  });
  $("#search").addEventListener("input", (e) => {
    state.query = e.target.value.trim();
    renderRows();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeTour(); return; }
    const tourOpen = $("#tour") && !$("#tour").hidden;
    if (e.key === "/" && !tourOpen &&
        !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) {
      e.preventDefault();
      $("#search").focus();
    }
  });
  $("#help").addEventListener("click", openTour);
  $("#tour-close").addEventListener("click", closeTour);
  $("#tour").addEventListener("click", (e) => { if (e.target === $("#tour")) closeTour(); });
  if (!localStorage.getItem(TOUR_KEY)) openTour(); // first visit
  $("#min-volume").addEventListener("change", load);
  $("#limit").addEventListener("change", load);
  $("#perps-only").addEventListener("change", renderRows);
  $("#rows").addEventListener("click", (e) => {
    if (e.target.closest("a")) return; // links inside detail rows
    const tr = e.target.closest("tr.data-row");
    if (tr) toggleDetail(tr);
  });
  $("#rows").addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const tr = e.target.closest("tr.data-row");
    if (tr) { e.preventDefault(); toggleDetail(tr); }
  });
  // Keyboard-sortable headers, scoped to the scanner grid.
  document.querySelectorAll("#grid thead th[data-k]").forEach((th) => {
    th.setAttribute("tabindex", "0");
    const sort = () => {
      const k = th.dataset.k;
      if (state.sortKey === k) state.sortDir *= -1;
      else { state.sortKey = k; state.sortDir = k === "base" ? 1 : -1; }
      renderRows();
    };
    th.addEventListener("click", sort);
    th.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); }
    });
  });
  setHeaderVar();
  window.addEventListener("resize", setHeaderVar);
  watchSections();
  load();
  loadPlan().then(loadPricing);
  loadAlerts();
  setInterval(load, 60000); // auto-refresh every 60s (loadCross piggybacks)
  setInterval(loadAlerts, 60000);
}

document.addEventListener("DOMContentLoaded", wire);
