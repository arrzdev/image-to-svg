const $ = (id) => document.getElementById(id);

async function fill(id, url) {
  const items = await (await fetch(url)).json();
  $(id).innerHTML = items.map((v) => `<option>${v}</option>`).join("");
}

async function init() {
  await Promise.all([fill("image", "/api/images"), fill("version", "/api/versions")]);
  $("version").value = [...$("version").options].at(-1).value; // latest by default
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
    $("output").innerHTML = r.svg;
    $("meta").textContent = `· ${version} · ${r.seconds}s · ${r.kb} KB`;
    const t = $("targetPanel");
    if (r.target) {
      t.style.display = "";
      $("target").innerHTML = `<img src="${r.target}">`;
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
