from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aether:aether@postgres:5432/aetherwatch?ssl=disable"
    redis_url: str = "redis://redis:6379/0"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "aetherwatch"
    minio_secret_key: str = "aetherwatch_dev"
    minio_bucket: str = "aetherwatch"
    minio_secure: bool = False
    admin_token: str = "aether-dev"
    open_meteo_base: str = "https://api.open-meteo.com"
    open_meteo_marine_base: str = "https://marine-api.open-meteo.com"
    # OSCAR v2.0 (NASA Earthdata / PO.DAAC). Token or username+password; never commit secrets.
    earthdata_username: str = ""
    earthdata_password: str = ""
    earthdata_token: str = ""
    oscar_short_name: str = "OSCAR_L4_OC_NRT_V2.0"
    oscar_collection_id: str = "C2102958977-POCLOUD"
    # CMEMS Global Ocean Physics Analysis and Forecast (DOI 10.48670/moi-00016).
    # Accept CMEMS_* or COPERNICUSMARINE_SERVICE_* (toolbox env names).
    cmems_username: str = ""
    cmems_password: str = ""
    cmems_token: str = ""
    copernicusmarine_service_username: str = ""
    copernicusmarine_service_password: str = ""
    copernicusmarine_service_token: str = ""
    cmems_dataset_id: str = "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m"
    cmems_product_id: str = "GLOBAL_ANALYSISFORECAST_PHY_001_024"
    current_source: str = "auto"
    current_source_nx: int = 36
    current_source_ny: int = 18
    current_source_cache_ttl_seconds: int = 86400
    current_field_dir: str = "/tmp/aetherwatch-currents"
    news_dir: str = "/content/news"
    geo_dir: str = "/content/geo"
    content_dir: str = "/content"
    # Live Redis TTL. Prefer cache over another Open-Meteo round-trip.
    cache_ttl_seconds: int = 21600
    wind_cache_ttl_seconds: int = 21600
    current_cache_ttl_seconds: int = 21600
    catalog_cache_ttl_seconds: int = 3600
    last_good_ttl_seconds: int = 604800
    open_meteo_stale_ttl_seconds: int = 604800
    # Conservative grids: stability over density (main had 64×48 / 36×18).
    field_nx: int = 20
    field_ny: int = 15
    current_nx: int = 16
    current_ny: int = 8
    current_nest_nx: int = 16
    current_nest_ny: int = 12
    # Live wind stays coarse; the globe bilinear-upsamples. Raise only with quota.
    wind_nx: int = 20
    wind_ny: int = 10
    # Conservative Open-Meteo pacing. Keep concurrency=1 and leave gaps.
    open_meteo_batch_size: int = 40
    open_meteo_concurrency: int = 1
    open_meteo_min_interval_seconds: float = 0.75
    open_meteo_max_retries: int = 6
    open_meteo_backoff_base: float = 2.0
    open_meteo_backoff_cap_seconds: float = 45.0


settings = Settings()
