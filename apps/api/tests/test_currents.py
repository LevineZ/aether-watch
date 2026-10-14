import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GEO_DIR", str(REPO / "content" / "geo"))


class CurrentSourceOrderTest(unittest.TestCase):
    def test_auto_tries_oscar_then_cmems_then_om(self):
        from app.currents import preferred_sources

        self.assertEqual(preferred_sources("best_match"), ["oscar", "cmems", "open-meteo"])
        self.assertEqual(preferred_sources("oscar_v2")[0], "oscar")
        self.assertEqual(preferred_sources("cmems_glo_phy")[0], "cmems")
        self.assertEqual(preferred_sources("meteofrance_currents"), ["open-meteo"])

    def test_cache_key_is_v4(self):
        from app.currents import CACHE_VER, cache_key

        self.assertEqual(CACHE_VER, "v4")
        self.assertTrue(cache_key("best_match", 16, 8).startswith("currents:v4:"))

    def test_creds_helpers_do_not_read_committed_secrets(self):
        example = (REPO / ".env.example").read_text(encoding="utf-8")
        self.assertIn("EARTHDATA_TOKEN=", example)
        self.assertIn("CMEMS_USERNAME=", example)
        self.assertNotRegex(example, r"EARTHDATA_TOKEN=\S+")
        self.assertNotRegex(example, r"CMEMS_PASSWORD=\S+")


class ResampleTest(unittest.TestCase):
    def test_wrap_and_bilerp_gyre(self):
        import numpy as np

        from app.currents import resample_uv, wrap_lon_360

        lons = np.linspace(0.0, 359.0, 8)
        self.assertTrue(np.all(wrap_lon_360(lons) >= -180))
        self.assertTrue(np.all(wrap_lon_360(lons) < 180))
        lats = np.linspace(-60.0, 60.0, 6)
        lon, lat = np.meshgrid(lons, lats)
        u = 0.4 * np.cos(np.radians(lat))
        v = 0.1 * np.sin(np.radians(lon))
        bbox = {"west": -180.0, "south": -70.0, "east": 180.0, "north": 70.0}
        ou, ov = resample_uv(u, v, lons, lats, bbox, 10, 5)
        self.assertEqual(ou.shape, (5, 10))
        self.assertGreater(float(np.max(np.abs(ou))), 0.05)
        # Pacific / Atlantic samples should be ocean-ish non-zero after resample
        self.assertTrue(np.isfinite(ou).all())

    def test_land_mask_zeros_beijing(self):
        import numpy as np

        from app.currents import field_to_payload

        bbox = {"west": 116.4, "south": 38.9, "east": 117.4, "north": 40.9}
        u = np.ones((2, 2))
        v = np.ones((2, 2))
        out = field_to_payload(u, v, bbox, "test:mask")
        self.assertIn("mask", out)
        # linspace south cell is exactly Beijing (116.4, 39.9) — land, no currents.
        nx = out["width"]
        lons = np.linspace(bbox["west"], bbox["east"], nx)
        lats = np.linspace(bbox["north"], bbox["south"], out["height"])
        i = int(np.argmin(np.abs(lons - 116.4)))
        j = int(np.argmin(np.abs(lats - 39.9)))
        self.assertEqual(out["mask"][j * nx + i], 0)
        self.assertEqual(out["u"][j * nx + i], 0.0)

    def test_pack_roundtrip(self):
        import numpy as np

        from app.currents import pack_daily, unpack_daily

        u = np.array([[0.1, 0.2], [0.0, 0.3]], dtype=float)
        v = np.array([[0.0, -0.1], [0.2, 0.0]], dtype=float)
        raw = pack_daily(u, v, np.array([120.0, 130.0]), np.array([30.0, 20.0]), {"source": "t"})
        uu, vv, lons, lats, meta = unpack_daily(raw)
        self.assertEqual(meta.get("source"), "t")
        self.assertEqual(list(lons), [120.0, 130.0])
        np.testing.assert_allclose(uu, u, atol=1e-5)


class CatalogCurrentModelsTest(unittest.TestCase):
    def test_oscar_and_cmems_chips(self):
        from app.catalog import CURRENT_BY_ID

        self.assertIn("oscar_v2", CURRENT_BY_ID)
        self.assertIn("cmems_glo_phy", CURRENT_BY_ID)
        self.assertIn("best_match", CURRENT_BY_ID)


class DocsTest(unittest.TestCase):
    def test_readme_documents_cmems_oscar_keys(self):
        text = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn("EARTHDATA_TOKEN", text)
        self.assertIn("CMEMS_USERNAME", text)
        self.assertIn("10.48670/moi-00016", text)
        self.assertIn("OSCAR", text)
        self.assertNotIn("earth.nullschool.net", text.lower())


if __name__ == "__main__":
    unittest.main()
