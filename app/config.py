from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    INVITE_CODE: str = "change-me"
    SECRET_KEY: str = "change-me"
    PORT: int = 8080
    TZ: str = "UTC"

    DATA_DIR: Path = Path("data")

    @property
    def db_path(self) -> Path:
        return self.DATA_DIR / "db" / "photoframe.db"

    @property
    def photos_dir(self) -> Path:
        return self.DATA_DIR / "photos"


settings = Settings()

for _subdir in ("original", "display", "thumb"):
    (settings.photos_dir / _subdir).mkdir(parents=True, exist_ok=True)
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
