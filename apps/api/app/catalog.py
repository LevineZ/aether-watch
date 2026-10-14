"""Preview model catalog — Open-Meteo ids used for live series/field."""

from typing import Any

PREVIEW_MODELS: list[dict[str, Any]] = [
    {
        "id": "gfs_seamless",
        "short": "GFS",
        "name": "NOAA GFS Seamless",
        "agency": "NCEP",
        "kind": "preview",
        "source": "open-meteo",
        "color": "#c1440e",
        "resolution": "13–25 km",
        "notes": "Global forecast; HRRR nested over CONUS.",
    },
    {
        "id": "ecmwf_ifs025",
        "short": "IFS",
        "name": "ECMWF IFS 0.25°",
        "agency": "ECMWF",
        "kind": "preview",
        "source": "open-meteo",
        "color": "#1d4e89",
        "resolution": "25 km",
        "notes": "Open-data IFS; interpolated to hourly.",
    },
    {
        "id": "ecmwf_aifs025_single",
        "short": "AIFS",
        "name": "ECMWF AIFS Single",
        "agency": "ECMWF",
        "kind": "preview",
        "source": "open-meteo",
        "color": "#b45309",
        "resolution": "28 km",
        "notes": "AI forecast system; native 6-hourly.",
    },
    {
        "id": "icon_seamless",
        "short": "ICON",
        "name": "DWD ICON Seamless",
        "agency": "DWD",
        "kind": "preview",
        "source": "open-meteo",
        "color": "#3f6f4e",
        "resolution": "2–13 km",
        "notes": "Global + EU nest where available.",
    },
    {
        "id": "ukmo_seamless",
        "short": "UKMO",
        "name": "UK Met Office Seamless",
        "agency": "UKMO",
        "kind": "preview",
        "source": "open-meteo",
        "color": "#6b3fa0",
        "resolution": "10–17 km",
        "notes": "Global + UK nest.",
    },
]

PREVIEW_BY_ID = {m["id"]: m for m in PREVIEW_MODELS}

# Current chips. best_match tries OSCAR v2 → CMEMS → Open-Meteo Marine.
CURRENT_MODELS: list[dict[str, Any]] = [
    {
        "id": "best_match",
        "short": "Auto",
        "name": "OSCAR / CMEMS / Marine auto",
        "agency": "AetherWatch",
        "kind": "currents",
        "source": "auto",
        "color": "#1d6a7a",
        "resolution": "0.25° / 0.083° / OM",
        "notes": "OSCAR v2.0 then CMEMS PHY 001-024, Open-Meteo Marine fallback.",
    },
    {
        "id": "oscar_v2",
        "short": "OSCAR",
        "name": "OSCAR v2.0 NRT",
        "agency": "NASA / ESR",
        "kind": "currents",
        "source": "oscar-v2",
        "color": "#0e7490",
        "resolution": "0.25° daily",
        "notes": "PO.DAAC OSCAR_L4_OC_NRT_V2.0. Needs Earthdata token or user/pass.",
    },
    {
        "id": "cmems_glo_phy",
        "short": "CMEMS",
        "name": "CMEMS Global Ocean Physics",
        "agency": "Mercator / CMEMS",
        "kind": "currents",
        "source": "cmems",
        "color": "#155e75",
        "resolution": "0.083° daily",
        "notes": "DOI 10.48670/moi-00016. Needs CMEMS username/password or token.",
    },
    {
        "id": "meteofrance_currents",
        "short": "SMOC",
        "name": "Météo-France SMOC Currents",
        "agency": "Météo-France",
        "kind": "currents",
        "source": "open-meteo-marine",
        "color": "#0f766e",
        "resolution": "0.08°",
        "notes": "Eulerian currents via Open-Meteo Marine (fallback path).",
    },
]
CURRENT_BY_ID = {m["id"]: m for m in CURRENT_MODELS}

GLOBE_ELEMENTS: list[dict[str, Any]] = [
    {
        "id": "ocean_current",
        "label": "洋流",
        "label_en": "Ocean current",
        "unit": "m/s",
        "kind": "vector",
        "endpoint": "currents",
        "palette": "current",
        "om": "ocean_current_velocity",
    },
    {
        "id": "wind_speed_10m",
        "label": "风场",
        "label_en": "10 m wind",
        "unit": "m/s",
        "kind": "vector",
        "endpoint": "wind",
        "palette": "wind",
        "om": "wind_speed_10m",
    },
    {
        "id": "temperature_2m",
        "label": "气温",
        "label_en": "2 m temperature",
        "unit": "°C",
        "kind": "scalar",
        "endpoint": "field",
        "palette": "thermal",
        "om": "temperature_2m",
    },
    {
        "id": "surface_pressure",
        "label": "气压",
        "label_en": "surface pressure",
        "unit": "hPa",
        "kind": "scalar",
        "endpoint": "field",
        "palette": "pressure",
        "om": "surface_pressure",
    },
    {
        "id": "precipitation",
        "label": "降水",
        "label_en": "hourly precipitation",
        "unit": "mm",
        "kind": "scalar",
        "endpoint": "field",
        "palette": "rain",
        "om": "precipitation",
    },
]
GLOBE_ELEMENT_BY_ID = {e["id"]: e for e in GLOBE_ELEMENTS}

ELEMENTS: list[dict[str, Any]] = [
    {
        "id": "temperature_2m",
        "label": "2 米气温",
        "label_en": "2 m temperature",
        "unit": "°C",
        "om": "temperature_2m",
        "palette": "thermal",
    },
    {
        "id": "relative_humidity_2m",
        "label": "2 米相对湿度",
        "label_en": "2 m humidity",
        "unit": "%",
        "om": "relative_humidity_2m",
        "palette": "humidity",
    },
    {
        "id": "dew_point_2m",
        "label": "2 米露点",
        "label_en": "2 m dew point",
        "unit": "°C",
        "om": "dew_point_2m",
        "palette": "thermal",
    },
    {
        "id": "wind_speed_10m",
        "label": "10 米风速",
        "label_en": "10 m wind speed",
        "unit": "m/s",
        "om": "wind_speed_10m",
        "palette": "wind",
    },
    {
        "id": "wind_gusts_10m",
        "label": "10 米阵风",
        "label_en": "10 m gusts",
        "unit": "m/s",
        "om": "wind_gusts_10m",
        "palette": "wind",
    },
    {
        "id": "surface_pressure",
        "label": "海平面气压",
        "label_en": "surface pressure",
        "unit": "hPa",
        "om": "surface_pressure",
        "palette": "pressure",
    },
    {
        "id": "precipitation",
        "label": "小时降水",
        "label_en": "hourly precipitation",
        "unit": "mm",
        "om": "precipitation",
        "palette": "rain",
    },
    {
        "id": "cloud_cover",
        "label": "云量",
        "label_en": "cloud cover",
        "unit": "%",
        "om": "cloud_cover",
        "palette": "cloud",
    },
]

ELEMENT_BY_ID = {e["id"]: e for e in ELEMENTS}

# Full PRC frame including Taiwan and the South China Sea (南海诸岛).
CHINA_BBOX = {"west": 73.0, "south": 3.0, "east": 135.0, "north": 54.0}
CHINA_SEAS_BBOX = {"west": 105.0, "south": 3.0, "east": 132.0, "north": 41.0}
GLOBAL_BBOX = {"west": -180.0, "south": -78.0, "east": 180.0, "north": 78.0}

DEFAULT_POINT = {"name": "北京", "name_en": "Beijing", "lat": 39.9042, "lon": 116.4074}
