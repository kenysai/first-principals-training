/* 第一性原理 · 问题拆解器 —— 单页前端（原生 JS，无需构建） */
"use strict";

const S = { config: null, problems: [], p: null, step: 0, filter: "", view: localStorage.getItem("fp_view") || "board",
  threshold: null, saveTimer: null, saving: false };
const STATUSES = ["提出", "拆解", "解决", "复盘", "完成"];
const DOMAINS = ["个人", "工作", "学习", "健康", "家庭", "财务", "其他"];
const TYPES = ["事实", "假设", "惯例"];

const STEPS = [
  { key: "quick", title: "快速判断", who: "第0步", status: "提出",
    guide: ["第一性原理很费脑子，先判断值不值得用。", "<b>做错代价大</b>、<b>常规做法没用</b>、或<b>你的情况和别人不一样</b>——满足任意一条就值得跑完整流程。", "否则用类比/常规做法就够了，省下精力。"] },
  { key: "define", title: "定义问题", who: "起点", status: "提出", ai: true,
    guide: ["先写清楚<b>真正要解决的问题</b>，最常见的错误是把某个方案当成问题。", "例：问题不是“怎么一周打满三次球”，而是“怎么在带孩子的情况下保持运动”。", "成功标准要<b>可衡量</b>：做到什么程度算解决？"] },
  { key: "feynman", title: "费曼检验", who: "费曼", status: "提出", ai: true,
    guide: ["用<b>小孩能听懂的一句话</b>讲清这个问题。", "讲不清的地方，就是你还没想清楚的地方——把它们写下来。", "“知道名字不等于理解”：避免用术语掩盖模糊。"] },
  { key: "decompose", title: "拆到基本事实", who: "马斯克", status: "拆解", ai: true,
    guide: ["列出问题背后的<b>所有假设</b>，逐条问：这真的必然成立吗？", "每条标注：<b class='type-事实'>事实</b>（可验证/你亲身确认）、<b class='type-假设'>假设</b>（看起来对但可能被推翻）、<b class='type-惯例'>惯例</b>（只是大家都这么做）。突破口通常藏在后两种里。", "对关键现象连续追问 <b>5 个为什么</b>，直到碰到根因。每一层也要分清事实还是猜测。"] },
  { key: "evidence", title: "查证据和偏见", who: "芒格", status: "拆解",
    guide: ["每条说法：<b>我有数据吗，还是只是感觉？</b>", "对照常见偏见自查：确认偏误、沉没成本、自责归因……", "分清<b>可以改变的因素</b>和<b>改变不了的约束</b>（比如孩子夜里要起夜）。"] },
  { key: "rebuild", title: "从事实重建", who: "马斯克", status: "解决", ai: true,
    guide: ["只用<b>确认过的事实和真实约束</b>当积木，从零设计方案，而不是修补旧方案。", "给出 1-3 个方案，写清依据、优缺点，然后选一个。"] },
  { key: "premortem", title: "逆向检查", who: "芒格", status: "解决", ai: true,
    guide: ["“反过来想，总是反过来想。”假设方案<b>已经失败了</b>，倒推最可能的原因。", "为每种失败方式写一个预防措施，再定几个“出现就停下来重新评估”的信号。"] },
  { key: "experiment", title: "小成本验证", who: "试错", status: "解决", ai: true,
    guide: ["别一次押上全部。用<b>最小代价、最短时间</b>验证关键假设。", "写清：试什么、多久、看哪些指标、截止日。到截止日回来复盘。"] },
  { key: "review", title: "复盘", who: "迭代", status: "复盘", ai: true,
    guide: ["对照成功标准和指标，写下<b>实际结果</b>。", "对差距用 5 个为什么追问；哪些假设被推翻、哪些被证实？更新事实清单。", "第一性原理不是想一次就完，而是一个循环：定下一轮怎么做。"] },
];

/* ---------------- 工具 ---------------- */
const $ = (sel, root = document) => root.querySelector(sel);
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else if (k === "value") el.value = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) el.append(c.nodeType ? c : document.createTextNode(c));
  return el;
}
const API = (window.FP_API_BASE || "").replace(/\/$/, "");
const getToken = () => localStorage.getItem("fp_token") || "";
function authHeaders(extra = {}) { const t = getToken(); return t ? { ...extra, Authorization: "Bearer " + t } : extra; }
async function rawFetch(url, opts = {}) {
  const r = await fetch(API + url, { ...opts, headers: authHeaders(opts.headers || {}) });
  if (r.status === 401 && url !== "/api/login") { localStorage.removeItem("fp_token"); showLogin("登录已过期，请重新登录"); throw new Error("未登录"); }
  return r;
}
async function api(method, url, body) {
  const r = await rawFetch(url, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (e) {}
    throw new Error(msg);
  }
  return r.json();
}
function toast(msg, err = false) {
  const t = h("div", { class: "toast" + (err ? " err" : "") }, msg);
  $("#toast").append(t);
  setTimeout(() => t.remove(), err ? 6000 : 3200);
}
function modal(content, wide = false) {
  const bg = h("div", { class: "modal-bg", onclick: (e) => { if (e.target === bg) close(); } });
  const box = h("div", { class: "modal" + (wide ? " wide" : "") }, content);
  bg.append(box);
  $("#modal-root").append(bg);
  function close() { bg.remove(); }
  return close;
}
const th = () => S.threshold ?? S.config.threshold;
const D = () => S.p.data;
function sec(key) { const d = D(); if (!d[key] || typeof d[key] !== "object") d[key] = {}; return d[key]; }
function arr(obj, key) { if (!Array.isArray(obj[key])) obj[key] = []; return obj[key]; }
const fmtConf = (c) => (c === undefined || c === null ? "-" : Number(c).toFixed(2));
const lines = (t) => (t || "").split("\n").map((x) => x.trim()).filter(Boolean);

