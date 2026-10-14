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
    cache_ttl_seconds: int = 1800
    wind_cache_ttl_seconds: int = 3600
    current_cache_ttl_seconds: int = 3600
    # China preview field sampling (Open-Meteo locations). 64×48 ≈ 1° over the full PRC frame.
    field_nx: int = 64
    field_ny: int = 48
    current_nx: int = 36
    current_ny: int = 18
    current_nest_nx: int = 36
    current_nest_ny: int = 28
    open_meteo_batch_size: int = 200
    open_meteo_concurrency: int = 4


settings = Settings()
