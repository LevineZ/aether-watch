"""Ocean-current grids from OSCAR v2.0 and/or CMEMS, with Open-Meteo fallback.

Order for model=best_match / CURRENT_SOURCE=auto:
  Redis live → Redis last-good → daily object/local field → OSCAR v2 → CMEMS → OM Marine → synthetic.

OSCAR is NASA PO.DAAC OSCAR_L4_OC_NRT_V2.0 (Earthdata username/password or token).
CMEMS is GLOBAL_ANALYSISFORECAST_PHY_001_024 / DOI 10.48670/moi-00016
(cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m) via username/password or token.

Neither source is scraped from earth.nullschool.net. Daily fields are cached
in MinIO + a local directory so we do not hammer upstream. OM grids stay at
CURRENT_NX × CURRENT_NY.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from app.catalog import CHINA_SEAS_BBOX, CURRENT_BY_ID
from app.config import settings
from app.landmask import apply_ocean_mask

log = logging.getLogger("aetherwatch.currents")

CACHE_VER = "v4"
GLOBAL_BBOX = {"west": -180.0, "south": -70.0, "east": 180.0, "north": 70.0}
USER_AGENT = "AetherWatch/0.1 (ocean currents; docker compose; no-nullschool)"
CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.json"
URS_TOKEN = "https://urs.earthdata.nasa.gov/api/users/token"
URS_TOKENS = "https://urs.earthdata.nasa.gov/api/users/tokens"
CMEMS_TOKEN_URLS = (
    "https://auth.marine.copernicus.eu/auth/realms/eds/protocol/openid-connect/token",
    "https://auth.marine.copernicus.eu/realms/eds/protocol/openid-connect/token",
    "https://identity.marine.copernicus.eu/auth/realms/eds/protocol/openid-connect/token",
)
CMEMS_CLIENT_IDS = ("copernicus-marine-client", "cds")

_http: httpx.AsyncClient | None = None
_earthdata_token: str | None = None
_source_gate: asyncio.Lock | None = None


def source_gate() -> asyncio.Lock:
    global _source_gate
    if _source_gate is None:
        _source_gate = asyncio.Lock()
    return _source_gate


async def http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            timeout=httpx.Timeout(90.0, connect=12.0),
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            follow_redirects=True,
        )
    return _http


async def close() -> None:
    global _http, _earthdata_token
    if _http is not None:
        await _http.aclose()
        _http = None
    _earthdata_token = None


def earthdata_user() -> str:
    return (settings.earthdata_username or "").strip()


def earthdata_password() -> str:
    return (settings.earthdata_password or "").strip()


def earthdata_token() -> str:
    return (settings.earthdata_token or "").strip()


def has_oscar_creds() -> bool:
    return bool(earthdata_token() or (earthdata_user() and earthdata_password()))


def cmems_user() -> str:
    return (settings.cmems_username or settings.copernicusmarine_service_username or "").strip()


def cmems_password() -> str:
    return (settings.cmems_password or settings.copernicusmarine_service_password or "").strip()


def cmems_token() -> str:
    return (settings.cmems_token or settings.copernicusmarine_service_token or "").strip()


def has_cmems_creds() -> bool:
    return bool(cmems_token() or (cmems_user() and cmems_password()))


def preferred_sources(model: str) -> list[str]:
    """Resolved fetch order. `auto` / best_match tries OSCAR then CMEMS then OM."""
    raw = (model or "best_match").strip()
    forced = (settings.current_source or "auto").strip().lower()
    if raw in {"oscar", "oscar_v2", "oscar_nrt"}:
        return ["oscar", "open-meteo"]
    if raw in {"cmems", "cmems_glo_phy", "cmems_phy"}:
        return ["cmems", "open-meteo"]
    if raw == "meteofrance_currents":
        return ["open-meteo"]
    if forced in {"oscar", "oscar_v2"}:
        return ["oscar", "open-meteo"]
    if forced in {"cmems", "cmems_glo_phy"}:
        return ["cmems", "open-meteo"]
    if forced in {"open-meteo", "om", "marine"}:
        return ["open-meteo"]
    return ["oscar", "cmems", "open-meteo"]


def wrap_lon_360(lon: np.ndarray) -> np.ndarray:
    """0–360 (or any) longitudes → [-180, 180)."""
    out = np.asarray(lon, dtype=float)
    return ((out + 180.0) % 360.0) - 180.0


def sort_lon_columns(
    lons: np.ndarray, u: np.ndarray, v: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    order = np.argsort(wrap_lon_360(lons))
    return wrap_lon_360(lons)[order], np.asarray(u)[:, order], np.asarray(v)[:, order]


def ensure_north_to_south(
    lats: np.ndarray, u: np.ndarray, v: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lats = np.asarray(lats, dtype=float)
    if lats.size >= 2 and lats[0] < lats[-1]:
        return lats[::-1].copy(), np.asarray(u)[::-1].copy(), np.asarray(v)[::-1].copy()
    return lats, np.asarray(u, dtype=float), np.asarray(v, dtype=float)


def resample_uv(
    src_u: np.ndarray,
    src_v: np.ndarray,
    src_lons: np.ndarray,
    src_lats: np.ndarray,
    bbox: dict[str, float],
    nx: int,
    ny: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Bilinear sample of a regular lat/lon u/v field onto nx×ny (rows north→south)."""
    lons, u, v = sort_lon_columns(src_lons, src_u, src_v)
    lats, u, v = ensure_north_to_south(np.asarray(src_lats, dtype=float), u, v)
    dest_lons = np.linspace(bbox["west"], bbox["east"], nx)
    dest_lats = np.linspace(bbox["north"], bbox["south"], ny)
    out_u = np.zeros((ny, nx), dtype=float)
    out_v = np.zeros((ny, nx), dtype=float)
    # lats are north→south after ensure
    lat_axis = lats
    for j, lat in enumerate(dest_lats):
        for i, lon in enumerate(dest_lons):
            uu, vv = _bilerp(u, v, lons, lat_axis, float(lon), float(lat))
            out_u[j, i] = uu
            out_v[j, i] = vv
    return out_u, out_v


