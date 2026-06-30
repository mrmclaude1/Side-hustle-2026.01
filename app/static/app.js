"use strict";

const state = {
  rows: [],
  sortKey: "radar_score",
  sortDir: -1, // -1 desc, 1 asc
};

const $ = (s) => document.querySelector(s);

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
  const dp = n >= 100 ? 2 : n >= 1 ? 3 : 6;
  return n.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

function signedClass(v) {
  if (v === null || v === undefined) return "";
  return Number(v) > 0 ? "pos" : Number(v) < 0 ? "neg" : "";
}

function scoreColor(s) {
  // 0 -> grey, 100 -> accent
  const t = Math.max(0, Math.min(1, s / 100));
  const r = Math.round(27 + t * (77 - 27));
  const g = Math.round(34 + t * (163 - 34));
  const b = Math.round(48 + t * (255 - 48));
  return `rgb(${r},${g},${b})`;
}

function renderSummary(s, meta) {
  const cards = [
    ["Assets scanned", s.assets],
    ["Breadth", s.breadth_pct === null ? "—" : s.breadth_pct + "% ↑"],
    ["Advancers / Decliners", `${s.advancers} / ${s.decliners}`],
    ["Avg 24h change", s.avg_change_pct === null ? "—" : fmtNum(s.avg_change_pct, { pct: true, sign: true })],
    ["Avg perp basis", s.avg_basis_bps === null ? "—" : fmtNum(s.avg_basis_bps) + " bps"],
    ["Total volume", "$" + fmtCompact(s.total_volume_usd)],
  ];
  $("#summary").innerHTML = cards
    .map(([k, v]) => `<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`)
    .join("");

  const pill = $("#source-pill");
  pill.textContent = meta.data_source === "live" ? "● LIVE" : "● DEMO SNAPSHOT";
  pill.className = "pill " + (meta.data_source === "live" ? "live" : "fixture");
}

function renderRows() {
  let rows = state.rows.slice();
  if ($("#perps-only").checked) rows = rows.filter((r) => r.has_perp);

  const k = state.sortKey;
  rows.sort((a, b) => {
    const av = a[k], bv = b[k];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    if (av < bv) return -1 * state.sortDir;
    if (av > bv) return 1 * state.sortDir;
    return 0;
  });

  $("#rows").innerHTML = rows
    .map((r) => {
      const badge = r.has_perp ? '<span class="badge">PERP</span>' : "";
      return `<tr>
        <td class="num"><span class="score" style="color:${scoreColor(r.radar_score)}">${r.radar_score.toFixed(1)}</span></td>
        <td><span class="asset">${r.base}</span>${badge}</td>
        <td class="num">${fmtPrice(r.price)}</td>
        <td class="num ${signedClass(r.change_pct)}">${fmtNum(r.change_pct, { pct: true, sign: true })}</td>
        <td class="num ${signedClass(r.basis_bps)}">${fmtNum(r.basis_bps, { dp: 1 })}</td>
        <td class="num">${fmtNum(r.range_pct, { dp: 1 })}</td>
        <td class="num">${fmtNum(r.spread_bps, { dp: 1 })}</td>
        <td class="num">${fmtCompact(r.open_interest)}</td>
        <td class="num">$${fmtCompact(r.volume_usd)}</td>
      </tr>`;
    })
    .join("");

  document.querySelectorAll("thead th").forEach((th) => {
    th.classList.toggle("sorted", th.dataset.k === state.sortKey);
  });
}

async function load() {
  const minVol = $("#min-volume").value || 0;
  const limit = $("#limit").value || 50;
  $("#refresh").disabled = true;
  try {
    const res = await fetch(`/api/scan?min_volume_usd=${minVol}&limit=${limit}`);
    const data = await res.json();
    state.rows = data.assets;
    renderSummary(data.summary, data.meta);
    renderRows();
    const age = data.meta.cache_age_s ? ` · cached ${data.meta.cache_age_s}s` : "";
    $("#updated").textContent = `Updated ${new Date().toLocaleTimeString()}${age}`;
  } catch (e) {
    $("#updated").textContent = "Failed to load data.";
  } finally {
    $("#refresh").disabled = false;
  }
}

function wire() {
  $("#refresh").addEventListener("click", load);
  $("#min-volume").addEventListener("change", load);
  $("#limit").addEventListener("change", load);
  $("#perps-only").addEventListener("change", renderRows);
  document.querySelectorAll("thead th").forEach((th) => {
    th.addEventListener("click", () => {
      const k = th.dataset.k;
      if (state.sortKey === k) state.sortDir *= -1;
      else { state.sortKey = k; state.sortDir = k === "base" ? 1 : -1; }
      renderRows();
    });
  });
  load();
  setInterval(load, 60000); // auto-refresh every 60s
}

document.addEventListener("DOMContentLoaded", wire);
