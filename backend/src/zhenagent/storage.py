import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class Secrets:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "secrets.json"
        self.keys: dict[str, str] = {}

    def load(self):
        if self.path.exists():
            if self.path.is_symlink():
                raise ValueError("密钥文件不能是符号链接")
            os.chmod(self.path, 0o600)
            self.keys = json.loads(self.path.read_text())

    def get(self, provider_id: str) -> str:
        return self.keys.get(provider_id, "")

    def set(self, provider_id: str, value: str | None):
        updated = dict(self.keys)
        if value is None:
            updated.pop(provider_id, None)
        else:
            updated[provider_id] = value
        descriptor, filename = tempfile.mkstemp(dir=self.directory, prefix=".secrets-")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(encode(updated))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(filename, self.path)
            self.keys = updated
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def redact(self, text: str) -> str:
        for key in self.keys.values():
            if key:
                text = text.replace(key, "[密钥已隐藏]")
        return text


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.lock = asyncio.Lock()
        self.db: aiosqlite.Connection | None = None

    async def open(self):
        self.db = await aiosqlite.connect(self.path)
        os.chmod(self.path, 0o600)
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS providers (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, base_url TEXT NOT NULL, models TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, provider_id TEXT NOT NULL REFERENCES providers(id),
                model_id TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                client_request_id TEXT NOT NULL, input_text TEXT NOT NULL, status TEXT NOT NULL,
                error TEXT, call_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(session_id, client_request_id)
            );
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id),
                run_id TEXT NOT NULL REFERENCES runs(id), body TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), round INTEGER NOT NULL,
                attempt INTEGER NOT NULL, status TEXT NOT NULL, text TEXT NOT NULL DEFAULT '',
                error TEXT, usage TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tools (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), call_id TEXT NOT NULL,
                name TEXT NOT NULL, arguments TEXT NOT NULL, status TEXT NOT NULL, round INTEGER NOT NULL,
                preview TEXT, result TEXT, error TEXT, approval_status TEXT,
                UNIQUE(run_id, call_id)
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
                type TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS events_run ON events(run_id, id);
            CREATE INDEX IF NOT EXISTS items_session ON items(session_id, id);
        """)
        await self.db.commit()

    async def close(self):
        if self.db:
            await self.db.close()

    async def execute(self, sql: str, values=()):
        async with self.lock:
            await self.db.execute(sql, values)
            await self.db.commit()

    async def rows(self, sql: str, values=()) -> list[dict]:
        async with self.lock:
            async with self.db.execute(sql, values) as cursor:
                return [dict(row) for row in await cursor.fetchall()]

    async def one(self, sql: str, values=()) -> dict | None:
        rows = await self.rows(sql, values)
        return rows[0] if rows else None

    async def context(self, session_id: str) -> list[dict]:
        return [json.loads(row["body"]) for row in await self.rows(
            "SELECT body FROM items WHERE session_id=? ORDER BY id", (session_id,)
        )]

    async def add_items(self, session_id: str, run_id: str, items: list[dict]):
        async with self.lock:
            await self.db.executemany(
                "INSERT INTO items(session_id,run_id,body) VALUES(?,?,?)",
                [(session_id, run_id, encode(item)) for item in items],
            )
            await self.db.commit()

    async def event(self, run_id: str, kind: str, data: dict):
        async with self.lock:
            cursor = await self.db.execute(
                "INSERT INTO events(run_id,type,data,created_at) VALUES(?,?,?,?)",
                (run_id, kind, encode(data), now()),
            )
            await self.db.commit()
            return cursor.lastrowid

    async def run_status(self, run_id: str, status: str, error: str | None = None):
        await self.execute("UPDATE runs SET status=?,error=?,updated_at=? WHERE id=?", (status, error, now(), run_id))
        await self.event(run_id, "run.status", {"status": status, "error": error})

    async def reconcile(self, session_id: str, run_id: str, reason: str):
        context = await self.context(session_id)
        outputs = {item.get("call_id") for item in context if item.get("type") == "function_call_output"}
        pending = [item for item in context if item.get("type") == "function_call" and item.get("call_id") not in outputs]
        if pending:
            await self.add_items(session_id, run_id, [
                {"type": "function_call_output", "call_id": item["call_id"], "output": encode({"error": reason})}
                for item in pending
            ])
        await self.execute(
            "UPDATE tools SET status='interrupted',error=?,approval_status=CASE WHEN approval_status='pending' THEN 'expired' ELSE approval_status END WHERE run_id=? AND status IN ('pending','running','awaiting_approval')",
            (reason, run_id),
        )

    async def recover(self):
        for run in await self.rows("SELECT * FROM runs WHERE status IN ('running','awaiting_approval')"):
            reason = "后端已重启，任务中断；已发生的操作不会回滚"
            await self.reconcile(run["session_id"], run["id"], reason)
            await self.run_status(run["id"], "interrupted", reason)
        await self.execute("UPDATE attempts SET status='interrupted',error='后端已重启' WHERE status='running'")
