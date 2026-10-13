"""Live Open-Meteo client. No API key for non-commercial use."""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any

import httpx
import numpy as np
import redis.asyncio as redis

from app.catalog import CHINA_BBOX, CURRENT_BY_ID, ELEMENT_BY_ID, PREVIEW_BY_ID
from app.config import settings
from app.landmask import apply_ocean_mask, is_land

USER_AGENT = "AetherWatch/0.1 (local observation; docker compose)"

_http: httpx.AsyncClient | None = None
_redis: redis.Redis | None = None


async def http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            timeout=httpx.Timeout(40.0, connect=10.0),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )
    return _http


async def cache() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def cache_get(key: str) -> Any | None:
    try:
        raw = await (await cache()).get(key)
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    try:
        await (await cache()).set(key, json.dumps(value), ex=ttl)
    except Exception:
        return


async def incr_visitors() -> int:
    try:
        n = await (await cache()).incr("aetherwatch:visitors")
        return int(n)
    except Exception:
        return 0


def _hourly_key(variable: str, model: str, payload: dict[str, Any]) -> str:
    hourly = payload.get("hourly") or {}
    suffixed = f"{variable}_{model}"
    if suffixed in hourly:
        return suffixed
    if variable in hourly:
        return variable
    return variable


async def fetch_series(
    lat: float,
    lon: float,
    variable: str,
    models: list[str],
    forecast_days: int = 5,
) -> dict[str, Any]:
    element = ELEMENT_BY_ID.get(variable, ELEMENT_BY_ID["temperature_2m"])
    om_var = element["om"]
    cache_key = f"series:{lat:.3f}:{lon:.3f}:{om_var}:{','.join(models)}:{forecast_days}"
    hit = await cache_get(cache_key)
    if hit:
        hit["cached"] = True
        return hit

    client = await http()
    model_payloads: dict[str, dict[str, Any]] = {}

    async def one(model: str) -> tuple[str, dict[str, Any] | None, str | None]:
        params = {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "hourly": om_var,
            "models": model,
            "forecast_days": str(forecast_days),
            "timezone": "auto",
            "wind_speed_unit": "ms",
        }
        # pressure_msl is more widely available than surface_pressure on some models
        if om_var == "surface_pressure":
            params["hourly"] = "surface_pressure,pressure_msl"
        url = f"{settings.open_meteo_base.rstrip('/')}/v1/forecast"
        try:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return model, r.json(), None
        except Exception as exc:
            return model, None, str(exc)

    results = await asyncio.gather(*[one(m) for m in models])
    times: list[str] | None = None
    errors: dict[str, str] = {}
    for model, payload, err in results:
        if err or payload is None:
            errors[model] = err or "empty"
            continue
        hourly = payload.get("hourly") or {}
        t = hourly.get("time") or []
        if times is None:
            times = t
        key = _hourly_key(om_var, model, payload)
        values = hourly.get(key)
        if values is None and om_var == "surface_pressure":
            values = hourly.get("pressure_msl") or hourly.get(f"pressure_msl_{model}")
        if values is None:
            errors[model] = f"variable {om_var} missing"
            continue
        meta = PREVIEW_BY_ID.get(model, {"short": model, "color": "#6b6258"})
        model_payloads[model] = {
            "id": model,
            "name": meta.get("short", model),
            "full_name": meta.get("name", model),
            "color": meta.get("color", "#6b6258"),
            "values": values,
            "timezone": payload.get("timezone"),
            "utc_offset_seconds": payload.get("utc_offset_seconds"),
        }

    out = {
        "lat": lat,
        "lon": lon,
        "variable": variable,
        "unit": element["unit"],
        "label": element["label"],
        "label_en": element["label_en"],
        "times": times or [],
        "models": model_payloads,
        "errors": errors,
        "source": "open-meteo",
        "cached": False,
    }
    if model_payloads:
        await cache_set(cache_key, out, settings.cache_ttl_seconds)
    return out


async def _gather_batches(
    points: list[tuple[float, float]],
    fetch_chunk,
    batch_size: int | None = None,
) -> list[dict[str, Any] | None]:
    """Fetch Open-Meteo multi-location chunks with a concurrency cap (rate-limit friendly)."""
    size = max(4, batch_size or settings.open_meteo_batch_size)
    conc = max(1, settings.open_meteo_concurrency)
    chunks = [points[i : i + size] for i in range(0, len(points), size)]
    sem = asyncio.Semaphore(conc)

    async def one(chunk: list[tuple[float, float]]) -> list[dict[str, Any] | None]:
        async with sem:
            try:
                return await fetch_chunk(chunk)
            except Exception:
                return [None] * len(chunk)

    groups = await asyncio.gather(*[one(c) for c in chunks])
    out: list[dict[str, Any] | None] = []
    for g in groups:
        out.extend(g)
    return out


