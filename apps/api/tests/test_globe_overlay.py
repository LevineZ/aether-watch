import inspect
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GEO_DIR", str(REPO / "content" / "geo"))


class WeatherModelTest(unittest.TestCase):
    def test_marine_chips_are_not_forecast_models(self):
        from app.catalog import weather_model_id

        self.assertEqual(weather_model_id("best_match"), "gfs_seamless")
        self.assertEqual(weather_model_id("oscar_v2"), "gfs_seamless")
        self.assertEqual(weather_model_id("cmems_glo_phy"), "gfs_seamless")
        self.assertEqual(weather_model_id("gfs_seamless"), "gfs_seamless")
        self.assertEqual(weather_model_id("ecmwf_ifs025"), "ecmwf_ifs025")


class GlobeCacheKeyTest(unittest.TestCase):
    def test_earth_page_16x10_key(self):
        from app.catalog import GLOBE_BBOX
        from app.config import settings
        from app.openmeteo import field_cache_key

        self.assertEqual(settings.globe_field_nx, 16)
        self.assertEqual(settings.globe_field_ny, 10)
        key = field_cache_key("gfs_seamless", "temperature_2m", GLOBE_BBOX, 16, 10, 0)
        self.assertEqual(
            key,
            "field:v4:gfs_seamless:temperature_2m:-180.0:-70.0:180.0:70.0:16x10:0",
        )
        pressure = field_cache_key("gfs_seamless", "surface_pressure", GLOBE_BBOX, 16, 10, 0)
        rain = field_cache_key("gfs_seamless", "precipitation", GLOBE_BBOX, 16, 10, 0)
        self.assertIn("surface_pressure", pressure)
        self.assertIn("precipitation", rain)
        self.assertIn("16x10", pressure)
        self.assertIn("16x10", rain)


class SyntheticOverlayTest(unittest.TestCase):
    def test_globe_and_wave_synthetics_have_signal(self):
        from app.openmeteo import synthetic_globe_field, synthetic_wave_field

        for var in ("temperature_2m", "surface_pressure", "precipitation"):
            field = synthetic_globe_field(var, 8, 4)
            self.assertGreaterEqual(int(field.get("filled") or 0), 8)
            self.assertTrue(any(v is not None for row in field["values"] for v in row))
        waves = synthetic_wave_field(8, 4)
        self.assertGreaterEqual(int(waves.get("filled") or 0), 8)
        self.assertEqual(waves["unit"], "s")


