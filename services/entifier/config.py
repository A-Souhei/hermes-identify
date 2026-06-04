from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://entifier:entifier@postgres:5432/entifier"
    qdrant_url: str = "http://qdrant:6333"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"
    firecrawl_url: str = ""
    minio_url: str = "http://minio:9000"
    minio_access_key: str = "entifier"
    minio_secret_key: str = "entifier123"
    minio_bucket: str = "entifier-files"


settings = Settings()
