from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN_CPP = ROOT / "src" / "main.cpp"


class DriverSelectionTest(unittest.TestCase):
    def setUp(self):
        self.source = MAIN_CPP.read_text(encoding="utf-8")

    def test_common_29_inch_bw_driver_macros_are_available(self):
        expected = {
            "NEKOPAW_EPD_DRIVER_290": ("<epd/GxEPD2_290.h>", "GxEPD2_290"),
            "NEKOPAW_EPD_DRIVER_290_T5": ("<epd/GxEPD2_290_T5.h>", "GxEPD2_290_T5"),
            "NEKOPAW_EPD_DRIVER_290_T5D": ("<epd/GxEPD2_290_T5D.h>", "GxEPD2_290_T5D"),
            "NEKOPAW_EPD_DRIVER_290_I6FD": ("<epd/GxEPD2_290_I6FD.h>", "GxEPD2_290_I6FD"),
            "NEKOPAW_EPD_DRIVER_T94": ("<epd/GxEPD2_290_T94.h>", "GxEPD2_290_T94"),
            "NEKOPAW_EPD_DRIVER_T94_V2": ("<epd/GxEPD2_290_T94_V2.h>", "GxEPD2_290_T94_V2"),
            "NEKOPAW_EPD_DRIVER_290_BS": ("<epd/GxEPD2_290_BS.h>", "GxEPD2_290_BS"),
            "NEKOPAW_EPD_DRIVER_290_M06": ("<epd/GxEPD2_290_M06.h>", "GxEPD2_290_M06"),
            "NEKOPAW_EPD_DRIVER_GDEY029T94": ("<gdey/GxEPD2_290_GDEY029T94.h>", "GxEPD2_290_GDEY029T94"),
            "NEKOPAW_EPD_DRIVER_GDEY029T71H": ("<gdey/GxEPD2_290_GDEY029T71H.h>", "GxEPD2_290_GDEY029T71H"),
        }

        for macro, (include_path, driver_class) in expected.items():
            with self.subTest(macro=macro):
                self.assertRegex(self.source, rf"defined\({macro}\)")
                self.assertIn(f"#include {include_path}", self.source)
                self.assertRegex(self.source, rf"using\s+ExampleEpdDriver\s*=\s*{driver_class}\s*;")

    def test_layout_uses_selected_driver_size_after_rotation(self):
        self.assertIn("ExampleEpdDriver::WIDTH", self.source)
        self.assertIn("ExampleEpdDriver::HEIGHT", self.source)
        self.assertRegex(self.source, r"kScreenWidth\s*=\s*kScreenRotated")
        self.assertRegex(self.source, r"kScreenHeight\s*=\s*kScreenRotated")


if __name__ == "__main__":
    unittest.main()
