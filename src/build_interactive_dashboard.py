"""
build_interactive_dashboard.py
-------------------------------
Owner: saahilkhan

Builds ONE self-contained interactive_dashboard.html with live toggle
controls (filter by device / channel, switch funnel + RFM metrics). All the
data is pre-computed here and embedded as JSON; the charts are rendered in
plain JavaScript so the toggles recompute everything instantly — no server,
no libraries, no install. Open the file in any browser.
"""
import json
import sqlite3
import pandas as pd

con = sqlite3.connect(":memory:")
for n in ["users", "events", "orders"]:
    pd.read_csv(f"data/{n}.csv").to_sql(n, con, index=False, if_exists="replace")

STAGE_ORDER = {"product_view": 1, "add_to_cart": 2,
               "begin_checkout": 3, "purchase": 4}

# ---- per-user furthest funnel stage, with their device + channel ----
ev = pd.read_sql_query("SELECT user_id, event_name FROM events", con)
ev["stage"] = ev["event_name"].map(STAGE_ORDER)
max_stage = ev.groupby("user_id")["stage"].max().rename("max_stage")
u = pd.read_sql_query(
    "SELECT user_id, acquisition_channel AS channel, device FROM users", con)
u = u.merge(max_stage, on="user_id", how="left").fillna({"max_stage": 0})
u["max_stage"] = u["max_stage"].astype(int)

# user matrix: counts by device x channel x max_stage  (drives funnel + conversion)
user_matrix = (u.groupby(["device", "channel", "max_stage"])
                 .size().reset_index(name="count")
                 .to_dict(orient="records"))

# revenue matrix: revenue + orders by device x channel  (drives revenue KPIs)
rev = pd.read_sql_query("""
    SELECT us.device, us.acquisition_channel AS channel,
           o.revenue
    FROM orders o JOIN users us ON o.user_id = us.user_id
""", con)
rev_matrix = (rev.groupby(["device", "channel"])
                .agg(revenue=("revenue", "sum"), orders=("revenue", "count"))
                .reset_index().round(2).to_dict(orient="records"))

# ---- RFM summary (global) ----
rfm = pd.read_sql_query("""
    WITH b AS (
      SELECT user_id, JULIANDAY('2025-06-30')-JULIANDAY(MAX(order_time)) rec,
             COUNT(*) freq, SUM(revenue) mon
      FROM orders GROUP BY user_id),
    s AS (
      SELECT user_id, 6-NTILE(5) OVER (ORDER BY rec) r,
             NTILE(5) OVER (ORDER BY freq) f, mon
      FROM b)
    SELECT CASE
        WHEN r>=4 AND f>=4 THEN 'Champions'
        WHEN r>=3 AND f>=3 THEN 'Loyal'
        WHEN r>=4 AND f<=2 THEN 'New / Promising'
        WHEN r<=2 AND f>=3 THEN 'At Risk'
        WHEN r<=2 AND f<=2 THEN 'Lost / Hibernating'
        ELSE 'Needs Attention' END AS segment,
      COUNT(*) customers, ROUND(SUM(mon),2) revenue
    FROM s GROUP BY segment
""", con)
rfm_data = rfm.sort_values("revenue", ascending=False).to_dict(orient="records")

# ---- cohort retention grid (global) ----
cohort = pd.read_sql_query("""
    WITH fp AS (SELECT user_id, MIN(strftime('%Y-%m', order_time)) cm
                FROM orders GROUP BY user_id),
    ac AS (SELECT DISTINCT user_id, strftime('%Y-%m', order_time) am
           FROM orders)
    SELECT fp.cm AS cohort_month,
      (CAST(strftime('%Y', ac.am||'-01') AS INT)*12
        + CAST(strftime('%m', ac.am||'-01') AS INT))
      -(CAST(strftime('%Y', fp.cm||'-01') AS INT)*12
        + CAST(strftime('%m', fp.cm||'-01') AS INT)) AS month_number,
      COUNT(DISTINCT ac.user_id) AS users
    FROM fp JOIN ac ON fp.user_id=ac.user_id
    GROUP BY fp.cm, month_number
""", con)
size = cohort[cohort.month_number == 0].set_index("cohort_month")["users"]
cohort["size"] = cohort["cohort_month"].map(size)
cohort["pct"] = (100 * cohort["users"] / cohort["size"]).round(1)
months = sorted(cohort["cohort_month"].unique())
max_n = int(cohort["month_number"].max())
grid = []
for m in months:
    row = {"cohort": m, "size": int(size[m]), "cells": []}
    sub = cohort[cohort.cohort_month == m].set_index("month_number")
    for n in range(max_n + 1):
        if n in sub.index:
            row["cells"].append({"pct": float(sub.loc[n, "pct"]),
                                 "users": int(sub.loc[n, "users"])})
        else:
            row["cells"].append(None)
    grid.append(row)

