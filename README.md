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

From the repo root (Apple Silicon and Intel both work with Compose). After pulling this change, rebuild **api + web** (and worker if you run the cache warmer) so OSCAR/CMEMS current sources, sheet particles, and forecast overlays land:

```bash
# from the AetherWatch repo root
docker compose up -d --build api worker web
```

Caddy still fronts the stack at `:8765`. No need to rebuild postgres / redis / minio / caddy unless their configs changed.

Then **hard-refresh** the browser (⌘⇧R / Ctrl+Shift+R) and open [http://127.0.0.1:8765](http://127.0.0.1:8765).

- Earth: continents should be a **slate land fill** (Natural Earth 110m, not black holes over China / SE Asia). Ocean / background is `#071624`. PRC land outline + 南海诸岛十段线 should be a **solid 观潮 orange** stroke (`rgba(255,186,92,0.95)`, ~1.4px; 十段线 is short geometry segments).
- Earth overlays: **洋流** = wave-period heatmap (blue→green→yellow→red) + current sheets; **风场** = wind-speed heatmap + particles; **气温 / 气压 / 降水** = filled scalar field (not a bare basemap). Click **earth** (bottom-left) to collapse the control panel.
- Forecast: maps should paint from Redis **20×15** without sitting on 「加载中」. IFS/AIFS 429 must not block GFS. Borders are a **thick dark solid** (~2px) above the heatmap, plus **起报 / 有效 … 北京时**.
- Currents particles should read as overlapping faded sheets across Pacific / Atlantic / Indian / Southern / China seas — not pile up only in 南海, and not draw on land.

Field / current grids are cached in Redis (`field:v4:`, `currents:v4:`, `wind:v2:`, `globe-fields:v1:`, `waves:v1:`) plus a 7-day last-good copy. **No Redis flush is required** for this deploy. Daily OSCAR/CMEMS fields also land in MinIO (`currents/oscar-v2/`, `currents/cmems-phy/`) and `/tmp/aetherwatch-currents`. If Open-Meteo 429s on a cold cache, wait — the API backs off and serves last-good. Do **not** raise `OPEN_METEO_CONCURRENCY` above 1 on a laptop deploy.

## 中文速览

```bash
docker compose up --build
```

浏览器打开 `http://127.0.0.1:8765`。导航：地球 / 预报 / 资讯 / 动态 / 关于 / 管理。

- 地球页默认 **洋流**：浪场周期色斑（蓝→绿→黄→红）+ 片状洋流粒子；可切到 **风场**（风速色斑 + 粒子）与气温 / 气压 / 降水色斑。左下 **earth** 可收起控制台。模式芯片会跟着要素换成 Auto/OSCAR/CMEMS/SMOC 或 GFS/IFS。
- 预报页多图 **镜头联动**（滚轮缩放 / 拖动平移同步），单击格点拉序列；时效 +0h～+120h，可播放。空间场直接走默认 **20×15** Redis 缓存（不再另打 8×6）。某一模式 429 时其余图照常出图。时间序列来自 Open-Meteo（GFS / IFS / AIFS 等）。
- 中国空间场默认约 **20×15** 点采样（可用 `FIELD_NX` / `FIELD_NY` 加密；默认偏向 Open-Meteo 限流稳定），预报图客户端 **双线性** 加密成连续色斑图；每张图标 **起报 / 有效** 时刻与 Open-Meteo 模式 id。国界为 DataV 中国国界（含台湾、南海诸岛）实线 + gmt-china 十段线（短几何段），地球页橙实线、预报页深色实线。
- 地球洋流粒子按洋盆播种（太平洋 / 大西洋 / 印度洋 / 南大洋 + 中国近海轻量嵌套），不再只堆在南海；气温 / 气压 / 降水是全球 16×10 插值色斑（启动预热写入 Redis），不是空底图。陆地用仓库内 Natural Earth 110m 多边形填色，OpenFreeMap 暗色底图失败时回落本地海洋底图，避免中国 / 东南亚大块黑斑。
- Open-Meteo 拉取默认 **concurrency=1**、小批次、请求间隔与指数退避；优先 Redis 缓存，禁止连打免费接口。
- 管理页可上传 NetCDF；`NcIngestActor` 解析，`NcTileActor` 产出一张二维场给地图。u/v 洋流 NetCDF 会出现在地球页洋流模式里。
- 公开源失败时地球粒子回落合成场，来源行会标明「合成场」。

## Layout

```
apps/web     Nuxt 3 + MapLibre (WebGL particle layer on globe)
apps/api     FastAPI + Taskiq actors
content/news seeded Markdown
content/geo  PRC land + 十段线 + globe NE 110m land fill (see content/geo/README.md)
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
- Open-Meteo Marine (currents fallback): <https://marine-api.open-meteo.com> — `ocean_current_velocity` + `ocean_current_direction`
- OSCAR v2.0 NRT (preferred currents): NASA PO.DAAC `OSCAR_L4_OC_NRT_V2.0` via Earthdata. Not scraped from any visualization CDN.
- CMEMS Global Ocean Physics Analysis and Forecast (DOI [10.48670/moi-00016](https://doi.org/10.48670/moi-00016)), dataset `cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m` (`uo`/`vo`).
- Preview models: `gfs_seamless`, `ecmwf_ifs025`, `ecmwf_aifs025_single`, `icon_seamless`, `ukmo_seamless`
- Current models: `best_match` (OSCAR → CMEMS → Marine), `oscar_v2`, `cmems_glo_phy`, `meteofrance_currents` (SMOC / OM)
- Full NOAA GFS GRIB ingest (cfgrib / NOMADS) is intentionally out of v1.
- Demo NetCDF: Admin → “生成演示 NetCDF” (T2m) or “生成演示洋流 NetCDF” (`uo`/`vo`).

## Env knobs (rate-limit / density)

Defaults prefer **Open-Meteo stability over dense grids** (not the 64×48 / 36×18 sampling):

1. **Prefer cache** — Redis live key first, then a longer-lived `:last` copy. Live fetches only run on a miss.
2. **concurrency=1** — one in-flight Open-Meteo request for the whole process (API and worker share the same defaults).
3. **Small batches + gap** — 40 locations per POST, ≥0.75s between calls.
4. **Short 429 then last-good** — at most 2 attempts, cap 8s (honors `Retry-After` up to the cap). Then serve Redis `:last` instead of waiting minutes.
5. Forecast requests the default **20×15** grid (omit `nx`/`ny`) so it hits the same `field:v4` keys prewarm writes. One model failing must not spin the whole page.

| Variable | Default | What |
| --- | --- | --- |
| `FIELD_NX` / `FIELD_NY` | `20` / `15` | China `/api/field` sample grid. Raise if you have quota. |
| `CURRENT_NX` / `CURRENT_NY` | `16` / `8` | Open-Meteo Marine fallback grid (land cells skipped). Do not raise live. |
| `CURRENT_SOURCE_NX` / `CURRENT_SOURCE_NY` | `36` / `18` | Resample size for cached OSCAR/CMEMS daily fields (one file, not OM). |
| `WIND_NX` / `WIND_NY` | `20` / `10` | Global wind u/v grid. Client bilinear-upsamples; do not raise live. |
| `OPEN_METEO_BATCH_SIZE` | `40` | Locations per Open-Meteo request (POST body). Hard-capped at 80. |
| `OPEN_METEO_CONCURRENCY` | `1` | Shared parallel Open-Meteo batches. Keep at 1. |
| `OPEN_METEO_MIN_INTERVAL_SECONDS` | `0.75` | Minimum gap between outbound Open-Meteo calls. |
| `CACHE_TTL_SECONDS` | `21600` | Live Redis TTL for series / China fields (6h). |
| `WIND_CACHE_TTL_SECONDS` | `21600` | Live TTL for `/api/wind`. |
| `CURRENT_CACHE_TTL_SECONDS` | `21600` | Live TTL for `/api/currents`. |
| `CURRENT_SOURCE_CACHE_TTL_SECONDS` | `86400` | Daily OSCAR/CMEMS field cache (Redis + object/local). |
| `CATALOG_CACHE_TTL_SECONDS` | `3600` | Redis TTL for `/api/catalog`. |
| `LAST_GOOD_TTL_SECONDS` / `OPEN_METEO_STALE_TTL_SECONDS` | `604800` | Last-good payload kept 7d; served on upstream 429. |
| `OPEN_METEO_BASE` | `https://api.open-meteo.com` | Forecast API. |
| `OPEN_METEO_MARINE_BASE` | `https://marine-api.open-meteo.com` | Marine / currents fallback. |
| `CURRENT_SOURCE` | `auto` | `auto` = OSCAR then CMEMS then OM. Or `oscar` / `cmems` / `open-meteo`. |
| `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` | _(empty)_ | NASA Earthdata login for OSCAR v2.0. |
| `EARTHDATA_TOKEN` | _(empty)_ | Alternative to username/password (URS bearer). |
| `OSCAR_SHORT_NAME` | `OSCAR_L4_OC_NRT_V2.0` | PO.DAAC short name. |
| `CMEMS_USERNAME` / `CMEMS_PASSWORD` | _(empty)_ | Copernicus Marine account. |
| `CMEMS_TOKEN` | _(empty)_ | Alternative OIDC / toolbox token. |
| `COPERNICUSMARINE_SERVICE_USERNAME` / `PASSWORD` | _(empty)_ | Official toolbox env aliases. |
| `CMEMS_DATASET_ID` | `cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m` | Daily surface uo/vo. |

OSCAR and CMEMS keys stay in `.env` (compose interpolates them). Never commit secrets. Without keys the globe still runs on cached last-good or Open-Meteo Marine. Optional: `pip install copernicusmarine` in the API image enables the official CMEMS ARCO client.

`/api/field` still accepts `nx`/`ny` query overrides (`4–96` / `4–72`). Forecast omits them so it uses `FIELD_NX`×`FIELD_NY` (**20×15**) and hits Redis. Globe scalars (`气温` / `气压` / `降水`) use global `−180…180 / −70…70` at **16×10** (`/api/globe-fields`, one Open-Meteo pass for all three, written through to `field:v4:`). Idle prewarm covers those globe keys **and** China-bbox GFS + IFS + AIFS temperature / pressure / precip so a cold Forecast / Earth page does not stampede into 429. Wave-period underlay is `/api/waves` (piggybacked on OM marine currents when that path runs).

### Cache, last-good, prewarm

- Live keys expire at the TTLs above. A successful fetch also writes `*:last` (7 days).
- On Open-Meteo **429 / sparse / empty**, endpoints return the last-good payload (`stale: true`) after a short retry instead of blocking for minutes. China `/api/field` never raises a bare 500: last-good first, else an empty grid with `error` / `unavailable` so the forecast card can show 暂无数据/限流.
- `/api/globe-fields` on 429 prefers existing `field:v4` global grids over `synthetic:open-meteo-429`.
- API **first-idle prewarm** (≈2s after startup) serializes **China 20×15 气温/气压/降水 for GFS + IFS + AIFS** with a gap between models. A 429 skips the remaining models that pass, then **retries with exponential backoff** until live+last `field:v4` keys land. Currents (OSCAR/CMEMS) still run; globe/wind/waves wait if OM is hot. Forecast header spinner clears as soon as any model paints; a single 429 shows a per-card error/retry instead of freezing 「加载中」.
- `POST /api/admin/cache/flush` (admin token) drops **live** keys only, keeps last-good, and schedules prewarm after **15s**.
- Daily OSCAR/CMEMS NetCDF-derived fields are also stored under MinIO `currents/` and `/tmp/aetherwatch-currents` so a Redis miss does not re-hit upstream.

Each field payload includes `init_time` (Open-Meteo hourly[0], 起报), `valid_time` (hourly[step], 有效), `model_id`, and `kind=model_forecast`. Current grids also carry a China-seas nest (`105–132°E`, `3–41°N`) used for local detail, not for dumping every particle into 南海.

PRC borders: see `content/geo/README.md`. Land is a **solid** stroke; **十段线** is the same color drawn as discrete GeoJSON segments (not `line-dasharray`). OpenFreeMap country lines are muted so Taiwan is not shown as a separate country; province lines stay and are restyled solid.

## Local development without Compose (optional)

API needs Postgres, Redis, and MinIO reachable at the URLs in `.env`. Web:

```bash
cd apps/web && npm install && NUXT_API_INTERNAL=http://127.0.0.1:8000 npm run dev
```
