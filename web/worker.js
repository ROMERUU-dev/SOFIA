// Runs the Python package under Pyodide, off the main thread so typing never stutters.
import { loadPyodide } from "https://cdn.jsdelivr.net/npm/pyodide@314.0.7/pyodide.mjs";

const ROOT = "/home/pyodide/sofia";
let designView = null;
let resolveBundle;
const bundleName = new Promise((resolve) => {
  resolveBundle = resolve;
});

async function boot() {
  postMessage({ type: "status", text: "Descargando el intérprete de Python…" });
  const [pyodide, bundle] = await Promise.all([
    loadPyodide(),
    bundleName.then((name) => fetch(name)).then((response) => {
      if (!response.ok) throw new Error(`no se pudo descargar el paquete (${response.status})`);
      return response.arrayBuffer();
    }),
  ]);
  postMessage({ type: "status", text: "Cargando SOFIA…" });
  pyodide.unpackArchive(bundle, "zip", { extractDir: ROOT });
  pyodide.runPython(`
import sys
sys.path.insert(0, "${ROOT}/src")
from sofia_filter_studio.forms import design_view_json
`);
  designView = pyodide.globals.get("design_view_json");
  postMessage({ type: "ready" });
}

const ready = boot().catch((error) => {
  postMessage({ type: "fatal", text: String(error && error.message ? error.message : error) });
  throw error;
});

onmessage = async (event) => {
  const message = event.data;
  if (message.type === "init") {
    resolveBundle(message.bundle);
    return;
  }
  if (message.type !== "design") return;
  try {
    await ready;
  } catch {
    return;
  }
  let json;
  try {
    json = designView(JSON.stringify(message.form));
  } catch (error) {
    json = JSON.stringify({ ok: false, error: `Error interno: ${error.message}`, fields: [] });
  }
  postMessage({ type: "result", id: message.id, json });
};
