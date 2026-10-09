"""Entry point of the packaged app: Windows .exe, Linux .deb and macOS .app.

Without arguments it opens the GUI. With arguments it runs the CLI (same options as `sofia`); the
Windows build has no console, so there use --netlist-out to get a file.

With SOFIA_SMOKE_TEST=1 it opens the window, draws the schematic, routes the board, prints what it
checked and exits (status 1 if something failed). The Linux and macOS build scripts run it on the
finished bundle to catch a missing module, Qt plugin or data file.
"""

import os
import sys

from sofia_filter_studio.cli import main as cli_main
from sofia_filter_studio.gui.app import main as gui_main


def smoke_test() -> int:
    import json
    import time

    from sofia_filter_studio.gui.app import MainWindow, create_application

    app = create_application([sys.argv[0]])
    window = MainWindow()
    window.show()
    window.tabs.setCurrentWidget(window.schematic_tab)
    schematic = window.schematic_view._item is not None
    window.tabs.setCurrentWidget(window.pcb_tab)
    deadline = time.time() + 180
    while window._pcb is None and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    checks = {
        "design": window.headline.text().startswith("Pasa bajas"),
        "netlist_with_model": ".subckt TL082" in window.netlist_view.toPlainText(),
        "schematic": schematic,
        "pcb_routed": window._pcb is not None and not window._pcb.unrouted,
        "platform": app.platformName(),
    }
    window.close()
    if sys.stdout is not None:  # the windowed Windows build has no console; its exit status says it all
        print(json.dumps(checks))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if os.environ.get("SOFIA_SMOKE_TEST"):
        raise SystemExit(smoke_test())
    if len(sys.argv) > 1:
        raise SystemExit(cli_main())
    gui_main()