def _axis_pos(values: np.ndarray, q: float) -> float:
    """Fractional index of q on a monotonic (either direction) 1-D axis."""
    if values.size < 2:
        return 0.0
    ascending = bool(values[0] < values[-1])
    xs = values if ascending else values[::-1]
    qq = float(q)
    if qq <= xs[0]:
        idx = 0.0
    elif qq >= xs[-1]:
        idx = float(xs.size - 1)
    else:
        k = int(np.searchsorted(xs, qq, side="right") - 1)
        k = min(max(k, 0), xs.size - 2)
        span = xs[k + 1] - xs[k]
        idx = k + (0.0 if span == 0 else (qq - xs[k]) / span)
    return idx if ascending else (values.size - 1) - idx


def _bilerp(
    u: np.ndarray,
    v: np.ndarray,
    lons: np.ndarray,
    lats: np.ndarray,
    lon: float,
    lat: float,
) -> tuple[float, float]:
    ny, nx = u.shape
    if nx < 2 or ny < 2:
        return 0.0, 0.0
    # longitude is cyclic on the wrapped -180..180 axis
    x = _axis_pos(lons, lon)
    y = _axis_pos(lats, lat)
    if not math.isfinite(x) or not math.isfinite(y):
        return 0.0, 0.0
    y = min(max(y, 0.0), ny - 1.0000001)
    x0 = int(math.floor(x)) % nx
    x1 = (x0 + 1) % nx
    y0 = min(max(int(math.floor(y)), 0), ny - 2)
    y1 = y0 + 1
    fx = x - math.floor(x)
    fy = y - y0
    def cell(arr: np.ndarray) -> float:
        return float(
            arr[y0, x0] * (1 - fx) * (1 - fy)
            + arr[y0, x1] * fx * (1 - fy)
            + arr[y1, x0] * (1 - fx) * fy
            + arr[y1, x1] * fx * fy
        )
    return cell(u), cell(v)


def pack_daily(u: np.ndarray, v: np.ndarray, lons: np.ndarray, lats: np.ndarray, meta: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        u=np.asarray(u, dtype=np.float32),
        v=np.asarray(v, dtype=np.float32),
        lons=np.asarray(lons, dtype=np.float32),
        lats=np.asarray(lats, dtype=np.float32),
        meta=np.array(json.dumps(meta, ensure_ascii=False)),
    )
    return buf.getvalue()


