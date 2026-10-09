// Inline SVG viewer for the schematic: wheel zooms around the cursor, dragging pans, a double click
// (or the Ajustar button) fits the whole sheet. Two fingers pinch-zoom on touch screens.

export class SchematicView {
  constructor(container) {
    this.container = container;
    this.svg = null;
    this.home = null;
    this.view = null;
    this.pointers = new Map();
    this.gesture = null;
    container.addEventListener("wheel", (event) => this.onWheel(event), { passive: false });
    container.addEventListener("pointerdown", (event) => this.onDown(event));
    container.addEventListener("pointermove", (event) => this.onMove(event));
    container.addEventListener("pointerup", (event) => this.onUp(event));
    container.addEventListener("pointercancel", (event) => this.onUp(event));
    container.addEventListener("dblclick", () => this.fit());
  }

  show(markup) {
    this.container.innerHTML = markup;
    this.svg = this.container.querySelector("svg");
    if (!this.svg) return;
    this.svg.removeAttribute("width");
    this.svg.removeAttribute("height");
    this.svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    this.home = this.svg.getAttribute("viewBox").split(/\s+/).map(Number);
    this.fit();
  }

  clear(text) {
    this.svg = null;
    this.container.innerHTML = `<p class="empty">${text}</p>`;
  }

  fit() {
    if (!this.svg) return;
    this.view = [...this.home];
    this.apply();
  }

  apply() {
    this.svg.setAttribute("viewBox", this.view.map((value) => value.toFixed(3)).join(" "));
  }

  // Container pixel -> SVG units, with preserveAspectRatio "meet".
  toUnits(clientX, clientY) {
    const box = this.container.getBoundingClientRect();
    const [x, y, w, h] = this.view;
    const scale = Math.min(box.width / w, box.height / h);
    const offsetX = (box.width - w * scale) / 2;
    const offsetY = (box.height - h * scale) / 2;
    return [x + (clientX - box.left - offsetX) / scale, y + (clientY - box.top - offsetY) / scale, scale];
  }

  zoom(factor, clientX, clientY) {
    const [ux, uy] = this.toUnits(clientX, clientY);
    const [x, y, w, h] = this.view;
    const newW = Math.min(Math.max(w * factor, this.home[2] / 40), this.home[2] * 1.5);
    const applied = newW / w;
    this.view = [ux - (ux - x) * applied, uy - (uy - y) * applied, w * applied, h * applied];
    this.apply();
  }

  onWheel(event) {
    if (!this.svg) return;
    event.preventDefault();
    const delta = event.deltaMode === 1 ? event.deltaY * 40 : event.deltaY;
    this.zoom(0.85 ** (-delta / 120), event.clientX, event.clientY);
  }

  onDown(event) {
    if (!this.svg) return;
    this.container.setPointerCapture(event.pointerId);
    this.pointers.set(event.pointerId, [event.clientX, event.clientY]);
    this.start();
  }

  start() {
    const points = [...this.pointers.values()];
    if (points.length === 1) {
      this.gesture = { kind: "pan", origin: points[0], view: [...this.view] };
    } else if (points.length >= 2) {
      const [a, b] = points;
      this.gesture = { kind: "pinch", distance: Math.hypot(a[0] - b[0], a[1] - b[1]), view: [...this.view] };
    } else {
      this.gesture = null;
    }
  }

  onMove(event) {
    if (!this.pointers.has(event.pointerId) || !this.gesture) return;
    this.pointers.set(event.pointerId, [event.clientX, event.clientY]);
    const points = [...this.pointers.values()];
    if (this.gesture.kind === "pan" && points.length === 1) {
      const scale = this.toUnits(0, 0)[2];
      const [x, y, w, h] = this.gesture.view;
      const dx = (points[0][0] - this.gesture.origin[0]) / scale;
      const dy = (points[0][1] - this.gesture.origin[1]) / scale;
      this.view = [x - dx, y - dy, w, h];
      this.container.classList.add("dragging");
      this.apply();
    } else if (this.gesture.kind === "pinch" && points.length >= 2) {
      const [a, b] = points;
      const distance = Math.hypot(a[0] - b[0], a[1] - b[1]);
      this.view = [...this.gesture.view];
      this.zoom(this.gesture.distance / Math.max(distance, 1), (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
    }
  }

  onUp(event) {
    this.pointers.delete(event.pointerId);
    this.container.classList.remove("dragging");
    this.start();
  }
}
