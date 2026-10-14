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

Both (typical after forecast / globe / field-grid changes):

```bash
docker compose up -d --build api worker web
```

Caddy still fronts the stack at `:8765`. No need to rebuild postgres / redis / minio / caddy unless their configs changed.

### Mac Docker notes

From the repo root (Apple Silicon and Intel both work with Compose). After pulling this change, rebuild **api + web** (and worker if you run the cache warmer) so the new border GeoJSON styling, particle seeding, and Open-Meteo throttle land:

```bash
# from the AetherWatch repo root
docker compose up -d --build api worker web
```

Caddy still fronts the stack at `:8765`. No need to rebuild postgres / redis / minio / caddy unless their configs changed.

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765).

- Earth: PRC land outline + 南海诸岛十段线 should be a **bright gold highlight** on the globe (above particles / overlays).
- Forecast: the same borders are a **vermillion highlight** above the heatmap.
- Currents particles should seed across Pacific / Atlantic / Indian / Southern / China seas — not pile up only in 南海.

Field / current grids are cached in Redis. After a density or cache-schema change, flush so you do not keep an old payload:

```bash
docker compose exec redis redis-cli FLUSHDB
```

Cache keys are versioned (`field:v4:`, `currents:v3:`, `wind:v2:`). A flush is only needed if you still see a stale overlay. If Open-Meteo 429s on a cold cache, wait — the API will back off, serve last-good Redis data when it has any, and fill the live key on the next success. Do **not** raise `OPEN_METEO_CONCURRENCY` above 1 on a laptop deploy.

## 中文速览

```bash
docker compose up --build
```

浏览器打开 `http://127.0.0.1:8765`。导航：地球 / 预报 / 资讯 / 动态 / 关于 / 管理。

- 地球页默认 **洋流**（Open-Meteo Marine 表层流），可切到 **风场** 与气温 / 气压 / 降水；模式芯片会跟着要素换成 Marine/SMOC 或 GFS/IFS。
- 预报页多图 **镜头联动**（滚轮缩放 / 拖动平移同步），单击格点拉序列；时效 +0h～+120h，可播放。时间序列来自 Open-Meteo（GFS / IFS / AIFS 等）。
- 中国空间场默认约 **20×15** 点采样（可用 `FIELD_NX` / `FIELD_NY` 加密；默认偏向 Open-Meteo 限流稳定），预报图预滤波 + 双三次插值；每张图标 **起报 / 有效** 时刻与 Open-Meteo 模式 id。国界为 DataV 中国国界（含台湾、南海诸岛）+ gmt-china 十段线，**虚线**叠在场之上。
- 地球洋流粒子按洋盆播种（太平洋 / 大西洋 / 印度洋 / 南大洋 + 中国近海轻量嵌套），不再只堆在南海；气温 / 气压 / 降水是半透明插值场，不是整球单色。
- Open-Meteo 拉取默认 **concurrency=1**、小批次、请求间隔与指数退避；优先 Redis 缓存，禁止连打免费接口。
- 管理页可上传 NetCDF；`NcIngestActor` 解析，`NcTileActor` 产出一张二维场给地图。u/v 洋流 NetCDF 会出现在地球页洋流模式里。
- 公开源失败时地球粒子回落合成场，来源行会标明「合成场」。

## Layout

```
apps/web     Nuxt 3 + MapLibre (WebGL particle layer on globe)
apps/api     FastAPI + Taskiq actors
content/news seeded Markdown
content/geo  PRC land + 十段线 GeoJSON (see content/geo/README.md)
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

Defaults prefer **Open-Meteo stability over dense grids** (not the 64×48 / 36×18 sampling):

1. **Prefer cache** — Redis live key first, then a longer-lived `:last` copy. Live fetches only run on a miss.
2. **concurrency=1** — one in-flight Open-Meteo request for the whole process (API and worker share the same defaults).
3. **Small batches + gap** — 40 locations per POST, ≥0.75s between calls.
4. **Exponential backoff** — 429 / 5xx wait `2^attempt` seconds (plus jitter, cap 45s) and honor `Retry-After`. Never tight-loop.
5. Forecast maps load models **one after another** so a compare view does not enqueue four full grids at once.

| Variable | Default | What |
| --- | --- | --- |
| `FIELD_NX` / `FIELD_NY` | `20` / `15` | China `/api/field` sample grid. Raise if you have quota. |
| `CURRENT_NX` / `CURRENT_NY` | `16` / `8` | Global current u/v grid (land cells skipped). |
| `OPEN_METEO_BATCH_SIZE` | `40` | Locations per Open-Meteo request (POST body). Hard-capped at 80. |
| `OPEN_METEO_CONCURRENCY` | `1` | Shared parallel Open-Meteo batches. Keep at 1. |
| `OPEN_METEO_MIN_INTERVAL_SECONDS` | `0.75` | Minimum gap between outbound Open-Meteo calls. |
| `CACHE_TTL_SECONDS` | `21600` | Live Redis TTL for series / China fields (6h). |
| `WIND_CACHE_TTL_SECONDS` | `21600` | Live TTL for `/api/wind`. |
| `CURRENT_CACHE_TTL_SECONDS` | `21600` | Live TTL for `/api/currents`. |
| `CATALOG_CACHE_TTL_SECONDS` | `3600` | Redis TTL for `/api/catalog`. |
| `LAST_GOOD_TTL_SECONDS` / `OPEN_METEO_STALE_TTL_SECONDS` | `604800` | Last-good payload kept 7d; served on upstream 429. |
| `OPEN_METEO_BASE` | `https://api.open-meteo.com` | Forecast API. |
| `OPEN_METEO_MARINE_BASE` | `https://marine-api.open-meteo.com` | Marine / currents API. |

`/api/field` still accepts `nx`/`ny` query overrides (`4–96` / `4–72`). Forecast maps omit them so the env defaults apply. Globe scalar overlay requests a coarser global `16×10` and paints it with a WebGL interpolated layer (transparent where empty / dry).

### Cache, last-good, prewarm

- Live keys expire at the TTLs above. A successful fetch also writes `*:last` (7 days).
- On Open-Meteo **429 / sparse / empty**, endpoints return the last-good payload (`stale: true`) instead of failing.
- API **first-idle prewarm** (≈2s after startup) serializes default **currents**, **wind 20×10**, and **China field 20×15**.
- `POST /api/admin/cache/flush` (admin token) drops **live** keys only, keeps last-good, and schedules prewarm after **15s**.

Each field payload includes `init_time` (Open-Meteo hourly[0], 起报), `valid_time` (hourly[step], 有效), `model_id`, and `kind=model_forecast`. Current grids also carry a China-seas nest (`105–132°E`, `3–41°N`) used for local detail, not for dumping every particle into 南海.

PRC borders: see `content/geo/README.md`. Land + **十段线** use a **dashed** stroke (not a thicker solid OSM admin line). OpenFreeMap admin lines are muted so Taiwan is not shown as a separate country.

## Local development without Compose (optional)

API needs Postgres, Redis, and MinIO reachable at the URLs in `.env`. Web:

```bash
cd apps/web && npm install && NUXT_API_INTERNAL=http://127.0.0.1:8000 npm run dev
```