class PrewarmCoverageTest(unittest.TestCase):
    def test_prewarm_covers_globe_and_china_scalars(self):
        from app.openmeteo import prewarm_hot_paths

        src = inspect.getsource(prewarm_hot_paths)
        self.assertIn("fetch_globe_fields", src)
        self.assertIn("fetch_china_fields", src)
        self.assertIn("temperature_2m", src)
        self.assertIn("surface_pressure", src)
        self.assertIn("precipitation", src)
        self.assertIn("FORECAST_PREVIEW_MODELS", src)
        self.assertIn("china_models", src)
        self.assertNotIn("nx=8", src)
        self.assertNotIn("ny=6", src)
        forecast = (REPO / "apps" / "web" / "pages" / "forecast.vue").read_text(encoding="utf-8")
        self.assertNotIn("COARSE_NX", forecast)
        self.assertNotIn("query.nx", forecast)

    def test_429_fast_falls_back_to_last_good(self):
        from app.openmeteo import _om_json, fetch_china_fields, fetch_field, fetch_globe_fields

        om = inspect.getsource(_om_json)
        self.assertIn("OpenMeteoRateLimit", om)
        field = inspect.getsource(fetch_field)
        self.assertIn("last_good_on_rate_limit", field)
        self.assertIn("unavailable_field", field)
        self.assertIn("assemble_scalar_fields_from_v4", field)
        china = inspect.getsource(fetch_china_fields)
        self.assertIn("last_good_on_rate_limit", china)
        globe = inspect.getsource(fetch_globe_fields)
        self.assertIn("last_good_on_rate_limit", globe)
        self.assertIn("globe_fields_from_v4", globe)
        self.assertIn("field:v4", globe)

    def test_prewarm_retries_with_backoff(self):
        from app.openmeteo import prewarm_hot_paths, prewarm_hot_paths_resilient

        src = inspect.getsource(prewarm_hot_paths)
        self.assertIn("open_meteo_prewarm_gap_seconds", src)
        self.assertIn("skip remaining models this pass", src)
        resilient = inspect.getsource(prewarm_hot_paths_resilient)
        self.assertIn("retry_wait_seconds", resilient)
        self.assertIn("open_meteo_prewarm_retry_base", resilient)
        main = (REPO / "apps" / "api" / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("prewarm_hot_paths_resilient", main)
        self.assertIn("unavailable_field", main)

    def test_marine_current_piggybacks_wave_period(self):
        from app.openmeteo import _fetch_current_patch

        src = inspect.getsource(_fetch_current_patch)
        self.assertIn("wave_peak_period", src)
        self.assertIn("wave_period", src)


class FrontGlobeStyleTest(unittest.TestCase):
    def test_underlay_keeps_particles_and_earth_dock(self):
        globe = (REPO / "apps" / "web" / "components" / "EarthGlobe.vue").read_text(encoding="utf-8")
        self.assertIn("layer?.setVisible(!!props.flow)", globe)
        self.assertNotIn("layer?.setVisible(false)", globe)
        self.assertIn("overlayOpacity", globe)
        self.assertIn("applyGlobeBasemap", globe)
        self.assertIn("ensureGlobeLand", globe)
        self.assertIn("globeFallbackStyle", globe)
        self.assertNotIn("OPENFREEMAP_DARK", globe)
        index = (REPO / "apps" / "web" / "pages" / "index.vue").read_text(encoding="utf-8")
        self.assertIn("earth-dock", index)
        self.assertIn("panelOpen", index)
        self.assertIn("/api/globe-fields", index)
        self.assertIn("/api/waves", index)
        cmap = (REPO / "apps" / "web" / "utils" / "colormap.ts").read_text(encoding="utf-8")
        self.assertIn("waves:", cmap)
        forecast = (REPO / "apps" / "web" / "pages" / "forecast.vue").read_text(encoding="utf-8")
        self.assertIn("finally", forecast)
        self.assertIn("timeout: 12000", forecast)
        self.assertIn("mapBusy", forecast)
        self.assertIn("pageBusy", forecast)
        self.assertIn("fieldPending", forecast)
        self.assertIn("fieldHasSignal", forecast)
        self.assertIn("fieldErrors", forecast)
        self.assertIn("retryField", forecast)
        self.assertIn("debounceFields", forecast)
        self.assertNotIn("COARSE_NX", forecast)
        self.assertNotIn("fetchFieldBackoff", forecast)
        fmap = (REPO / "apps" / "web" / "components" / "FieldMap.vue").read_text(encoding="utf-8")
        self.assertIn("map-error", fmap)
        self.assertIn("forecast.retry", fmap)
        self.assertIn("forecast.rateLimited", (REPO / "apps" / "web" / "utils" / "messages.ts").read_text(encoding="utf-8"))

    def test_globe_uses_ocean_background_and_local_land_fill(self):
        land = (REPO / "apps" / "web" / "utils" / "globeLand.ts").read_text(encoding="utf-8")
        style = (REPO / "apps" / "web" / "utils" / "globeStyle.ts").read_text(encoding="utf-8")
        self.assertIn('GLOBE_OCEAN = "#071624"', land)
        self.assertIn("aw-globe-land-fill", land)
        self.assertIn("/geo/ne-110m-land.geojson", land)
        self.assertIn("/api/geo/ne-110m-land.json", land)
        self.assertIn("applyGlobeBasemap", land)
        self.assertIn("ensureGlobeLand", style)
        self.assertNotIn('"background-color", "#05070d"', style)
        self.assertNotIn('"background-color", "#05070d"', land)
        api = (REPO / "apps" / "api" / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("/api/geo/ne-110m-land.json", api)


class GlobeLandGeoTest(unittest.TestCase):
    def test_ne110m_land_covers_china(self):
        import json

        paths = [
            REPO / "content" / "geo" / "ne-110m-land.geojson",
            REPO / "apps" / "web" / "public" / "geo" / "ne-110m-land.geojson",
        ]
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["type"], "FeatureCollection")
            self.assertGreaterEqual(len(data["features"]), 100)
            china = False

            def walk(coords):
                nonlocal china
                if not coords:
                    return
                if isinstance(coords[0], (int, float)):
                    lon, lat = float(coords[0]), float(coords[1])
                    if 70.0 <= lon <= 140.0 and 15.0 <= lat <= 55.0:
                        china = True
                    return
                for item in coords:
                    walk(item)

            for feat in data["features"]:
                walk((feat.get("geometry") or {}).get("coordinates"))
            self.assertTrue(china, f"{path} missing East Asia land")


if __name__ == "__main__":
    unittest.main()
