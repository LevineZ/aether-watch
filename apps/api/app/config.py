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
    news_dir: str = "/content/news"
    geo_dir: str = "/content/geo"
    content_dir: str = "/content"
    cache_ttl_seconds: int = 1800
    wind_cache_ttl_seconds: int = 3600


settings = Settings()
