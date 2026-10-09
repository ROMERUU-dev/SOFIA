"""Smoke tests of the desktop app. Skipped when PySide6 is not installed."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from sofia_filter_studio.gui.app import MainWindow, create_application
except SystemExit:  # raised by the app module when PySide6 is missing
    MainWindow = None


@unittest.skipIf(MainWindow is None, "PySide6 is not installed")
class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = create_application([])

    def setUp(self) -> None:
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()

    def test_starts_with_a_valid_design(self) -> None:
        self.assertIn("Pasa bajas Butterworth de orden 8", self.window.headline.text())
        self.assertIn(".subckt TL082", self.window.netlist_view.toPlainText())
        self.assertTrue(self.window.save_button.isEnabled())

    def test_band_filter_and_engineering_notation(self) -> None:
        self.window.kind_group.button(2).click()
        self.window.fp1.set_text("0.8k")
        self.window.recalculate()
        self.assertTrue(self.window.headline.text().startswith("Pasa banda"))
        self.assertFalse(self.window.single_spec.isVisibleTo(self.window))

    def test_invalid_spec_shows_message_and_disables_export(self) -> None:
        self.window.fs.set_text("500")
        self.window.recalculate()
        self.assertTrue(self.window.error_banner.isVisibleTo(self.window))
        self.assertIn("Fs debe ser mayor que Fp", self.window.error_banner.text())
        self.assertFalse(self.window.save_button.isEnabled())
        self.assertEqual(self.window.netlist_view.toPlainText(), "")

    def test_lowpass_highpass_switch_keeps_the_spec_valid(self) -> None:
        self.window.kind_group.button(1).click()
        self.window.recalculate()
        self.assertFalse(self.window.error_banner.isVisibleTo(self.window))
        self.assertTrue(self.window.headline.text().startswith("Pasa altas"))

    def test_schematic_tab_shows_the_drawing(self) -> None:
        self.window.tabs.setCurrentWidget(self.window.schematic_tab)
        self.assertIsNotNone(self.window.schematic_view._item)
        self.window.mounting.setCurrentIndex(1)
        self.assertIsNotNone(self.window.schematic_view._item)

    def test_pcb_tab_routes_the_board(self) -> None:
        import time

        self.window.tabs.setCurrentWidget(self.window.pcb_tab)
        deadline = time.time() + 60
        while self.window._pcb is None and time.time() < deadline:
            self.app.processEvents()
            time.sleep(0.05)
        self.assertIsNotNone(self.window._pcb)
        self.assertEqual(self.window._pcb.unrouted, [])
        self.assertIn("ruteo completo", self.window.pcb_status.text())

    def test_detour_through_a_band_filter_keeps_the_spec_valid(self) -> None:
        for index, expected in ((2, "Pasa banda"), (1, "Pasa altas"), (0, "Pasa bajas")):
            self.window.kind_group.button(index).click()
            self.window.recalculate()
            self.assertFalse(self.window.error_banner.isVisibleTo(self.window), self.window.error_banner.text())
            self.assertTrue(self.window.headline.text().startswith(expected))


if __name__ == "__main__":
    unittest.main()
