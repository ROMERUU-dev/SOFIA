"""Capture legacy.cir for each benchmark case by driving the original Sofia.exe (Windows only).

The original SOFIA (Borland C++ Builder 5) is operated through Win32 messages, following the same
clicks a person would do: spec -> filter kind -> approximation -> "Pole and Zero Generation" ->
"Frequency Response" -> "Topologies" -> topology menu -> capacitor -> "Execute" -> 5% tolerance ->
"Commercial Value" -> op amp menu -> "Netlist". Disabled controls are never clicked, so every
captured netlist is one a user can obtain.

Note: the SOFIA netlist editor copies the op amp model through the Windows clipboard, so running
this overwrites the clipboard contents.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).absolute().parents[1]
BENCHMARK_DIR = ROOT / "docs" / "benchmark"
MODELS_DIR = ROOT / "resources" / "models"

KIND = {"lowpass": "Lowpass", "highpass": "Highpass", "bandpass": "Bandpass", "bandstop": "Band-Reject"}
APPROX = {"butterworth": "Butterworth", "chebyshev": "Chebyshev"}
TOPOLOGY_MENU = {
    "sallen_key": ["Topologies", "Second Order", "One Opamp", "Sallen-Key"],
    "mfb": ["Topologies", "Second Order", "One Opamp", "MFB"],
    "antoniou": ["Topologies", "Second Order", "Two Opamp", "Antonious"],
    "tow_thomas": ["Topologies", "Second Order", "ThreeOpamp", "Tow-Thomas"],
}
OPAMP_MENU = {
    "LM324": "LM324",
    "LM318": "LM318",
    "uA741": "uA741",
    "TL082": "Tl082",
    "LM7171": "LM7171",
    "LM6164": "LM6164",
    "LM6165": "LM6165",
    "LM6171": "LM6171",
}
MODEL_FILE = {
    "LM324": "oplm324.cir",
    "LM318": "LM318.cir",
    "uA741": "ua741.cir",
    "TL082": "TL082.cir",
    "LM7171": "LM7171.cir",
    "LM6164": "LM6164.cir",
    "LM6165": "LM6165.cir",
    "LM6171": "LM6171.cir",
}
NETLIST_FILE = {"sallen_key": "SallenKey.cir", "mfb": "Mfb.cir", "antoniou": "Antonious.cir", "tow_thomas": "TowThomas.cir"}
# Main-form list boxes by their client position in Unit1.dfm.
MAIN_LISTBOXES = {(219, 235): "order", (218, 291): "epsilon", (366, 331): "q", (296, 211): "wo_normalized", (448, 211): "wo_denormalized"}
# Band edges: SOFIA reads f1 < f2 < f3 < f4.
BAND_EDGES = {
    "bandpass": (("f1", "fs1"), ("f2", "fp1"), ("f3", "fp2"), ("f4", "fs2")),
    "bandstop": (("f1", "fp1"), ("f2", "fs1"), ("f3", "fs2"), ("f4", "fp2")),
}

WM_SETTEXT, WM_GETTEXT, WM_COMMAND, WM_CLOSE = 0x000C, 0x000D, 0x0111, 0x0010
LB_GETCOUNT, LB_GETTEXT, LB_GETTEXTLEN = 0x018B, 0x0189, 0x018A
BN_CLICKED, MF_BYPOSITION, SMTO_ABORTIFHUNG = 0, 0x400, 0x0002


class Win32:
    def __init__(self) -> None:
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendMessageTimeoutW.argtypes = [
            wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_size_t)
        ]
        self.user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        self.enum_proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def class_name(self, hwnd: int) -> str:
        buffer = ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, buffer, 256)
        return buffer.value

    def text(self, hwnd: int) -> str:
        length = self.user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def top_windows(self, pid: int) -> list[int]:
        found: list[int] = []

        def callback(hwnd: int, _: int) -> bool:
            owner = wt.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid:
                found.append(hwnd)
            return True

        self.user32.EnumWindows(self.enum_proc(callback), 0)
        return found

    def children(self, hwnd: int) -> list[int]:
        found: list[int] = []
        self.user32.EnumChildWindows(hwnd, self.enum_proc(lambda child, _: found.append(child) or True), 0)
        return found

    def send(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        result = ctypes.c_size_t()
        self.user32.SendMessageTimeoutW(hwnd, message, wparam, lparam, SMTO_ABORTIFHUNG, 3000, ctypes.byref(result))
        return result.value

    def set_text(self, hwnd: int, value: str) -> None:
        buffer = ctypes.create_unicode_buffer(value)
        self.send(hwnd, WM_SETTEXT, 0, ctypes.cast(buffer, ctypes.c_void_p).value)

    def click(self, hwnd: int) -> None:
        # Posted (not sent): a click handler may open a modal ShowMessage and block.
        if not self.user32.IsWindowEnabled(hwnd):
            raise RuntimeError(f"control deshabilitado en SOFIA: {self.text(hwnd)!r}")
        control_id = self.user32.GetDlgCtrlID(hwnd) & 0xFFFF
        self.user32.PostMessageW(self.user32.GetParent(hwnd), WM_COMMAND, (BN_CLICKED << 16) | control_id, hwnd)

    def listbox_items(self, hwnd: int) -> list[str]:
        items: list[str] = []
        for index in range(self.send(hwnd, LB_GETCOUNT, 0, 0)):
            buffer = ctypes.create_unicode_buffer(self.send(hwnd, LB_GETTEXTLEN, index, 0) + 2)
            self.send(hwnd, LB_GETTEXT, index, ctypes.cast(buffer, ctypes.c_void_p).value)
            items.append(buffer.value)
        return items

    def client_position(self, hwnd: int) -> tuple[int, int]:
        rect = wt.RECT()
        self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        point = wt.POINT(rect.left, rect.top)
        self.user32.ScreenToClient(self.user32.GetParent(hwnd), ctypes.byref(point))
        return point.x, point.y

    def menu_click(self, form: int, path: list[str]) -> None:
        menu = self.user32.GetMenu(form)
        for depth, label in enumerate(path):
            names = []
            for index in range(self.user32.GetMenuItemCount(menu)):
                buffer = ctypes.create_unicode_buffer(256)
                self.user32.GetMenuStringW(menu, index, buffer, 256, MF_BYPOSITION)
                names.append(buffer.value.replace("&", "").strip())
            matches = [index for index, name in enumerate(names) if name.lower().startswith(label.lower())]
            if not matches:
                raise RuntimeError(f"menu {label!r} no disponible en SOFIA (hay: {names})")
            if depth == len(path) - 1:
                item_id = self.user32.GetMenuItemID(menu, matches[0]) & 0xFFFF
                self.user32.PostMessageW(form, WM_COMMAND, item_id, 0)
            else:
                menu = self.user32.GetSubMenu(menu, matches[0])


class SofiaSession:
    def __init__(self, win: Win32, exe: Path, workdir: Path) -> None:
        self.win = win
        self.process = subprocess.Popen([str(exe)], cwd=str(workdir))
        self.step = "inicio"
        self.dialogs: list[str] = []
        self.main = self._wait_for_form("TfrmFiltro")

    def _wait_for_form(self, class_name: str, timeout: float = 30) -> int:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for hwnd in self.win.top_windows(self.process.pid):
                if self.win.class_name(hwnd) == class_name and self.win.user32.IsWindowVisible(hwnd):
                    time.sleep(1.0)
                    return hwnd
            time.sleep(0.5)
        raise RuntimeError(f"SOFIA no mostro {class_name}")

    def form(self, class_name: str) -> int:
        for hwnd in self.win.top_windows(self.process.pid):
            if self.win.class_name(hwnd) == class_name:
                return hwnd
        raise RuntimeError(f"ventana {class_name} no encontrada")

    def control(self, form: int, class_name: str, label: str) -> int:
        for hwnd in self.win.children(form):
            if self.win.class_name(hwnd) == class_name and self.win.text(hwnd).strip() == label:
                return hwnd
        raise RuntimeError(f"{class_name} {label!r} no encontrado")

    def settle(self, seconds: float = 0.6) -> None:
        """Wait, then dismiss any ShowMessage dialog and remember at which step it appeared."""
        time.sleep(seconds)
        for _ in range(10):
            dialogs = [
                hwnd
                for hwnd in self.win.top_windows(self.process.pid)
                if self.win.class_name(hwnd) == "TMessageForm" and self.win.user32.IsWindowVisible(hwnd)
            ]
            if not dialogs:
                return
            for dialog in dialogs:
                self.dialogs.append(self.step)
                buttons = [hwnd for hwnd in self.win.children(dialog) if self.win.class_name(hwnd) == "TButton"]
                if buttons:
                    self.win.click(buttons[0])
                else:
                    self.win.user32.PostMessageW(dialog, WM_CLOSE, 0, 0)
            time.sleep(0.6)

    def do(self, step: str, action, wait: float = 0.6) -> None:
        self.step = step
        action()
        self.settle(wait)

    def close(self) -> None:
        try:
            self.process.kill()
            self.process.wait(timeout=10)
        except Exception:
            pass


def capture_case(win: Win32, spec: dict[str, Any], exe: Path, workdir: Path) -> dict[str, Any]:
    netlist_path = workdir / NETLIST_FILE[spec["topology"]]
    netlist_path.unlink(missing_ok=True)
    log: dict[str, Any] = {}
    session = SofiaSession(win, exe, workdir)
    try:
        main = session.main
        edits = {win.text(hwnd): hwnd for hwnd in win.children(main) if win.class_name(hwnd) == "TEdit"}
        # Startup texts of the Unit1.dfm edits identify each field.
        field = {"amax": "-3", "amin": "-30", "fp": "100", "fs": "200", "f1": "10", "f2": "30", "f3": "50", "f4": "70"}
        values = {"amax": f"-{float(spec['ap']):g}", "amin": f"-{float(spec['as']):g}"}
        if spec["kind"] in BAND_EDGES:
            values.update({key: f"{float(spec[source]):g}" for key, source in BAND_EDGES[spec["kind"]]})
        else:
            values.update({"fp": f"{float(spec['fp']):g}", "fs": f"{float(spec['fs']):g}"})
        session.step = "especificacion"
        for key, value in values.items():
            win.set_text(edits[field[key]], value)
        session.settle(0.3)
        session.do("tipo", lambda: win.click(session.control(main, "TGroupButton", KIND[spec["kind"]])))
        session.do("aproximacion", lambda: win.click(session.control(main, "TGroupButton", APPROX[spec["approx"]])))
        session.do("polos", lambda: win.click(session.control(main, "TButton", "Pole and Zero Generation")), 1.0)
        log["approximation"] = {
            MAIN_LISTBOXES[pos]: win.listbox_items(hwnd)
            for hwnd in win.children(main)
            if win.class_name(hwnd) == "TListBox" and (pos := win.client_position(hwnd)) in MAIN_LISTBOXES
        }
        session.do("respuesta", lambda: win.click(session.control(main, "TButton", "Frequency Response")), 1.5)
        session.do("topologias", lambda: win.click(session.control(main, "TButton", "Topologies")), 1.0)
        synthesis = session.form("TfrmFiltro2")
        session.do("menu_topologia", lambda: win.menu_click(synthesis, TOPOLOGY_MENU[spec["topology"]]))
        capacitor = next(h for h in win.children(synthesis) if win.class_name(h) == "TEdit" and win.text(h) == "0.1e-6")
        session.step = "capacitor"
        win.set_text(capacitor, f"{float(spec['cap']):g}")
        session.settle(0.3)
        session.do("ejecutar", lambda: win.click(session.control(synthesis, "TButton", "Execute")), 1.0)
        session.do("tolerancia", lambda: win.click(session.control(synthesis, "TGroupButton", "5% of Tolerance")), 0.3)
        session.do("valor_comercial", lambda: win.click(session.control(synthesis, "TButton", "Commercial Value")), 1.0)
        log["components"] = [
            win.listbox_items(hwnd) for hwnd in win.children(synthesis) if win.class_name(hwnd) == "TListBox"
        ]
        session.do("menu_opamp", lambda: win.menu_click(synthesis, ["Opamps", OPAMP_MENU[spec["opamp"]]]))
        session.do("netlist", lambda: win.click(session.control(synthesis, "TButton", "Netlist")), 2.0)
        for _ in range(20):
            if netlist_path.exists() and netlist_path.stat().st_size > 0:
                break
            time.sleep(0.5)
    except RuntimeError as exc:
        log["error"] = f"{exc} (paso: {session.step})"
    finally:
        session.close()
    log["dialogs_at_steps"] = session.dialogs
    log["netlist"] = netlist_path.read_text(encoding="cp1252", errors="replace") if netlist_path.exists() else None
    return log


def write_case(case_dir: Path, spec: dict[str, Any], log: dict[str, Any]) -> str:
    netlist = log.pop("netlist")
    if netlist is None:
        log["status"] = "sin_netlist"
    else:
        log["status"] = "capturado_con_aviso" if log["dialogs_at_steps"] else "capturado"
        model = Path(os.path.relpath(MODELS_DIR / MODEL_FILE[spec["opamp"]], case_dir)).as_posix()
        header = [
            "* Netlist capturado del SOFIA original (Sofia.exe) con scripts/legacy_capture.py",
            "* El editor de SOFIA pega el modelo del opamp desde el portapapeles; aqui se referencia con .include",
        ]
        if log["dialogs_at_steps"]:
            header.append(f"* SOFIA mostro avisos en: {', '.join(log['dialogs_at_steps'])}")
        header.append(f'.include "{model}"')
        (case_dir / "legacy.cir").write_text("\n".join(header) + "\n" + netlist, encoding="utf-8")
    (case_dir / "legacy_capture.json").write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return log["status"]


def prepare_workdir(exe: Path, workdir: Path) -> Path:
    shutil.copyfile(exe, workdir / "Sofia.exe")
    source_models = exe.parent / "modelos"
    shutil.copytree(source_models if source_models.is_dir() else MODELS_DIR, workdir / "modelos")
    return workdir / "Sofia.exe"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture legacy.cir from the original Sofia.exe for each benchmark case.")
    parser.add_argument("--sofia", default=os.environ.get("SOFIA_LEGACY_EXE"), help="Path to Sofia.exe (or set SOFIA_LEGACY_EXE).")
    parser.add_argument("--case-id", action="append", help="Capture only this case id. Can be passed more than once.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if sys.platform != "win32":
        raise SystemExit("legacy_capture.py drives the Windows GUI of Sofia.exe; run it on Windows.")
    if not args.sofia or not Path(args.sofia).exists():
        raise SystemExit("Pass --sofia C:\\ruta\\Sofia.exe or set SOFIA_LEGACY_EXE.")
    cases = (
        [BENCHMARK_DIR / case_id for case_id in args.case_id]
        if args.case_id
        else sorted(path for path in BENCHMARK_DIR.iterdir() if (path / "input.json").exists())
    )
    win = Win32()
    summary = {}
    with tempfile.TemporaryDirectory(prefix="sofia_legacy_") as tmp:
        exe = prepare_workdir(Path(args.sofia), Path(tmp))
        for case_dir in cases:
            spec = json.loads((case_dir / "input.json").read_text(encoding="utf-8"))
            log = capture_case(win, spec, exe, Path(tmp))
            summary[case_dir.name] = write_case(case_dir, spec, log)
            print(f"{case_dir.name}: {summary[case_dir.name]}", flush=True)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
