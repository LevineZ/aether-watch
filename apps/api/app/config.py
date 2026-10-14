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
    news_dir: str = "/content/news"
    geo_dir: str = "/content/geo"
    content_dir: str = "/content"
    # Live Redis TTL. Raise these if Open-Meteo 429s after cache expiry.
    cache_ttl_seconds: int = 21600
    wind_cache_ttl_seconds: int = 21600
    current_cache_ttl_seconds: int = 21600
    catalog_cache_ttl_seconds: int = 3600
    last_good_ttl_seconds: int = 604800
    # China preview field sampling. 20×15 ≈ 3° over CHINA_BBOX (was 40×30).
    # Raise FIELD_NX/NY if you have headroom; lower further on 429s.
    field_nx: int = 20
    field_ny: int = 15
    current_nx: int = 16
    current_ny: int = 8
    open_meteo_batch_size: int = 40
    open_meteo_concurrency: int = 1
    open_meteo_max_retries: int = 4
    open_meteo_backoff_base: float = 1.5


settings = Settings()
