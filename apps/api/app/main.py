from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import (
    CHINA_BBOX,
    DEFAULT_POINT,
    ELEMENT_BY_ID,
    ELEMENTS,
    PREVIEW_BY_ID,
    PREVIEW_MODELS,
)
from app.config import settings
from app.db import Activity, Dataset, SessionLocal, get_session, init_db
from app.news import get_article, list_articles
from app import ncproc, openmeteo, storage
from app.workers import ForecastIngestActor, NcIngestActor, broker

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("aetherwatch")


async def _wait_db(retries: int = 20) -> None:
    last = None
    for i in range(retries):
        try:
            await asyncio.wait_for(init_db(), timeout=8)
            return
        except Exception as exc:
            last = exc
            log.warning("db init retry %s: %s", i, exc)
            await asyncio.sleep(1.0)
    raise last  # type: ignore[misc]


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("init database")
    await _wait_db()
    log.info("ensure object bucket")
    try:
        await asyncio.to_thread(storage.ensure_bucket)
    except Exception as exc:
        log.warning("minio bucket: %s", exc)
    log.info("start taskiq broker")
    try:
        await asyncio.wait_for(broker.startup(), timeout=8)
        await asyncio.wait_for(ForecastIngestActor.run.kiq(False), timeout=8)
        log.info("forecast ingest enqueued")
    except Exception as exc:
        log.warning("forecast ingest enqueue: %s", exc)
    yield
    try:
        await broker.shutdown()
    except Exception:
        pass
    await openmeteo.close()


