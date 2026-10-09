// Web page of SOFIA Filter Studio. The form lives here; the design runs in Python (worker.js).
import { ResponsePlot } from "./plot.js";
import { SchematicView } from "./schematicview.js";

const $ = (id) => document.getElementById(id);
const TEXT_FIELDS = ["fp", "fs", "fp1", "fp2", "fs1", "fs2", "ap", "as", "cap"];
const BAND_FIELDS = ["fp1", "fp2", "fs1", "fs2"];
const SELECTS = ["topology", "opamp", "series", "mounting"];
const SINGLE_KINDS = new Set(["lowpass", "highpass"]);
const DEBOUNCE_MS = 160;

const state = {
  options: null,
  form: null,
  bandValues: {},
  singleKind: "lowpass",
  ready: false,
  inFlight: false,
  dirty: false,
  seq: 0,
  sentAt: 0,
  view: null,
};
let plot;
let worker;
let schematicView;
let pcbView;
let pcbWorker = null;
const pending = new Map();
let requestCounter = 0;
let timer;

// Icons -----------------------------------------------------------------------------------------
// Same shapes as gui/icons.py, on a 64x36 box.
function shapePath(kind) {
  const left = 7;
  const right = 60;
  const top = 7;
  const bottom = 30;
  const w = right - left;
  const x = (f) => (left + w * f).toFixed(2);
  switch (kind) {
    case "lowpass":
      return `M${left} ${top}H${x(0.42)}C${x(0.58)} ${top} ${x(0.62)} ${bottom} ${x(0.82)} ${bottom}H${right}`;
    case "highpass":
      return `M${left} ${bottom}H${x(0.18)}C${x(0.38)} ${bottom} ${x(0.42)} ${top} ${x(0.58)} ${top}H${right}`;
    case "bandpass":
      return (
        `M${left} ${bottom}H${x(0.12)}C${x(0.3)} ${bottom} ${x(0.32)} ${top} ${x(0.42)} ${top}H${x(0.58)}` +
        `C${x(0.68)} ${top} ${x(0.7)} ${bottom} ${x(0.88)} ${bottom}H${right}`
      );
    default:
      return (
        `M${left} ${top}H${x(0.3)}C${x(0.42)} ${top} ${x(0.44)} ${bottom} ${x(0.5)} ${bottom}` +
        `C${x(0.56)} ${bottom} ${x(0.58)} ${top} ${x(0.7)} ${top}H${right}`
      );
  }
}

function kindIcon(kind) {
  return (
    `<svg viewBox="0 0 64 36" aria-hidden="true"><path class="axis" d="M3 3V33H62"/>` +
    `<path class="curve" d="${shapePath(kind)}"/></svg>`
  );
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// Form ------------------------------------------------------------------------------------------
function radioGroup(container, items, name, render) {
  container.innerHTML = "";
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("role", "radio");
    button.dataset.value = item.value;
    button.className = name === "kind" ? "kind" : "segment";
    button.innerHTML = render(item);
    button.addEventListener("click", () => {
      if (name === "kind") changeKind(item.value);
      else {
        state.form[name] = item.value;
        syncRadios();
        schedule();
      }
    });
    container.append(button);
  }
  // Arrow keys move between options, like native radio buttons.
  container.addEventListener("keydown", (event) => {
    const buttons = [...container.querySelectorAll("button")];
    const index = buttons.indexOf(document.activeElement);
    if (index < 0) return;
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
    if (!step) return;
    event.preventDefault();
    const next = buttons[(index + step + buttons.length) % buttons.length];
    next.focus();
    next.click();
  });
}

function buildForm(options) {
  radioGroup($("kinds"), options.kinds, "kind", (item) => `${kindIcon(item.value)}<span>${escapeHtml(item.label)}</span>`);
  radioGroup(
    $("approximations"),
    options.approximations,
    "approximation",
    (item) => `${escapeHtml(item.label)}<small>${escapeHtml(item.detail)}</small>`,
  );
  const lists = { topology: options.topologies, opamp: options.opamps, series: options.series, mounting: options.mountings };
  for (const name of SELECTS) {
    const select = $(name);
    select.innerHTML = lists[name].map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join("");
    select.addEventListener("change", () => {
      state.form[name] = select.value;
      schedule();
    });
  }
  for (const name of TEXT_FIELDS) {
    $(name).addEventListener("input", (event) => {
      state.form[name] = event.target.value;
      schedule();
    });
  }
  $("auto_cap").addEventListener("change", (event) => {
    state.form.auto_cap = event.target.checked;
    schedule();
  });
  $("version").textContent = `SOFIA Filter Studio ${options.version}`;
}

