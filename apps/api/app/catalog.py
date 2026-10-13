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

CHINA_BBOX = {"west": 73.0, "south": 18.0, "east": 135.0, "north": 54.0}
GLOBAL_BBOX = {"west": -180.0, "south": -78.0, "east": 180.0, "north": 78.0}

DEFAULT_POINT = {"name": "北京", "name_en": "Beijing", "lat": 39.9042, "lon": 116.4074}