def unpack_daily(raw: bytes) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    data = np.load(io.BytesIO(raw), allow_pickle=False)
    meta_raw = data["meta"].item() if "meta" in data.files else "{}"
    if isinstance(meta_raw, bytes):
        meta_raw = meta_raw.decode("utf-8")
    try:
        meta = json.loads(str(meta_raw))
    except json.JSONDecodeError:
        meta = {}
    return (
        np.asarray(data["u"], dtype=float),
        np.asarray(data["v"], dtype=float),
        np.asarray(data["lons"], dtype=float),
        np.asarray(data["lats"], dtype=float),
        meta,
    )


def local_path(kind: str, stamp: str) -> Path:
    root = Path(settings.current_field_dir or "/tmp/aetherwatch-currents")
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{kind}-{stamp}.npz"


def object_key(kind: str, stamp: str) -> str:
    return f"currents/{kind}/{stamp}.npz"


def read_local(kind: str, stamp: str) -> bytes | None:
    path = local_path(kind, stamp)
    if path.is_file():
        try:
            return path.read_bytes()
        except OSError:
            return None
    return None


def write_local(kind: str, stamp: str, raw: bytes) -> None:
    path = local_path(kind, stamp)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    except OSError as exc:
        log.warning("local current cache write: %s", exc)


def read_object(kind: str, stamp: str) -> bytes | None:
    try:
        from app import storage

        return storage.try_get_bytes(object_key(kind, stamp))
    except Exception:
        return None


def write_object(kind: str, stamp: str, raw: bytes) -> None:
    try:
        from app import storage

        storage.put_bytes(object_key(kind, stamp), raw, "application/octet-stream")
    except Exception as exc:
        log.warning("object current cache write: %s", exc)


def load_daily(kind: str, stamp: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]] | None:
    raw = read_local(kind, stamp) or read_object(kind, stamp)
    if not raw:
        return None
    try:
        return unpack_daily(raw)
    except Exception as exc:
        log.warning("unpack %s %s: %s", kind, stamp, exc)
        return None


def save_daily(
    kind: str,
    stamp: str,
    u: np.ndarray,
    v: np.ndarray,
    lons: np.ndarray,
    lats: np.ndarray,
    meta: dict[str, Any],
) -> None:
    raw = pack_daily(u, v, lons, lats, meta)
    write_local(kind, stamp, raw)
    write_object(kind, stamp, raw)


def source_grid_size(source: str, nx: int | None, ny: int | None) -> tuple[int, int]:
    """OSCAR/CMEMS may be a bit denser (one daily file). OM stays at CURRENT_NX/NY."""
    if source in {"oscar", "cmems"}:
        return (
            int(nx or settings.current_source_nx or 36),
            int(ny or settings.current_source_ny or 18),
        )
    return (int(nx or settings.current_nx), int(ny or settings.current_ny))


def cache_key(model: str, nx: int, ny: int) -> str:
    return f"currents:{CACHE_VER}:{model}:{nx}x{ny}:nest"