function syncRadios() {
  for (const [id, name] of [["kinds", "kind"], ["approximations", "approximation"]]) {
    for (const button of $(id).querySelectorAll("button")) {
      const checked = button.dataset.value === state.form[name];
      button.setAttribute("aria-checked", String(checked));
      button.tabIndex = checked ? 0 : -1;
    }
  }
}

function applyForm() {
  const form = state.form;
  for (const name of TEXT_FIELDS) $(name).value = form[name];
  for (const name of SELECTS) $(name).value = form[name];
  $("auto_cap").checked = Boolean(form.auto_cap);
  syncRadios();
  const single = SINGLE_KINDS.has(form.kind);
  $("single-spec").hidden = !single;
  $("band-spec").hidden = single;
  $("spec-hint").textContent = state.options.hints[form.kind];
}

function changeKind(kind) {
  const form = state.form;
  const previous = form.kind;
  if (kind === previous) return;
  if (!SINGLE_KINDS.has(previous)) state.bandValues[previous] = BAND_FIELDS.map((name) => form[name]);
  if (!SINGLE_KINDS.has(kind)) {
    BAND_FIELDS.forEach((name, index) => {
      form[name] = state.bandValues[kind][index];
    });
  } else if (kind !== state.singleKind) {
    // Fp/Fs were typed for the other single-edge filter (maybe before a detour through a band
    // filter): swap them so the spec stays valid.
    [form.fp, form.fs] = [form.fs, form.fp];
    state.singleKind = kind;
  }
  form.kind = kind;
  applyForm();
  schedule();
}

// URL: the form travels in the hash so a link opens the same design.
function readHash(options) {
  const params = new URLSearchParams(location.hash.slice(1));
  const form = {};
  const allowed = {
    kind: options.kinds,
    approximation: options.approximations,
    topology: options.topologies,
    opamp: options.opamps,
    series: options.series,
    mounting: options.mountings,
  };
  for (const [name, items] of Object.entries(allowed)) {
    const value = params.get(name);
    if (value && items.some((item) => item.value === value)) form[name] = value;
  }
  for (const name of TEXT_FIELDS) {
    const value = params.get(name);
    if (value !== null && value.length <= 32) form[name] = value;
  }
  if (params.has("auto_cap")) form.auto_cap = params.get("auto_cap") !== "0";
  return form;
}

function writeHash() {
  const form = state.form;
  const params = new URLSearchParams();
  params.set("kind", form.kind);
  params.set("approximation", form.approximation);
  const fields = SINGLE_KINDS.has(form.kind) ? ["fp", "fs"] : BAND_FIELDS;
  for (const name of [...fields, "ap", "as", "topology", "opamp", "cap", "series", "mounting"]) params.set(name, form[name]);
  if (!form.auto_cap) params.set("auto_cap", "0");
  history.replaceState(null, "", `#${params}`);
}

// Engine ----------------------------------------------------------------------------------------
function schedule() {
  writeHash();
  clearTimeout(timer);
  timer = setTimeout(request, DEBOUNCE_MS);
}

function request() {
  if (!state.ready || state.inFlight) {
    state.dirty = true;
    return;
  }
  state.inFlight = true;
  state.dirty = false;
  state.sentAt = performance.now();
  worker.postMessage({ type: "design", id: ++state.seq, form: state.form });
}

function onWorkerMessage(event) {
  const message = event.data;
  if (message.type === "status") {
    $("loading-title").textContent = message.text;
  } else if (message.type === "ready") {
    state.ready = true;
    $("status").textContent = "Motor de cálculo listo";
    request();
  } else if (message.type === "fatal") {
    showFatal(message.text);
  } else if (message.type === "result") {
    state.inFlight = false;
    const elapsed = performance.now() - state.sentAt;
    render(JSON.parse(message.json), elapsed);
    if (state.dirty) request();
  } else if (pending.has(message.id)) {
    pending.get(message.id)(JSON.parse(message.json));
    pending.delete(message.id);
  }
}

