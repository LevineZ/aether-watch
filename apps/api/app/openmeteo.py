"""Live Open-Meteo client. No API key for non-commercial use.

Never hammer the free API: concurrency defaults to 1, batches stay small,
requests are paced, and 429s use exponential backoff + Retry-After.
Redis cache (and a longer-lived last-good copy) is preferred over a refetch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
from typing import Any

import httpx
import numpy as np
import redis.asyncio as redis

from app.catalog import CHINA_BBOX, CHINA_SEAS_BBOX, CURRENT_BY_ID, ELEMENT_BY_ID, PREVIEW_BY_ID
from app.config import settings
from app.fieldmeta import field_clock
from app.landmask import apply_ocean_mask, is_land

USER_AGENT = "AetherWatch/0.1 (local observation; docker compose)"
log = logging.getLogger("aetherwatch.openmeteo")

_http: httpx.AsyncClient | None = None
_redis: redis.Redis | None = None
_om_gate: asyncio.Semaphore | None = None
_pace_lock: asyncio.Lock | None = None
_next_ok: float = 0.0


def om_gate() -> asyncio.Semaphore:
    global _om_gate
    if _om_gate is None:
        _om_gate = asyncio.Semaphore(max(1, settings.open_meteo_concurrency))
    return _om_gate


def retry_wait_seconds(
    attempt: int,
    retry_after: str | None = None,
    *,
    base: float | None = None,
    cap: float | None = None,
    jitter: bool = True,
) -> float:
    """Exponential backoff for 429 / transient Open-Meteo errors.

    attempt is 1-based. Retry-After (seconds) wins when parseable.
    """
    cap_s = float(cap if cap is not None else settings.open_meteo_backoff_cap_seconds)
    if retry_after:
        try:
            return min(cap_s, max(1.0, float(retry_after.strip())))
        except ValueError:
            pass
    base_s = float(base if base is not None else settings.open_meteo_backoff_base)
    raw = min(cap_s, base_s ** max(1, attempt))
    if not jitter:
        return raw
    return raw * (1.0 + random.uniform(0.05, 0.2))


def _pace_lock_get() -> asyncio.Lock:
    global _pace_lock
    if _pace_lock is None:
        _pace_lock = asyncio.Lock()
    return _pace_lock


async def pace_open_meteo() -> None:
    """Serialize outbound Open-Meteo calls with a minimum gap."""
    global _next_ok
    gap = max(0.2, float(settings.open_meteo_min_interval_seconds))
    async with _pace_lock_get():
        now = time.monotonic()
        wait = _next_ok - now
        if wait > 0:
            await asyncio.sleep(wait)
        _next_ok = time.monotonic() + gap


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
        _redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=2.0,
        )
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


async def cache_remember(key: str, value: Any, ttl: int) -> None:
    """Write the live key plus a longer-lived last-good copy."""
    await cache_set(key, value, ttl)
    last_ttl = max(ttl, settings.open_meteo_stale_ttl_seconds, settings.last_good_ttl_seconds)
    await cache_set(f"{key}:last", value, last_ttl)


async def cache_set_live_and_last(key: str, value: Any, ttl: int) -> None:
    await cache_remember(key, value, ttl)


async def cache_get_prefer(key: str) -> Any | None:
    hit = await cache_get(key)
    if hit:
        return hit
    last = await cache_get(f"{key}:last")
    if last:
        last["cached"] = True
        last["stale"] = True
        last.setdefault("degraded", "open-meteo-stale")
    return last


LIVE_PREFIXES = ("field:", "currents:", "wind:", "series:", "catalog:")


async def flush_live_cache() -> int:
    """Drop live keys only. Keep *:last so 429s can still serve last-good."""
    try:
        r = await cache()
    except Exception:
        return 0
    n = 0
    try:
        async for key in r.scan_iter(match="*"):
            if not isinstance(key, str):
                continue
            if key.endswith(":last") or key in {"aetherwatch:visitors"}:
                continue
            if key.startswith(LIVE_PREFIXES):
                await r.delete(key)
                n += 1
    except Exception as exc:
        log.warning("flush live cache: %s", exc)
    return n


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
    hit = await cache_get_prefer(cache_key)
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
            data = await _om_json(client, url, params)
            return model, data, None
        except Exception as exc:
            return model, None, str(exc)

    results: list[tuple[str, dict[str, Any] | None, str | None]] = []
    for model in models:
        results.append(await one(model))
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
        await cache_remember(cache_key, out, settings.cache_ttl_seconds)
    else:
        stale = await cache_get_prefer(cache_key)
        if stale:
            stale["cached"] = True
            return stale
    return out


async def _gather_batches(
    points: list[tuple[float, float]],
    fetch_chunk,
    batch_size: int | None = None,
) -> list[dict[str, Any] | None]:
    """Fetch Open-Meteo multi-location chunks one-at-a-time (never hammer)."""
    size = max(4, min(80, batch_size or settings.open_meteo_batch_size))
    chunks = [points[i : i + size] for i in range(0, len(points), size)]
    gate = om_gate()
    out: list[dict[str, Any] | None] = []
    for chunk in chunks:
        async with gate:
            try:
                group = await fetch_chunk(chunk)
            except Exception:
                group = [None] * len(chunk)
        out.extend(group)
    return out


async def _om_json(client: httpx.AsyncClient, url: str, params: dict[str, str]) -> Any:
    """POST first (large multi-location bodies); GET fallback; exponential 429 backoff."""
    last: Exception | None = None
    retries = max(2, settings.open_meteo_max_retries)
    for attempt in range(1, retries + 1):
        await pace_open_meteo()
        try:
            r = await client.post(url, data=params)
            if r.status_code not in (200, 429) and r.status_code < 500:
                r = await client.get(url, params=params)
            if r.status_code == 429:
                wait = retry_wait_seconds(attempt, r.headers.get("Retry-After"))
                log.warning("open-meteo 429 on %s — backing off %.1fs (attempt %s/%s)", url, wait, attempt, retries)
                await asyncio.sleep(wait)
                last = RuntimeError("open-meteo 429")
                continue
            if r.status_code >= 500:
                wait = retry_wait_seconds(attempt)
                log.warning("open-meteo %s on %s — retry in %.1fs", r.status_code, url, wait)
                await asyncio.sleep(wait)
                last = RuntimeError(f"open-meteo {r.status_code}")
                continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last = exc
            await asyncio.sleep(retry_wait_seconds(attempt, jitter=True) * 0.35)
    if last:
        raise last
    raise RuntimeError("open-meteo empty")


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
        f"field:v4:{model}:{om_var}:{bbox['west']}:{bbox['south']}:{bbox['east']}:{bbox['north']}"
        f":{nx}x{ny}:{step}"
    )
    hit = await cache_get_prefer(cache_key)
    if hit:
        hit["cached"] = True
        return hit

    lats, lons = _grid_points(bbox, nx, ny)
    points: list[tuple[float, float]] = [(lat, lon) for lat in lats for lon in lons]

    client = await http()
    values = np.full((ny, nx), np.nan, dtype=float)
    init_time: str | None = None
    valid_time: str | None = None

    async def batch(chunk: list[tuple[float, float]]) -> list[dict[str, Any] | None]:
        lat_s = ",".join(f"{p[0]:.3f}" for p in chunk)
        lon_s = ",".join(f"{p[1]:.3f}" for p in chunk)
        params = {
            "latitude": lat_s,
            "longitude": lon_s,
            "hourly": om_var if om_var != "surface_pressure" else "surface_pressure,pressure_msl",
            "models": model,
            "forecast_days": "6",
            "timezone": "UTC",
            "wind_speed_unit": "ms",
        }
        url = f"{settings.open_meteo_base.rstrip('/')}/v1/forecast"
        data = await _om_json(client, url, params)
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
            init_time, valid_time = field_clock(times, step)
        row = idx // nx
        col = idx % nx
        if val is not None:
            values[row, col] = float(val)

    finite = values[np.isfinite(values)]
    vmin = float(np.min(finite)) if finite.size else 0.0
    vmax = float(np.max(finite)) if finite.size else 1.0
    out = {
        "model": model,
        "model_id": model,
        "variable": variable,
        "unit": element["unit"],
        "label": element["label"],
        "label_en": element["label_en"],
        "init_time": init_time,
        "valid_time": valid_time,
        "lead_hours": step,
        "step": step,
        "kind": "model_forecast",
        "provider": "open-meteo",
        "bbox": bbox,
        "lats": lats,
        "lons": lons,
        "values": [[None if not math.isfinite(v) else round(float(v), 3) for v in row] for row in values],
        "min": round(vmin, 3),
        "max": round(vmax, 3),
        "source": f"open-meteo:{model}",
        "source_note": "near-real-time numerical model forecast, not station observations",
        "cached": False,
        "nx": nx,
        "ny": ny,
    }
    if finite.size:
        await cache_remember(cache_key, out, settings.cache_ttl_seconds)
    else:
        stale = await cache_get_prefer(cache_key)
        if stale:
            stale["cached"] = True
            return stale
    return out


async def fetch_wind_grid(model: str = "gfs_seamless", nx: int = 24, ny: int = 12) -> dict[str, Any]:
    bbox = {"west": -180.0, "south": -70.0, "east": 180.0, "north": 70.0}
    cache_key = f"wind:v2:{model}:{nx}x{ny}"
    hit = await cache_get_prefer(cache_key)
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
        data = await _om_json(client, url, params)
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
        stale = await cache_get_prefer(cache_key)
        if stale:
            stale["cached"] = True
            return stale
        # last-resort synthetic field so the globe still animates offline
        return synthetic_wind(nx, ny, bbox, reason="open-meteo-sparse")

    out = _vector_payload(nx, ny, bbox, u, v, f"open-meteo:{model}", filled, kind="wind")
    await cache_remember(cache_key, out, settings.wind_cache_ttl_seconds)
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


def _fill_ocean_gaps(u: np.ndarray, v: np.ndarray, bbox: dict[str, float]) -> None:
    """Bilinear-ish fill for empty ocean cells so SCS/China seas are not holes."""
    ny, nx = u.shape
    lons = np.linspace(bbox["west"], bbox["east"], nx)
    lats = np.linspace(bbox["north"], bbox["south"], ny)
    ocean = np.zeros((ny, nx), dtype=bool)
    for j in range(ny):
        for i in range(nx):
            ocean[j, i] = not is_land(float(lons[i]), float(lats[j]))
    for _ in range(4):
        nu, nv = u.copy(), v.copy()
        changed = False
        for j in range(ny):
            for i in range(nx):
                if not ocean[j, i]:
                    continue
                if abs(u[j, i]) + abs(v[j, i]) > 1e-6:
                    continue
                acc_u = acc_v = 0.0
                n = 0
                for dj, di in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    y, x = j + dj, i + di
                    if 0 <= y < ny and 0 <= x < nx and ocean[y, x] and abs(u[y, x]) + abs(v[y, x]) > 1e-6:
                        acc_u += u[y, x]
                        acc_v += v[y, x]
                        n += 1
                if n:
                    nu[j, i] = acc_u / n
                    nv[j, i] = acc_v / n
                    changed = True
        u[:] = nu
        v[:] = nv
        if not changed:
            break


async def _fetch_current_patch(
    marine_model: str,
    bbox: dict[str, float],
    nx: int,
    ny: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    lats, lons = _grid_points(bbox, nx, ny)
    points = [(lat, lon) for lat in reversed(lats) for lon in lons]
    u = np.zeros((ny, nx), dtype=float)
    v = np.zeros((ny, nx), dtype=float)
    client = await http()
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
        data = await _om_json(client, f"{marine}/v1/marine", params)
        return data if isinstance(data, list) else [data]

    payloads = await _gather_batches(ocean_pts, batch)
    filled = 0
    for (idx, req_lat, req_lon), payload in zip(ocean_idx, payloads, strict=False):
        if not payload:
            continue
        act_lat = payload.get("latitude")
        act_lon = payload.get("longitude")
        if act_lat is not None and act_lon is not None:
            dlat = float(act_lat) - req_lat
            dlon = ((float(act_lon) - req_lon + 180.0) % 360.0) - 180.0
            dist = math.hypot(dlat, dlon * math.cos(math.radians(req_lat)))
            if dist > 1.35:
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
        row = idx // nx
        col = idx % nx
        u[row, col] = speed * math.sin(rad)
        v[row, col] = speed * math.cos(rad)
        filled += 1
    _fill_ocean_gaps(u, v, bbox)
    return u, v, filled


async def fetch_current_grid(model: str = "best_match", nx: int | None = None, ny: int | None = None) -> dict[str, Any]:
    """Surface ocean currents from Open-Meteo Marine, plus a China-seas nest."""
    bbox = {"west": -180.0, "south": -70.0, "east": 180.0, "north": 70.0}
    nx = int(nx or settings.current_nx)
    ny = int(ny or settings.current_ny)
    marine_model = model if model in CURRENT_BY_ID else "best_match"
    cache_key = f"currents:v3:{marine_model}:{nx}x{ny}:nest"
    hit = await cache_get_prefer(cache_key)
    if hit:
        hit["cached"] = True
        return hit

    u, v, filled = await _fetch_current_patch(marine_model, bbox, nx, ny)
    if filled < 8:
        stale = await cache_get_prefer(cache_key)
        if stale:
            stale["cached"] = True
            return stale
        return synthetic_currents(nx, ny, bbox, reason="open-meteo-marine-sparse")

    out = apply_ocean_mask(
        _vector_payload(nx, ny, bbox, u, v, f"open-meteo-marine:{marine_model}", filled, kind="currents")
    )
    try:
        nest_u, nest_v, nest_filled = await _fetch_current_patch(
            marine_model,
            CHINA_SEAS_BBOX,
            settings.current_nest_nx,
            settings.current_nest_ny,
        )
        if nest_filled >= 6:
            nest = apply_ocean_mask(
                _vector_payload(
                    settings.current_nest_nx,
                    settings.current_nest_ny,
                    CHINA_SEAS_BBOX,
                    nest_u,
                    nest_v,
                    f"open-meteo-marine:{marine_model}:china-seas",
                    nest_filled,
                    kind="currents",
                )
            )
            out["nest"] = nest
    except Exception:
        pass
    await cache_remember(cache_key, out, settings.current_cache_ttl_seconds)
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


async def prewarm_hot_paths() -> dict[str, Any]:
    """Serialized warm of catalog-adjacent OM payloads. Safe to call on idle start."""
    summary: dict[str, Any] = {"ok": [], "errors": {}}
    try:
        await fetch_current_grid("best_match")
        summary["ok"].append(f"currents:{settings.current_nx}x{settings.current_ny}")
    except Exception as exc:
        summary["errors"]["currents"] = str(exc)
        log.warning("prewarm currents: %s", exc)
    try:
        await fetch_wind_grid("gfs_seamless", nx=settings.wind_nx, ny=settings.wind_ny)
        summary["ok"].append(f"wind:{settings.wind_nx}x{settings.wind_ny}")
    except Exception as exc:
        summary["errors"]["wind"] = str(exc)
        log.warning("prewarm wind: %s", exc)
    try:
        await fetch_field(
            "gfs_seamless",
            "temperature_2m",
            CHINA_BBOX,
            nx=settings.field_nx,
            ny=settings.field_ny,
            step=0,
        )
        summary["ok"].append(f"field:{settings.field_nx}x{settings.field_ny}")
    except Exception as exc:
        summary["errors"]["field"] = str(exc)
        log.warning("prewarm field: %s", exc)
    log.info("open-meteo prewarm %s", summary)
    return summary


async def close() -> None:
    global _http, _redis
    if _http is not None:
        await _http.aclose()
        _http = None
    if _redis is not None:
        await _redis.aclose()
        _redis = None
