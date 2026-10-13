# AetherWatch

International weather + AI observation desk. Multi-model forecast (Open-Meteo), a WebGL ocean-current / wind globe, editorial notes, and an admin path that turns uploaded NetCDF into map fields.

Brand is **AetherWatch** only. UI language is **Chinese by default**, with a 中/EN toggle (persisted in `localStorage`). Forecast / Earth maps prefer Chinese place names from OpenFreeMap.

## Quick start

```bash
cp .env.example .env   # optional; compose has working defaults
docker compose up --build
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765).

| Path | What |
| --- | --- |
| `/` | Earth globe — **洋流** particles by default, switchable **风场** / scalar overlays |
| `/forecast` | Linked-camera model compare, Chinese basemap labels, click-for-series, +0–120h steps |
| `/news` | Seeded Markdown notes |
| `/feeds` | Ingest / tile actor timeline |
| `/about` | Stack and data-plane notes |
| `/admin` | Upload `.nc` / `.nc4` (header `X-Admin-Token`) |

API: [http://127.0.0.1:8765/api/health](http://127.0.0.1:8765/api/health) · docs at `/api/docs` via the `api` service if you publish port 8000.

Default admin token: `aether-dev` (see `.env.example`).

## Rebuild just web or api

After UI / globe changes:

```bash
docker compose up -d --build web
```

After API, catalog, field-grid, or current-source changes:

```bash
docker compose up -d --build api worker
```

Both (typical after this desktop):

```bash
docker compose up -d --build api worker web
```

Caddy still fronts the stack at `:8765`. No need to rebuild postgres / redis / minio / caddy unless their configs changed.

## 中文速览

```bash
docker compose up --build
```

浏览器打开 `http://127.0.0.1:8765`。导航：地球 / 预报 / 资讯 / 动态 / 关于 / 管理。

- 地球页默认 **洋流**（Open-Meteo Marine 表层流），可切到 **风场** 与气温 / 气压 / 降水；模式芯片会跟着要素换成 Marine/SMOC 或 GFS/IFS。
- 预报页多图 **镜头联动**（滚轮缩放 / 拖动平移同步），单击格点拉序列；时效 +0h～+120h，可播放。时间序列来自 Open-Meteo（GFS / IFS / AIFS 等）。
- 中国空间场默认约 **40×30** 点采样（不再是 10×7 色块）。
- 管理页可上传 NetCDF；`NcIngestActor` 解析，`NcTileActor` 产出一张二维场给地图。u/v 洋流 NetCDF 会出现在地球页洋流模式里。
- 公开源失败时地球粒子回落合成场，来源行会标明「合成场」。

## Layout

```
apps/web     Nuxt 3 + MapLibre (WebGL particle layer on globe)
apps/api     FastAPI + Taskiq actors
content/news seeded Markdown
content/geo  China bounds GeoJSON
infra/caddy  reverse proxy
```

## Actors

| Actor | Job |
| --- | --- |
| `ForecastIngestActor` | Warm Redis with Open-Meteo series / China field / wind / currents |
| `NcIngestActor` | Validate uploaded NetCDF, parse dims/vars, store metadata |
| `NcTileActor` | Extract one 2D slice → MinIO JSON for `/api/field` |

Worker command: `taskiq worker app.workers:broker`.

MinIO is built from the community GitHub binary (`infra/minio/Dockerfile`) because `minio/minio` Hub tags are often login-walled after the AIStor split. The API still creates the bucket on startup.

## Data notes

- Open-Meteo forecast API, no key for non-commercial use: <https://api.open-meteo.com>
- Open-Meteo Marine (currents): <https://marine-api.open-meteo.com> — `ocean_current_velocity` + `ocean_current_direction`
- Preview models: `gfs_seamless`, `ecmwf_ifs025`, `ecmwf_aifs025_single`, `icon_seamless`, `ukmo_seamless`
- Current models: `best_match` (Marine), `meteofrance_currents` (SMOC)
- Full NOAA GFS GRIB ingest (cfgrib / NOMADS) is intentionally out of v1.
- Demo NetCDF: Admin → “生成演示 NetCDF” (T2m) or “生成演示洋流 NetCDF” (`uo`/`vo`).

## Env knobs (rate-limit / density)

| Variable | Default | What |
| --- | --- | --- |
| `FIELD_NX` / `FIELD_NY` | `40` / `30` | China `/api/field` sample grid. Lower if Open-Meteo rate-limits. |
| `CURRENT_NX` / `CURRENT_NY` | `24` / `12` | Global current u/v grid (land cells skipped). |
| `OPEN_METEO_BATCH_SIZE` | `40` | Locations per Open-Meteo request. |
| `OPEN_METEO_CONCURRENCY` | `3` | Parallel Open-Meteo batches. |
| `OPEN_METEO_BASE` | `https://api.open-meteo.com` | Forecast API. |
| `OPEN_METEO_MARINE_BASE` | `https://marine-api.open-meteo.com` | Marine / currents API. |

`/api/field` still accepts `nx`/`ny` query overrides (`4–48` / `4–36`). Forecast maps omit them so the env defaults apply. Globe scalar overlay still requests a coarser global `16×10`.

Redis caches fields (`CACHE_TTL_SECONDS`, default 1800) and current/wind grids (3600s) so a cold 40×30 fetch is rare.

## Local development without Compose (optional)

API needs Postgres, Redis, and MinIO reachable at the URLs in `.env`. Web:

```bash
cd apps/web && npm install && NUXT_API_INTERNAL=http://127.0.0.1:8000 npm run dev
```