// Schematic and exports: on demand, answered by id.
function ask(type, extra = {}, target = worker) {
  return new Promise((resolve) => {
    const id = `${type}-${++requestCounter}`;
    pending.set(id, resolve);
    target.postMessage({ type, id, form: state.form, ...extra });
  });
}

// The PCB is routed in a second engine, so typing stays responsive while it works.
function ensurePcbWorker() {
  if (pcbWorker) return pcbWorker;
  pcbWorker = new Worker("worker.js", { type: "module" });
  pcbWorker.onmessage = (event) => {
    const message = event.data;
    if (message.type === "status") $("pcb-status").textContent = message.text;
    else if (message.type === "fatal") $("pcb-status").textContent = `No se pudo cargar el motor de la placa: ${message.text}`;
    else if (pending.has(message.id)) {
      pending.get(message.id)(JSON.parse(message.json));
      pending.delete(message.id);
    }
  };
  pcbWorker.postMessage({ type: "init", bundle: state.options.bundle });
  return pcbWorker;
}

function pcbVisible() {
  return !$("panel-pcb").hidden;
}

async function refreshPcb() {
  if (!state.ready || !state.view || !state.view.ok) return;
  const key = JSON.stringify(state.form) + state.pcbSide;
  if (state.pcbKey === key || state.pcbBusy) {
    state.pcbAgain = state.pcbBusy && state.pcbKey !== key;
    return;
  }
  state.pcbKey = key;
  state.pcbBusy = true;
  $("pcb-status").textContent = "Colocando y ruteando la placa…";
  const view = await ask("pcb", { side: state.pcbSide }, ensurePcbWorker());
  state.pcbBusy = false;
  if (state.pcbKey === key) {
    if (view.ok) {
      pcbView.show(view.svg);
      const routing = view.unrouted ? `${view.unrouted} conexiones sin rutear` : "ruteo completo";
      const rules = view.problems.length ? ` · ${view.problems.length} avisos de reglas` : " · sin errores de reglas";
      $("pcb-status").textContent = `${view.width} × ${view.height} mm · ${view.parts} componentes · ${view.vias} vías · ${routing}${rules}`;
      $("pcb-cpl").hidden = !view.smd;
    } else {
      pcbView.clear(escapeHtml(view.error));
      $("pcb-status").textContent = "";
    }
  }
  if (state.pcbAgain) {
    state.pcbAgain = false;
    if (pcbVisible()) refreshPcb();
  }
}

