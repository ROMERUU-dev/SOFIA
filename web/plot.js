// Frequency-response plot on a canvas: log axis, spec mask, zoom/pan and hover readout.
// Same behaviour as the desktop plot (gui/plot.py): wheel zooms around the cursor (Shift: only dB,
// Ctrl: only frequency), dragging pans, double click returns to the full view. Two fingers pinch-zoom.

const AUTO_FLOOR_DB = -240;
const WHEEL_STEP = 0.85;
const MARGIN = { left: 62, right: 16, top: 14, bottom: 34 };
const PREFIXES = [[1e9, "G"], [1e6, "M"], [1e3, "k"], [1, ""], [1e-3, "m"], [1e-6, "µ"], [1e-9, "n"], [1e-12, "p"]];

export function formatQuantity(value, unit = "", digits = 4) {
  if (value === 0 || !Number.isFinite(value)) return `${value} ${unit}`.trim();
  let [scale, prefix] = PREFIXES[PREFIXES.length - 1];
  for (const [s, p] of PREFIXES) {
    if (Math.abs(value) >= s * 0.9995) {
      [scale, prefix] = [s, p];
      break;
    }
  }
  return `${Number((value / scale).toPrecision(digits))} ${prefix}${unit}`.trim();
}

function bisectLeft(values, target) {
  let lo = 0;
  let hi = values.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (values[mid] < target) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

export class ResponsePlot {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.data = null;
    this.passbandView = false;
    this.view = { xLo: 0, xHi: 1, yTop: 5, yBottom: -60 };
    this.hoverX = null;
    this.pointers = new Map();
    this.gesture = null;
    this.emptyText = "";
    this.readColors();
    new ResizeObserver(() => this.draw()).observe(canvas);
    this.bindEvents();
  }

  readColors() {
    const style = getComputedStyle(document.documentElement);
    const color = (name) => style.getPropertyValue(name).trim();
    this.colors = {
      surface: color("--surface"),
      text: color("--text"),
      muted: color("--muted"),
      accent: color("--accent"),
      border: color("--border"),
      grid: color("--grid"),
      gridStrong: color("--grid-strong"),
      forbidden: color("--forbidden"),
      tooltip: color("--tooltip"),
      tooltipText: color("--tooltip-text"),
    };
    this.draw();
  }

  // Data and views ------------------------------------------------------------------------------
  setData(data) {
    this.data = data;
    this.resetView();
  }

  clear(text = "") {
    this.data = null;
    this.emptyText = text;
    this.draw();
  }

  setPassbandView(enabled) {
    this.passbandView = enabled;
    this.resetView();
  }

  resetView() {
    const data = this.data;
    if (data) {
      const { freqs, gains } = data;
      this.view.xLo = Math.log10(freqs[0]);
      this.view.xHi = Math.log10(freqs[freqs.length - 1]);
      if (this.passbandView) {
        const span = Math.max(0.5, data.ripple_db);
        this.view.yTop = span * 0.5;
        this.view.yBottom = -span * 2.5;
      } else {
        // Whole curve: down to its deepest point (at least As + 20 dB below 0 dB).
        let deepest = AUTO_FLOOR_DB;
        let any = false;
        for (const gain of gains) {
          if (gain > AUTO_FLOOR_DB) {
            deepest = any ? Math.min(deepest, gain) : gain;
            any = true;
          }
        }
        const floorForSpec = -Math.ceil((data.attenuation_db + 20) / 20) * 20;
        this.view.yTop = 5;
        this.view.yBottom = Math.max(Math.min(Math.floor((deepest - 5) / 20) * 20, floorForSpec), AUTO_FLOOR_DB);
      }
    }
    this.draw();
  }

  // Geometry ------------------------------------------------------------------------------------
  rect() {
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    return {
      left: MARGIN.left,
      top: MARGIN.top,
      width: Math.max(10, width - MARGIN.left - MARGIN.right),
      height: Math.max(10, height - MARGIN.top - MARGIN.bottom),
      get right() { return this.left + this.width; },
      get bottom() { return this.top + this.height; },
    };
  }

  x(freq, rect) {
    const { xLo, xHi } = this.view;
    return rect.left + ((Math.log10(freq) - xLo) / (xHi - xLo)) * rect.width;
  }

  y(gain, rect) {
    const { yTop, yBottom } = this.view;
    const span = yTop - yBottom;
    // Keep coordinates bounded; the canvas clips anything outside the plot.
    const bounded = Math.min(yTop + span, Math.max(yBottom - span, gain));
    return rect.top + ((yTop - bounded) / span) * rect.height;
  }

  yStep() {
    const span = this.view.yTop - this.view.yBottom;
    for (const step of [0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 20, 40, 50]) {
      if (span / step <= 9) return step;
    }
    return 100;
  }

  dataRange() {
    const { freqs } = this.data;
    return [Math.log10(freqs[0]), Math.log10(freqs[freqs.length - 1])];
  }

  zoomAround(px, py, factorX, factorY) {
    const rect = this.rect();
    const view = this.view;
    if (factorX !== 1) {
      const anchor = view.xLo + ((px - rect.left) / rect.width) * (view.xHi - view.xLo);
      const lo = anchor - (anchor - view.xLo) * factorX;
      const hi = anchor + (view.xHi - anchor) * factorX;
      const [dataLo, dataHi] = this.dataRange();
      if (hi - lo >= 0.02) {
        view.xLo = Math.max(lo, dataLo);
        view.xHi = Math.min(hi, dataHi);
      }
    }
    if (factorY !== 1) {
      const anchor = view.yTop - ((py - rect.top) / rect.height) * (view.yTop - view.yBottom);
      const top = anchor + (view.yTop - anchor) * factorY;
      const bottom = anchor - (anchor - view.yBottom) * factorY;
      if (top - bottom >= 0.05) {
        view.yTop = Math.min(top, 40);
        view.yBottom = Math.max(bottom, -400);
      }
    }
  }

  panBy(dxPixels, dyPixels, start) {
    const rect = this.rect();
    const [dataLo, dataHi] = this.dataRange();
    let dx = (dxPixels / rect.width) * (start.xHi - start.xLo);
    const dy = (dyPixels / rect.height) * (start.yTop - start.yBottom);
    dx = Math.min(Math.max(dx, start.xHi - dataHi), start.xLo - dataLo);
    this.view.xLo = start.xLo - dx;
    this.view.xHi = start.xHi - dx;
    this.view.yTop = start.yTop + dy;
    this.view.yBottom = start.yBottom + dy;
  }

  // Input ---------------------------------------------------------------------------------------
  bindEvents() {
    const canvas = this.canvas;
    const local = (event) => {
      const box = canvas.getBoundingClientRect();
      return [event.clientX - box.left, event.clientY - box.top];
    };

    canvas.addEventListener(
      "wheel",
      (event) => {
        if (!this.data) return;
        event.preventDefault();
        const [px, py] = local(event);
        const delta = event.deltaMode === 1 ? event.deltaY * 40 : event.deltaY;
        const factor = WHEEL_STEP ** (-delta / 120);
        this.zoomAround(px, py, event.shiftKey ? 1 : factor, event.ctrlKey ? 1 : factor);
        this.draw();
      },
      { passive: false },
    );

    canvas.addEventListener("pointerdown", (event) => {
      if (!this.data) return;
      canvas.setPointerCapture(event.pointerId);
      this.pointers.set(event.pointerId, local(event));
      this.startGesture();
      if (event.pointerType !== "mouse") {
        this.hoverX = local(event)[0];
        this.draw();
      }
    });

    canvas.addEventListener("pointermove", (event) => {
      const point = local(event);
      if (this.pointers.has(event.pointerId)) {
        this.pointers.set(event.pointerId, point);
        this.continueGesture();
      }
      const rect = this.rect();
      this.hoverX = point[0] >= rect.left && point[0] <= rect.right ? point[0] : null;
      this.draw();
    });

    const release = (event) => {
      this.pointers.delete(event.pointerId);
      this.startGesture();
      if (!this.pointers.size) canvas.classList.remove("dragging");
      this.draw();
    };
    canvas.addEventListener("pointerup", release);
    canvas.addEventListener("pointercancel", release);
    canvas.addEventListener("pointerleave", (event) => {
      if (event.pointerType === "mouse") {
        this.hoverX = null;
        this.draw();
      }
    });
    canvas.addEventListener("dblclick", () => this.resetView());
  }

  startGesture() {
    const points = [...this.pointers.values()];
    if (!points.length) {
      this.gesture = null;
      return;
    }
    const start = { ...this.view };
    if (points.length === 1) {
      this.gesture = { kind: "pan", origin: points[0], start, moved: false };
    } else {
      const [a, b] = points;
      this.gesture = {
        kind: "pinch",
        start,
        center: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2],
        spanX: Math.max(24, Math.abs(a[0] - b[0])),
        spanY: Math.max(24, Math.abs(a[1] - b[1])),
      };
    }
  }

  continueGesture() {
    const gesture = this.gesture;
    if (!gesture) return;
    const points = [...this.pointers.values()];
    if (gesture.kind === "pan" && points.length === 1) {
      const [x, y] = points[0];
      const dx = x - gesture.origin[0];
      const dy = y - gesture.origin[1];
      if (!gesture.moved && Math.hypot(dx, dy) < 3) return;
      gesture.moved = true;
      this.canvas.classList.add("dragging");
      this.panBy(dx, dy, gesture.start);
    } else if (gesture.kind === "pinch" && points.length >= 2) {
      const [a, b] = points;
      this.view = { ...gesture.start };
      const factorX = gesture.spanX / Math.max(24, Math.abs(a[0] - b[0]));
      const factorY = gesture.spanY / Math.max(24, Math.abs(a[1] - b[1]));
      this.zoomAround(gesture.center[0], gesture.center[1], factorX, factorY);
    }
  }

  // Painting ------------------------------------------------------------------------------------
  draw() {
    const canvas = this.canvas;
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;
    if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
    }
    const ctx = this.ctx;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const rect = this.rect();
    ctx.fillStyle = this.colors.surface;
    ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
    const style = getComputedStyle(canvas);
    ctx.font = `${style.fontSize} ${style.fontFamily}`;
    if (!this.data || this.data.freqs.length < 2) {
      ctx.fillStyle = this.colors.muted;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(this.emptyText, rect.left + rect.width / 2, rect.top + rect.height / 2);
      return;
    }
    ctx.save();
    ctx.beginPath();
    ctx.rect(rect.left, rect.top, rect.width, rect.height);
    ctx.clip();
    this.paintMask(ctx, rect);
    ctx.restore();
    this.paintGrid(ctx, rect);
    this.paintCurve(ctx, rect);
    this.paintHover(ctx, rect);
  }

  paintMask(ctx, rect) {
    const { freqs, passbands, stopbands, ripple_db: ripple, attenuation_db: attenuation } = this.data;
    const fLo = freqs[0];
    const fHi = freqs[freqs.length - 1];
    const band = (lo, hi, level, below) => {
      lo = Math.max(lo, fLo);
      hi = Math.min(hi, fHi);
      if (hi <= lo) return;
      const x0 = this.x(lo, rect);
      const x1 = this.x(hi, rect);
      const y = this.y(level, rect);
      ctx.globalAlpha = 0.1;
      ctx.fillStyle = this.colors.forbidden;
      if (below) ctx.fillRect(x0, y, x1 - x0, rect.bottom - y);
      else ctx.fillRect(x0, rect.top, x1 - x0, y - rect.top);
      ctx.globalAlpha = 0.55;
      ctx.strokeStyle = this.colors.forbidden;
      ctx.lineWidth = 1.2;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x1, y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
    };
    for (const [lo, hi] of passbands) band(lo, hi, -ripple, true);
    for (const [lo, hi] of stopbands) band(lo, hi, -attenuation, false);
  }

  paintGrid(ctx, rect) {
    const { xLo, xHi, yTop, yBottom } = this.view;
    ctx.lineWidth = 1;
    ctx.textBaseline = "top";
    ctx.textAlign = "center";
    // Label the 2-3-5-7 ticks whenever they fit (always when zoomed in), so the axis keeps a scale.
    // 5 -> 7 is the closest pair of labels on a log axis.
    const pixelsPerDecade = rect.width / (xHi - xLo);
    const labelMinor = pixelsPerDecade * Math.log10(7 / 5) >= ctx.measureText("700 Hz").width + 10;
    for (let decade = Math.floor(xLo); decade <= Math.ceil(xHi); decade++) {
      for (let step = 1; step < 10; step++) {
        const freq = step * 10 ** decade;
        const position = Math.log10(freq);
        if (position < xLo || position > xHi) continue;
        const x = Math.round(this.x(freq, rect)) + 0.5;
        ctx.strokeStyle = step === 1 ? this.colors.gridStrong : this.colors.grid;
        ctx.beginPath();
        ctx.moveTo(x, rect.top);
        ctx.lineTo(x, rect.bottom);
        ctx.stroke();
        if (step === 1 || (labelMinor && [2, 3, 5, 7].includes(step))) {
          ctx.fillStyle = this.colors.muted;
          ctx.fillText(formatQuantity(freq, "Hz", 3), x, rect.bottom + 8);
        }
      }
    }
    const stepDb = this.yStep();
    const decimals = stepDb >= 1 ? 0 : stepDb >= 0.1 ? 1 : 2;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let gain = Math.floor(yTop / stepDb) * stepDb; gain >= yBottom - 1e-9; gain -= stepDb) {
      const y = Math.round(this.y(gain, rect)) + 0.5;
      ctx.strokeStyle = Math.abs(gain) < 1e-9 ? this.colors.gridStrong : this.colors.grid;
      ctx.beginPath();
      ctx.moveTo(rect.left, y);
      ctx.lineTo(rect.right, y);
      ctx.stroke();
      ctx.fillStyle = this.colors.muted;
      ctx.fillText(`${(Math.abs(gain) < 1e-9 ? 0 : gain).toFixed(decimals)} dB`, rect.left - 8, y);
    }
    ctx.strokeStyle = this.colors.border;
    ctx.strokeRect(rect.left + 0.5, rect.top + 0.5, rect.width - 1, rect.height - 1);
  }

  paintCurve(ctx, rect) {
    const { freqs, gains } = this.data;
    ctx.save();
    ctx.beginPath();
    ctx.rect(rect.left, rect.top, rect.width, rect.height);
    ctx.clip();
    ctx.beginPath();
    freqs.forEach((freq, index) => {
      const x = this.x(freq, rect);
      const y = this.y(gains[index], rect);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = this.colors.accent;
    ctx.lineWidth = 2.4;
    ctx.lineJoin = "round";
    ctx.stroke();
    ctx.restore();
  }

  paintHover(ctx, rect) {
    if (this.hoverX === null || this.canvas.classList.contains("dragging")) return;
    const { freqs, gains } = this.data;
    const { xLo, xHi } = this.view;
    const position = xLo + ((this.hoverX - rect.left) / rect.width) * (xHi - xLo);
    const index = Math.min(freqs.length - 1, bisectLeft(freqs, 10 ** position));
    const freq = freqs[index];
    const gain = gains[index];
    const x = this.x(freq, rect);
    const y = this.y(gain, rect);
    ctx.strokeStyle = this.colors.muted;
    ctx.setLineDash([2, 3]);
    ctx.beginPath();
    ctx.moveTo(x, rect.top);
    ctx.lineTo(x, rect.bottom);
    ctx.stroke();
    ctx.setLineDash([]);
    if (y >= rect.top && y <= rect.bottom) {
      ctx.fillStyle = this.colors.accent;
      ctx.strokeStyle = this.colors.surface;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
    const label = `${formatQuantity(freq, "Hz", 4)}   ${gain.toFixed(2)} dB`;
    const width = ctx.measureText(label).width + 16;
    const height = 24;
    const boxX = x + 10 + width < rect.right ? x + 10 : x - 10 - width;
    ctx.fillStyle = this.colors.tooltip;
    ctx.beginPath();
    ctx.roundRect(boxX, rect.top + 8, width, height, 6);
    ctx.fill();
    ctx.fillStyle = this.colors.tooltipText;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, boxX + width / 2, rect.top + 8 + height / 2);
  }
}
