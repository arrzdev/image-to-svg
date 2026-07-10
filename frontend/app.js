const $ = (id) => document.getElementById(id);

// Render an SVG to a high-resolution raster before display. The browser
// rasterizes INLINE SVG at the panel's on-screen size (~480px), where our
// ~1px strokes go sub-pixel and drop out — the "missing strokes" the eye
// sees vs the high-res production-line render. Rasterizing to a large canvas
// first (crisp strokes), then letting CSS scale the canvas down, matches how
// the production line renders (draw big, downsample) and preserves thin lines
// as anti-aliased gray instead of dropping them.
const HIRES = 2048;
function showSvgHiRes(container, svgText) {
  const blob = new Blob([svgText], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const img = new Image();
  img.onload = () => {
    const ar =
      img.naturalWidth && img.naturalHeight
        ? img.naturalHeight / img.naturalWidth
        : 1;
    const cw = HIRES;
    const ch = Math.max(1, Math.round(HIRES * ar));
    const canvas = document.createElement("canvas");
    canvas.width = cw;
    canvas.height = ch;
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, 0, 0, cw, ch);
    container.innerHTML = "";
    canvas.style.width = "100%";
    canvas.style.height = "auto";
    container.appendChild(canvas);
    URL.revokeObjectURL(url);
  };
  img.onerror = () => {
    container.innerHTML = svgText; // fallback: inline SVG
    URL.revokeObjectURL(url);
  };
  img.src = url;
}

async function fill(id, url) {
  const items = await (await fetch(url)).json();
  $(id).innerHTML = items.map((v) => `<option>${v}</option>`).join("");
}

// Version names are `prefix-N` (quant-11, ideal-2). Group by prefix into
// <optgroup>s and sort each group numerically 1→∞ (plain string sort puts v10
// before v3 and 11 before 2). Names without a numeric suffix (e.g. "staged")
// go in a trailing "other" group.
// active lineage first. quant=quantize-first, region=region-first (was ideal),
// edge=boundary-first.
const GROUP_ORDER = ["edge", "region", "quant"];
function parseVersion(v) {
  const m = /^(.+)-(\d+)$/.exec(v);
  return m ? { prefix: m[1], num: +m[2] } : { prefix: "other", num: -1 };
}
async function fillVersions() {
  const items = await (await fetch("/api/versions")).json();
  const groups = {};
  for (const v of items) {
    const { prefix } = parseVersion(v);
    (groups[prefix] ||= []).push(v);
  }
  const prefixes = Object.keys(groups).sort((a, b) => {
    const ia = GROUP_ORDER.indexOf(a), ib = GROUP_ORDER.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
  });
  const sel = $("version");
  sel.innerHTML = "";
  for (const p of prefixes) {
    const og = document.createElement("optgroup");
    og.label = p;
    groups[p]
      .sort((a, b) => parseVersion(a).num - parseVersion(b).num)
      .forEach((v) => og.appendChild(new Option(v, v)));
    sel.appendChild(og);
  }
  return items;
}

async function init() {
  const [, versions] = await Promise.all([
    fill("image", "/api/images"),
    fillVersions(),
  ]);
  // Default to the newest quant version (quant-12 hit all Recraft metric axes
  // >= 0.90; the edge lineage over-fragments ~10x). Fall back edge -> region.
  const best = (pred) =>
    versions
      .map(parseVersion)
      .filter(pred)
      .sort((a, b) => b.num - a.num)[0];
  const pick =
    best((x) => x.prefix === "quant") ||
    best((x) => x.prefix === "edge") ||
    best((x) => x.prefix === "region") ||
    best((x) => x.num >= 0);
  if (pick) $("version").value = `${pick.prefix}-${pick.num}`;
}

async function run() {
  const image = $("image").value, version = $("version").value;
  $("run").disabled = true;
  $("status").textContent = `running ${version} on ${image}…`;
  $("panels").hidden = true;
  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image, version }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const r = await res.json();

    $("original").innerHTML = `<img src="/inputs/${encodeURIComponent(image)}">`;
    showSvgHiRes($("output"), r.svg);
    $("meta").textContent = `· ${version} · ${r.seconds}s · ${r.kb} KB`;
    const t = $("targetPanel");
    if (r.target) {
      t.style.display = "";
      $("target").innerHTML = `<img src="${r.target}">`;
      $("targetMeta").textContent =
        r.target_kb != null ? `· ${r.target_kb} KB` : "";
    } else {
      t.style.display = "none";
    }
    $("panels").hidden = false;
    $("status").textContent = `saved: ${r.saved}`;
  } catch (e) {
    $("status").textContent = `✗ ${e.message}`;
  } finally {
    $("run").disabled = false;
  }
}

$("run").addEventListener("click", run);
init();

// ---------------------------------------------------------------- tabs
for (const btn of document.querySelectorAll("#tabs .tab")) {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#tabs .tab").forEach((b) =>
      b.classList.toggle("active", b === btn));
    $("tab-tester").hidden = btn.dataset.tab !== "tester";
    $("tab-edgelab").hidden = btn.dataset.tab !== "edgelab";
  });
}

// ------------------------------------------------------------- edge lab
// Boundary-first playground: POST the current params, show the three stage
// rasters (edges / bucket fills / composite). Auto-run debounces slider drags.
const EL_IDS = ["el-dim", "el-pre", "el-prestr", "el-thr", "el-close",
                "el-mincell", "el-image"];

function elParams() {
  return {
    image: $("el-image").value,
    work_dim: +$("el-dim").value,
    pre: $("el-pre").value,
    pre_strength: +$("el-prestr").value,
    threshold: +$("el-thr").value,
    close_k: +$("el-close").value,
    min_cell: +$("el-mincell").value,
  };
}

let elBusy = false, elQueued = false;
async function elRun() {
  if (elBusy) { elQueued = true; return; }
  elBusy = true;
  $("el-run").disabled = true;
  $("el-status").textContent = "running…";
  try {
    const res = await fetch("/api/edgelab", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(elParams()),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const r = await res.json();
    $("el-original").innerHTML =
      `<img src="/inputs/${encodeURIComponent($("el-image").value)}">`;
    $("el-edges").innerHTML = `<img src="${r.edges}">`;
    $("el-fills").innerHTML = `<img src="${r.fills}">`;
    $("el-composite").innerHTML = `<img src="${r.composite}">`;
    $("el-panels").hidden = false;
    const s = r.stats;
    $("el-status").textContent =
      `${s.dim} · ${s.cells} cells · ${(s.boundary_px / 1000).toFixed(0)}k boundary px · ${s.seconds}s`;
  } catch (e) {
    $("el-status").textContent = `✗ ${e.message}`;
  } finally {
    elBusy = false;
    $("el-run").disabled = false;
    if (elQueued) { elQueued = false; elRun(); }
  }
}

let elTimer = null;
function elChanged() {
  $("el-prestr-v").textContent = $("el-prestr").value;
  $("el-thr-v").textContent = $("el-thr").value;
  $("el-mincell-v").textContent = $("el-mincell").value;
  if ($("el-auto").checked) {
    clearTimeout(elTimer);
    elTimer = setTimeout(elRun, 350);
  }
}

async function elInit() {
  await fill("el-image", "/api/images");
  const opts = [...$("el-image").options].map((o) => o.value);
  if (opts.includes("chopchop.png")) $("el-image").value = "chopchop.png";
  for (const id of EL_IDS) {
    $(id).addEventListener("input", elChanged);
    $(id).addEventListener("change", elChanged);
  }
  $("el-run").addEventListener("click", elRun);
}
elInit();