function base64ToBytes(text) {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

function schematicVisible() {
  return !$("panel-schematic").hidden;
}

async function refreshSchematic() {
  if (!state.ready || !state.view || !state.view.ok) return;
  const key = JSON.stringify(state.form);
  if (state.schematicKey === key) return;
  state.schematicKey = key;
  const view = await ask("schematic");
  if (state.schematicKey !== key) return;
  if (view.ok) schematicView.show(view.svg);
  else schematicView.clear(escapeHtml(view.error));
}

async function download(what, target = worker) {
  if (!state.ready || !state.view || !state.view.ok) return;
  if (target === pcbWorker) toast("Preparando los archivos de la placa…");
  const file = await ask("export", { what }, target);
  if (!file.ok) {
    toast(file.error);
    return;
  }
  const body = file.base64 ? base64ToBytes(file.base64) : file.content;
  const url = URL.createObjectURL(new Blob([body], { type: file.mime }));
  const link = document.createElement("a");
  link.href = url;
  link.download = file.filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast(`Descargado ${file.filename}`);
}

function showFatal(text) {
  const loading = $("loading");
  loading.hidden = false;
  loading.classList.add("failed");
  $("loading-title").textContent = "No se pudo cargar el motor de cálculo";
  $("loading-text").textContent = `${text}. Revisa tu conexión a internet y recarga la página.`;
  $("headline").textContent = "Sin conexión con el motor";
}

// Rendering -------------------------------------------------------------------------------------
function render(view, elapsed) {
  state.view = view;
  $("loading").hidden = true;
  for (const name of TEXT_FIELDS) $(name).parentElement.classList.remove("invalid");
  const error = $("error");
  const enabled = Boolean(view.ok);
  $("save").disabled = !enabled;
  $("copy").disabled = !enabled;
  if (!view.ok) {
    for (const name of view.fields) $(name).parentElement.classList.add("invalid");
    error.textContent = view.error;
    error.hidden = false;
    $("headline").textContent = "Revisa la especificación";
    $("chips").innerHTML = "";
    plot.clear("Completa la especificación para ver la respuesta");
    $("stages").innerHTML = "";
    $("netlist").textContent = "";
    $("panel-warnings").innerHTML = "";
    $("panel-details").innerHTML = "";
    $("warnings-tab").textContent = "Avisos";
    $("status").textContent = "Revisa la especificación";
    state.schematicKey = null;
    schematicView.clear("Completa la especificación para ver el esquemático");
    state.pcbKey = null;
    pcbView.clear("Completa la especificación para ver la placa");
    return;
  }
  error.hidden = true;
  $("headline").textContent = view.headline;
  $("chips").innerHTML = view.chips
    .map((chip) => `<span class="chip ${chip.tone === "info" ? "" : chip.tone}">${escapeHtml(chip.text)}</span>`)
    .join("");
  plot.setData(view.plot);
  renderStages(view.stages);
  renderWarnings(view.warnings);
  renderDetails(view);
  $("netlist").textContent = view.netlist;
  $("status").textContent = `Diseño actualizado en ${Math.round(elapsed)} ms`;
  if (schematicVisible()) refreshSchematic();
  if (pcbVisible()) refreshPcb();
}

function renderStages(stages) {
  $("stages").innerHTML = stages
    .map((stage) => {
      const rows = stage.parts
        .map(
          (part) =>
            `<tr><td>${escapeHtml(part.name)}</td><td>${escapeHtml(part.value)}</td><td>${escapeHtml(part.detail)}</td></tr>`,
        )
        .join("");
      return (
        `<article class="stage"><header><h4>${escapeHtml(stage.title)}</h4>` +
        `<span class="chip">${escapeHtml(stage.topology)}</span><span class="chip">${escapeHtml(stage.order)}</span></header>` +
        `<p class="metrics">${escapeHtml(stage.metrics)}</p><table class="parts">${rows}</table></article>`
      );
    })
    .join("");
}

function renderWarnings(warnings) {
  $("panel-warnings").innerHTML = warnings.length
    ? warnings.map((text) => `<div class="note warn">⚠&nbsp; ${escapeHtml(text)}</div>`).join("")
    : `<div class="note ok">✓&nbsp; Todo en orden: el diseño no tiene avisos.</div>`;
  $("warnings-tab").textContent = warnings.length ? `Avisos (${warnings.length})` : "Avisos";
}

function renderDetails(view) {
  const info = view.details.map(([name, value]) => `<tr><td>${escapeHtml(name)}</td><td>${escapeHtml(value)}</td></tr>`).join("");
  const poles = view.poles
    .map(([real, imag], index) => `<tr><td>${index + 1}</td><td>${escapeHtml(real)}</td><td>${escapeHtml(imag)}</td></tr>`)
    .join("");
  $("panel-details").innerHTML =
    `<table class="details">${info}</table><h4>Polos (rad/s)</h4>` +
    `<table class="details poles"><tr><td>#</td><td>real</td><td>imaginaria</td></tr>${poles}</table>`;
}

// Actions ---------------------------------------------------------------------------------------
function toast(text) {
  const element = $("toast");
  element.textContent = text;
  element.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove("show"), 2200);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    const done = document.execCommand("copy");
    area.remove();
    return done;
  }
}