def field_to_payload(
    u: np.ndarray,
    v: np.ndarray,
    bbox: dict[str, float],
    source: str,
    *,
    kind: str = "currents",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.openmeteo import _vector_payload

    filled = int(np.count_nonzero(np.abs(u) + np.abs(v) > 1e-6))
    out = apply_ocean_mask(_vector_payload(u.shape[1], u.shape[0], bbox, u, v, source, filled, kind=kind))
    if extra:
        out.update(extra)
    return out


def payload_from_daily(
    u: np.ndarray,
    v: np.ndarray,
    lons: np.ndarray,
    lats: np.ndarray,
    source: str,
    nx: int,
    ny: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gu, gv = resample_uv(u, v, lons, lats, GLOBAL_BBOX, nx, ny)
    out = field_to_payload(gu, gv, GLOBAL_BBOX, source, extra=extra)
    try:
        nu, nv = resample_uv(
            u,
            v,
            lons,
            lats,
            CHINA_SEAS_BBOX,
            settings.current_nest_nx,
            settings.current_nest_ny,
        )
        nest = field_to_payload(nu, nv, CHINA_SEAS_BBOX, f"{source}:china-seas")
        if int(nest.get("filled") or 0) >= 6:
            out["nest"] = nest
    except Exception as exc:
        log.warning("china-seas nest: %s", exc)
    return out


def _decode_nc_uv(raw: bytes) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    import xarray as xr

    ds = xr.open_dataset(io.BytesIO(raw), decode_times=True, mask_and_scale=True)
    try:
        u_name = next((n for n in ("u", "uo", "ucur", "eastward_sea_water_velocity") if n in ds.data_vars), None)
        v_name = next((n for n in ("v", "vo", "vcur", "northward_sea_water_velocity") if n in ds.data_vars), None)
        if not u_name or not v_name:
            raise RuntimeError(f"no u/v in netcdf vars={list(ds.data_vars)}")
        u = ds[u_name]
        v = ds[v_name]
        for dim in list(u.dims):
            if dim in {"time", "depth", "elevation", "lev", "z"} and u.sizes.get(dim, 1) > 0:
                u = u.isel({dim: 0})
                v = v.isel({dim: 0})
        lat_name = next((n for n in ("lat", "latitude") if n in ds.coords or n in ds.variables), None)
        lon_name = next((n for n in ("lon", "longitude") if n in ds.coords or n in ds.variables), None)
        if not lat_name or not lon_name:
            raise RuntimeError("no lat/lon in netcdf")
        lats = np.asarray(ds[lat_name].values, dtype=float).reshape(-1)
        lons = np.asarray(ds[lon_name].values, dtype=float).reshape(-1)
        uu = np.asarray(u.values, dtype=float)
        vv = np.asarray(v.values, dtype=float)
        while uu.ndim > 2:
            uu = uu[0]
            vv = vv[0]
        uu = np.where(np.isfinite(uu) & (np.abs(uu) < 5), uu, 0.0)
        vv = np.where(np.isfinite(vv) & (np.abs(vv) < 5), vv, 0.0)
        meta = {"u": u_name, "v": v_name, "lat": lat_name, "lon": lon_name}
        return uu, vv, lons, lats, meta
    finally:
        ds.close()


async def _earthdata_bearer() -> str | None:
    global _earthdata_token
    if earthdata_token():
        return earthdata_token()
    if _earthdata_token:
        return _earthdata_token
    user, password = earthdata_user(), earthdata_password()
    if not (user and password):
        return None
    client = await http()
    try:
        r = await client.post(URS_TOKEN, auth=(user, password))
        if r.status_code == 200:
            token = (r.json() or {}).get("access_token") or (r.json() or {}).get("token")
            if token:
                _earthdata_token = str(token)
                return _earthdata_token
        listed = await client.get(URS_TOKENS, auth=(user, password))
        if listed.status_code == 200:
            rows = listed.json()
            if isinstance(rows, list) and rows:
                token = rows[0].get("access_token") or rows[0].get("token")
                if token:
                    _earthdata_token = str(token)
                    return _earthdata_token
    except Exception as exc:
        log.warning("earthdata token: %s", exc)
    return None


async def _cmr_latest_oscar() -> dict[str, str] | None:
    client = await http()
    params = {
        "short_name": settings.oscar_short_name or "OSCAR_L4_OC_NRT_V2.0",
        "sort_key": "-start_date",
        "page_size": "1",
    }
    r = await client.get(CMR_GRANULES, params=params)
    r.raise_for_status()
    entries = ((r.json() or {}).get("feed") or {}).get("entry") or []
    if not entries:
        return None
    entry = entries[0]
    href = ""
    opendap = ""
    for link in entry.get("links") or []:
        rel = str(link.get("rel") or "")
        url = str(link.get("href") or "")
        if url.endswith(".nc") and "protected" in url:
            href = url
        if "opendap.earthdata.nasa.gov/collections" in url and "granules" in url:
            opendap = url.rstrip("/")
    title = str(entry.get("title") or "oscar")
    start = str(entry.get("time_start") or "")[:10].replace("-", "")
    stamp = start or title.replace("oscar_currents_nrt_", "").replace(".nc", "")
    return {"href": href, "opendap": opendap, "title": title, "stamp": stamp, "time": str(entry.get("time_start") or "")}


async def fetch_oscar_daily() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]] | None:
    if not has_oscar_creds():
        log.info("oscar skipped (set EARTHDATA_TOKEN or EARTHDATA_USERNAME/PASSWORD)")
        return None
    try:
        granule = await _cmr_latest_oscar()
    except Exception as exc:
        log.warning("oscar cmr: %s", exc)
        return None
    if not granule:
        return None
    stamp = granule["stamp"] or datetime.now(timezone.utc).strftime("%Y%m%d")
    cached = load_daily("oscar-v2", stamp)
    if cached:
        u, v, lons, lats, meta = cached
        meta = {**meta, "stamp": stamp, "cached": True, "source": "oscar-v2"}
        return u, v, lons, lats, meta
    token = await _earthdata_bearer()
    client = await http()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    auth = (earthdata_user(), earthdata_password()) if (earthdata_user() and earthdata_password()) else None
    raw: bytes | None = None
    # Prefer a strided OPeNDAP slice so we do not pull the full 0.25° cube every day.
    if granule.get("opendap"):
        ce = f"{granule['opendap']}.nc?u[0][0:4:719][0:4:1439],v[0][0:4:719][0:4:1439]"
        try:
            r = await client.get(ce, headers=headers, auth=auth)
            if r.status_code == 200 and len(r.content) > 800:
                raw = r.content
        except Exception as exc:
            log.warning("oscar opendap: %s", exc)
    if raw is None and granule.get("href"):
        try:
            r = await client.get(granule["href"], headers=headers, auth=auth)
            if r.status_code == 200 and len(r.content) > 800:
                raw = r.content
        except Exception as exc:
            log.warning("oscar download: %s", exc)
    if raw is None:
        return None
    try:
        u, v, lons, lats, meta = await asyncio.to_thread(_decode_nc_uv, raw)
    except Exception as exc:
        log.warning("oscar decode: %s", exc)
        return None
    meta.update({"stamp": stamp, "title": granule.get("title"), "time": granule.get("time"), "source": "oscar-v2"})
    save_daily("oscar-v2", stamp, u, v, lons, lats, meta)
    return u, v, lons, lats, meta