def _grid_points(bbox: dict[str, float], nx: int, ny: int) -> tuple[list[float], list[float]]:
    lons = np.linspace(bbox["west"], bbox["east"], nx).tolist()
    lats = np.linspace(bbox["south"], bbox["north"], ny).tolist()
    return lats, lons


async def fetch_field(
    model: str,
    variable: str,
    bbox: dict[str, float] | None = None,
    nx: int | None = None,
    ny: int | None = None,
    step: int = 0,
) -> dict[str, Any]:
    bbox = bbox or CHINA_BBOX
    nx = int(nx or settings.field_nx)
    ny = int(ny or settings.field_ny)
    element = ELEMENT_BY_ID.get(variable, ELEMENT_BY_ID["temperature_2m"])
    om_var = element["om"]
    cache_key = (
        f"field:{model}:{om_var}:{bbox['west']}:{bbox['south']}:{bbox['east']}:{bbox['north']}"
        f":{nx}x{ny}:{step}"
    )
    hit = await cache_get(cache_key)
    if hit:
        hit["cached"] = True
        return hit

    lats, lons = _grid_points(bbox, nx, ny)
    points: list[tuple[float, float]] = [(lat, lon) for lat in lats for lon in lons]

    client = await http()
    values = np.full((ny, nx), np.nan, dtype=float)
    valid_time: str | None = None

    async def batch(chunk: list[tuple[float, float]]) -> list[dict[str, Any] | None]:
        lat_s = ",".join(f"{p[0]:.3f}" for p in chunk)
        lon_s = ",".join(f"{p[1]:.3f}" for p in chunk)
        params = {
            "latitude": lat_s,
            "longitude": lon_s,
            "hourly": om_var if om_var != "surface_pressure" else "surface_pressure,pressure_msl",
            "models": model,
            "forecast_days": "2",
            "timezone": "UTC",
            "wind_speed_unit": "ms",
        }
        url = f"{settings.open_meteo_base.rstrip('/')}/v1/forecast"
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        # multi-location returns a list; single returns an object
        if isinstance(data, list):
            return data
        return [data]

    payloads = await _gather_batches(points, batch)

    for idx, payload in enumerate(payloads):
        if not payload:
            continue
        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        key = _hourly_key(om_var, model, payload)
        series = hourly.get(key)
        if series is None and om_var == "surface_pressure":
            series = hourly.get("pressure_msl") or hourly.get(f"pressure_msl_{model}")
        if not series:
            continue
        si = min(max(step, 0), len(series) - 1)
        val = series[si]
        if times and valid_time is None:
            valid_time = times[si]
        row = idx // nx
        col = idx % nx
        if val is not None:
            values[row, col] = float(val)

    finite = values[np.isfinite(values)]
    vmin = float(np.min(finite)) if finite.size else 0.0
    vmax = float(np.max(finite)) if finite.size else 1.0
    out = {
        "model": model,
        "variable": variable,
        "unit": element["unit"],
        "label": element["label"],
        "label_en": element["label_en"],
        "valid_time": valid_time,
        "step": step,
        "bbox": bbox,
        "lats": lats,
        "lons": lons,
        "values": [[None if not math.isfinite(v) else round(float(v), 3) for v in row] for row in values],
        "min": round(vmin, 3),
        "max": round(vmax, 3),
        "source": f"open-meteo:{model}",
        "cached": False,
        "nx": nx,
        "ny": ny,
    }
    if finite.size:
        await cache_set(cache_key, out, settings.cache_ttl_seconds)
    return out