app = FastAPI(
    title="AetherWatch API",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _admin(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    expected = settings.admin_token
    if expected and x_admin_token != expected:
        # also allow query-less local form posts from same compose network without header
        # when token is the documented default, still require it from the web client
        raise HTTPException(status_code=401, detail="invalid admin token")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    checks: dict[str, str] = {}
    try:
        async with SessionLocal() as session:
            await session.execute(select(Dataset.id).limit(1))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error:{exc.__class__.__name__}"
    try:
        r = await openmeteo.cache()
        await r.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error:{exc.__class__.__name__}"
    try:
        storage.ensure_bucket()
        checks["minio"] = "ok"
    except Exception as ext:
        checks["minio"] = f"error:{ext.__class__.__name__}"
    ok = all(v == "ok" for v in checks.values())
    return {
        "ok": ok,
        "service": "aetherwatch-api",
        "time": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


@app.get("/api/meta")
async def meta() -> dict[str, Any]:
    visitors = await openmeteo.incr_visitors()
    return {
        "name": "AetherWatch",
        "tagline": "天气与智能的观测台",
        "tagline_en": "Weather and intelligence, observed.",
        "visitors": visitors,
        "now": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/catalog")
async def catalog(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    result = await session.execute(select(Dataset).order_by(desc(Dataset.created_at)))
    datasets = []
    for row in result.scalars():
        datasets.append(
            {
                "id": f"nc:{row.id}",
                "dataset_id": row.id,
                "short": row.filename.rsplit(".", 1)[0][:18],
                "name": row.filename,
                "kind": "upload",
                "source": "netcdf",
                "status": row.status,
                "color": "#0f766e",
                "variables": row.variables,
                "dims": row.dims,
                "bbox": row.bbox,
                "preview_variable": row.preview_variable,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "error_message": row.error_message,
            }
        )
    return {"models": PREVIEW_MODELS, "elements": ELEMENTS, "datasets": datasets}


@app.get("/api/series")
async def series(
    lat: float = Query(DEFAULT_POINT["lat"]),
    lon: float = Query(DEFAULT_POINT["lon"]),
    variable: str = Query("temperature_2m"),
    models: str = Query("gfs_seamless,ecmwf_ifs025,ecmwf_aifs025_single"),
    forecast_days: int = Query(5, ge=1, le=16),
) -> dict[str, Any]:
    model_ids = [m.strip() for m in models.split(",") if m.strip() and not m.startswith("nc:")]
    if not model_ids:
        model_ids = ["gfs_seamless"]
    if variable not in ELEMENT_BY_ID:
        raise HTTPException(400, f"unknown variable {variable}")
    return await openmeteo.fetch_series(lat, lon, variable, model_ids, forecast_days)


@app.get("/api/field")
async def field(
    model: str = Query("gfs_seamless"),
    variable: str = Query("temperature_2m"),
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
    step: int = 0,
    nx: int = Query(10, ge=4, le=16),
    ny: int = Query(7, ge=4, le=12),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    bbox = {
        "west": west if west is not None else CHINA_BBOX["west"],
        "south": south if south is not None else CHINA_BBOX["south"],
        "east": east if east is not None else CHINA_BBOX["east"],
        "north": north if north is not None else CHINA_BBOX["north"],
    }
    if model.startswith("nc:"):
        return await _nc_field(session, model[3:], step)
    if variable not in ELEMENT_BY_ID:
        raise HTTPException(400, f"unknown variable {variable}")
    return await openmeteo.fetch_field(model, variable, bbox, nx=nx, ny=ny, step=step)


@app.get("/api/compare")
async def compare(
    models: str = Query("gfs_seamless,ecmwf_ifs025"),
    variable: str = Query("temperature_2m"),
    step: int = 0,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ids = [m.strip() for m in models.split(",") if m.strip()][:4]
    grids = []
    for mid in ids:
        if mid.startswith("nc:"):
            grids.append(await _nc_field(session, mid[3:], step))
        else:
            grids.append(await openmeteo.fetch_field(mid, variable, CHINA_BBOX, nx=8, ny=6, step=step))
    return {"variable": variable, "step": step, "grids": grids}


@app.get("/api/runs")
async def runs(hours: int = Query(120, ge=6, le=240)) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    steps = []
    for h in range(0, hours + 1, 6):
        t = now + timedelta(hours=h)
        steps.append({"lead": h, "time": t.isoformat(), "label": f"+{h}h"})
    return {"init": now.isoformat(), "steps": steps}


@app.get("/api/wind")
async def wind(model: str = Query("gfs_seamless")) -> dict[str, Any]:
    if model not in PREVIEW_BY_ID:
        model = "gfs_seamless"
    try:
        return await openmeteo.fetch_wind_grid(model, nx=20, ny=10)
    except Exception as exc:
        log.warning("wind live fetch failed: %s", exc)
        return openmeteo.synthetic_wind(20, 10, {"west": -180, "south": -70, "east": 180, "north": 70})


@app.get("/api/news")
async def news_list(category: str | None = None) -> dict[str, Any]:
    items = list_articles()
    if category and category not in {"all", "全部", ""}:
        items = [a for a in items if a.get("category") == category]
    cats = sorted({a.get("category") or "资讯" for a in list_articles()})
    return {"articles": items, "categories": cats, "total": len(items)}


@app.get("/api/news/{article_id}")
async def news_detail(article_id: str) -> dict[str, Any]:
    article = get_article(article_id)
    if not article:
        raise HTTPException(404, "article not found")
    return article


@app.get("/api/feeds")
async def feeds(session: AsyncSession = Depends(get_session), limit: int = 40) -> dict[str, Any]:
    result = await session.execute(select(Activity).order_by(desc(Activity.created_at)).limit(limit))
    events = []
    for row in result.scalars():
        events.append(
            {
                "id": row.id,
                "kind": row.kind,
                "title": row.title,
                "detail": row.detail,
                "payload": row.payload,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    # seed a few editorial events if the table is empty
    if not events:
        events = [
            {
                "id": 0,
                "kind": "news",
                "title": "资讯台已装载样本稿件",
                "detail": "content/news 下的 Markdown 已建立索引",
                "payload": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    return {"events": events}


@app.get("/api/geo/china-bounds.json")
async def china_bounds() -> dict[str, Any]:
    from pathlib import Path

    path = Path(settings.geo_dir) / "china-bounds.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "China bounds"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [CHINA_BBOX["west"], CHINA_BBOX["south"]],
                            [CHINA_BBOX["east"], CHINA_BBOX["south"]],
                            [CHINA_BBOX["east"], CHINA_BBOX["north"]],
                            [CHINA_BBOX["west"], CHINA_BBOX["north"]],
                            [CHINA_BBOX["west"], CHINA_BBOX["south"]],
                        ]
                    ],
                },
            }
        ],
    }


@app.post("/api/admin/datasets/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _admin(x_admin_token)
    name = file.filename or "upload.nc"
    lower = name.lower()
    if not (lower.endswith(".nc") or lower.endswith(".nc4") or lower.endswith(".netcdf")):
        raise HTTPException(400, "only NetCDF (.nc / .nc4) is accepted")
    data = await file.read()
    if len(data) < 16:
        raise HTTPException(400, "empty file")
    if len(data) > 250 * 1024 * 1024:
        raise HTTPException(413, "file too large (250 MB limit in v1)")
    dataset_id = str(uuid.uuid4())
    key = f"raw/{dataset_id}/{name}"
    try:
        storage.put_bytes(key, data, "application/x-netcdf")
    except Exception as exc:
        raise HTTPException(503, f"object store unavailable: {exc}") from exc
    row = Dataset(id=dataset_id, filename=name, status="uploaded", minio_key=key)
    session.add(row)
    session.add(Activity(kind="dataset", title=f"上传 {name}", detail=f"{len(data)} bytes", payload={"id": dataset_id}))
    await session.commit()
    try:
        await NcIngestActor.run.kiq(dataset_id)
    except Exception as exc:
        log.warning("enqueue ingest: %s", exc)
    return {"id": dataset_id, "filename": name, "status": "uploaded", "bytes": len(data)}


@app.post("/api/admin/datasets/demo")
async def seed_demo_nc(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _admin(x_admin_token)
    data = ncproc.make_demo_nc()
    dataset_id = str(uuid.uuid4())
    name = "demo_t2m_china.nc"
    key = f"raw/{dataset_id}/{name}"
    storage.put_bytes(key, data, "application/x-netcdf")
    row = Dataset(id=dataset_id, filename=name, status="uploaded", minio_key=key)
    session.add(row)
    await session.commit()
    await NcIngestActor.run.kiq(dataset_id)
    return {"id": dataset_id, "filename": name, "status": "uploaded", "bytes": len(data)}


@app.get("/api/admin/datasets")
async def list_datasets(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _admin(x_admin_token)
    result = await session.execute(select(Dataset).order_by(desc(Dataset.created_at)))
    items = []
    for row in result.scalars():
        items.append(
            {
                "id": row.id,
                "filename": row.filename,
                "status": row.status,
                "dims": row.dims,
                "preview_variable": row.preview_variable,
                "bbox": row.bbox,
                "error_message": row.error_message,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return {"datasets": items}


async def _nc_field(session: AsyncSession, dataset_id: str, step: int) -> dict[str, Any]:
    row = await session.get(Dataset, dataset_id)
    if row is None:
        raise HTTPException(404, "dataset not found")
    if row.status != "ready" or not row.derived_key:
        raise HTTPException(409, f"dataset not ready ({row.status})")
    raw = storage.get_bytes(row.derived_key)
    field = json.loads(raw)
    field["model"] = f"nc:{dataset_id}"
    field["step"] = step
    return field