async def _cmems_oidc_token() -> str | None:
    if cmems_token():
        return cmems_token()
    user, password = cmems_user(), cmems_password()
    if not (user and password):
        return None
    client = await http()
    for url in CMEMS_TOKEN_URLS:
        for client_id in CMEMS_CLIENT_IDS:
            try:
                r = await client.post(
                    url,
                    data={
                        "client_id": client_id,
                        "grant_type": "password",
                        "username": user,
                        "password": password,
                    },
                )
                if r.status_code == 200:
                    token = (r.json() or {}).get("access_token")
                    if token:
                        return str(token)
            except Exception as exc:
                log.info("cmems token %s: %s", url, exc)
    return None


def _cmems_via_toolbox(stamp_hint: str | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]] | None:
    """Optional official toolbox path (installed on Mac if desired)."""
    try:
        import copernicusmarine  # type: ignore
    except ImportError:
        return None
    day = stamp_hint or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    kwargs: dict[str, Any] = {
        "dataset_id": settings.cmems_dataset_id,
        "variables": ["uo", "vo"],
        "minimum_depth": 0,
        "maximum_depth": 1.5,
        "start_datetime": f"{day}T00:00:00",
        "end_datetime": f"{day}T23:59:59",
        "disable_progress_bar": True,
    }
    if cmems_user() and cmems_password():
        kwargs["username"] = cmems_user()
        kwargs["password"] = cmems_password()
    ds = copernicusmarine.open_dataset(**kwargs)
    try:
        u = ds["uo"]
        v = ds["vo"]
        for dim in list(u.dims):
            if dim in {"time", "depth", "elevation", "lev"}:
                u = u.isel({dim: 0})
                v = v.isel({dim: 0})
        lat_name = "latitude" if "latitude" in ds.coords else "lat"
        lon_name = "longitude" if "longitude" in ds.coords else "lon"
        # Coarsen the 0.083° native grid so the daily cache stays small.
        step = 4
        uu = np.asarray(u.values, dtype=float)[::step, ::step]
        vv = np.asarray(v.values, dtype=float)[::step, ::step]
        lats = np.asarray(ds[lat_name].values, dtype=float).reshape(-1)[::step]
        lons = np.asarray(ds[lon_name].values, dtype=float).reshape(-1)[::step]
        uu = np.where(np.isfinite(uu) & (np.abs(uu) < 5), uu, 0.0)
        vv = np.where(np.isfinite(vv) & (np.abs(vv) < 5), vv, 0.0)
        return uu, vv, lons, lats, {"source": "cmems", "day": day, "dataset": settings.cmems_dataset_id}
    finally:
        try:
            ds.close()
        except Exception:
            pass


