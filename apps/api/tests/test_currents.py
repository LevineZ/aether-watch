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


# Realistic CMR granule links (HTTPS data, then s3://, then OPeNDAP). Last .nc+"protected"
# match used to overwrite href with s3:// and crash httpx.
SAMPLE_CMR_LINKS = [
    {
        "rel": "http://esipfed.org/ns/fedsearch/1.1/data#",
        "title": "Download oscar_currents_nrt_20261011.nc",
        "href": "https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-protected/OSCAR_L4_OC_NRT_V2.0/oscar_currents_nrt_20261011.nc",
    },
    {
        "rel": "http://esipfed.org/ns/fedsearch/1.1/metadata#",
        "title": "Download oscar_currents_nrt_20261011.nc.md5",
        "href": "https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-public/OSCAR_L4_OC_NRT_V2.0/oscar_currents_nrt_20261011.nc.md5",
    },
    {
        "rel": "http://esipfed.org/ns/fedsearch/1.1/s3#",
        "title": "This link provides direct download access via S3 to the granule",
        "href": "s3://podaac-ops-cumulus-protected/OSCAR_L4_OC_NRT_V2.0/oscar_currents_nrt_20261011.nc",
    },
    {
        "rel": "http://esipfed.org/ns/fedsearch/1.1/metadata#",
        "href": "s3://podaac-ops-cumulus-public/OSCAR_L4_OC_NRT_V2.0/oscar_currents_nrt_20261011.nc.md5",
    },
    {
        "rel": "http://esipfed.org/ns/fedsearch/1.1/metadata#",
        "href": "https://archive.podaac.earthdata.nasa.gov/s3credentials",
    },
    {
        "rel": "http://esipfed.org/ns/fedsearch/1.1/service#",
        "title": "OPeNDAP request URL",
        "href": "https://opendap.earthdata.nasa.gov/collections/C2102958977-POCLOUD/granules/oscar_currents_nrt_20261011",
    },
    {
        "rel": "http://esipfed.org/ns/fedsearch/1.1/service#",
        "href": "https://opendap.earthdata.nasa.gov",
    },
    {
        "rel": "http://esipfed.org/ns/fedsearch/1.1/data#",
        "href": "https://search.earthdata.nasa.gov/search/granules?p=C2102958977-POCLOUD",
    },
]


class OscarCmrUrlTest(unittest.TestCase):
    def test_s3_maps_to_podaac_https(self):
        from app.currents import http_fetch_url, s3_to_https

        s3 = "s3://podaac-ops-cumulus-protected/OSCAR_L4_OC_NRT_V2.0/oscar_currents_nrt_20261011.nc"
        https = s3_to_https(s3)
        self.assertTrue(https.startswith("https://archive.podaac.earthdata.nasa.gov/"))
        self.assertIn("oscar_currents_nrt_20261011.nc", https)
        self.assertFalse(https.startswith("s3://"))
        self.assertEqual(http_fetch_url(s3), https)
        self.assertIsNone(http_fetch_url("s3://unknown-bucket/file.nc"))
        self.assertIsNone(http_fetch_url("ftp://example.com/x.nc"))

    def test_parse_prefers_https_not_raw_s3(self):
        from app.currents import parse_oscar_granule

        parsed = parse_oscar_granule(
            {
                "title": "oscar_currents_nrt_20261011",
                "time_start": "2026-10-11T00:00:00.000Z",
                "links": SAMPLE_CMR_LINKS,
            }
        )
        self.assertEqual(parsed["stamp"], "20261011")
        self.assertTrue(parsed["href"].startswith("https://"))
        self.assertNotIn("s3://", parsed["href"])
        self.assertIn("podaac-ops-cumulus-protected", parsed["href"])
        self.assertTrue(parsed["href"].endswith(".nc"))
        self.assertIn("opendap.earthdata.nasa.gov/collections/", parsed["opendap"])
        self.assertIn("oscar_currents_nrt_20261011", parsed["opendap"])

    def test_s3_only_granule_still_https(self):
        from app.currents import parse_oscar_granule

        parsed = parse_oscar_granule(
            {
                "title": "oscar_currents_nrt_20261011",
                "time_start": "2026-10-11T00:00:00.000Z",
                "links": [
                    {
                        "rel": "http://esipfed.org/ns/fedsearch/1.1/s3#",
                        "href": "s3://podaac-ops-cumulus-protected/OSCAR_L4_OC_NRT_V2.0/x.nc",
                    }
                ],
            }
        )
        self.assertEqual(
            parsed["href"],
            "https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-protected/OSCAR_L4_OC_NRT_V2.0/x.nc",
        )
        self.assertFalse(parsed["href"].startswith("s3://"))

    def test_opendap_constraints_stay_in_range(self):
        from app.currents import OSCAR_LAT_LAST, oscar_opendap_request_urls

        urls = oscar_opendap_request_urls(
            "https://opendap.earthdata.nasa.gov/collections/C2102958977-POCLOUD/granules/oscar_currents_nrt_20261011"
        )
        self.assertGreaterEqual(len(urls), 2)
        joined = " ".join(urls)
        self.assertNotIn("[0:4:719]", joined)
        self.assertIn(f"[0:4:{OSCAR_LAT_LAST}]", joined)
        self.assertTrue(all(u.startswith("https://") for u in urls))
        self.assertEqual(oscar_opendap_request_urls("s3://bucket/key"), [])

    def test_bearer_survives_as_auth_flow(self):
        import httpx

        from app.currents import EarthdataBearer

        token = "test-earthdata-token"
        req = httpx.Request("GET", "https://archive.podaac.earthdata.nasa.gov/file.nc")
        next(EarthdataBearer(token).auth_flow(req))
        self.assertEqual(req.headers["Authorization"], f"Bearer {token}")

    def test_coarsen_native_oscar_grid(self):
        import numpy as np

        from app.currents import coarsen_uv

        u = np.ones((719, 1440))
        v = np.zeros((719, 1440))
        lons = np.linspace(0, 359.75, 1440)
        lats = np.linspace(89.75, -89.75, 719)
        cu, cv, clons, clats = coarsen_uv(u, v, lons, lats, 4)
        self.assertLess(cu.shape[0], 200)
        self.assertEqual(cu.shape[1], clons.size)
        already = coarsen_uv(cu, cv, clons, clats, 4)
        self.assertEqual(already[0].shape, cu.shape)


