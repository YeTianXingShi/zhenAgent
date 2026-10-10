import asyncio
import json
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .agent import Agent, Conflict, TERMINAL
from .catalog import Catalog
from .config import Limits, Settings
from .models import ApprovalInput, ProviderInput, RunInput, SessionInput
from .responses import Responses, reasoning_text
from .storage import Secrets, Store, encode, new_id, now


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    workspace = settings.absolute(settings.workspace_root)
    directory = settings.absolute(settings.data_dir)
    if workspace.is_relative_to(directory):
        raise ValueError("工作目录不能位于 agent 私有数据目录内")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    workspace.mkdir(parents=True, exist_ok=True)
    secrets = Secrets(directory)
    secrets.load()
    store = Store(directory / "zhenagent.db")
    await store.open()
    await store.recover()
    saved = await store.one("SELECT value FROM config WHERE key='limits'")
    limits = Limits.model_validate_json(saved["value"]) if saved else Limits()
    async with httpx.AsyncClient(follow_redirects=False) as client:
        catalog = Catalog(client, directory)
        catalog.load()
        if catalog.stale():
            await catalog.refresh()
        if catalog.providers and not await store.one("SELECT value FROM config WHERE key='catalog_link_migration'"):
            for provider in await store.rows("SELECT * FROM providers WHERE catalog_provider_id IS NULL"):
                catalog_id = catalog.infer_provider(provider)
                if catalog_id:
                    await store.execute("UPDATE providers SET catalog_provider_id=? WHERE id=?", (catalog_id, provider["id"]))
            await store.execute("INSERT INTO config(key,value) VALUES('catalog_link_migration','1')")
        agent = Agent(store, secrets, Responses(client), workspace, directory, limits)
        app.state.settings = settings
        app.state.store = store
        app.state.secrets = secrets
        app.state.agent = agent
        app.state.catalog = catalog
        catalog_task = asyncio.create_task(catalog.maintain())
        try:
            yield
        finally:
            catalog_task.cancel()
            await asyncio.gather(catalog_task, return_exceptions=True)
            await agent.close()
            await store.close()