async def fetch_cmems_daily() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]] | None:
    if not has_cmems_creds():
        log.info("cmems skipped (set CMEMS_USERNAME/PASSWORD or CMEMS_TOKEN)")
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    cached = load_daily("cmems-phy", stamp)
    if cached:
        u, v, lons, lats, meta = cached
        meta = {**meta, "stamp": stamp, "cached": True, "source": "cmems"}
        return u, v, lons, lats, meta
    # Toolbox first (handles ARCO + auth). OIDC token is reserved for a later zarr path.
    try:
        got = await asyncio.to_thread(_cmems_via_toolbox, datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    except Exception as exc:
        log.warning("cmems toolbox: %s", exc)
        got = None
    if got is None:
        token = await _cmems_oidc_token()
        if not token:
            log.warning("cmems: no toolbox and no OIDC token")
            return None
        log.warning("cmems: OIDC token ok but ARCO zarr still needs the toolbox or S3 keys")
        return None
    u, v, lons, lats, meta = got
    meta.update({"stamp": stamp})
    save_daily("cmems-phy", stamp, u, v, lons, lats, meta)
    return u, v, lons, lats, meta


async def fetch_current_grid(model: str = "best_match", nx: int | None = None, ny: int | None = None) -> dict[str, Any]:
    from app import openmeteo

    marine = model if model in {"best_match", "meteofrance_currents"} else "best_match"
    sources = preferred_sources(model)
    # Live key is per requested model. v4 is a new prefix — no Redis flush needed.
    om_nx = int(nx or settings.current_nx)
    om_ny = int(ny or settings.current_ny)
    key = cache_key(model if model in CURRENT_BY_ID else "best_match", om_nx, om_ny)
    # Prefer a source-specific live key when auto resolves to oscar/cmems.
    hit = await openmeteo.cache_get_prefer(key)
    if hit:
        hit["cached"] = True
        return hit

    async with source_gate():
        again = await openmeteo.cache_get_prefer(key)
        if again:
            again["cached"] = True
            return again
        last_error = ""
        for source in sources:
            try:
                if source == "oscar":
                    daily = await fetch_oscar_daily()
                    if not daily:
                        continue
                    u, v, lons, lats, meta = daily
                    sx, sy = source_grid_size("oscar", nx, ny)
                    out = payload_from_daily(
                        u,
                        v,
                        lons,
                        lats,
                        f"oscar-v2:{settings.oscar_short_name}",
                        sx,
                        sy,
                        extra={
                            "provider": "oscar-v2",
                            "valid_time": meta.get("time"),
                            "init_time": meta.get("time"),
                            "kind": "oscar_analysis",
                            "doi": "10.5067/OSCAR-25N20",
                        },
                    )
                    ttl = max(settings.current_cache_ttl_seconds, settings.current_source_cache_ttl_seconds)
                    await openmeteo.cache_remember(key, out, ttl)
                    return out
                if source == "cmems":
                    daily = await fetch_cmems_daily()
                    if not daily:
                        continue
                    u, v, lons, lats, meta = daily
                    sx, sy = source_grid_size("cmems", nx, ny)
                    out = payload_from_daily(
                        u,
                        v,
                        lons,
                        lats,
                        f"cmems:{settings.cmems_dataset_id}",
                        sx,
                        sy,
                        extra={
                            "provider": "cmems",
                            "valid_time": meta.get("day"),
                            "init_time": meta.get("day"),
                            "kind": "cmems_analysis_forecast",
                            "doi": "10.48670/moi-00016",
                            "product": settings.cmems_product_id,
                        },
                    )
                    ttl = max(settings.current_cache_ttl_seconds, settings.current_source_cache_ttl_seconds)
                    await openmeteo.cache_remember(key, out, ttl)
                    return out
                if source == "open-meteo":
                    return await openmeteo.fetch_om_current_grid(marine, nx=om_nx, ny=om_ny)
            except Exception as exc:
                last_error = str(exc)
                log.warning("current source %s: %s", source, exc)
        stale = await openmeteo.cache_get_prefer(key)
        if stale:
            stale["cached"] = True
            stale.setdefault("degraded", last_error or "upstream")
            return stale
        return openmeteo.synthetic_currents(om_nx, om_ny, GLOBAL_BBOX, reason=last_error or "no-current-source")
