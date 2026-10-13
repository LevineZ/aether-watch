"""0.5° land mask (Natural Earth 110m), packed bits: 1 = land, row 0 = 90°N, col 0 = -180°."""

from __future__ import annotations

from pathlib import Path

import numpy as np

NX = 720
NY = 360
_BITS: np.ndarray | None = None


def _bits() -> np.ndarray:
    global _BITS
    if _BITS is None:
        raw = (Path(__file__).parent / "assets" / "landmask_720x360.bin").read_bytes()
        _BITS = np.unpackbits(np.frombuffer(raw, dtype=np.uint8))[: NX * NY].reshape(NY, NX)
    return _BITS


def is_land(lon: float, lat: float) -> bool:
    if lat < -85:
        return True
    x = int(((lon + 180.0) / 360.0) * NX) % NX
    y = int((90.0 - lat) / 180.0 * NY)
    y = min(max(y, 0), NY - 1)
    return bool(_bits()[y, x])


def apply_ocean_mask(out: dict) -> dict:
    """Zero current vectors on land and attach a 0/1 ocean mask (row-major, north → south)."""
    nx, ny = int(out["width"]), int(out["height"])
    u = np.asarray(out["u"], dtype=float).reshape(ny, nx)
    v = np.asarray(out["v"], dtype=float).reshape(ny, nx)
    lons = np.linspace(float(out["west"]), float(out["east"]), nx)
    lats = np.linspace(float(out["north"]), float(out["south"]), ny)
    mask = np.zeros((ny, nx), dtype=np.uint8)
    for j in range(ny):
        for i in range(nx):
            if is_land(float(lons[i]), float(lats[j])):
                u[j, i] = 0.0
                v[j, i] = 0.0
            else:
                mask[j, i] = 1
    out["u"] = [round(float(x), 3) for x in u.reshape(-1).tolist()]
    out["v"] = [round(float(x), 3) for x in v.reshape(-1).tolist()]
    out["mask"] = [int(x) for x in mask.reshape(-1).tolist()]
    out["uMin"] = round(float(np.min(u)), 3)
    out["uMax"] = round(float(np.max(u)), 3)
    out["vMin"] = round(float(np.min(v)), 3)
    out["vMax"] = round(float(np.max(v)), 3)
    ocean_filled = int(np.count_nonzero((mask == 1) & ((np.abs(u) + np.abs(v)) > 1e-6)))
    out["filled"] = ocean_filled
    out["ocean_cells"] = int(mask.sum())
    return out
