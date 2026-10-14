import copy
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GEO_DIR", str(REPO / "content" / "geo"))


def _real_grid(variable: str, model: str, bbox: dict, nx: int, ny: int, value: float = 12.0) -> dict:
    import numpy as np

    from app.openmeteo import _grid_points, _scalar_payload

    lats, lons = _grid_points(bbox, nx, ny)
    values = np.full((ny, nx), float(value), dtype=float)
    return _scalar_payload(variable, model, bbox, lats, lons, values)


class Field429FallbackTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store: dict = {}
        from app import openmeteo

        store = self.store

        async def cache_get(key: str):
            val = store.get(key)
            return copy.deepcopy(val) if val is not None else None

        async def cache_set(key: str, value, ttl: int):
            store[key] = copy.deepcopy(value)

        self._p_get = patch.object(openmeteo, "cache_get", cache_get)
        self._p_set = patch.object(openmeteo, "cache_set", cache_set)
        self._p_get.start()
        self._p_set.start()

    def tearDown(self):
        self._p_get.stop()
        self._p_set.stop()

    async def test_china_field_serves_last_good_without_om(self):
        from app.catalog import CHINA_BBOX
        from app.openmeteo import fetch_field, field_cache_key, field_is_real

        key = field_cache_key("ecmwf_ifs025", "temperature_2m", CHINA_BBOX, 20, 15, 0)
        self.store[f"{key}:last"] = _real_grid("temperature_2m", "ecmwf_ifs025", CHINA_BBOX, 20, 15, 18.5)
        gather = AsyncMock(side_effect=AssertionError("must not hit Open-Meteo when last-good exists"))
        with patch("app.openmeteo._gather_batches", gather):
            out = await fetch_field("ecmwf_ifs025", "temperature_2m", CHINA_BBOX, 20, 15, 0)
        gather.assert_not_called()
        self.assertTrue(field_is_real(out))
        self.assertTrue(out.get("stale"))
        self.assertGreater(out.get("filled") or 0, 0)

    async def test_china_field_429_skips_empty_live_uses_last(self):
        from app.catalog import CHINA_BBOX
        from app.openmeteo import OpenMeteoRateLimit, fetch_field, field_cache_key, field_is_real, unavailable_field

        key = field_cache_key("ecmwf_ifs025", "temperature_2m", CHINA_BBOX, 20, 15, 0)
        self.store[key] = unavailable_field(
            "ecmwf_ifs025", "temperature_2m", CHINA_BBOX, 20, 15, reason="open-meteo-429"
        )
        self.store[f"{key}:last"] = _real_grid("temperature_2m", "ecmwf_ifs025", CHINA_BBOX, 20, 15, 18.5)
        with patch(
            "app.openmeteo._gather_batches",
            AsyncMock(side_effect=OpenMeteoRateLimit("open-meteo 429")),
        ):
            out = await fetch_field("ecmwf_ifs025", "temperature_2m", CHINA_BBOX, 20, 15, 0)
        self.assertTrue(field_is_real(out))
        self.assertTrue(out.get("stale"))
        self.assertEqual(out.get("degraded"), "open-meteo-429")
        self.assertNotEqual(out.get("error"), "open-meteo-429")
        self.assertGreater(out.get("filled") or 0, 0)

    async def test_china_field_429_without_stale_is_parseable_not_500(self):
        from app.catalog import CHINA_BBOX
        from app.openmeteo import OpenMeteoRateLimit, fetch_field, field_is_real

        with patch(
            "app.openmeteo._gather_batches",
            AsyncMock(side_effect=OpenMeteoRateLimit("open-meteo 429")),
        ):
            out = await fetch_field("ecmwf_aifs025_single", "precipitation", CHINA_BBOX, 20, 15, 0)
        self.assertFalse(field_is_real(out))
        self.assertEqual(out.get("error"), "open-meteo-429")
        self.assertTrue(out.get("unavailable"))
        self.assertEqual(out.get("filled"), 0)
        self.assertEqual(out.get("kind"), "unavailable")
        self.assertTrue(all(v is None for row in out["values"] for v in row))

    async def test_globe_fields_prefers_field_v4_over_synthetic(self):
        from app.catalog import ELEMENT_BY_ID, GLOBE_BBOX, GLOBE_SCALAR_VARS
        from app.openmeteo import OpenMeteoRateLimit, fetch_globe_fields, field_cache_key, field_is_real

        nx, ny = 16, 10
        for var in GLOBE_SCALAR_VARS:
            om = ELEMENT_BY_ID[var]["om"]
            key = field_cache_key("gfs_seamless", om, GLOBE_BBOX, nx, ny, 0)
            self.store[key] = _real_grid(var, "gfs_seamless", GLOBE_BBOX, nx, ny, 7.0)
        gather = AsyncMock(side_effect=OpenMeteoRateLimit("open-meteo 429"))
        with patch("app.openmeteo._gather_batches", gather):
            out = await fetch_globe_fields("gfs_seamless")
        gather.assert_not_called()
        self.assertIn("field:v4", out.get("source") or "")
        self.assertFalse(str(out.get("source") or "").startswith("synthetic"))
        self.assertFalse(out.get("fallback"))
        for var in GLOBE_SCALAR_VARS:
            self.assertTrue(field_is_real(out["fields"][var]), var)

    async def test_globe_fields_429_partial_v4_not_all_synthetic(self):
        from app.catalog import ELEMENT_BY_ID, GLOBE_BBOX
        from app.openmeteo import OpenMeteoRateLimit, fetch_globe_fields, field_cache_key, field_is_real

        key = field_cache_key("gfs_seamless", ELEMENT_BY_ID["temperature_2m"]["om"], GLOBE_BBOX, 16, 10, 0)
        self.store[key] = _real_grid("temperature_2m", "gfs_seamless", GLOBE_BBOX, 16, 10, 3.0)
        with patch(
            "app.openmeteo._gather_batches",
            AsyncMock(side_effect=OpenMeteoRateLimit("open-meteo 429")),
        ):
            out = await fetch_globe_fields("gfs_seamless")
        self.assertTrue(field_is_real(out["fields"]["temperature_2m"]))
        self.assertIn("field:v4", out.get("source") or "")
        self.assertNotEqual(out.get("source"), "synthetic:open-meteo-429")