async def fetch_wind_grid(model: str = "gfs_seamless", nx: int = 24, ny: int = 12) -> dict[str, Any]:
    bbox = {"west": -180.0, "south": -70.0, "east": 180.0, "north": 70.0}
    cache_key = f"wind:{model}:{nx}x{ny}"
    hit = await cache_get(cache_key)
    if hit:
        hit["cached"] = True
        return hit

    lats, lons = _grid_points(bbox, nx, ny)
    points = [(lat, lon) for lat in reversed(lats) for lon in lons]  # north → south
    client = await http()
    u = np.zeros((ny, nx), dtype=float)
    v = np.zeros((ny, nx), dtype=float)

    async def batch(chunk: list[tuple[float, float]]) -> list[dict[str, Any] | None]:
        lat_s = ",".join(f"{p[0]:.2f}" for p in chunk)
        lon_s = ",".join(f"{p[1]:.2f}" for p in chunk)
        params = {
            "latitude": lat_s,
            "longitude": lon_s,
            "hourly": "wind_speed_10m,wind_direction_10m",
            "models": model,
            "forecast_days": "1",
            "timezone": "UTC",
            "wind_speed_unit": "ms",
        }
        url = f"{settings.open_meteo_base.rstrip('/')}/v1/forecast"
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else [data]

    payloads = await _gather_batches(points, batch)

    filled = 0
    for idx, payload in enumerate(payloads):
        if not payload:
            continue
        hourly = payload.get("hourly") or {}
        spd_key = _hourly_key("wind_speed_10m", model, payload)
        dir_key = _hourly_key("wind_direction_10m", model, payload)
        spd = (hourly.get(spd_key) or [None])[0]
        wdir = (hourly.get(dir_key) or [None])[0]
        if spd is None or wdir is None:
            continue
        rad = math.radians(float(wdir))
        # meteorological direction: FROM which the wind blows
        uu = -float(spd) * math.sin(rad)
        vv = -float(spd) * math.cos(rad)
        row = idx // nx
        col = idx % nx
        u[row, col] = uu
        v[row, col] = vv
        filled += 1

    if filled < 8:
        # last-resort synthetic field so the globe still animates offline
        return synthetic_wind(nx, ny, bbox, reason="open-meteo-sparse")

    out = _vector_payload(nx, ny, bbox, u, v, f"open-meteo:{model}", filled, kind="wind")
    await cache_set(cache_key, out, settings.wind_cache_ttl_seconds)
    return out


def _vector_payload(
    nx: int,
    ny: int,
    bbox: dict[str, float],
    u: np.ndarray,
    v: np.ndarray,
    source: str,
    filled: int,
    kind: str,
    cached: bool = False,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "width": nx,
        "height": ny,
        "west": bbox["west"],
        "south": bbox["south"],
        "east": bbox["east"],
        "north": bbox["north"],
        "uMin": round(float(np.min(u)), 3),
        "uMax": round(float(np.max(u)), 3),
        "vMin": round(float(np.min(v)), 3),
        "vMax": round(float(np.max(v)), 3),
        "u": [round(float(x), 3) for x in np.asarray(u).reshape(-1).tolist()],
        "v": [round(float(x), 3) for x in np.asarray(v).reshape(-1).tolist()],
        "source": source,
        "cached": cached,
        "filled": filled,
        "fallback": source.startswith("synthetic"),
    }


def _speed_unit_scale(unit: str | None) -> float:
    if not unit:
        return 1.0
    u = unit.lower()
    if "km" in u:
        return 1.0 / 3.6
    if "kn" in u:
        return 0.514444
    if "mph" in u or "mi" in u:
        return 0.44704
    return 1.0


async def fetch_current_grid(model: str = "best_match", nx: int | None = None, ny: int | None = None) -> dict[str, Any]:
    """Surface ocean currents from Open-Meteo Marine (no API key)."""
    bbox = {"west": -180.0, "south": -70.0, "east": 180.0, "north": 70.0}
    nx = int(nx or settings.current_nx)
    ny = int(ny or settings.current_ny)
    marine_model = model if model in CURRENT_BY_ID else "best_match"
    cache_key = f"currents:{marine_model}:{nx}x{ny}:oceanmask"
    hit = await cache_get(cache_key)
    if hit:
        hit["cached"] = True
        return hit

    lats, lons = _grid_points(bbox, nx, ny)
    points = [(lat, lon) for lat in reversed(lats) for lon in lons]
    client = await http()
    u = np.zeros((ny, nx), dtype=float)
    v = np.zeros((ny, nx), dtype=float)
    marine = settings.open_meteo_marine_base.rstrip("/")
    ocean_idx = [(i, lat, lon) for i, (lat, lon) in enumerate(points) if not is_land(lon, lat)]
    ocean_pts = [(lat, lon) for _, lat, lon in ocean_idx]

    async def batch(chunk: list[tuple[float, float]]) -> list[dict[str, Any] | None]:
        lat_s = ",".join(f"{p[0]:.2f}" for p in chunk)
        lon_s = ",".join(f"{p[1]:.2f}" for p in chunk)
        params = {
            "latitude": lat_s,
            "longitude": lon_s,
            "hourly": "ocean_current_velocity,ocean_current_direction",
            "models": marine_model,
            "forecast_days": "1",
            "timezone": "UTC",
            "wind_speed_unit": "ms",
            "cell_selection": "sea",
        }
        url = f"{marine}/v1/marine"
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else [data]

    payloads = await _gather_batches(ocean_pts, batch)

    filled = 0
    for (idx, req_lat, req_lon), payload in zip(ocean_idx, payloads, strict=False):
        if not payload:
            continue
        # cell_selection=sea snaps land queries onto nearby ocean; drop those.
        act_lat = payload.get("latitude")
        act_lon = payload.get("longitude")
        if act_lat is not None and act_lon is not None:
            dlat = float(act_lat) - req_lat
            dlon = ((float(act_lon) - req_lon + 180.0) % 360.0) - 180.0
            dist = math.hypot(dlat, dlon * math.cos(math.radians(req_lat)))
            if dist > 1.15:
                continue
        hourly = payload.get("hourly") or {}
        units = payload.get("hourly_units") or {}
        spd_key = _hourly_key("ocean_current_velocity", marine_model, payload)
        dir_key = _hourly_key("ocean_current_direction", marine_model, payload)
        spd = (hourly.get(spd_key) or [None])[0]
        cdir = (hourly.get(dir_key) or [None])[0]
        if spd is None or cdir is None:
            continue
        scale = _speed_unit_scale(str(units.get(spd_key) or "m/s"))
        speed = float(spd) * scale
        rad = math.radians(float(cdir))
        # oceanographic direction: TOWARDS which the current flows
        uu = speed * math.sin(rad)
        vv = speed * math.cos(rad)
        row = idx // nx
        col = idx % nx
        u[row, col] = uu
        v[row, col] = vv
        filled += 1

    if filled < 8:
        return synthetic_currents(nx, ny, bbox, reason="open-meteo-marine-sparse")

    out = apply_ocean_mask(
        _vector_payload(
            nx, ny, bbox, u, v, f"open-meteo-marine:{marine_model}", filled, kind="currents"
        )
    )
    await cache_set(cache_key, out, settings.current_cache_ttl_seconds)
    return out