/* ---------------- 启动 & 路由 ---------------- */
function showLogin(msg) {
  if (document.querySelector(".login-box")) return;
  $("#modal-root").replaceChildren();
  document.querySelector(".top-right").style.visibility = "hidden";
  const pw = h("input", { type: "password", placeholder: "密码", autocomplete: "current-password" });
  const err = h("div", { class: "small", style: "color:var(--danger);min-height:22px" }, msg || "");
  const btn = h("button", { class: "btn primary", style: "width:100%", type: "submit" }, "登录");
  const form = h("form", { class: "login-box panel", onsubmit: async (e) => {
    e.preventDefault(); btn.disabled = true; err.textContent = "";
    try {
      const r = await fetch(API + "/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: pw.value }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || r.statusText);
      if (j.token) localStorage.setItem("fp_token", j.token);
      location.hash = location.hash || "#/"; boot();
    } catch (e2) { err.textContent = e2.message === "Failed to fetch" ? "连不上服务器：" + (API || location.origin) : e2.message; btn.disabled = false; pw.select(); }
  } },
    h("div", { style: "font-size:40px;text-align:center" }, "🧩"), h("h2", { style: "text-align:center" }, "第一性原理 · 问题拆解器"),
    h("p", { class: "muted small", style: "text-align:center;margin-top:0" }, "请输入访问密码"), pw, err, btn);
  $("#app").replaceChildren(form);
  setTimeout(() => pw.focus(), 50);
}
async function boot() {
  try { S.config = await api("GET", "/api/config"); }
  catch (e) { if (e.message !== "未登录") $("#app").replaceChildren(h("div", { class: "panel empty" }, "连不上服务器（" + (API || location.origin) + "）：" + e.message)); return; }
  document.querySelector(".top-right").style.visibility = "";
  const lo = $("#btn-logout");
  lo.style.display = getToken() ? "" : "none";
  lo.onclick = () => { localStorage.removeItem("fp_token"); S.p = null; showLogin("已退出"); };
  const saved = localStorage.getItem("fp_threshold");
  S.threshold = saved ? Number(saved) : null;
  const pj = $("#pill-jev");
  pj.textContent = { real: "Jev 已连接", mock: "Jev 模拟", off: "Jev 未配置" }[S.config.jev];
  pj.className = "pill " + (S.config.jev === "real" ? "on" : S.config.jev === "mock" ? "mock" : "");
  const pl = $("#pill-llm");
  pl.textContent = S.config.llm_enabled ? "AI 建议：" + S.config.llm_name.replace("openai-compatible:", "") : "AI 建议未启用";
  pl.className = "pill " + (S.config.llm_enabled ? (S.config.llm_name.includes("mock") ? "mock" : "on") : "");
  pl.title = S.config.llm_reason || "";
  $("#btn-settings").onclick = openSettings;
  if (!S.routing) { window.addEventListener("hashchange", route); S.routing = true; }
  route();
}
async function route() {
  clearTimeout(S.saveTimer);
  const m = location.hash.match(/^#\/p\/(\d+)(?:\/(\d+))?/);
  if (m) {
    const id = Number(m[1]);
    if (!S.p || S.p.id !== id) {
      try { S.p = await api("GET", `/api/problems/${id}`); } catch (e) { toast("问题不存在", true); location.hash = "#/"; return; }
    }
    S.step = m[2] !== undefined ? Number(m[2]) : Number(localStorage.getItem("fp_step_" + id) || 0);
    localStorage.setItem("fp_step_" + id, S.step);
    renderWizard();
  } else {
    S.p = null;
    renderDashboard();
  }
  window.scrollTo(0, 0);
}

/* ---------------- 设置 ---------------- */
function openSettings() {
  const inp = h("input", { type: "number", min: "0.5", max: "0.99", step: "0.05", value: th() });
  const close = modal([
    h("h2", {}, "设置"),
    h("div", { class: "field" }, h("label", {}, "置信度阈值", h("span", { class: "hint" }, "Jev 判断的置信度低于它会标为 ⚠待确认（服务器默认 " + S.config.threshold + "）")), inp),
    h("p", { class: "small muted" }, "Jev：" + { real: "已配置（服务器端 TYPESAFE_API_KEY）", mock: "模拟模式", off: "未配置，Jev 按钮不可用" }[S.config.jev]),
    h("p", { class: "small muted" }, "AI 建议：" + (S.config.llm_enabled ? "已启用（" + S.config.llm_name + "）" : "未启用。" + (S.config.llm_reason || ""))),
    h("div", { class: "row" }, h("span", { class: "spacer" }),
      h("button", { class: "btn", onclick: () => { localStorage.removeItem("fp_threshold"); S.threshold = null; close(); route(); } }, "恢复默认"),
      h("button", { class: "btn primary", onclick: () => { const v = Number(inp.value); if (v > 0 && v < 1) { localStorage.setItem("fp_threshold", v); S.threshold = v; } close(); route(); } }, "保存")),
  ]);
}

/* ---------------- 进度 ---------------- */
function filled(p, key) {
  const d = p.data || {};
  const s = d[key] || {};
  switch (key) {
    case "quick": return ["costly", "conventional_works", "same_as_others"].every((k) => s[k] && typeof s[k].answer === "boolean");
    case "define": return !!(s.problem_restated || s.goal);
    case "feynman": return !!s.one_sentence;
    case "decompose": return (s.assumptions || []).some((a) => a.statement);
    case "evidence": return (d.decompose?.assumptions || []).some((a) => typeof a.has_data === "boolean") || !!(s.changeable || s.fixed);
    case "rebuild": return (s.options || []).some((o) => o.name || o.description);
    case "premortem": return (s.failure_modes || []).some((f) => f.mode);
    case "experiment": return !!(s.what_to_test || (s.metrics || []).length);
    case "review": return !!(s.actual || s.gap_summary || Object.values(s.metric_actuals || {}).some(Boolean));
  }
  return false;
}
const progress = (p) => STEPS.filter((s) => filled(p, s.key)).length;

/* ---------------- 首页 ---------------- */
async function renderDashboard() {
  const app = $("#app");
  try { S.problems = await api("GET", "/api/problems"); } catch (e) { toast(e.message, true); }
  const counts = Object.fromEntries(STATUSES.map((s) => [s, S.problems.filter((p) => p.status === s).length]));
  const list = S.problems.filter((p) => !S.filter || p.status === S.filter);
  const chips = h("div", { class: "chips" },
    h("button", { class: "chip" + (S.filter ? "" : " active"), onclick: () => { S.filter = ""; renderDashboard(); } }, "全部", h("span", { class: "n" }, S.problems.length)),
    STATUSES.map((s) => h("button", { class: "chip" + (S.filter === s ? " active" : ""), onclick: () => { S.filter = s; renderDashboard(); } }, s, h("span", { class: "n" }, counts[s]))));
  const seg = h("div", { class: "seg" },
    h("button", { class: S.view === "board" ? "active" : "", onclick: () => { S.view = "board"; localStorage.setItem("fp_view", "board"); renderDashboard(); } }, "看板"),
    h("button", { class: S.view === "list" ? "active" : "", onclick: () => { S.view = "list"; localStorage.setItem("fp_view", "list"); renderDashboard(); } }, "列表"));
  const head = h("div", { class: "dash-head" },
    h("div", {}, h("h1", {}, "我的问题"), h("p", {}, "提出 → 拆解 → 解决 → 复盘，一个问题一个循环。")),
    h("span", { class: "spacer" }), seg, h("button", { class: "btn primary", onclick: newProblem }, "＋ 新建问题"));
  let body;
  if (!S.problems.length) {
    body = h("div", { class: "panel empty" }, h("p", {}, "还没有问题。"), h("button", { class: "btn primary", onclick: newProblem }, "＋ 新建第一个问题"), " ",
      h("button", { class: "btn", onclick: async () => { await api("POST", "/api/demo"); renderDashboard(); } }, "恢复示例"));
  } else if (S.view === "board") {
    const cols = (S.filter ? [S.filter] : STATUSES);
    body = h("div", { class: "board", style: S.filter ? "grid-template-columns: minmax(240px, 420px)" : "" },
      cols.map((st) => h("div", { class: "col" },
        h("div", { class: "col-head" }, h("span", {}, st), h("span", { class: "muted" }, counts[st])),
        list.filter((p) => p.status === st).map(card),
        list.filter((p) => p.status === st).length ? null : h("div", { class: "empty" }, "暂无"))));
  } else {
    body = h("table", { class: "list" },
      h("thead", {}, h("tr", {}, ["问题", "状态", "领域", "重要性", "进度", "验证截止", "复盘日", "更新"].map((x) => h("th", {}, x)))),
      h("tbody", {}, list.map((p) => h("tr", { onclick: () => (location.hash = `#/p/${p.id}`) },
        h("td", {}, p.title, p.is_demo ? h("span", { class: "tag demo", style: "margin-left:6px" }, "示例") : null),
        h("td", {}, h("span", { class: "tag st" }, p.status)), h("td", {}, p.domain), h("td", {}, h("span", { class: "tag imp-" + p.importance }, p.importance)),
        h("td", {}, `${progress(p)}/9`), h("td", {}, p.deadline || "-"), h("td", {}, p.review_date || "-"), h("td", { class: "muted" }, p.updated_at.slice(5, 16).replace("T", " "))))));
    if (!list.length) body = h("div", { class: "panel empty" }, "这个状态下暂无问题");
  }
  app.replaceChildren(head, h("div", { style: "margin-bottom:14px" }, chips), body);
}
function card(p) {
  const n = progress(p);
  const today = new Date().toISOString().slice(0, 10);
  const due = p.deadline && p.status !== "完成" && p.deadline <= today;
  return h("div", { class: "card", onclick: () => (location.hash = `#/p/${p.id}`) },
    h("div", { class: "card-title" }, p.title),
    h("div", { class: "tags" }, h("span", { class: "tag" }, p.domain), h("span", { class: "tag imp-" + p.importance }, "重要性 " + p.importance),
      p.is_demo ? h("span", { class: "tag demo" }, "示例") : null),
    h("div", { class: "progress" }, h("i", { style: `width:${(n / 9) * 100}%` })),
    h("div", { class: "card-foot" }, h("span", {}, `进度 ${n}/9`),
      h("span", { style: due ? "color:var(--warn);font-weight:600" : "" }, p.deadline ? (due ? "⏰ 该复盘 " : "截止 ") + p.deadline.slice(5) : "")));
}
function newProblem() {
  const title = h("textarea", { rows: 2, placeholder: "例：部门周报每周要花半天，怎么压缩到 1 小时？" });
  const bg = h("textarea", { rows: 3, placeholder: "你的真实情况和约束（只有你知道）。例：数据来自 3 个系统，要手工导出；经理要求周一 10 点前交。" });
  const dom = h("select", {}, DOMAINS.map((d) => h("option", {}, d)));
  const imp = h("select", {}, ["高", "中", "低"].map((d) => h("option", { selected: d === "中" }, d)));
  const close = modal([
    h("h2", {}, "新建问题"), h("p", { class: "muted small" }, "先把问题原样写下来，下一步再重新定义它。"),
    h("div", { class: "field" }, h("label", {}, "问题"), title),
    h("div", { class: "field" }, h("label", {}, "背景", h("span", { class: "hint" }, "可选")), bg),
    h("div", { class: "grid2" }, h("div", { class: "field" }, h("label", {}, "领域"), dom), h("div", { class: "field" }, h("label", {}, "重要性"), imp)),
    h("div", { class: "row" }, h("span", { class: "spacer" }), h("button", { class: "btn", onclick: () => close() }, "取消"),
      h("button", { class: "btn primary", onclick: async () => {
        if (!title.value.trim()) { title.focus(); return; }
        try {
          const p = await api("POST", "/api/problems", { title: title.value.trim(), background: bg.value.trim(), domain: dom.value, importance: imp.value, data: {} });
          close(); location.hash = `#/p/${p.id}/0`;
        } catch (e) { toast(e.message, true); }
      } }, "创建并开始")),
  ]);
  setTimeout(() => title.focus(), 50);
}

/* ---------------- 保存 ---------------- */
function advanceStatus() {
  const target = STEPS[S.step].status;
  if (S.p.status === "完成") return;
  if (STATUSES.indexOf(target) > STATUSES.indexOf(S.p.status) && filled(S.p, STEPS[S.step].key)) {
    S.p.status = target;
    const sel = $("#status-sel"); if (sel) sel.value = target;
  }
}
function changed() {
  advanceStatus();
  const ind = $("#save-ind"); if (ind) ind.textContent = "未保存…";
  clearTimeout(S.saveTimer);
  S.saveTimer = setTimeout(save, 600);
}
async function save() {
  clearTimeout(S.saveTimer);
  const ind = $("#save-ind");
  const p = S.p;
  try {
    const r = await api("PUT", `/api/problems/${p.id}`, { title: p.title, background: p.background, status: p.status, domain: p.domain,
      importance: p.importance, deadline: p.deadline || "", review_date: p.review_date || "", data: p.data });
    p.updated_at = r.updated_at;
    if (ind && S.p === p) ind.textContent = "已保存 " + r.updated_at.slice(11, 16);
  } catch (e) { if (ind) ind.textContent = "保存失败"; toast("保存失败：" + e.message, true); }
}

/* ---------------- 表单绑定 ---------------- */
function bind(obj, key, opts = {}) {
  const tag = opts.area || opts.grow ? "textarea" : opts.options ? "select" : "input";
  const attrs = { placeholder: opts.ph || "", rows: opts.rows || (opts.area ? 3 : null), type: opts.type || null, class: opts.cls || null };
  const el = tag === "select" ? h("select", attrs, opts.options.map((o) => h("option", { value: o.v ?? o, selected: (obj[key] ?? "") === (o.v ?? o) }, o.t ?? (o || "—")))) : h(tag, { ...attrs, value: obj[key] ?? "" });
  if (opts.grow) {
    const fit = () => { el.style.height = "auto"; el.style.height = el.scrollHeight + 2 + "px"; };
    el.classList.add("grow"); el.rows = 1;
    el.addEventListener("input", fit);
    requestAnimationFrame(fit);
  }
  el.addEventListener(tag === "select" ? "change" : "input", () => {
    obj[key] = opts.type === "number" ? (el.value === "" ? "" : Number(el.value)) : el.value;
    opts.onchange && opts.onchange(el.value);
    changed();
  });
  return el;
}
const field = (label, input, hint) => h("div", { class: "field" }, h("label", {}, label, hint ? h("span", { class: "hint" }, hint) : null), input);
function yn(get, set, labels = ["是", "否"]) {
  const v = get();
  return h("div", { class: "yn" },
    h("button", { class: v === true ? "on-yes" : "", onclick: () => { set(true); changed(); renderStep(); } }, labels[0]),
    h("button", { class: v === false ? "on-no" : "", onclick: () => { set(false); changed(); renderStep(); } }, labels[1]));
}
function jevChip(label, conf, confirmed) {
  const warn = conf !== undefined && conf !== null && conf < th() && !confirmed;
  return h("span", { class: "jev" + (warn ? " warn" : confirmed ? " ok" : ""), title: "Jev 的判断与置信度" },
    "Jev：", label, h("span", { class: "conf" }, fmtConf(conf)), warn ? " ⚠待确认" : confirmed ? " ✓" : "");
}
function rowList(list, makeRow, makeNew, addLabel) {
  const wrap = h("div", {});
  list.forEach((it, i) => wrap.append(makeRow(it, i, () => { list.splice(i, 1); changed(); renderStep(); })));
  wrap.append(h("button", { class: "btn sm", onclick: () => { list.push(makeNew()); changed(); renderStep(); } }, "＋ " + addLabel));
  return wrap;
}
const del = (fn) => h("button", { class: "btn ghost sm", title: "删除", onclick: fn }, "✕");

/* ---------------- 向导 ---------------- */
function renderWizard() {
  const p = S.p;
  const title = h("textarea", { class: "wz-title grow", rows: 1, value: p.title });
  const fitTitle = () => { title.style.height = "auto"; title.style.height = title.scrollHeight + 2 + "px"; };
  title.addEventListener("input", () => { fitTitle(); if (title.value.trim()) { p.title = title.value.replace(/\n/g, " "); changed(); } });
  requestAnimationFrame(fitTitle);
  const st = h("select", { id: "status-sel" }, STATUSES.map((s) => h("option", { selected: s === p.status }, s)));
  st.onchange = () => { p.status = st.value; changed(); };
  const dom = h("select", {}, [...new Set([...DOMAINS, p.domain])].map((s) => h("option", { selected: s === p.domain }, s)));
  dom.onchange = () => { p.domain = dom.value; changed(); };
  const imp = h("select", {}, ["高", "中", "低"].map((s) => h("option", { selected: s === p.importance }, "重要性 " + s)));
  imp.onchange = () => { p.importance = imp.value.slice(-1); changed(); };
  const head = h("div", { class: "wz-head" },
    h("div", { style: "flex:1;min-width:260px" },
      h("a", { href: "#/", class: "small" }, "← 全部问题"), title,
      h("div", { class: "wz-meta" }, st, dom, imp, p.is_demo ? h("span", { class: "tag demo" }, "示例，可删除") : null, h("span", { id: "save-ind", class: "save-ind" }, ""))),
    h("div", { class: "row" },
      h("button", { class: "btn", onclick: previewMd }, "预览报告"),
      h("button", { class: "btn", onclick: () => download("md") }, "导出 Markdown"),
      h("button", { class: "btn", onclick: () => download("json") }, "导出 JSON"),
      h("button", { class: "btn danger", onclick: async () => {
        if (!confirm(`确定删除「${p.title}」？此操作不可恢复。`)) return;
        await api("DELETE", `/api/problems/${p.id}`); toast("已删除"); location.hash = "#/";
      } }, "删除")));
  const stepper = h("nav", { class: "stepper" }, STEPS.map((s, i) =>
    h("a", { class: "step-link" + (i === S.step ? " active" : "") + (filled(p, s.key) ? " done" : ""), href: `#/p/${p.id}/${i}`, onclick: () => save() },
      h("span", { class: "step-no" }, filled(p, s.key) && i !== S.step ? "✓" : i), h("span", {}, s.title), h("span", { class: "step-who" }, s.who))));
  const panel = h("section", { class: "panel", id: "panel" });
  $("#app").replaceChildren(head, h("div", { class: "wz-grid" }, stepper, panel));
  renderStep();
  const act = stepper.querySelector(".active");
  if (act && window.innerWidth <= 900) stepper.scrollLeft = act.offsetLeft - 12;
}
function renderStep() {
  const s = STEPS[S.step];
  const panel = $("#panel");
  const scrollY = window.scrollY;
  const aiBtn = s.ai && S.config.llm_enabled && S.config.ai_steps.includes(s.key)
    ? h("button", { class: "btn ai", onclick: (e) => aiSuggest(s.key, e.currentTarget) }, "✨ AI 建议") : null;
  const body = RENDER[s.key]();
  panel.replaceChildren(
    h("div", { class: "panel-head" }, h("div", { style: "flex:1" }, h("div", { class: "muted small" }, `第 ${S.step} 步 · ${s.who}`), h("h2", {}, s.title)), aiBtn),
    h("div", { class: "guide" }, h("ul", {}, s.guide.map((g) => h("li", { html: g })))),
    body,
    h("div", { class: "nav-foot" },
      S.step > 0 ? h("a", { class: "btn", href: `#/p/${S.p.id}/${S.step - 1}`, onclick: () => save() }, "← 上一步") : h("span"),
      S.step < STEPS.length - 1 ? h("a", { class: "btn primary", href: `#/p/${S.p.id}/${S.step + 1}`, onclick: () => save() }, "下一步 →") : h("span")));
  window.scrollTo(0, scrollY);
}
async function jevCall(kind, btn, label) {
  await save();
  btn.disabled = true; const old = btn.textContent; btn.textContent = "Jev 判断中…";
  try {
    const r = await api("POST", `/api/problems/${S.p.id}/jev/${kind}`);
    S.p = r.problem;
    toast(`${label}完成（${r.stats.model}，${r.stats.seconds}s，${r.stats.input_tokens}+${r.stats.output_tokens} tokens）`);
  } catch (e) { toast(e.message, true); }
  btn.disabled = false; btn.textContent = old;
  renderStep();
}
const jevBtn = (kind, label, text) => S.config.jev === "off"
  ? h("button", { class: "btn jev", disabled: true, title: "服务器未配置 TYPESAFE_API_KEY" }, text)
  : h("button", { class: "btn jev", onclick: (e) => jevCall(kind, e.currentTarget, label) }, text);

/* ---------------- AI 建议（通用 LLM，可选） ---------------- */
const FIELD_LABELS = { problem_restated: "真正要解决的问题", goal: "目标", success_criteria: "成功标准", out_of_scope: "不在本次范围",
  one_sentence: "一句话", analogy: "类比", unclear_points: "还讲不清的地方", assumptions: "假设", key_phenomenon: "关键现象", five_whys: "5个为什么",
  root_cause: "根因（假设）", base_facts: "基本事实", options: "方案", recommended: "推荐方案", failure_modes: "失败方式", stop_signals: "停止信号",
  what_to_test: "试什么", steps: "步骤", duration_days: "天数", metrics: "指标", deadline: "截止日", cost: "成本", gap_summary: "差距", overturned: "被推翻的假设",
  confirmed: "被证实的假设", updated_facts: "更新后的事实", lessons: "经验教训", next_keep: "保留", next_change: "改变", next_experiment: "下一个小实验", next_review_date: "下次复盘" };
function itemText(k, it) {
  if (k === "assumptions") return `[${it.type}] ${it.statement}${it.reason ? "（" + it.reason + "）" : ""}`;
  if (k === "five_whys") return `${it.why} → ${it.answer}（${it.type}）`;
  if (k === "options") return `${it.name}：${it.description}`;
  if (k === "failure_modes") return `${it.mode}（${it.likelihood}）→ ${it.prevention}`;
  if (k === "metrics") return `${it.name}：${it.target}（${it.how}）`;
  if (k === "overturned") return `${it.assumption}（证据：${it.evidence}）`;
  return JSON.stringify(it);
}
async function aiSuggest(key, btn) {
  await save();
  btn.disabled = true; const old = btn.textContent; btn.textContent = "AI 思考中…（约 10-30 秒）";
  let r;
  try { r = await api("POST", `/api/problems/${S.p.id}/ai/${key}`); }
  catch (e) { toast(e.message, true); btn.disabled = false; btn.textContent = old; return; }
  btn.disabled = false; btn.textContent = old;
  const sug = r.suggestion, target = sec(key === "review" ? "review" : key);
  const picks = [];
  const rows = [];
  for (const [k, v] of Object.entries(sug)) {
    if (Array.isArray(v)) {
      rows.push(h("h3", {}, FIELD_LABELS[k] || k, h("span", { class: "hint small muted" }, "  勾选的条目会追加到现有内容后面")));
      v.forEach((it) => { const cb = h("input", { type: "checkbox", checked: true, style: "width:auto" }); picks.push({ k, it, cb, arr: true });
        rows.push(h("label", { class: "row", style: "align-items:flex-start;flex-wrap:nowrap;margin-bottom:6px" }, cb, h("span", {}, itemText(k, it)))); });
    } else {
      const cur = target[k];
      const empty = cur === undefined || cur === null || cur === "";
      const cb = h("input", { type: "checkbox", checked: empty, style: "width:auto" }); picks.push({ k, it: v, cb });
      rows.push(h("h3", {}, FIELD_LABELS[k] || k), h("label", { class: "row", style: "align-items:flex-start;flex-wrap:nowrap" }, cb,
        h("div", {}, h("div", { style: "white-space:pre-wrap" }, String(v)), !empty ? h("div", { class: "small muted" }, "（勾选会替换你现在写的：" + String(cur).slice(0, 80) + "）") : null)));
    }
  }
  const u = r.usage || {};
  const close = modal([
    h("h2", {}, "✨ AI 建议 · " + STEPS[S.step].title),
    h("div", { class: "callout" }, "这些只是建议。AI 不知道你的真实情况：凡是你没写过的个人/公司情况，都只能当作“假设”，请逐条确认后再采用。"),
    ...rows,
    h("p", { class: "small muted" }, `${u.model || ""} · ${u.seconds ?? "-"}s` + (u.prompt_tokens ? ` · ${u.prompt_tokens}+${u.completion_tokens} tokens` : "") + (u.cost_usd !== undefined ? ` · 约 $${u.cost_usd}` : "")),
    h("div", { class: "row" }, h("span", { class: "spacer" }), h("button", { class: "btn", onclick: () => close() }, "放弃"),
      h("button", { class: "btn primary", onclick: () => {
        let n = 0;
        for (const pk of picks) {
          if (!pk.cb.checked) continue;
          n++;
          if (pk.arr) {
            const item = { ...pk.it };
            if (pk.k === "assumptions") { item.type_by = "AI"; }
            arr(target, pk.k).push(item);
          } else target[pk.k] = pk.it;
          if (key === "experiment" && pk.k === "deadline") S.p.deadline = pk.it;
          if (key === "review" && pk.k === "next_review_date") {}
        }
        close(); changed(); renderStep(); toast(`已采用 ${n} 项建议`);
      } }, "采用勾选的建议")),
  ], true);
}

/* ---------------- 各步骤 ---------------- */
const QUICK = [
  ["costly", "做错代价大吗？", "难以反悔，或影响健康、金钱、职业、重要关系"],
  ["conventional_works", "常规做法有用吗？", "照别人或以前的做法，能解决吗？"],
  ["same_as_others", "我的情况和别人一样吗？", "有没有特殊约束（孩子、时间、预算、身份）？"],
];
function verdict(q) {
  const a = (k) => q[k]?.answer;
  if (QUICK.some(([k]) => typeof a(k) !== "boolean")) return null;
  return a("costly") || !a("conventional_works") || !a("same_as_others");
}
const RENDER = {
  quick() {
    const q = sec("quick");
    const v = verdict(q);
    return h("div", {},
      h("div", { class: "row", style: "margin-bottom:12px" }, jevBtn("quick-check", "快速判断", "⚡ 用 Jev 判断这三个问题"), h("span", { class: "small muted" }, "Jev 只根据你写的问题和背景判断；你的回答为准。")),
      QUICK.map(([k, label, sub]) => {
        const it = q[k] || (q[k] = {});
        const jv = it.jev;
        const flag = jv && jv.confidence < th() && !it.jev_confirmed;
        return h("div", { class: "qc" + (flag ? " flag" : "") },
          h("div", { class: "q" }, label, h("small", {}, sub)),
          yn(() => it.answer, (x) => { it.answer = x; it.by = "user"; if (jv) it.jev_confirmed = true; }),
          jv ? jevChip(jv.answer ? "是" : "否", jv.confidence, it.jev_confirmed) : h("span"),
          jv && (flag || it.answer !== jv.answer) ? h("button", { class: "btn sm", onclick: () => { it.answer = jv.answer; it.jev_confirmed = true; changed(); renderStep(); } }, "采用 Jev") : h("span"));
      }),
      v === null ? h("div", { class: "verdict no" }, "回答完三个问题后显示结论") :
        h("div", { class: "verdict " + (v ? "yes" : "no") }, v ? "✅ 值得跑完整的第一性原理流程" : "⚪ 用常规做法/类比可能就够了——当然你仍然可以继续"));
  },
  define() {
    const d = sec("define");
    return h("div", {},
      field("原始问题", bind(S.p, "title", { area: true, rows: 2 }), "你最初写下的"),
      field("背景和约束", bind(S.p, "background", { area: true, rows: 3, ph: "只有你知道的真实情况" })),
      field("真正要解决的问题", bind(d, "problem_restated", { area: true, rows: 2, ph: "不是某个方案，而是背后的目的" })),
      field("目标", bind(d, "goal", { ph: "一句话目标" })),
      h("div", { class: "grid2" },
        field("成功标准", bind(d, "success_criteria", { area: true, rows: 4, ph: "每行一条，可衡量\n例：连续 2 周每周完成 2 次" }), "每行一条"),
        field("不在本次范围", bind(d, "out_of_scope", { area: true, rows: 4, ph: "每行一条" }), "每行一条")));
  },
  feynman() {
    const d = sec("feynman");
    return h("div", {},
      field("用一句大白话讲清这个问题", bind(d, "one_sentence", { area: true, rows: 2, ph: "讲给一个 10 岁小孩听" })),
      field("打个比方", bind(d, "analogy", { area: true, rows: 2, ph: "就像……" })),
      field("还讲不清 / 模糊的地方", bind(d, "unclear_points", { area: true, rows: 3, ph: "每行一条。卡住的地方就是你还没懂的地方" })));
  },
  decompose() {
    const d = sec("decompose");
    const list = arr(d, "assumptions");
    const nFlag = list.filter((a) => a.jev && a.jev.confidence < th() && !a.jev_confirmed).length;
    return h("div", {},
      h("h3", {}, "假设清单"),
      h("div", { class: "legend" }, h("span", {}, h("b", { class: "type-事实" }, "事实"), "：可验证/你亲身确认"), h("span", {}, h("b", { class: "type-假设" }, "假设"), "：可能被推翻"),
        h("span", {}, h("b", { class: "type-惯例" }, "惯例"), "：只是大家都这么做"), h("span", {}, `⚠ = Jev 置信度低于 ${th()}，需要你确认`)),
      h("div", { class: "row", style: "margin-bottom:10px" }, jevBtn("classify", "自动标注", "🏷 用 Jev 标注 事实/假设/惯例"),
        nFlag ? h("span", { class: "jev warn" }, `${nFlag} 条待确认`) : null),
      rowList(list, (a, i, rm) => {
        const jv = a.jev;
        const flag = jv && jv.confidence < th() && !a.jev_confirmed;
        const sel = bind(a, "type", { options: [{ v: "", t: "未标注" }, ...TYPES], cls: "type-sel v-" + (a.type || ""),
          onchange: (v) => { a.type_by = "user"; if (jv) a.jev_confirmed = true; sel.className = "type-sel v-" + v; setTimeout(renderStep, 0); } });
        return h("div", { class: "item" + (flag ? " flag" : "") },
          h("div", { class: "item-row" }, h("span", { class: "item-no" }, i + 1), bind(a, "statement", { grow: true, ph: "一条说法，例：一周打三次才算坚持" }), sel,
            jv ? h("span", { class: "row", style: "gap:6px;flex-wrap:nowrap" }, jevChip(jv.type, jv.confidence, a.jev_confirmed),
              (flag || a.type !== jv.type) ? h("button", { class: "btn sm", onclick: () => { a.type = jv.type; a.jev_confirmed = true; changed(); renderStep(); } }, "采用") : null) : h("span"),
            del(rm)),
          h("div", { class: "item-sub row", style: "flex-wrap:nowrap" }, bind(a, "reason", { grow: true, ph: "为什么这样标注？（可选）" }),
            a.type_by === "AI" ? h("span", { class: "tag demo" }, "AI 建议") : null));
      }, () => ({ statement: "", type: "", reason: "" }), "添加一条假设"),
      h("h3", {}, "关键现象"),
      bind(d, "key_phenomenon", { ph: "例：计划一周打 3 次，实际只去了 1 天" }),
      h("h3", {}, "5个为什么"),
      whyChain(arr(d, "five_whys"), () => d.key_phenomenon),
      field("根因（假设）", bind(d, "root_cause", { area: true, rows: 2, ph: "拆到这里，真正要改的是什么？" })));
  },
  evidence() {
    const e = sec("evidence");
    const list = arr(sec("decompose"), "assumptions").filter((a) => a.statement);
    const b = e.biases || (e.biases = {});
    const BIAS = [["confirmation", "确认偏误", "只找支持自己的证据"], ["sunk_cost", "沉没成本", "已经投入了，所以硬撑"],
      ["self_blame", "自责归因", "把系统/计划问题归咎于“我不够努力”"], ["availability", "可得性偏差", "被最近、印象深的事带偏"],
      ["overconfidence", "过度自信", "高估自己的判断和执行力"], ["anchoring", "锚定效应", "被第一个数字或方案锁住"]];
    return h("div", {},
      h("h3", {}, "每条说法：有数据支持吗？"),
      h("div", { class: "row", style: "margin-bottom:10px" }, jevBtn("has-data", "数据判断", "🔎 用 Jev 判断“有没有数据支持”"),
        h("span", { class: "small muted" }, "只有你的明确陈述或记录才算数据；推测不算。")),
      list.length ? list.map((a, i) => {
        const jd = a.jev_data;
        const flag = jd && jd.confidence < th() && !a.jev_data_confirmed;
        return h("div", { class: "item" + (flag ? " flag" : "") },
          h("div", { class: "ev-row" }, h("span", { class: "item-no" }, i + 1),
            h("span", {}, a.statement, " ", a.type ? h("span", { class: "small type-" + a.type }, "［" + a.type + "］") : null),
            yn(() => a.has_data, (x) => { a.has_data = x; a.has_data_by = "user"; if (jd) a.jev_data_confirmed = true; }, ["有", "没有"]),
            jd ? jevChip(jd.answer ? "有" : "没有", jd.confidence, a.jev_data_confirmed) : h("span"),
            jd && (flag || a.has_data !== jd.answer) ? h("button", { class: "btn sm", onclick: () => { a.has_data = jd.answer; a.jev_data_confirmed = true; changed(); renderStep(); } }, "采用") : h("span"),
            bind(a, "evidence", { grow: true, ph: a.has_data === false ? "要收集什么数据？" : "依据是什么？" })));
      }) : h("div", { class: "callout info" }, "先在第3步写下假设清单。"),
      h("h3", {}, "偏见自查"),
      BIAS.map(([k, name, desc]) => {
        const it = b[k] || (b[k] = {});
        const cb = h("input", { type: "checkbox", checked: !!it.checked });
        cb.onchange = () => { it.checked = cb.checked; changed(); };
        return h("div", { class: "bias" }, cb, h("span", {}, h("b", {}, name), h("span", { class: "muted small" }, "　" + desc)), bind(it, "note", { ph: "在这个问题里具体表现为？" }));
      }),
      h("div", { class: "grid2", style: "margin-top:14px" },
        field("可变因素", bind(e, "changeable", { area: true, rows: 4, ph: "每行一条：你能改变的" })),
        field("不可变约束", bind(e, "fixed", { area: true, rows: 4, ph: "每行一条：改变不了的（必须是真实情况）" }))));
  },
  rebuild() {
    const r = sec("rebuild");
    const opts = arr(r, "options");
    if (!opts.length) opts.push({ name: "", description: "", pros: "", cons: "" });
    return h("div", {},
      h("div", { class: "row", style: "justify-content:space-between;align-items:flex-end" }, h("h3", {}, "基本事实（积木）"),
        h("button", { class: "btn sm", onclick: () => {
          const facts = arr(sec("decompose"), "assumptions").filter((a) => a.type === "事实" && a.statement).map((a) => a.statement);
          const fixed = lines(sec("evidence").fixed).map((x) => "约束：" + x);
          const cur = lines(r.base_facts);
          r.base_facts = [...cur, ...[...facts, ...fixed].filter((x) => !cur.includes(x))].join("\n");
          changed(); renderStep();
        } }, "从第3、4步带入事实和约束")),
      bind(r, "base_facts", { area: true, rows: 4, ph: "每行一条：确认过的事实和不可变约束" }),
      h("h3", {}, "方案（1-3 个）"),
      opts.map((o, i) => h("div", { class: "opt-card" + (o.name && r.recommended === o.name ? " rec" : "") },
        h("div", { class: "row", style: "flex-wrap:nowrap" }, bind(o, "name", { ph: `方案 ${i + 1} 名称` }),
          h("button", { class: "btn sm" + (o.name && r.recommended === o.name ? " primary" : ""), onclick: () => { r.recommended = o.name; changed(); renderStep(); } }, r.recommended === o.name && o.name ? "⭐ 已推荐" : "设为推荐"),
          opts.length > 1 ? del(() => { opts.splice(i, 1); changed(); renderStep(); }) : null),
        h("div", { style: "margin-top:8px" }, bind(o, "description", { area: true, rows: 2, ph: "具体做法：只用上面的事实，从零怎么做？" })),
        h("div", { class: "grid2", style: "margin-top:8px" }, bind(o, "pros", { ph: "优点" }), bind(o, "cons", { ph: "缺点" })))),
      opts.length < 3 ? h("button", { class: "btn sm", onclick: () => { opts.push({ name: "", description: "", pros: "", cons: "" }); changed(); renderStep(); } }, "＋ 添加方案") : null);
  },
  premortem() {
    const pm = sec("premortem");
    return h("div", {},
      h("h3", {}, "假设方案失败了，最可能是因为……"),
      rowList(arr(pm, "failure_modes"), (f, i, rm) => h("div", { class: "fm" }, bind(f, "mode", { grow: true, ph: "失败方式" }),
        bind(f, "likelihood", { options: ["高", "中", "低"] }), bind(f, "prevention", { grow: true, ph: "预防措施" }), del(rm)),
        () => ({ mode: "", likelihood: "中", prevention: "" }), "添加失败方式"),
      field("出现就停下来重新评估的信号", bind(pm, "stop_signals", { area: true, rows: 3, ph: "每行一条" })));
  },
  experiment() {
    const x = sec("experiment");
    return h("div", {},
      field("试什么", bind(x, "what_to_test", { area: true, rows: 2, ph: "要验证的关键假设或方案" })),
      field("具体步骤", bind(x, "steps", { area: true, rows: 3, ph: "每行一步" })),
      h("div", { class: "grid3" },
        field("持续天数", bind(x, "duration_days", { type: "number", ph: "14", onchange: (v) => {
          if (v && !x.deadline) { const d = new Date(); d.setDate(d.getDate() + Number(v)); x.deadline = d.toISOString().slice(0, 10); S.p.deadline = x.deadline; setTimeout(renderStep, 0); } } })),
        field("验证截止日", bind(x, "deadline", { type: "date", onchange: (v) => { S.p.deadline = v; } })),
        field("复盘日", bind(S.p, "review_date", { type: "date" }))),
      field("成本", bind(x, "cost", { ph: "时间 / 金钱 / 精力" })),
      h("h3", {}, "指标"),
      rowList(arr(x, "metrics"), (m, i, rm) => h("div", { class: "metric" }, bind(m, "name", { ph: "指标" }), bind(m, "target", { ph: "目标值" }),
        bind(m, "how", { ph: "怎么测量/记录" }), del(rm)), () => ({ name: "", target: "", how: "" }), "添加指标"));
  },
  review() {
    const rv = sec("review");
    const x = sec("experiment");
    const acts = rv.metric_actuals || (rv.metric_actuals = {});
    const assumptions = arr(sec("decompose"), "assumptions").filter((a) => a.statement);
    const dl = h("datalist", { id: "assump-list" }, assumptions.map((a) => h("option", { value: a.statement })));
    return h("div", {}, dl,
      x.what_to_test ? h("div", { class: "callout info" }, `验证内容：${x.what_to_test}　截止：${x.deadline || "-"}`) : null,
      h("h3", {}, "实际结果"),
      (x.metrics || []).filter((m) => m.name).map((m) => field(`${m.name}（目标：${m.target || "-"}）`, bind(acts, m.name, { ph: "实际是多少？" }))),
      field("还发生了什么？", bind(rv, "actual", { area: true, rows: 3, ph: "意外情况、新发现的事实或约束" })),
      field("差距", bind(rv, "gap_summary", { area: true, rows: 2, ph: "计划和实际差在哪里？" })),
      h("h3", {}, "对差距的 5 个为什么"),
      whyChain(arr(rv, "five_whys"), () => rv.gap_summary),
      h("h3", {}, "被推翻的假设"),
      rowList(arr(rv, "overturned"), (o, i, rm) => h("div", { class: "ot" }, (() => { const el = bind(o, "assumption", { ph: "选择或输入一条假设" }); el.setAttribute("list", "assump-list"); return el; })(),
        bind(o, "evidence", { grow: true, ph: "证据" }), del(rm)), () => ({ assumption: "", evidence: "" }), "添加"),
      h("div", { class: "grid2", style: "margin-top:12px" },
        field("被证实的假设", bind(rv, "confirmed", { area: true, rows: 3, ph: "每行一条" })),
        field("更新后的事实", bind(rv, "updated_facts", { area: true, rows: 3, ph: "每行一条" }))),
      field("经验教训", bind(rv, "lessons", { area: true, rows: 2, ph: "每行一条" })),
      h("h3", {}, "下一轮迭代"),
      h("div", { class: "grid2" }, field("保留", bind(rv, "next_keep", { area: true, rows: 2 })), field("改变", bind(rv, "next_change", { area: true, rows: 2 }))),
      h("div", { class: "grid2" }, field("下一个小实验", bind(rv, "next_experiment", { ph: "下一轮试什么" })), field("下次复盘", bind(rv, "next_review_date", { type: "date" }))),
      h("div", { class: "row", style: "margin-top:10px" },
        h("button", { class: "btn primary", onclick: async () => { S.p.status = "完成"; await save(); toast("已标记为完成 🎉"); renderWizard(); } }, S.p.status === "完成" ? "✓ 已完成" : "复盘完成，标记为完成"),
        h("button", { class: "btn", onclick: async () => {
          await save();
          const facts = [...lines(rv.updated_facts), ...lines(sec("evidence").fixed).map((f) => "约束：" + f)];
          const np = await api("POST", "/api/problems", { title: S.p.title + "（下一轮）", domain: S.p.domain, importance: S.p.importance,
            background: [S.p.background, rv.next_experiment ? "下一轮实验：" + rv.next_experiment : "", facts.length ? "已确认的事实：" + facts.join("；") : ""].filter(Boolean).join("\n"),
            data: { define: { ...sec("define") } } });
          S.p.status = "完成"; await save();
          toast("已创建下一轮问题"); location.hash = `#/p/${np.id}/0`;
        } }, "基于下一轮新建问题")));
  },
};
function whyChain(list, seed) {
  return h("div", { class: "why-chain" },
    list.map((w, i) => h("div", { class: "why" }, h("span", { class: "why-no" }, i + 1), bind(w, "why", { grow: true, ph: "为什么……？" }), bind(w, "answer", { grow: true, ph: "因为……" }),
      bind(w, "type", { options: [{ v: "", t: "未标注" }, ...TYPES], cls: "type-sel v-" + (w.type || ""), onchange: () => setTimeout(renderStep, 0) }),
      del(() => { list.splice(i, 1); changed(); renderStep(); }))),
    h("button", { class: "btn sm", onclick: () => {
      const prev = list.length ? list[list.length - 1].answer : seed();
      list.push({ why: prev ? `为什么${String(prev).replace(/^因为/, "").replace(/[。.]$/, "")}？` : "为什么……？", answer: "", type: "" });
      changed(); renderStep();
    } }, list.length ? "＋ 再问一个为什么" : "＋ 开始追问"));
}
async function download(ext) {
  await save();
  try {
    const r = await rawFetch(`/api/problems/${S.p.id}/export.${ext}`);
    if (!r.ok) throw new Error(r.statusText);
    const blob = await r.blob();
    const cd = r.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename\*=UTF-8''([^;]+)/);
    const a = h("a", { href: URL.createObjectURL(blob), download: m ? decodeURIComponent(m[1]) : `problem-${S.p.id}.${ext}` });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  } catch (e) { toast("导出失败：" + e.message, true); }
}
async function previewMd() {
  await save();
  const r = await rawFetch(`/api/problems/${S.p.id}/export.md?download=0`);
  const txt = await r.text();
  modal([h("div", { class: "row" }, h("h2", {}, "报告预览（Markdown）"), h("span", { class: "spacer" }),
    h("button", { class: "btn sm", onclick: () => { navigator.clipboard.writeText(txt); toast("已复制"); } }, "复制")), h("pre", {}, txt)], true);
}
window.addEventListener("beforeunload", () => { if (S.p) save(); });
boot();