app = FastAPI(title="zhenAgent", version="0.1.0", lifespan=lifespan)
initial_settings = Settings()
app.add_middleware(CORSMiddleware, allow_origins=initial_settings.origins,
                   allow_methods=["GET", "POST", "PUT", "DELETE"],
                   allow_headers=["Content-Type", "Last-Event-ID"])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in initial_settings.origins:
        return JSONResponse({"detail": "不允许此页面来源访问本地 agent"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError):
    issues = [f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}" for issue in error.errors()]
    return JSONResponse({"detail": "；".join(issues)}, status_code=422)


@app.exception_handler(Conflict)
async def conflict(request: Request, error: Conflict):
    return JSONResponse({"detail": str(error)}, status_code=409)


def store() -> Store:
    return app.state.store


def safe(value):
    return json.loads(app.state.secrets.redact(encode(value)))


def provider_view(provider: dict) -> dict:
    return {**provider, "models": [app.state.catalog.resolve(provider, model) for model in json.loads(provider["models"])],
            "has_api_key": bool(app.state.secrets.get(provider["id"]))}


async def require_provider(provider_id: str) -> dict:
    value = await store().one("SELECT * FROM providers WHERE id=?", (provider_id,))
    if not value:
        raise HTTPException(404, "服务不存在")
    return value


async def require_session(session_id: str) -> dict:
    value = await store().one("SELECT * FROM sessions WHERE id=?", (session_id,))
    if not value:
        raise HTTPException(404, "会话不存在")
    return value


@app.get("/api/settings")
async def settings_view():
    agent = app.state.agent
    return {"workspace_root": str(agent.workspace), "limits": agent.limits.model_dump(),
            "active_run": {"id": agent.active.id} if agent.active else None}


@app.put("/api/settings")
async def change_limits(limits: Limits):
    await store().execute("INSERT INTO config(key,value) VALUES('limits',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (limits.model_dump_json(),))
    app.state.agent.limits = limits
    return await settings_view()


@app.get("/api/providers")
async def providers():
    return safe([provider_view(provider) for provider in await store().rows("SELECT * FROM providers ORDER BY name")])


@app.get("/api/model-catalog")
async def model_catalog():
    return app.state.catalog.summary()


@app.post("/api/model-catalog/refresh")
async def refresh_catalog():
    await app.state.catalog.refresh()
    return app.state.catalog.summary()


@app.get("/api/model-catalog/providers/{catalog_id}")
async def catalog_provider(catalog_id: str):
    provider = app.state.catalog.providers.get(catalog_id)
    if not provider:
        raise HTTPException(404, "Models.dev 缓存中没有该服务，请更新模型信息或使用手动配置")
    return {**provider, "models": list(provider["models"].values())}


@app.post("/api/providers", status_code=201)
async def add_provider(value: ProviderInput):
    provider_id = new_id()
    if value.api_key and value.api_key.strip():
        app.state.secrets.set(provider_id, value.api_key.strip())
    await store().execute("INSERT INTO providers(id,name,base_url,models,catalog_provider_id) VALUES(?,?,?,?,?)", (
        provider_id, value.name.strip(), value.base_url, encode([model.model_dump() for model in value.models]), value.catalog_provider_id,
    ))
    return safe(provider_view(await require_provider(provider_id)))


@app.put("/api/providers/{provider_id}")
async def update_provider(provider_id: str, value: ProviderInput):
    await require_provider(provider_id)
    referenced = await store().rows("SELECT DISTINCT model_id FROM sessions WHERE provider_id=?", (provider_id,))
    ids = {model.id for model in value.models}
    if any(row["model_id"] not in ids for row in referenced):
        raise Conflict("已有会话使用的模型不能移除；可另建一个服务配置")
    if value.api_key and value.api_key.strip():
        app.state.secrets.set(provider_id, value.api_key.strip())
    await store().execute("UPDATE providers SET name=?,base_url=?,models=?,catalog_provider_id=? WHERE id=?", (
        value.name.strip(), value.base_url, encode([model.model_dump() for model in value.models]), value.catalog_provider_id, provider_id,
    ))
    return safe(provider_view(await require_provider(provider_id)))


@app.delete("/api/providers/{provider_id}", status_code=204)
async def delete_provider(provider_id: str):
    await require_provider(provider_id)
    if await store().one("SELECT id FROM sessions WHERE provider_id=? LIMIT 1", (provider_id,)):
        raise Conflict("已有会话引用此服务，不能删除")
    await store().execute("DELETE FROM providers WHERE id=?", (provider_id,))
    app.state.secrets.set(provider_id, None)


@app.get("/api/sessions")
async def sessions():
    return await store().rows("""
        SELECT sessions.*,providers.name AS provider_name,
        (SELECT status FROM runs WHERE session_id=sessions.id ORDER BY created_at DESC LIMIT 1) AS last_status
        FROM sessions JOIN providers ON providers.id=sessions.provider_id ORDER BY updated_at DESC
    """)


@app.post("/api/sessions", status_code=201)
async def create_session(value: SessionInput):
    provider = await require_provider(value.provider_id)
    if value.model_id not in {model["id"] for model in json.loads(provider["models"])}:
        raise HTTPException(422, "模型不在该服务的配置中")
    session_id = new_id()
    timestamp = now()
    await store().execute("INSERT INTO sessions(id,title,provider_id,model_id,created_at,updated_at) VALUES(?,?,?,?,?,?)", (
        session_id, value.title, value.provider_id, value.model_id, timestamp, timestamp,
    ))
    return await require_session(session_id)


@app.get("/api/sessions/{session_id}")
async def session_detail(session_id: str):
    cursor = await store().one("SELECT COALESCE(MAX(id),0) AS id FROM events")
    session = await require_session(session_id)
    runs = await store().rows("SELECT * FROM runs WHERE session_id=? ORDER BY created_at", (session_id,))
    for run in runs:
        legacy = await store().rows("SELECT body FROM items WHERE run_id=? AND attempt_id IS NULL ORDER BY id", (run["id"],))
        run["legacy_reasoning"] = reasoning_text([json.loads(item["body"]) for item in legacy])
        run["attempts"] = await store().rows("SELECT * FROM attempts WHERE run_id=? ORDER BY round,attempt", (run["id"],))
        for attempt in run["attempts"]:
            attempt["usage"] = json.loads(attempt["usage"]) if attempt["usage"] else None
        run["tools"] = await store().rows("SELECT * FROM tools WHERE run_id=? ORDER BY rowid", (run["id"],))
        chunks = await store().rows("SELECT data FROM events WHERE run_id=? AND type='tool.output' ORDER BY id", (run["id"],))
        stdout: dict[str, str] = {}
        for row in chunks:
            chunk = json.loads(row["data"])
            stdout[chunk["id"]] = stdout.get(chunk["id"], "") + chunk["delta"]
        for tool in run["tools"]:
            for field in ("preview", "result"):
                tool[field] = json.loads(tool[field]) if tool[field] else None
            tool["live_output"] = stdout.get(tool["id"], "")
    return safe({**session, "runs": runs, "event_cursor": cursor["id"]})


@app.post("/api/sessions/{session_id}/runs", status_code=202)
async def start_run(session_id: str, value: RunInput):
    session = await require_session(session_id)
    provider = await require_provider(session["provider_id"])
    model = next((entry for entry in json.loads(provider["models"]) if entry["id"] == session["model_id"]), None)
    if not model:
        raise Conflict("会话使用的模型已不存在")
    resolved = app.state.catalog.resolve(provider, model)
    resolved["max_output_tokens"] = resolved["resolved_max_output_tokens"]
    resolved["context_tokens"] = resolved["resolved_context_tokens"]
    return await app.state.agent.start(session, value.text, value.client_request_id, provider, resolved)


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    await app.state.agent.cancel(run_id)
    return {"status": "stopped"}


@app.post("/api/approvals/{tool_id}")
async def approval(tool_id: str, value: ApprovalInput):
    await app.state.agent.approve(tool_id, value.approve)
    return {"status": "approved" if value.approve else "denied"}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, after: int = 0):
    if not await store().one("SELECT id FROM runs WHERE id=?", (run_id,)):
        raise HTTPException(404, "任务不存在")
    try:
        cursor = max(0, after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        raise HTTPException(422, "事件游标无效")

    async def stream():
        nonlocal cursor
        idle = 0
        while not await request.is_disconnected():
            rows = await store().rows("SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id LIMIT 200", (run_id, cursor))
            for row in rows:
                cursor = row["id"]
                value = safe({"type": row["type"], "data": json.loads(row["data"])})
                yield f"id: {cursor}\ndata: {encode(value)}\n\n"
            if len(rows) == 200:
                continue
            run = await store().one("SELECT status FROM runs WHERE id=?", (run_id,))
            if run["status"] in TERMINAL:
                yield "event: end\ndata: {}\n\n"
                return
            idle = 0 if rows else idle + 1
            if idle >= 60:
                yield ": heartbeat\n\n"
                idle = 0
            await asyncio.sleep(0.25)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})