def synthetic_currents(nx: int, ny: int, bbox: dict[str, float], reason: str = "fallback") -> dict[str, Any]:
    """Gyres + ACC + Kuroshio/Gulf Stream so the globe still moves offline."""
    lons = np.linspace(bbox["west"], bbox["east"], nx)
    lats = np.linspace(bbox["north"], bbox["south"], ny)
    lon, lat = np.meshgrid(lons, lats)
    u = np.zeros_like(lon)
    v = np.zeros_like(lat)
    # Antarctic Circumpolar Current
    acc = np.exp(-((lat + 54.0) ** 2) / 70.0)
    u += 0.85 * acc
    # Equatorial current
    eq = np.exp(-(lat**2) / 28.0)
    u += -0.35 * eq
    # Kuroshio
    kdx = (lon - 138.0) * np.cos(np.radians(lat))
    kdy = lat - 32.0
    kr = np.sqrt(kdx * kdx + kdy * kdy) + 0.4
    kmask = np.exp(-kr / 12.0)
    u += 0.55 * kmask
    v += 0.22 * kmask * np.cos(np.radians(lat - 28))
    # Gulf Stream
    gdx = (lon + 65.0) * np.cos(np.radians(lat))
    gdy = lat - 36.0
    gr = np.sqrt(gdx * gdx + gdy * gdy) + 0.4
    gmask = np.exp(-gr / 11.0)
    u += 0.6 * gmask
    v += 0.18 * gmask
    # subtropical gyre swirl (N Pacific)
    dx = (lon - 180.0) * np.cos(np.radians(lat))
    dy = lat - 28.0
    r = np.sqrt(dx * dx + dy * dy) + 0.5
    swirl = np.exp(-r / 28.0)
    u += -0.28 * dy / r * swirl
    v += 0.28 * dx / r * swirl
    return apply_ocean_mask(
        _vector_payload(nx, ny, bbox, u, v, f"synthetic:{reason}", nx * ny, kind="currents")
    )


def synthetic_wind(nx: int, ny: int, bbox: dict[str, float], reason: str = "fallback") -> dict[str, Any]:
    """Procedural mid-latitude westerlies + two gyres. Used only if live fetch fails."""
    lons = np.linspace(bbox["west"], bbox["east"], nx)
    lats = np.linspace(bbox["north"], bbox["south"], ny)
    lon, lat = np.meshgrid(lons, lats)
    u = 8.0 * np.cos(np.radians(lat)) + 4.0 * np.sin(np.radians(lon / 2))
    v = 3.0 * np.sin(np.radians(lon)) * np.cos(np.radians(lat * 1.2))
    # a cyclone-like swirl in the NW Pacific
    cy, cx = 22.0, 132.0
    dx = (lon - cx) * np.cos(np.radians(lat))
    dy = lat - cy
    r = np.sqrt(dx * dx + dy * dy) + 0.6
    u += -12.0 * dy / r * np.exp(-r / 18)
    v += 12.0 * dx / r * np.exp(-r / 18)
    return _vector_payload(nx, ny, bbox, u, v, f"synthetic:{reason}", nx * ny, kind="wind")


async def close() -> None:
    global _http, _redis
    if _http is not None:
        await _http.aclose()
        _http = None
    if _redis is not None:
        await _redis.aclose()
        _redis = None