DATA = {
    "stages": ["product_view", "add_to_cart", "begin_checkout", "purchase"],
    "stageLabels": ["Product View", "Add to Cart", "Begin Checkout", "Purchase"],
    "devices": ["Mobile", "Desktop", "Tablet"],
    "channels": ["Organic", "Paid Search", "Social", "Email", "Referral"],
    "userMatrix": user_matrix,
    "revMatrix": rev_matrix,
    "rfm": rfm_data,
    "cohort": {"maxN": max_n, "grid": grid},
}

# =====================================================================
# HTML  (JSON injected via placeholder to avoid brace-escaping issues)
# =====================================================================
HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Commerce Intelligence — Funnel & Retention</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root{
    --ink:#0f172a; --sub:#64748b; --line:#e6e8ee; --panel:#ffffff;
    --bg:#f5f6f9; --accent:#4f46e5; --accent2:#818cf8; --soft:#eef2ff;
    --warn:#b45309; --warn-soft:#fff7ed; --good:#0f766e;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font-family:Inter,system-ui,sans-serif;line-height:1.5}
  .wrap{max-width:1120px;margin:0 auto;padding:28px 22px 70px}
  header{display:flex;justify-content:space-between;align-items:flex-end;
    border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:20px;
    flex-wrap:wrap;gap:10px}
  .brand{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:21px;
    letter-spacing:-.02em}
  .brand b{color:var(--accent)}
  .meta{font-size:12.5px;color:var(--sub)}

  /* ---- toggle controls ---- */
  .controls{display:flex;gap:22px;flex-wrap:wrap;align-items:flex-end;
    background:var(--panel);border:1px solid var(--line);border-radius:14px;
    padding:14px 16px;margin-bottom:22px}
  .ctrl label{display:block;font-size:11px;letter-spacing:.06em;
    text-transform:uppercase;color:var(--sub);margin-bottom:6px;font-weight:600}
  .pills{display:flex;gap:6px;flex-wrap:wrap}
  .pill{border:1px solid var(--line);background:#fff;color:var(--ink);
    font:inherit;font-size:13px;padding:6px 12px;border-radius:999px;
    cursor:pointer;transition:.15s}
  .pill:hover{border-color:var(--accent2)}
  .pill.active{background:var(--accent);border-color:var(--accent);color:#fff}
  .reset{margin-left:auto;align-self:center}
  .reset button{border:1px solid var(--line);background:#fff;border-radius:8px;
    padding:7px 12px;font:inherit;font-size:13px;cursor:pointer;color:var(--sub)}
  .reset button:hover{color:var(--ink);border-color:var(--sub)}

  /* ---- KPI cards ---- */
  .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:22px}
  .kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:14px 16px}
  .kpi .l{font-size:11px;color:var(--sub);text-transform:uppercase;
    letter-spacing:.06em}
  .kpi .v{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:26px;
    font-variant-numeric:tabular-nums;margin-top:2px}
  .kpi .s{font-size:12px;color:var(--sub)}

  /* ---- cards / layout ---- */
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;
    padding:16px 18px}
  .card.full{grid-column:1 / -1}
  .card h3{margin:0 0 4px;font-family:'Space Grotesk',sans-serif;font-size:15px;
    font-weight:600}
  .card .cap{font-size:12px;color:var(--sub);margin:0 0 14px}
  .head-row{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
  .mini-toggle{display:flex;gap:5px}
  .mini-toggle button{border:1px solid var(--line);background:#fff;font:inherit;
    font-size:12px;padding:4px 9px;border-radius:7px;cursor:pointer;color:var(--sub)}
  .mini-toggle button.active{background:var(--soft);border-color:var(--accent2);
    color:var(--accent)}

  /* ---- funnel bars ---- */
  .fbar{margin:0 0 12px}
  .fbar .top{display:flex;justify-content:space-between;font-size:13px;
    margin-bottom:4px}
  .fbar .name{font-weight:500}
  .fbar .track{height:26px;background:#f1f2f6;border-radius:7px;overflow:hidden}
  .fbar .fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));
    border-radius:7px;transition:width .5s cubic-bezier(.4,0,.2,1);min-width:2px}
  .fbar .step{color:var(--sub);font-variant-numeric:tabular-nums}
  .leak{background:var(--warn-soft);border-left:3px solid var(--warn);
    border-radius:8px;padding:9px 12px;font-size:13px;color:#7c4a12;margin-top:4px}

  /* ---- horizontal bars (conversion / rfm) ---- */
  .hbar{display:grid;grid-template-columns:120px 1fr auto;align-items:center;
    gap:10px;margin-bottom:9px;font-size:13px}
  .hbar .cat{color:var(--ink);white-space:nowrap;overflow:hidden;
    text-overflow:ellipsis}
  .hbar .track{height:18px;background:#f1f2f6;border-radius:6px;overflow:hidden}
  .hbar .fill{height:100%;background:var(--accent);border-radius:6px;
    transition:width .5s ease}
  .hbar .val{font-variant-numeric:tabular-nums;color:var(--sub);min-width:64px;
    text-align:right}

  /* ---- cohort heatmap ---- */
  .heat{overflow-x:auto}
  table.heat-tbl{border-collapse:collapse;font-size:12.5px;width:100%}
  .heat-tbl th{color:var(--sub);font-weight:600;padding:6px 4px;text-align:center}
  .heat-tbl td{padding:0;text-align:center}
  .heat-tbl .rowlab{color:var(--ink);font-weight:600;text-align:left;
    padding-right:10px;white-space:nowrap}
  .cell{display:flex;align-items:center;justify-content:center;height:34px;
    border-radius:6px;margin:2px;font-variant-numeric:tabular-nums}

  footer{margin-top:26px;font-size:12px;color:var(--sub);
    border-top:1px solid var(--line);padding-top:14px}
  @media(max-width:820px){.kpis{grid-template-columns:1fr 1fr}
    .grid{grid-template-columns:1fr}.hbar{grid-template-columns:96px 1fr auto}}
</style></head>
<body><div class="wrap">
  <header>
    <div>
      <div class="brand">commerce<b>·</b>intel</div>
      <div class="meta">Funnel, conversion, retention & customer value — interactive</div>
    </div>
    <div class="meta" id="scope">Showing: all users</div>
  </header>

  <!-- TOGGLE CONTROLS -->
  <div class="controls">
    <div class="ctrl"><label>Device</label><div class="pills" id="devicePills"></div></div>
    <div class="ctrl"><label>Channel</label><div class="pills" id="channelPills"></div></div>
    <div class="reset"><button id="resetBtn">Reset filters</button></div>
  </div>

  <section class="kpis" id="kpis"></section>

  <div class="grid">
    <div class="card full">
      <div class="head-row">
        <div><h3>Conversion funnel</h3>
          <p class="cap">Distinct users reaching each stage. Toggle to see step conversion.</p></div>
        <div class="mini-toggle" id="funnelToggle">
          <button data-m="users" class="active">Users</button>
          <button data-m="step">Step %</button>
        </div>
      </div>
      <div id="funnel"></div>
      <div class="leak" id="leak"></div>
    </div>

    <div class="card"><h3>Conversion by channel</h3>
      <p class="cap" id="chanCap">% of users who purchased</p>
      <div id="chanChart"></div></div>

    <div class="card"><h3>Conversion by device</h3>
      <p class="cap" id="devCap">% of users who purchased</p>
      <div id="devChart"></div></div>

    <div class="card">
      <div class="head-row">
        <div><h3>Customer value (RFM)</h3>
          <p class="cap">Segments ranked by contribution</p></div>
        <div class="mini-toggle" id="rfmToggle">
          <button data-m="revenue" class="active">Revenue</button>
          <button data-m="customers">Customers</button>
        </div>
      </div>
      <div id="rfmChart"></div>
    </div>

    <div class="card">
      <div class="head-row">
        <div><h3>Cohort retention</h3>
          <p class="cap">By first-purchase month</p></div>
        <div class="mini-toggle" id="cohortToggle">
          <button data-m="pct" class="active">%</button>
          <button data-m="users">Users</button>
        </div>
      </div>
      <div class="heat" id="cohort"></div>
    </div>
  </div>

  <footer>Interactive dashboard · data pre-computed with SQL + Python, rendered client-side.
    RFM & cohort are global; funnel, conversion & KPIs respond to the device/channel filters.</footer>
</div>

<script>
const DATA = __DATA__;
const state = {device:'All', channel:'All', funnel:'users', rfm:'revenue', cohort:'pct'};
const money = n => n.toLocaleString(undefined,{maximumFractionDigits:0});
const pct = n => n.toFixed(1)+'%';

// ---------- filtering helpers ----------
function filteredUsers(){
  return DATA.userMatrix.filter(r =>
    (state.device==='All'  || r.device===state.device) &&
    (state.channel==='All' || r.channel===state.channel));
}
function usersReached(rows){
  // reached stage i (0..3) if max_stage >= i+1
  const c=[0,0,0,0];
  rows.forEach(r=>{ for(let i=0;i<4;i++) if(r.max_stage>=i+1) c[i]+=r.count; });
  return c;
}
function revenueFor(){
  return DATA.revMatrix.filter(r =>
    (state.device==='All'  || r.device===state.device) &&
    (state.channel==='All' || r.channel===state.channel))
    .reduce((a,r)=>({revenue:a.revenue+r.revenue, orders:a.orders+r.orders}),
            {revenue:0,orders:0});
}

// ---------- renderers ----------
function renderKPIs(){
  const rows=filteredUsers();
  const reached=usersReached(rows);
  const total=reached[0], buyers=reached[3];
  const conv=total? 100*buyers/total : 0;
  const {revenue,orders}=revenueFor();
  const aov=orders? revenue/orders : 0;
  const cards=[
    ['Users', money(total), 'reached the funnel'],
    ['Conversion', pct(conv), 'visitor \u2192 buyer'],
    ['Revenue', money(revenue), orders+' orders'],
    ['AOV', money(aov), 'avg order value'],
  ];
  document.getElementById('kpis').innerHTML = cards.map(c=>
    `<div class="kpi"><div class="l">${c[0]}</div><div class="v">${c[1]}</div>
     <div class="s">${c[2]}</div></div>`).join('');
}

function renderFunnel(){
  const reached=usersReached(filteredUsers());
  const top=reached[0]||1;
  let html='';
  for(let i=0;i<4;i++){
    const w=100*reached[i]/top;
    const step = i===0?100:(reached[i-1]? 100*reached[i]/reached[i-1]:0);
    const right = state.funnel==='users'
      ? `${money(reached[i])} <span class="step">(${(100*reached[i]/top).toFixed(0)}%)</span>`
      : `<span class="step">step ${step.toFixed(0)}%</span>`;
    html+=`<div class="fbar"><div class="top">
        <span class="name">${DATA.stageLabels[i]}</span><span>${right}</span></div>
      <div class="track"><div class="fill" style="width:${w}%"></div></div></div>`;
  }
  document.getElementById('funnel').innerHTML=html;
  // dynamic "biggest leak" callout
  let worst=1, worstV=101;
  for(let i=1;i<4;i++){ const s=reached[i-1]?100*reached[i]/reached[i-1]:0;
    if(s<worstV){worstV=s;worst=i;} }
  document.getElementById('leak').innerHTML =
    `<b>Biggest leak:</b> ${DATA.stageLabels[worst-1]} \u2192 ${DATA.stageLabels[worst]} `+
    `— only ${worstV.toFixed(0)}% continue. Focus experiments here.`;
}

function hbars(el, items, fmt, maxV){
  const max=maxV||Math.max(...items.map(i=>i.v),1);
  el.innerHTML=items.map(i=>{
    const w=100*i.v/max;
    return `<div class="hbar"><span class="cat" title="${i.cat}">${i.cat}</span>
      <div class="track"><div class="fill" style="width:${w}%"></div></div>
      <span class="val">${fmt(i.v)}</span></div>`;
  }).join('');
}

function conversionBy(dim, fixedDim, fixedVal){
  // dim = 'channel' or 'device'; compute conversion within current opposite filter
  const rows=DATA.userMatrix.filter(r =>
     (fixedVal==='All' || r[fixedDim]===fixedVal));
  const groups={};
  rows.forEach(r=>{
    const k=r[dim];
    if(!groups[k]) groups[k]={total:0,buy:0};
    groups[k].total+=r.count;
    if(r.max_stage>=4) groups[k].buy+=r.count;
  });
  return Object.entries(groups).map(([cat,g])=>
    ({cat, v: g.total? 100*g.buy/g.total : 0}))
    .sort((a,b)=>b.v-a.v);
}

function renderConversion(){
  // channel chart respects the DEVICE filter; device chart respects CHANNEL filter
  const chan=conversionBy('channel','device',state.device);
  const dev =conversionBy('device','channel',state.channel);
  hbars(document.getElementById('chanChart'), chan, pct, 100*Math.max(...chan.map(i=>i.v))/100*1);
  hbars(document.getElementById('devChart'),  dev,  pct);
  document.getElementById('chanCap').textContent =
    state.device==='All'?'% who purchased (all devices)':`% who purchased on ${state.device}`;
  document.getElementById('devCap').textContent =
    state.channel==='All'?'% who purchased (all channels)':`% who purchased from ${state.channel}`;
}

function renderRFM(){
  const items=DATA.rfm.map(r=>({cat:r.segment,
    v: state.rfm==='revenue'? r.revenue : r.customers}))
    .sort((a,b)=>b.v-a.v);
  const fmt = state.rfm==='revenue' ? (v=>money(v)) : (v=>v+' cust');
  hbars(document.getElementById('rfmChart'), items, fmt);
}

function heatColor(p){ // white -> indigo
  const t=Math.max(0,Math.min(1,p/100));
  const r=Math.round(255+(79-255)*t), g=Math.round(255+(70-255)*t),
        b=Math.round(255+(229-255)*t);
  return `rgb(${r},${g},${b})`;
}
function renderCohort(){
  const {maxN,grid}=DATA.cohort;
  let head='<tr><th class="rowlab">Cohort</th>';
  for(let n=0;n<=maxN;n++) head+=`<th>M${n}</th>`; head+='</tr>';
  let body='';
  grid.forEach(row=>{
    body+=`<tr><td class="rowlab">${row.cohort}<br><span style="color:var(--sub);font-weight:400">n=${row.size}</span></td>`;
    row.cells.forEach(c=>{
      if(c===null){ body+='<td></td>'; return; }
      const val = state.cohort==='pct' ? c.pct.toFixed(0)+'%' : c.users;
      const col = heatColor(c.pct);
      const txt = c.pct>55?'#fff':'#0f172a';
      body+=`<td><div class="cell" style="background:${col};color:${txt}">${val}</div></td>`;
    });
    body+='</tr>';
  });
  document.getElementById('cohort').innerHTML=
    `<table class="heat-tbl">${head}${body}</table>`;
}

function renderScope(){
  const parts=[];
  if(state.device!=='All') parts.push(state.device);
  if(state.channel!=='All') parts.push(state.channel);
  document.getElementById('scope').textContent =
    'Showing: '+(parts.length? parts.join(' · ') : 'all users');
}

function renderAll(){
  renderKPIs(); renderFunnel(); renderConversion();
  renderRFM(); renderCohort(); renderScope();
}

// ---------- build controls ----------
function pillGroup(elId, values, key){
  const el=document.getElementById(elId);
  const all=['All',...values];
  el.innerHTML=all.map(v=>
    `<button class="pill${v==='All'?' active':''}" data-v="${v}">${v}</button>`).join('');
  el.querySelectorAll('.pill').forEach(btn=>btn.onclick=()=>{
    state[key]=btn.dataset.v;
    el.querySelectorAll('.pill').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active'); renderAll();
  });
}
function miniToggle(elId, key){
  const el=document.getElementById(elId);
  el.querySelectorAll('button').forEach(btn=>btn.onclick=()=>{
    state[key]=btn.dataset.m;
    el.querySelectorAll('button').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active'); renderAll();
  });
}

pillGroup('devicePills', DATA.devices, 'device');
pillGroup('channelPills', DATA.channels, 'channel');
miniToggle('funnelToggle','funnel');
miniToggle('rfmToggle','rfm');
miniToggle('cohortToggle','cohort');
document.getElementById('resetBtn').onclick=()=>{
  state.device='All'; state.channel='All';
  document.querySelectorAll('.pills').forEach(g=>{
    g.querySelectorAll('.pill').forEach(b=>b.classList.toggle('active', b.dataset.v==='All'));
  });
  renderAll();
};
renderAll();
</script></body></html>"""

html = HTML.replace("__DATA__", json.dumps(DATA))
with open("interactive_dashboard.html", "w") as f:
    f.write(html)
print("interactive_dashboard.html written")
print(f"userMatrix rows: {len(user_matrix)}, revMatrix rows: {len(rev_matrix)}, "
      f"rfm segments: {len(rfm_data)}, cohorts: {len(grid)}")
