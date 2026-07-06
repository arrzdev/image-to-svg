"use strict";

const $ = (s) => document.querySelector(s);
const state = {
  pipelines: [],   // schema list
  selected: new Set(),
  params: {},      // {pid: {key: value}}
  file: null,      // File object or null
  sample: null,    // sample name or null
};

// ---------- init ----------
async function init() {
  const [pipes, samples] = await Promise.all([
    fetch("/api/pipelines").then((r) => r.json()),
    fetch("/api/samples").then((r) => r.json()),
  ]);
  state.pipelines = pipes.pipelines;
  renderAiStatus(pipes.ai);
  renderPipelines();
  renderSamples(samples.samples);
  wireInputs();
}

function renderAiStatus(ai) {
  const badge = $("#ai-badge");
  badge.textContent = ai.configured ? `AI: ${ai.model}` : "AI: off (no key)";
  badge.classList.toggle("on", ai.configured);
  const sel = $("#ai-prompt");
  ai.prompts.forEach((p) => {
    const o = document.createElement("option");
    o.value = p; o.textContent = p.replace(/_/g, " ");
    sel.appendChild(o);
  });
  $("#ai-hint").textContent = ai.configured
    ? "Applies a Gemini image edit before vectorizing, then measures SSIM vs the AI output."
    : ai.note;
  if (!ai.configured) sel.disabled = true;
}

function renderSamples(samples) {
  const sel = $("#sample");
  sel.innerHTML = '<option value="">—</option>';
  samples.forEach((s) => {
    const o = document.createElement("option");
    o.value = s; o.textContent = s;
    sel.appendChild(o);
  });
}

function renderPipelines() {
  const box = $("#pipelines");
  box.innerHTML = "";
  state.pipelines.forEach((p) => {
    state.params[p.id] = {};
    p.params.forEach((pp) => (state.params[p.id][pp.key] = pp.default));

    const el = document.createElement("div");
    el.className = "pipe" + (p.available ? "" : " unavailable");

    const head = document.createElement("div");
    head.className = "pipe-head";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.disabled = !p.available;
    cb.checked = p.available;               // default: all available on
    if (p.available) state.selected.add(p.id);
    cb.addEventListener("click", (e) => e.stopPropagation());
    cb.addEventListener("change", () => {
      cb.checked ? state.selected.add(p.id) : state.selected.delete(p.id);
    });
    const name = document.createElement("div");
    name.className = "pipe-name";
    name.textContent = p.name;
    const gear = document.createElement("div");
    gear.className = "pipe-gear";
    gear.textContent = p.available ? "params ▾" : "unavailable";

    head.append(cb, name, gear);

    const desc = document.createElement("p");
    desc.className = "pipe-desc";
    desc.textContent = p.available ? p.description : p.unavailable_reason;

    const params = document.createElement("div");
    params.className = "pipe-params";
    p.params.forEach((pp) => params.appendChild(renderParam(p.id, pp)));

    head.addEventListener("click", () => {
      if (!p.available) return;
      params.classList.toggle("open");
    });

    el.append(head, desc);
    if (p.available) el.append(params);
    box.appendChild(el);
  });
}

