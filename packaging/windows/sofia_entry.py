"""Entry point of the Windows executable.

Without arguments it opens the GUI. With arguments it runs the CLI (same options as `sofia`); in the
windowed build there is no console, so use --netlist-out to get a file.
"""

import sys

from sofia_filter_studio.cli import main as cli_main
from sofia_filter_studio.gui.app import main as gui_main


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit(cli_main())
    gui_main()
