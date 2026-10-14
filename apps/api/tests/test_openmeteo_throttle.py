import asyncio
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GEO_DIR", str(REPO / "content" / "geo"))


class RetryWaitTest(unittest.TestCase):
    def test_exponential_no_jitter(self):
        from app.openmeteo import retry_wait_seconds

        self.assertEqual(retry_wait_seconds(1, base=2.0, cap=45.0, jitter=False), 2.0)
        self.assertEqual(retry_wait_seconds(2, base=2.0, cap=45.0, jitter=False), 4.0)
        self.assertEqual(retry_wait_seconds(3, base=2.0, cap=45.0, jitter=False), 8.0)
        self.assertEqual(retry_wait_seconds(6, base=2.0, cap=45.0, jitter=False), 45.0)

    def test_retry_after_header_wins(self):
        from app.openmeteo import retry_wait_seconds

        self.assertEqual(retry_wait_seconds(1, "12", base=2.0, cap=45.0, jitter=False), 12.0)
        self.assertEqual(retry_wait_seconds(1, "99", base=2.0, cap=45.0, jitter=False), 45.0)
        self.assertEqual(retry_wait_seconds(1, "nope", base=2.0, cap=45.0, jitter=False), 2.0)


class GatherBatchesTest(unittest.TestCase):
    def test_sequential_and_capped_batch(self):
        from app import openmeteo

        seen: list[int] = []

        async def chunk(pts):
            seen.append(len(pts))
            return [{"ok": True}] * len(pts)

        points = [(float(i), 0.0) for i in range(130)]

        async def run():
            return await openmeteo._gather_batches(points, chunk, batch_size=48)

        out = asyncio.run(run())
        self.assertEqual(len(out), 130)
        self.assertEqual(seen, [48, 48, 34])
        self.assertTrue(all(p and p.get("ok") for p in out))


class ChinaGeoTest(unittest.TestCase):
    def test_prc_geojson_has_land_and_dash(self):
        import json

        path = Path(os.environ["GEO_DIR"]) / "china-prc.geojson"
        if not path.exists():
            path = REPO / "content" / "geo" / "china-prc.geojson"
        data = json.loads(path.read_text(encoding="utf-8"))
        kinds = {(f.get("properties") or {}).get("kind") for f in data["features"]}
        self.assertIn("land", kinds)
        self.assertIn("dash", kinds)
        dash = next(f for f in data["features"] if (f.get("properties") or {}).get("kind") == "dash")
        self.assertEqual(dash["geometry"]["type"], "MultiLineString")
        land = next(f for f in data["features"] if (f.get("properties") or {}).get("kind") == "land")
        self.assertEqual(land["geometry"]["type"], "MultiPolygon")

    def test_defaults_are_conservative(self):
        from app.config import settings

        self.assertEqual(settings.open_meteo_concurrency, 1)
        self.assertLessEqual(settings.open_meteo_batch_size, 80)
        self.assertGreaterEqual(settings.open_meteo_min_interval_seconds, 0.5)
        self.assertLessEqual(settings.field_nx, 32)
        self.assertLessEqual(settings.field_ny, 24)
        self.assertLessEqual(settings.current_nx, 24)
        self.assertLessEqual(settings.current_ny, 12)

    def test_current_basins_are_global_not_scs_only(self):
        text = (REPO / "apps" / "web" / "utils" / "windField.ts").read_text(encoding="utf-8")
        weights = {}
        for name in ("n-pacific", "s-pacific", "n-atlantic", "s-atlantic", "indian", "southern", "china-seas", "scs"):
            marker = f'name: "{name}"'
            self.assertIn(marker, text)
            after = text.split(marker, 1)[1]
            weight = float(after.split("weight:", 1)[1].split(",", 1)[0].strip())
            weights[name] = weight
        self.assertGreater(weights["n-pacific"], weights["scs"])
        self.assertLess(weights["scs"] + weights["china-seas"], 0.2)
        self.assertGreater(weights["n-pacific"] + weights["s-pacific"] + weights["n-atlantic"], 0.4)


if __name__ == "__main__":
    unittest.main()
