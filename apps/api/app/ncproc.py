"""NetCDF inspect + 2D slice export for the forecast map."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr


LAT_NAMES = ("latitude", "lat", "y", "nav_lat")
LON_NAMES = ("longitude", "lon", "x", "nav_lon")
TIME_NAMES = ("time", "valid_time", "t", "forecast_time")


def _find_coord(ds: xr.Dataset, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in ds.coords or name in ds.variables or name in ds.dims:
            return name
    for dim in ds.dims:
        lowered = dim.lower()
        if any(n in lowered for n in names):
            return dim
    return None


def pick_preview_name(meta: dict[str, Any]) -> str | None:
    ranked: list[tuple[int, str]] = []
    for item in meta.get("variables") or []:
        dims = item.get("dims") or []
        if len(dims) < 2:
            continue
        name = item["name"]
        score = len(dims)
        lowered = name.lower()
        if any(k in lowered for k in ("temp", "t2m", "tas", "sst", "air")):
            score += 10
        if any(k in lowered for k in ("wind", "u10", "v10")):
            score += 6
        ranked.append((score, name))
    if ranked:
        ranked.sort(reverse=True)
        return ranked[0][1]
    variables = meta.get("variables") or []
    return variables[0]["name"] if variables else None


def inspect_dataset(path: str | Path) -> dict[str, Any]:
    ds = xr.open_dataset(path, decode_times=True, mask_and_scale=True)
    try:
        variables = []
        for name, da in ds.data_vars.items():
            variables.append(
                {
                    "name": name,
                    "dims": list(da.dims),
                    "shape": list(da.shape),
                    "dtype": str(da.dtype),
                    "attrs": {k: _jsonish(v) for k, v in dict(da.attrs).items()},
                }
            )
        return {
            "dims": {k: int(v) for k, v in ds.sizes.items()},
            "coords": list(ds.coords),
            "variables": variables,
            "attrs": {k: _jsonish(v) for k, v in dict(ds.attrs).items()},
            "lat_name": _find_coord(ds, LAT_NAMES),
            "lon_name": _find_coord(ds, LON_NAMES),
            "time_name": _find_coord(ds, TIME_NAMES),
        }
    finally:
        ds.close()


def _jsonish(value: Any) -> Any:
    if isinstance(value, (np.generic,)):
        return value.item()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _pick_variable(ds: xr.Dataset, preferred: str | None = None) -> str:
    if preferred and preferred in ds.data_vars:
        return preferred
    ranked: list[tuple[int, str]] = []
    for name, da in ds.data_vars.items():
        if da.ndim < 2:
            continue
        score = da.ndim
        lowered = name.lower()
        if any(k in lowered for k in ("temp", "t2m", "tas", "sst")):
            score += 10
        if any(k in lowered for k in ("wind", "u10", "v10")):
            score += 6
        ranked.append((score, name))
    if not ranked:
        return next(iter(ds.data_vars))
    ranked.sort(reverse=True)
    return ranked[0][1]


def extract_field(path: str | Path, variable: str | None = None, step: int = 0) -> dict[str, Any]:
    ds = xr.open_dataset(path, decode_times=True, mask_and_scale=True)
    try:
        var = _pick_variable(ds, variable)
        da = ds[var]
        lat_name = _find_coord(ds, LAT_NAMES)
        lon_name = _find_coord(ds, LON_NAMES)
        time_name = _find_coord(ds, TIME_NAMES)

        # squeeze singleton extra dims (level, ensemble, …)
        squeeze_dims = [d for d in da.dims if da.sizes[d] == 1]
        if squeeze_dims:
            da = da.squeeze(squeeze_dims, drop=True)

        if time_name and time_name in da.dims:
            ntime = da.sizes[time_name]
            idx = min(max(step, 0), ntime - 1)
            da = da.isel({time_name: idx})
            valid = da.coords.get(time_name)
            valid_time = str(valid.values) if valid is not None else None
        else:
            valid_time = None
            # leftover extra dims: take first index
            extra = [d for d in da.dims if d not in {lat_name, lon_name}]
            for d in extra:
                da = da.isel({d: 0})

        if lat_name is None or lon_name is None:
            # fabricate a regular grid if coordinates missing
            ny, nx = (da.shape + (1, 1))[:2]
            lats = np.linspace(18, 54, ny).tolist()
            lons = np.linspace(73, 135, nx).tolist()
            values = np.array(da.values, dtype=float)
            if values.ndim == 1:
                values = values.reshape(ny, nx)
        else:
            # ensure lat/lon are 1D
            lat_da = ds[lat_name]
            lon_da = ds[lon_name]
            if lat_da.ndim > 1:
                lats = np.array(lat_da.values)[:, 0].astype(float).tolist()
            else:
                lats = np.array(lat_da.values, dtype=float).tolist()
            if lon_da.ndim > 1:
                lons = np.array(lon_da.values)[0, :].astype(float).tolist()
            else:
                lons = np.array(lon_da.values, dtype=float).tolist()
            values = np.array(da.values, dtype=float)
            # if dim order is lon, lat — transpose
            if da.dims and da.dims[0] == lon_name:
                values = values.T

        values = np.array(values, dtype=float)
        if values.ndim == 1:
            values = values.reshape(len(lats), len(lons))
        # downsample huge grids so the browser stays snappy
        values, lats, lons = _downsample(values, lats, lons, max_side=96)
        finite = values[np.isfinite(values)]
        vmin = float(np.min(finite)) if finite.size else 0.0
        vmax = float(np.max(finite)) if finite.size else 1.0
        unit = str(da.attrs.get("units") or "")
        bbox = {
            "west": float(min(lons)),
            "east": float(max(lons)),
            "south": float(min(lats)),
            "north": float(max(lats)),
        }
        return {
            "model": Path(path).stem,
            "variable": var,
            "unit": unit,
            "label": str(da.attrs.get("long_name") or var),
            "label_en": var,
            "valid_time": valid_time,
            "step": step,
            "bbox": bbox,
            "lats": [round(float(x), 4) for x in lats],
            "lons": [round(float(x), 4) for x in lons],
            "values": [
                [None if not math.isfinite(v) else round(float(v), 4) for v in row] for row in values
            ],
            "min": round(vmin, 4),
            "max": round(vmax, 4),
            "source": "netcdf",
            "nx": len(lons),
            "ny": len(lats),
        }
    finally:
        ds.close()


def _downsample(
    values: np.ndarray, lats: list[float], lons: list[float], max_side: int
) -> tuple[np.ndarray, list[float], list[float]]:
    ny, nx = values.shape[:2]
    if ny <= max_side and nx <= max_side:
        return values, lats, lons
    stride_y = max(1, math.ceil(ny / max_side))
    stride_x = max(1, math.ceil(nx / max_side))
    return values[::stride_y, ::stride_x], lats[::stride_y], lons[::stride_x]


def field_to_json_bytes(field: dict[str, Any]) -> bytes:
    return json.dumps(field, ensure_ascii=False).encode("utf-8")


def write_temp(data: bytes, suffix: str = ".nc") -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.flush()
    tmp.close()
    return tmp.name


def make_demo_nc() -> bytes:
    """Tiny China T2m field (synthetic, CF-ish) so upload path can be demoed."""
    import netCDF4 as nc

    lats = np.linspace(18.0, 54.0, 37)
    lons = np.linspace(73.0, 135.0, 63)
    lon, lat = np.meshgrid(lons, lats)
    t2m = 28.0 - 0.55 * (lat - 22) + 4.0 * np.sin(np.radians(lon - 105)) * np.cos(np.radians(lat))
    t2m -= 6.0 * np.exp(-((lon - 90) ** 2 + (lat - 34) ** 2) / 80)
    t2m += 3.5 * np.exp(-((lon - 118) ** 2 + (lat - 32) ** 2) / 40)

    # netCDF4 needs a real file; write tempfile then return bytes
    path = write_temp(b"", suffix=".nc")
    with nc.Dataset(path, "w", format="NETCDF4") as ds:
        ds.createDimension("lat", lats.size)
        ds.createDimension("lon", lons.size)
        ds.createDimension("time", 1)
        times = ds.createVariable("time", "f8", ("time",))
        times.units = "hours since 2026-10-13 00:00:00"
        times.standard_name = "time"
        times[:] = [14.0]
        la = ds.createVariable("lat", "f4", ("lat",))
        la.units = "degrees_north"
        la.standard_name = "latitude"
        la[:] = lats
        lo = ds.createVariable("lon", "f4", ("lon",))
        lo.units = "degrees_east"
        lo.standard_name = "longitude"
        lo[:] = lons
        t = ds.createVariable("t2m", "f4", ("time", "lat", "lon"), zlib=True)
        t.units = "degC"
        t.long_name = "2 metre temperature"
        t[:] = t2m[None, :, :]
        ds.title = "AetherWatch demo 2 m temperature over China"
        ds.source = "synthetic demo for local NetCDF ingest"
    data = Path(path).read_bytes()
    Path(path).unlink(missing_ok=True)
    return data
