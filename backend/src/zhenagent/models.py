from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ModelConfig(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    label: str = Field(default="", max_length=200)
    reasoning_effort: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{0,49}$")
    max_output_tokens: int | None = Field(default=None, ge=1)
    context_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)

    @field_validator("id")
    @classmethod
    def strip_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("模型 ID 不能为空")
        return value


class ProviderInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=2048)
    models: list[ModelConfig] = Field(min_length=1, max_length=100)
    api_key: str | None = Field(default=None, max_length=10000)
    catalog_provider_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("服务名称不能为空")
        return value

    @field_validator("base_url")
    @classmethod
    def clean_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        url = urlsplit(value)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("请输入不含凭证、查询参数的 HTTP(S) 服务地址")
        if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("远程服务地址必须使用 HTTPS")
        if value.endswith("/responses"):
            raise ValueError("填写 base_url，不要包含末尾的 /responses")
        return value

    @model_validator(mode="after")
    def unique_models(self):
        ids = [model.id for model in self.models]
        if len(set(ids)) != len(ids):
            raise ValueError("模型 ID 不能重复")
        return self


class SessionInput(BaseModel):
    provider_id: str
    model_id: str
    title: str = Field(default="新会话", min_length=1, max_length=100)


class RunInput(BaseModel):
    text: str = Field(min_length=1, max_length=50000)
    client_request_id: str = Field(min_length=1, max_length=100)

    @field_validator("text")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("消息不能为空")
        return value


class ApprovalInput(BaseModel):
    approve: bool


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListDirectory(ToolArgs):
    path: str = "."


class ReadFile(ToolArgs):
    path: str
    start_line: int = Field(default=1, ge=1)
    end_line: int = Field(default=200, ge=1)

    @model_validator(mode="after")
    def line_range(self):
        if self.end_line < self.start_line:
            raise ValueError("结束行不能小于开始行")
        return self


class SearchFiles(ToolArgs):
    pattern: str = Field(min_length=1, max_length=500)
    path: str = "."


class WriteFile(ToolArgs):
    path: str
    content: str = Field(max_length=1048576)


class EditFile(ToolArgs):
    path: str
    old_text: str = Field(min_length=1, max_length=1048576)
    new_text: str = Field(max_length=1048576)


class ExecuteCommand(ToolArgs):
    command: str = Field(min_length=1, max_length=10000)


class SessionRename(BaseModel):
    title: str = Field(min_length=1, max_length=100, pattern=r"\S")
