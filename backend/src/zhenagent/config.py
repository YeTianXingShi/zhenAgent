from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Limits(BaseModel):
    max_model_calls: int = Field(default=20, ge=1, le=200)
    command_timeout: int = Field(default=120, ge=1, le=3600)
    request_timeout: int = Field(default=180, ge=1, le=1800)
    max_retries: int = Field(default=2, ge=0, le=10)
    retry_delay: float = Field(default=1, ge=0.1, le=30)
    command_output_bytes: int = Field(default=1048576, ge=1024, le=16777216)
    model_output_bytes: int = Field(default=4194304, ge=1024, le=16777216)
    read_file_bytes: int = Field(default=262144, ge=1024, le=4194304)
    tool_context_bytes: int = Field(default=32768, ge=1024, le=262144)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ZHEN_", env_file=PROJECT_ROOT / ".env", extra="ignore"
    )
    workspace_root: Path = PROJECT_ROOT / "workspace"
    data_dir: Path = PROJECT_ROOT / ".local"
    frontend_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    def absolute(self, path: Path) -> Path:
        return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()

    @property
    def origins(self) -> list[str]:
        return [value.strip().rstrip("/") for value in self.frontend_origins.split(",") if value.strip()]