class PrewarmBackoffTest(unittest.IsolatedAsyncioTestCase):
    async def test_china_429_skips_remaining_models_same_pass(self):
        from app.openmeteo import prewarm_hot_paths

        calls: list[str] = []

        async def fake_china(mid, *args, **kwargs):
            calls.append(mid)
            return {
                "error": "open-meteo-429",
                "degraded": "open-meteo-429",
                "fallback": True,
                "fields": {},
            }

        with (
            patch("app.openmeteo.fetch_china_fields", fake_china),
            patch("app.openmeteo.asyncio.sleep", AsyncMock()),
        ):
            summary = await prewarm_hot_paths(
                include_currents=False,
                include_globe=False,
                include_wind=False,
                include_waves=False,
            )
        self.assertEqual(calls, ["gfs_seamless"])
        self.assertIn("china-fields-ecmwf_ifs025", summary["errors"])
        self.assertIn("china-fields-ecmwf_aifs025_single", summary["errors"])
        self.assertEqual(summary["errors"]["china-fields-gfs_seamless"], "open-meteo-429")

    async def test_resilient_prewarm_retries_after_backoff(self):
        from app.catalog import GLOBE_SCALAR_VARS
        from app.openmeteo import prewarm_hot_paths_resilient

        n = {"china": 0}
        sleeps: list[float] = []

        async def fake_sleep(seconds: float):
            sleeps.append(float(seconds))

        async def fake_china(mid, *args, **kwargs):
            n["china"] += 1
            if n["china"] == 1:
                return {
                    "error": "open-meteo-429",
                    "degraded": "open-meteo-429",
                    "fallback": True,
                    "fields": {},
                }
            return {
                "fields": {
                    var: {"filled": 20, "source": f"open-meteo:{mid}", "values": [[1.0]]}
                    for var in GLOBE_SCALAR_VARS
                }
            }

        async def fake_globe(*args, **kwargs):
            return {
                "fields": {
                    var: {"filled": 20, "source": "open-meteo:gfs_seamless", "values": [[1.0]]}
                    for var in GLOBE_SCALAR_VARS
                },
                "source": "open-meteo:gfs_seamless",
                "fallback": False,
            }

        with (
            patch("app.openmeteo.fetch_china_fields", fake_china),
            patch("app.openmeteo.fetch_globe_fields", fake_globe),
            patch("app.openmeteo.fetch_current_grid", AsyncMock()),
            patch("app.openmeteo.fetch_wind_grid", AsyncMock()),
            patch("app.openmeteo.fetch_wave_field", AsyncMock()),
            patch("app.openmeteo.asyncio.sleep", fake_sleep),
        ):
            summary = await prewarm_hot_paths_resilient()
        self.assertGreaterEqual(n["china"], 2)
        self.assertTrue(any(s >= 15.0 for s in sleeps))
        self.assertTrue(any("china-fields:" in item and "gfs_seamless" in item for item in summary["ok"]))
        self.assertGreaterEqual(int(summary.get("prewarm_attempts") or 0), 2)


class DefaultsStillConservative(unittest.TestCase):
    def test_concurrency_stays_one(self):
        from app.config import settings

        self.assertEqual(settings.open_meteo_concurrency, 1)
        self.assertEqual(settings.field_nx, 20)
        self.assertEqual(settings.field_ny, 15)
        self.assertGreaterEqual(settings.open_meteo_prewarm_gap_seconds, 2.0)
        self.assertGreaterEqual(settings.open_meteo_prewarm_retry_base, 15.0)


if __name__ == "__main__":
    unittest.main()