class OscarDailyFetchTest(unittest.IsolatedAsyncioTestCase):
    async def test_https_download_returns_oscar_field(self):
        import numpy as np

        from app import currents

        lons = np.linspace(-180.0, 170.0, 12)
        lats = np.linspace(60.0, -60.0, 8)
        u = np.full((8, 12), 0.25)
        v = np.full((8, 12), -0.1)
        nc_bytes = b"CDF\x01" + b"\x00" * 12  # netCDF magic; decode is stubbed
        seen: list[str] = []

        class FakeResp:
            def __init__(self, status: int, content: bytes, payload=None):
                self.status_code = status
                self.content = content
                self._payload = payload or {}

            def json(self):
                return self._payload

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"http {self.status_code}")

        cmr = {
            "feed": {
                "entry": [
                    {
                        "title": "oscar_currents_nrt_20261011",
                        "time_start": "2026-10-11T00:00:00.000Z",
                        "links": SAMPLE_CMR_LINKS,
                    }
                ]
            }
        }

        class FakeClient:
            async def get(self, url, params=None, auth=None):
                seen.append(url)
                if "cmr.earthdata.nasa.gov" in url:
                    return FakeResp(200, b"{}", cmr)
                if url.startswith("s3://"):
                    raise AssertionError(f"must not fetch s3:// {url}")
                if "archive.podaac.earthdata.nasa.gov" in url and url.endswith(".nc"):
                    return FakeResp(200, nc_bytes)
                return FakeResp(404, b"missing")

        original = {
            "http": currents.http,
            "load_daily": currents.load_daily,
            "save_daily": currents.save_daily,
            "earthdata_token": currents.earthdata_token,
            "has_oscar_creds": currents.has_oscar_creds,
            "_decode_nc_uv": currents._decode_nc_uv,
        }

        async def fake_http():
            return FakeClient()

        currents.http = fake_http  # type: ignore[assignment]
        currents.load_daily = lambda *a, **k: None  # type: ignore[assignment]
        currents.save_daily = lambda *a, **k: None  # type: ignore[assignment]
        currents.earthdata_token = lambda: "test-earthdata-token"  # type: ignore[assignment]
        currents.has_oscar_creds = lambda: True  # type: ignore[assignment]
        currents._decode_nc_uv = lambda raw: (u, v, lons, lats, {"u": "u", "v": "v"})  # type: ignore[assignment]
        try:
            daily = await currents.fetch_oscar_daily()
            self.assertIsNotNone(daily)
            ou, ov, out_lons, out_lats, meta = daily
            self.assertEqual(meta.get("source"), "oscar-v2")
            self.assertEqual(meta.get("fetch"), "https")
            self.assertGreater(float(np.max(np.abs(ou))), 0.05)
            self.assertTrue(any("archive.podaac.earthdata.nasa.gov" in item for item in seen))
            self.assertFalse(any(item.startswith("s3://") for item in seen))
            payload = currents.payload_from_daily(
                ou, ov, out_lons, out_lats, "oscar-v2:OSCAR_L4_OC_NRT_V2.0", 10, 5
            )
            self.assertIn("oscar", payload["source"])
        finally:
            for name, value in original.items():
                setattr(currents, name, value)


class OscarFetchGuardTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_bytes_maps_s3_to_https_never_fetches_s3(self):
        from app import currents

        seen: list[str] = []

        class FakeResp:
            status_code = 404
            content = b"nope"

        class FakeClient:
            async def get(self, url, auth=None):
                seen.append(url)
                return FakeResp()

        async def fake_http():
            return FakeClient()

        original = currents.http
        currents.http = fake_http  # type: ignore[assignment]
        try:
            got = await currents._oscar_get_bytes(
                "s3://podaac-ops-cumulus-protected/OSCAR_L4_OC_NRT_V2.0/x.nc",
                None,
                label="download",
            )
            self.assertIsNone(got)
            self.assertEqual(len(seen), 1)
            self.assertTrue(seen[0].startswith("https://archive.podaac.earthdata.nasa.gov/"))
            self.assertFalse(any(u.startswith("s3://") for u in seen))
        finally:
            currents.http = original

    async def test_get_bytes_skips_unmapped_s3(self):
        from app import currents

        async def boom():
            raise AssertionError("http client must not run for unmapped s3://")

        original = currents.http
        currents.http = boom  # type: ignore[assignment]
        try:
            got = await currents._oscar_get_bytes("s3://unknown-bucket/x.nc", None, label="download")
            self.assertIsNone(got)
        finally:
            currents.http = original


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