function bindActions() {
  $("save").addEventListener("click", () => {
    const view = state.view;
    if (!view || !view.ok) return;
    const url = URL.createObjectURL(new Blob([`${view.netlist}\n`], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = view.filename;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast(`Descargado ${view.filename}`);
  });
  $("copy").addEventListener("click", async () => {
    if (state.view && state.view.ok && (await copyText(state.view.netlist))) toast("Netlist copiado al portapapeles");
  });
  $("share").addEventListener("click", async () => {
    if (await copyText(location.href)) toast("Enlace copiado: abre este mismo diseño");
  });
  for (const button of $("view").querySelectorAll("button")) {
    button.addEventListener("click", () => {
      for (const other of $("view").querySelectorAll("button")) other.setAttribute("aria-pressed", String(other === button));
      plot.setPassbandView(button.dataset.passband === "1");
    });
  }
  for (const tab of document.querySelectorAll(".tabs button")) {
    tab.addEventListener("click", () => {
      for (const other of document.querySelectorAll(".tabs button")) {
        const selected = other === tab;
        other.setAttribute("aria-selected", String(selected));
        $(`panel-${other.dataset.panel}`).hidden = !selected;
      }
      if (tab.dataset.panel === "schematic") refreshSchematic();
      if (tab.dataset.panel === "pcb") refreshPcb();
    });
  }
  for (const button of document.querySelectorAll("[data-export]")) {
    button.addEventListener("click", () => download(button.dataset.export));
  }
  for (const [button, panel] of [["schematic-full", "panel-schematic"], ["pcb-full", "panel-pcb"]]) {
    $(button).addEventListener("click", async () => {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if ($(panel).requestFullscreen) await $(panel).requestFullscreen();
    });
  }
  document.addEventListener("fullscreenchange", () => {
    for (const button of ["schematic-full", "pcb-full"]) $(button).textContent = document.fullscreenElement ? "Salir" : "Ampliar";
    schematicView.fit();
    pcbView.fit();
  });
  for (const button of document.querySelectorAll("[data-pcb-export]")) {
    button.addEventListener("click", () => download(button.dataset.pcbExport, ensurePcbWorker()));
  }
  for (const button of $("pcb-side").querySelectorAll("button")) {
    button.addEventListener("click", () => {
      for (const other of $("pcb-side").querySelectorAll("button")) other.setAttribute("aria-pressed", String(other === button));
      state.pcbSide = button.dataset.side;
      refreshPcb();
    });
  }
}

// Start -----------------------------------------------------------------------------------------
async function main() {
  plot = new ResponsePlot($("plot"));
  schematicView = new SchematicView($("schematic-view"));
  pcbView = new SchematicView($("pcb-view"));
  state.pcbSide = "top";
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => plot.readColors());
  if (matchMedia("(pointer: coarse)").matches) {
    $("plot-hint").textContent = "Zonas rojas: fuera de la especificación. Pellizca para zoom · arrastra para mover.";
  }
  bindActions();

  worker = new Worker("worker.js", { type: "module" });
  worker.onmessage = onWorkerMessage;
  worker.onerror = (event) => showFatal(event.message || "el navegador no pudo iniciar el cálculo");

  let options;
  try {
    const response = await fetch("options.json", { cache: "no-cache" });
    options = await response.json();
  } catch (error) {
    showFatal(String(error));
    return;
  }
  state.options = options;
  worker.postMessage({ type: "init", bundle: options.bundle });
  buildForm(options);
  loadFromHash();
  // A link pasted into this same tab only changes the hash: load that design too.
  addEventListener("hashchange", loadFromHash);
}

function loadFromHash() {
  const options = state.options;
  const fromHash = readHash(options);
  const form = { ...options.defaults, ...fromHash };
  state.form = form;
  state.bandValues = structuredClone(options.default_bands);
  if (!SINGLE_KINDS.has(form.kind)) {
    // Edges missing from the link take this filter's own defaults, not the band-pass ones.
    BAND_FIELDS.forEach((name, index) => {
      if (!(name in fromHash)) form[name] = state.bandValues[form.kind][index];
    });
    state.bandValues[form.kind] = BAND_FIELDS.map((name) => form[name]);
  } else if (form.kind === "highpass" && !("fp" in fromHash) && !("fs" in fromHash)) {
    [form.fp, form.fs] = [form.fs, form.fp];
  }
  // Which single-edge filter the Fp/Fs values belong to (the defaults are low-pass ones).
  state.singleKind = SINGLE_KINDS.has(form.kind) ? form.kind : "lowpass";
  applyForm();
  request();
}

main();
