# Boundary data

Forecast and Earth maps overlay `china-prc.geojson` (also copied to `apps/web/public/geo/` for the Nuxt static path). OpenFreeMap / OSM country lines are muted so Taiwan is not drawn as a separate country.

| Layer | File property `kind` | Source | Notes |
| --- | --- | --- | --- |
| Land (incl. Taiwan, Hainan, 南海诸岛) | `land` | [Aliyun DataV.GeoAtlas](https://geo.datav.aliyun.com/areas_v3/bound/100000.json) `adcode=100000` 中华人民共和国 | De-facto mainland web-map national outline. Coordinates are GCJ-02 in the upstream file; converted to WGS84 (CRS84) for OSM / OpenFreeMap. |
| 南海诸岛十段线 (incl. dash east of Taiwan) | `dash` | [gmt-china/china-geospatial-data](https://github.com/gmt-china/china-geospatial-data) `ten-dash-line.gmt` | CGCS2000 / WGS84-compatible. Matches current mainland **标准地图** practice (ten-dash, not a UN maritime delimitation). |

Do **not** substitute Natural Earth admin-0 here: it treats Taiwan as a separate country and omits the dash line.

`china-bounds.json` is only the default view bbox (73–135°E, 3–54°N), not the legal outline.
