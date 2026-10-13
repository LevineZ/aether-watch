"""Actor-style Taskiq tasks.

Each actor is a class with a single `run` taskiq task. The API enqueues work
with `Actor.run.kiq(...)`; the worker process executes it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app.config import settings

logger = logging.getLogger("aetherwatch.actors")

broker = ListQueueBroker(url=settings.redis_url).with_result_backend(
    RedisAsyncResultBackend(redis_url=settings.redis_url)
)


class ForecastIngestActor:
    """Warm Redis with live Open-Meteo series/field/wind so the UI is snappy."""

    @staticmethod
    @broker.task(task_name="forecast_ingest")
    async def run(force: bool = False) -> dict:
        from app.catalog import CHINA_BBOX, DEFAULT_POINT, PREVIEW_MODELS
        from app.openmeteo import fetch_field, fetch_series, fetch_wind_grid

        models = [m["id"] for m in PREVIEW_MODELS[:3]]
        summary: dict = {"actor": "ForecastIngestActor", "ok": [], "errors": {}}
        try:
            await fetch_series(DEFAULT_POINT["lat"], DEFAULT_POINT["lon"], "temperature_2m", models)
            summary["ok"].append("series:beijing:t2m")
        except Exception as exc:
            summary["errors"]["series"] = str(exc)
        try:
            await fetch_field(models[0], "temperature_2m", CHINA_BBOX, nx=8, ny=6, step=0)
            summary["ok"].append("field:gfs:t2m")
        except Exception as exc:
            summary["errors"]["field"] = str(exc)
        try:
            await fetch_wind_grid(models[0], nx=20, ny=10)
            summary["ok"].append("wind:gfs")
        except Exception as exc:
            summary["errors"]["wind"] = str(exc)

        await _activity("ingest", "预报缓存刷新", json.dumps(summary, ensure_ascii=False)[:800], summary)
        return summary


class NcIngestActor:
    """Validate an uploaded NetCDF, parse dims/vars, store metadata."""

    @staticmethod
    @broker.task(task_name="nc_ingest")
    async def run(dataset_id: str) -> dict:
        from app.db import Dataset, SessionLocal
        from app import ncproc, storage

        async with SessionLocal() as session:
            row = await session.get(Dataset, dataset_id)
            if row is None:
                return {"ok": False, "error": "dataset not found"}
            row.status = "ingesting"
            await session.commit()

            tmp = None
            try:
                raw = storage.get_bytes(row.minio_key)
                tmp = ncproc.write_temp(raw, suffix=".nc")
                meta = ncproc.inspect_dataset(tmp)
                row.variables = meta["variables"]
                row.dims = meta["dims"]
                row.preview_variable = ncproc.pick_preview_name(meta)
                row.status = "parsed"
                await session.commit()
            except Exception as exc:
                row.status = "error"
                row.error_message = str(exc)[:2000]
                await session.commit()
                await _activity("dataset", f"NetCDF 解析失败 {row.filename}", str(exc)[:400], {"id": dataset_id})
                return {"ok": False, "error": str(exc)}
            finally:
                if tmp:
                    Path(tmp).unlink(missing_ok=True)

        await NcTileActor.run.kiq(dataset_id)
        await _activity("dataset", f"已解析 {row.filename}", None, {"id": dataset_id, "dims": row.dims})
        return {"ok": True, "id": dataset_id, "status": "parsed"}


class NcTileActor:
    """Slice a 2D field from the uploaded NC and store JSON for the map."""

    @staticmethod
    @broker.task(task_name="nc_tile")
    async def run(dataset_id: str, step: int = 0) -> dict:
        from app.db import Dataset, SessionLocal
        from app import ncproc, storage

        async with SessionLocal() as session:
            row = await session.get(Dataset, dataset_id)
            if row is None:
                return {"ok": False, "error": "dataset not found"}
            tmp = None
            try:
                raw = storage.get_bytes(row.minio_key)
                tmp = ncproc.write_temp(raw, suffix=".nc")
                field = ncproc.extract_field(tmp, variable=row.preview_variable, step=step)
                key = f"derived/{dataset_id}/field.json"
                storage.put_bytes(key, ncproc.field_to_json_bytes(field), "application/json")
                row.derived_key = key
                row.bbox = field.get("bbox")
                row.unit = field.get("unit")
                row.preview_variable = field.get("variable")
                row.status = "ready"
                row.error_message = None
                await session.commit()
                await _activity(
                    "dataset",
                    f"切片就绪 {row.filename}",
                    field.get("variable"),
                    {"id": dataset_id, "bbox": field.get("bbox")},
                )
                return {"ok": True, "id": dataset_id, "variable": field.get("variable")}
            except Exception as exc:
                row.status = "error"
                row.error_message = str(exc)[:2000]
                await session.commit()
                return {"ok": False, "error": str(exc)}
            finally:
                if tmp:
                    Path(tmp).unlink(missing_ok=True)


async def _activity(kind: str, title: str, detail: str | None, payload: dict | None) -> None:
    try:
        from app.db import Activity, SessionLocal

        async with SessionLocal() as session:
            session.add(Activity(kind=kind, title=title, detail=detail, payload=payload))
            await session.commit()
    except Exception as exc:
        logger.warning("activity write failed: %s", exc)


# Re-exported so `taskiq worker app.workers:broker` discovers decorated tasks.
__all__ = ["broker", "ForecastIngestActor", "NcIngestActor", "NcTileActor"]
