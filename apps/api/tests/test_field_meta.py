import unittest

from app.fieldmeta import field_clock


class FieldClockTest(unittest.TestCase):
    def test_init_and_valid(self):
        times = [f"2026-10-14T{h:02d}:00" for h in range(0, 12)]
        init, valid = field_clock(times, 6)
        self.assertEqual(init, "2026-10-14T00:00")
        self.assertEqual(valid, "2026-10-14T06:00")

    def test_empty(self):
        self.assertEqual(field_clock([], 3), (None, None))


class ChinaSeasMaskTest(unittest.TestCase):
    def test_scs_is_ocean(self):
        try:
            from app.landmask import is_forced_ocean, is_land
        except ImportError:
            self.skipTest("numpy not installed")
        self.assertTrue(is_forced_ocean(114.0, 12.0))
        self.assertFalse(is_land(114.0, 12.0))

    def test_beijing_is_land(self):
        try:
            from app.landmask import is_forced_ocean, is_land
        except ImportError:
            self.skipTest("numpy not installed")
        self.assertFalse(is_forced_ocean(116.4, 39.9))
        self.assertTrue(is_land(116.4, 39.9))


if __name__ == "__main__":
    unittest.main()
