from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..design import design_filter
from ..models import Approximation, DesignInputs, FilterKind, FilterSpec, OpAmpModel, ResistorSeries, Topology
from ..netlist import render_netlist


class SofiaApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("SOFIA Filter Studio")
        self.root.geometry("1100x760")
        self._build_state()
        self._build_layout()
        self._refresh_form_for_kind()

    def _build_state(self) -> None:
        self.kind = tk.StringVar(value=FilterKind.LOWPASS.value)
        self.approximation = tk.StringVar(value=Approximation.BUTTERWORTH.value)
        self.topology = tk.StringVar(value=Topology.SALLEN_KEY.value)
        self.opamp = tk.StringVar(value=OpAmpModel.TL082.value)
        self.resistor_series = tk.StringVar(value=ResistorSeries.E24.value)
        self.allow_arrays = tk.BooleanVar(value=True)
        self.auto_stage_capacitor = tk.BooleanVar(value=True)
        self.max_network_size = tk.StringVar(value="2")
        self.ap = tk.StringVar(value="1.0")
        self.a_stop = tk.StringVar(value="40.0")
        self.cap = tk.StringVar(value="1e-8")
        self.fp = tk.StringVar(value="1000")
        self.fs = tk.StringVar(value="2000")
        self.fp1 = tk.StringVar(value="1000")
        self.fp2 = tk.StringVar(value="2000")
        self.fs1 = tk.StringVar(value="700")
        self.fs2 = tk.StringVar(value="2600")

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=0)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)

        form = ttk.LabelFrame(container, text="Design Inputs", padding=12)
        form.grid(row=0, column=0, sticky="nsw", padx=(0, 16))

        ttk.Label(form, text="Filter kind").grid(row=0, column=0, sticky="w")
        kind_box = ttk.Combobox(form, textvariable=self.kind, values=[item.value for item in FilterKind], state="readonly")
        kind_box.grid(row=1, column=0, sticky="ew")
        kind_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_form_for_kind())

        ttk.Label(form, text="Approximation").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Combobox(form, textvariable=self.approximation, values=[item.value for item in Approximation], state="readonly").grid(row=3, column=0, sticky="ew")

        ttk.Label(form, text="Topology").grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Combobox(form, textvariable=self.topology, values=[item.value for item in Topology], state="readonly").grid(row=5, column=0, sticky="ew")

        ttk.Label(form, text="Op amp").grid(row=6, column=0, sticky="w", pady=(10, 0))
        ttk.Combobox(form, textvariable=self.opamp, values=[item.value for item in OpAmpModel], state="readonly").grid(row=7, column=0, sticky="ew")

        ttk.Label(form, text="Resistor series").grid(row=8, column=0, sticky="w", pady=(10, 0))
        ttk.Combobox(form, textvariable=self.resistor_series, values=[item.value for item in ResistorSeries], state="readonly").grid(row=9, column=0, sticky="ew")

        ttk.Checkbutton(form, text="Allow resistor arrays", variable=self.allow_arrays).grid(row=10, column=0, sticky="w", pady=(10, 0))
        ttk.Checkbutton(form, text="Auto tune stage capacitor", variable=self.auto_stage_capacitor).grid(row=11, column=0, sticky="w", pady=(6, 0))

        ttk.Label(form, text="Max resistors per network").grid(row=12, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(form, textvariable=self.max_network_size).grid(row=13, column=0, sticky="ew")

        ttk.Label(form, text="Passband ripple (dB)").grid(row=14, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(form, textvariable=self.ap).grid(row=15, column=0, sticky="ew")

        ttk.Label(form, text="Stopband attenuation (dB)").grid(row=16, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(form, textvariable=self.a_stop).grid(row=17, column=0, sticky="ew")

        ttk.Label(form, text="Stage capacitor (F)").grid(row=18, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(form, textvariable=self.cap).grid(row=19, column=0, sticky="ew")

        self.single_band_frame = ttk.LabelFrame(form, text="Low/High")
        self.single_band_frame.grid(row=20, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(self.single_band_frame, text="Fp (Hz)").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.single_band_frame, textvariable=self.fp).grid(row=1, column=0, sticky="ew")
        ttk.Label(self.single_band_frame, text="Fs (Hz)").grid(row=2, column=0, sticky="w")
        ttk.Entry(self.single_band_frame, textvariable=self.fs).grid(row=3, column=0, sticky="ew")

        self.band_frame = ttk.LabelFrame(form, text="Band Edges")
        self.band_frame.grid(row=21, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(self.band_frame, text="Fp1 (Hz)").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.band_frame, textvariable=self.fp1).grid(row=1, column=0, sticky="ew")
        ttk.Label(self.band_frame, text="Fp2 (Hz)").grid(row=2, column=0, sticky="w")
        ttk.Entry(self.band_frame, textvariable=self.fp2).grid(row=3, column=0, sticky="ew")
        ttk.Label(self.band_frame, text="Fs1 (Hz)").grid(row=4, column=0, sticky="w")
        ttk.Entry(self.band_frame, textvariable=self.fs1).grid(row=5, column=0, sticky="ew")
        ttk.Label(self.band_frame, text="Fs2 (Hz)").grid(row=6, column=0, sticky="w")
        ttk.Entry(self.band_frame, textvariable=self.fs2).grid(row=7, column=0, sticky="ew")

        ttk.Button(form, text="Calculate", command=self.calculate).grid(row=22, column=0, sticky="ew", pady=(16, 0))
        ttk.Button(form, text="Save Netlist", command=self.save_netlist).grid(row=23, column=0, sticky="ew", pady=(8, 0))

        output = ttk.Notebook(container)
        output.grid(row=0, column=1, sticky="nsew")

        result_frame = ttk.Frame(output, padding=8)
        netlist_frame = ttk.Frame(output, padding=8)
        output.add(result_frame, text="Result")
        output.add(netlist_frame, text="Netlist")

        self.result_text = tk.Text(result_frame, wrap="word")
        self.result_text.pack(fill=tk.BOTH, expand=True)
        self.netlist_text = tk.Text(netlist_frame, wrap="none")
        self.netlist_text.pack(fill=tk.BOTH, expand=True)

    def _refresh_form_for_kind(self) -> None:
        kind = FilterKind(self.kind.get())
        if kind in {FilterKind.LOWPASS, FilterKind.HIGHPASS}:
            self.single_band_frame.state(["!disabled"])
            self.band_frame.state(["disabled"])
        else:
            self.single_band_frame.state(["disabled"])
            self.band_frame.state(["!disabled"])

    def _build_inputs(self) -> DesignInputs:
        kind = FilterKind(self.kind.get())
        if kind in {FilterKind.LOWPASS, FilterKind.HIGHPASS}:
            spec = FilterSpec(passband_hz=float(self.fp.get()), stopband_hz=float(self.fs.get()))
        else:
            spec = FilterSpec(
                passband_hz=(float(self.fp1.get()), float(self.fp2.get())),
                stopband_hz=(float(self.fs1.get()), float(self.fs2.get())),
            )
        return DesignInputs(
            kind=kind,
            approximation=Approximation(self.approximation.get()),
            spec=spec,
            passband_ripple_db=float(self.ap.get()),
            stopband_attenuation_db=float(self.a_stop.get()),
            topology=Topology(self.topology.get()),
            opamp=OpAmpModel(self.opamp.get()),
            stage_capacitor_f=float(self.cap.get()),
            resistor_series=ResistorSeries(self.resistor_series.get()),
            allow_resistor_arrays=bool(self.allow_arrays.get()),
            max_resistors_per_network=int(self.max_network_size.get()),
            auto_stage_capacitor=bool(self.auto_stage_capacitor.get()),
        )

    def calculate(self) -> None:
        try:
            inputs = self._build_inputs()
            result = design_filter(inputs)
            netlist = render_netlist(inputs, result)
        except Exception as exc:
            messagebox.showerror("Calculation error", str(exc))
            return

        self.result_text.delete("1.0", tk.END)
        self.result_text.insert(tk.END, json.dumps(result.as_dict(), indent=2))
        self.netlist_text.delete("1.0", tk.END)
        self.netlist_text.insert(tk.END, netlist)

    def save_netlist(self) -> None:
        netlist = self.netlist_text.get("1.0", tk.END).strip()
        if not netlist:
            messagebox.showinfo("Nothing to save", "Calculate a design first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save SPICE netlist",
            defaultextension=".cir",
            filetypes=[("SPICE netlists", "*.cir *.sp"), ("All files", "*.*")],
        )
        if not path:
            return
        Path(path).write_text(netlist + "\n", encoding="utf-8")
        messagebox.showinfo("Saved", f"Netlist saved to {path}")


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    SofiaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
