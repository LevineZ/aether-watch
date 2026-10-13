# AetherWatch

International weather + AI observation desk. Multi-model forecast (Open-Meteo), a WebGL wind globe, editorial notes, and an admin path that turns uploaded NetCDF into map fields.

Brand is **AetherWatch** only.

## Quick start

```bash
cp .env.example .env   # optional; compose has working defaults
docker compose up --build
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765).

| Path | What |
| --- | --- |
| `/` | Earth globe + particle wind |
| `/forecast` | Model chips, China field maps, Open-Meteo series |
| `/news` | Seeded Markdown notes |
| `/feeds` | Ingest / tile actor timeline |
| `/about` | Stack and data-plane notes |
| `/admin` | Upload `.nc` / `.nc4` (header `X-Admin-Token`) |

API: [http://127.0.0.1:8765/api/health](http://127.0.0.1:8765/api/health) · docs at `/api/docs` via the `api` service if you publish port 8000.

Default admin token: `aether-dev` (see `.env.example`).

## 中文速览

```bash
docker compose up --build
```

浏览器打开 `http://127.0.0.1:8765`。导航：地球 / 预报 / 资讯 / 动态 / 关于 / 管理。

- 预报页的时间序列来自 Open-Meteo 的真实 HTTP 请求（GFS / IFS / AIFS 等）。
- 管理页可上传 NetCDF；`NcIngestActor` 解析，`NcTileActor` 产出一张二维场给地图。
- 没有上传时，空间场用 Open-Meteo 对中国范围的粗网格采样；地球风场同理。全球 GRIB 未进 v1。

## Layout

```
apps/web     Nuxt 3 + MapLibre
apps/api     FastAPI + Taskiq actors
content/news seeded Markdown
content/geo  China bounds GeoJSON
infra/caddy  reverse proxy
```

## Actors

| Actor | Job |
| --- | --- |
| `ForecastIngestActor` | Warm Redis with Open-Meteo series / China field / wind grid |
| `NcIngestActor` | Validate uploaded NetCDF, parse dims/vars, store metadata |
| `NcTileActor` | Extract one 2D slice → MinIO JSON for `/api/field` |

Worker command: `taskiq worker app.workers:broker`.

MinIO is built from the community GitHub binary (`infra/minio/Dockerfile`) because `minio/minio` Hub tags are often login-walled after the AIStor split. The API still creates the bucket on startup.

## Data notes

- Open-Meteo forecast API, no key for non-commercial use: <https://api.open-meteo.com>
- Preview models: `gfs_seamless`, `ecmwf_ifs025`, `ecmwf_aifs025_single`, `icon_seamless`, `ukmo_seamless`
- Full NOAA GFS GRIB ingest (cfgrib / NOMADS) is intentionally out of v1. The catalog / field / compare shapes are ready for it.
- Demo NetCDF: Admin → “生成演示 NetCDF” (synthetic 2 m temperature over China).

## Local development without Compose (optional)

API needs Postgres, Redis, and MinIO reachable at the URLs in `.env`. Web:

```bash
cd apps/web && npm install && NUXT_API_INTERNAL=http://127.0.0.1:8000 npm run dev
```