function renderParam(pid, pp) {
  const wrap = document.createElement("div");
  wrap.className = "param";
  const id = `p_${pid}_${pp.key}`;

  if (pp.type === "select") {
    const lab = document.createElement("label");
    lab.innerHTML = `<span>${pp.label}</span>`;
    const sel = document.createElement("select");
    (pp.options || []).forEach((o) => {
      const opt = document.createElement("option");
      opt.value = o; opt.textContent = o;
      if (o === pp.default) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.addEventListener("change", () => (state.params[pid][pp.key] = sel.value));
    wrap.append(lab, sel);
  } else if (pp.type === "bool") {
    const lab = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = !!pp.default;
    cb.addEventListener("change", () => (state.params[pid][pp.key] = cb.checked));
    lab.append(document.createTextNode(pp.label), cb);
    wrap.append(lab);
  } else {
    const lab = document.createElement("label");
    const valSpan = document.createElement("span");
    valSpan.className = "pval";
    valSpan.textContent = pp.default;
    lab.innerHTML = `<span>${pp.label}</span>`;
    lab.appendChild(valSpan);
    const rng = document.createElement("input");
    rng.type = "range";
    rng.min = pp.min ?? 0; rng.max = pp.max ?? 100;
    rng.step = pp.step ?? (pp.type === "int" ? 1 : 0.1);
    rng.value = pp.default;
    rng.addEventListener("input", () => {
      const v = pp.type === "int" ? parseInt(rng.value, 10) : parseFloat(rng.value);
      state.params[pid][pp.key] = v;
      valSpan.textContent = v;
    });
    wrap.append(lab, rng);
  }
  if (pp.help) {
    const h = document.createElement("div");
    h.className = "phelp"; h.textContent = pp.help;
    wrap.appendChild(h);
  }
  return wrap;
}

function wireInputs() {
  $("#file").addEventListener("change", (e) => {
    const f = e.target.files[0];
    if (!f) return;
    state.file = f; state.sample = null;
    $("#sample").value = "";
    const url = URL.createObjectURL(f);
    showPreview(url);
  });
  $("#sample").addEventListener("change", (e) => {
    const s = e.target.value;
    if (!s) return;
    state.sample = s; state.file = null;
    $("#file").value = "";
    showPreview(`/samples/${s}`);
  });
  $("#run").addEventListener("click", run);
  $("#optimize").addEventListener("click", runOptimize);
  $("#tournament").addEventListener("click", runTournament);
  $("#modal-close").addEventListener("click", () => $("#modal").classList.add("hidden"));
  $("#modal").addEventListener("click", (e) => {
    if (e.target.id === "modal") $("#modal").classList.add("hidden");
  });
  // default to first sample for instant gratification
  const firstSample = $("#sample").options[1];
  if (firstSample) { $("#sample").value = firstSample.value; $("#sample").dispatchEvent(new Event("change")); }
}

function showPreview(url) {
  $("#preview-wrap").classList.remove("hidden");
  const img = $("#source-preview");
  img.onload = () => ($("#source-dims").textContent = `${img.naturalWidth} × ${img.naturalHeight}px`);
  img.src = url;
}

// ---------- run ----------
async function run() {
  if (!state.file && !state.sample) { setStatus("Pick an image first."); return; }
  if (state.selected.size === 0) { setStatus("Select at least one pipeline."); return; }

  const btn = $("#run");
  btn.disabled = true;
  setStatus("Vectorizing…");

  const fd = new FormData();
  if (state.file) fd.append("image", state.file);
  else fd.append("sample", state.sample);
  fd.append("pipelines", [...state.selected].join(","));
  fd.append("params_json", JSON.stringify(state.params));
  const aiPrompt = $("#ai-prompt").value;
  if (aiPrompt) fd.append("ai_preprocess", aiPrompt);

  // Processing resolution: "original" sends the source's true long side.
  const procSel = $("#process-dim").value;
  let procDim = parseInt(procSel, 10);
  if (procSel === "orig") {
    const img = $("#source-preview");
    procDim = Math.max(img.naturalWidth || 0, img.naturalHeight || 0) || 4096;
  }
  fd.append("process_dim", String(procDim));
  fd.append("simplify_eps", $("#simplify-eps").value);

  const t0 = performance.now();
  try {
    const res = await fetch("/api/vectorize", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    renderResults(data);
    const total = Math.round(performance.now() - t0);
    let msg = `Done in ${total}ms.`;
    if (data.ai) msg += data.ai.applied ? " AI preprocess applied." : ` AI preprocess failed: ${data.ai.error}`;
    setStatus(msg);
  } catch (e) {
    setStatus("Error: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

function setStatus(t) { $("#status").textContent = t; }

async function runTournament() {
  if (!state.file && !state.sample) { setStatus("Pick an image first."); return; }
  const btn = $("#tournament");
  btn.disabled = true; $("#run").disabled = true; $("#optimize").disabled = true;
  const mode = $("#opt-mode").value;
  setStatus(`Tournament (${mode})… running candidate portfolio`);

  const fd = new FormData();
  if (state.file) fd.append("image", state.file);
  else fd.append("sample", state.sample);
  fd.append("mode", mode);
  if ($("#dv-refine").checked) fd.append("dv", "true");

  const t0 = performance.now();
  const tick = setInterval(() =>
    setStatus(`Tournament (${mode})… ${Math.round((performance.now() - t0) / 1000)}s`), 1000);
  try {
    const res = await fetch("/api/tournament", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    renderResults(data);
    const a = data.analysis || {};
    setStatus(`Tournament done in ${data.seconds}s · image kind: ${a.kind} (${a.n_colors} colors) · leaderboard ranked left→right`);
  } catch (e) {
    setStatus("Tournament error: " + e.message);
  } finally {
    clearInterval(tick);
    btn.disabled = false; $("#run").disabled = false; $("#optimize").disabled = false;
  }
}

async function runOptimize() {
  if (!state.file && !state.sample) { setStatus("Pick an image first."); return; }
  const btn = $("#optimize");
  btn.disabled = true; $("#run").disabled = true;
  const mode = $("#opt-mode").value;
  setStatus(`Auto-optimizing (${mode})… searching params + resolution + simplify, ~1–2 min`);

  const fd = new FormData();
  if (state.file) fd.append("image", state.file);
  else fd.append("sample", state.sample);
  fd.append("mode", mode);

  const t0 = performance.now();
  const tick = setInterval(() =>
    setStatus(`Auto-optimizing (${mode})… ${Math.round((performance.now() - t0) / 1000)}s`), 1000);
  try {
    const res = await fetch("/api/optimize", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    renderResults(data);
    const r = data.results[0];
    setStatus(`Optimized in ${Math.round((performance.now() - t0) / 1000)}s · ${r.evals} configs tried · quality ${r.metrics.quality}`);
  } catch (e) {
    setStatus("Optimize error: " + e.message);
  } finally {
    clearInterval(tick);
    btn.disabled = false; $("#run").disabled = false;
  }
}

// ---------- results ----------
function renderResults(data) {
  const grid = $("#results");
  grid.innerHTML = "";

  // source card
  grid.appendChild(sourceCard(data.source));

  const ok = data.results.filter((r) => r.ok && r.metrics && r.metrics.quality != null);
  const bestQuality = ok.length ? Math.max(...ok.map((r) => r.metrics.quality)) : null;
  const bestSize = ok.length ? Math.min(...ok.map((r) => r.metrics.gzip_bytes)) : null;

  data.results.forEach((r) => grid.appendChild(resultCard(r, bestQuality, bestSize)));
}

function sourceCard(src) {
  const card = document.createElement("div");
  card.className = "card source";
  const traced = src.proc_width && (src.proc_width !== src.width || src.proc_height !== src.height)
    ? `${src.proc_width}×${src.proc_height}` : "same";
  card.innerHTML = `
    <div class="card-canvas"><img src="${src.data_url}" alt="source"/></div>
    <div class="card-title"><span class="tag">SOURCE</span> original raster</div>
    <div class="metrics">
      <div class="metric"><span class="k">output size</span><span class="v">${src.width}×${src.height}</span></div>
      <div class="metric"><span class="k">traced at</span><span class="v">${traced}</span></div>
    </div>`;
  return card;
}

function resultCard(r, bestQuality, bestSize) {
  const card = document.createElement("div");
  card.className = "card";
  if (!r.ok) {
    card.innerHTML = `
      <div class="card-title"><span class="fail">✕ ${r.pipeline}</span></div>
      <div class="card-error">${escapeHtml(r.error || "failed")}</div>`;
    return card;
  }
  const m = r.metrics;
  const isBest = m.quality != null && m.quality === bestQuality;
  const isBestSize = m.gzip_bytes === bestSize;
  if (isBest) card.classList.add("best");

  const canvas = document.createElement("div");
  canvas.className = "card-canvas";
  canvas.innerHTML = r.svg;
  const svgEl = canvas.querySelector("svg");
  if (svgEl) { svgEl.removeAttribute("width"); svgEl.removeAttribute("height"); svgEl.style.width = "100%"; svgEl.style.height = "100%"; }

  const title = document.createElement("div");
  title.className = "card-title";
  title.innerHTML = `${r.pipeline}${isBest ? '<span class="tag">best</span>' : ""}`;

  // Headline quality bar + component breakdown.
  const q = m.quality;
  const quom = document.createElement("div");
  quom.className = "quality";
  quom.innerHTML = `
    <div class="q-head"><span>quality</span><span class="q-val ${isBest ? "good" : ""}">${q != null ? q.toFixed(4) : "—"}</span></div>
    <div class="q-bar"><div class="q-fill" style="width:${q != null ? Math.max(0, (q - 0.8) / 0.2 * 100).toFixed(1) : 0}%"></div></div>`;

  const metrics = document.createElement("div");
  metrics.className = "metrics";
  metrics.innerHTML = [
    metricRow("structure", m.ms_ssim ?? "—", ""),
    metricRow("color", m.color_score ?? "—", ""),
    metricRow("edges", m.edge_score ?? "—", ""),
    metricRow("local", m.local_score ?? "—", m.local_score != null && m.local_score < 0.5 ? "bad" : ""),
    metricRow("strokes", m.coherence ?? "—", m.coherence != null && m.coherence < 0.4 ? "bad" : ""),
    metricRow("paths", m.num_paths, ""),
    metricRow("points", m.num_points, ""),
    metricRow("gzip", fmtBytes(m.gzip_bytes), isBestSize ? "good" : ""),
    metricRow("time", r.ms + " ms", ""),
  ].join("");

  const actions = document.createElement("div");
  actions.className = "card-actions";
  const dl = document.createElement("a");
  dl.textContent = "Download";
  dl.href = URL.createObjectURL(new Blob([r.svg], { type: "image/svg+xml" }));
  dl.download = `${r.pipeline}.svg`;
  const view = document.createElement("button");
  view.textContent = "View source";
  view.addEventListener("click", () => showSource(r.pipeline, r.svg));
  actions.append(dl, view);

  card.append(canvas, title, quom, metrics);
  if (r.config) {
    const cfg = document.createElement("div");
    cfg.className = "card-config";
    cfg.textContent = Object.entries(r.config).map(([k, v]) => `${k}=${v}`).join(" ");
    card.appendChild(cfg);
  }
  card.appendChild(actions);
  return card;
}

function metricRow(k, v, cls) {
  return `<div class="metric"><span class="k">${k}</span><span class="v ${cls}">${v}</span></div>`;
}
function fmtBytes(b) {
  if (b == null) return "—";
  return b < 1024 ? b + " B" : (b / 1024).toFixed(1) + " KB";
}
function showSource(name, svg) {
  $("#modal-title").textContent = name + ".svg";
  $("#modal-src").textContent = svg;
  $("#modal").classList.remove("hidden");
}
function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

init();
