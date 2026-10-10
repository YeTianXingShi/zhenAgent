import asyncio
import codecs
import difflib
import hashlib
import json
import os
import signal
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

from .config import Limits
from .models import EditFile, ExecuteCommand, ListDirectory, ReadFile, SearchFiles, WriteFile


TOOLS = {
    "list_directory": (ListDirectory, "列出工作目录内的文件和目录，最多返回 500 项。"),
    "read_file": (ReadFile, "按行读取 UTF-8 文件，可调整起止行；使用搜索缩小范围。"),
    "search_files": (SearchFiles, "在工作目录内按字面文本搜索 UTF-8 文件，返回文件名与行号。"),
    "write_file": (WriteFile, "新建或覆盖 UTF-8 文件，执行前需要用户批准差异。"),
    "edit_file": (EditFile, "将文件中唯一匹配的 old_text 替换为 new_text，执行前需要审批。"),
    "execute_command": (ExecuteCommand, "在工作目录执行本机 shell 命令，每次执行需要用户批准。"),
}


def definitions() -> list[dict]:
    return [{"type": "function", "name": name, "description": description,
             "parameters": model.model_json_schema(), "strict": False}
            for name, (model, description) in TOOLS.items()]


class ToolError(Exception):
    pass


class ToolRunner:
    def __init__(self, workspace: Path, data_dir: Path, limits: Limits):
        self.workspace = workspace
        self.data_dir = data_dir
        self.limits = limits

    def path(self, value: str) -> Path:
        original = Path(value)
        resolved = (original if original.is_absolute() else self.workspace / original).resolve()
        if not resolved.is_relative_to(self.workspace):
            raise ToolError("文件路径超出工作目录")
        if resolved.is_relative_to(self.data_dir):
            raise ToolError("不能访问 agent 的私有数据目录")
        return resolved

    def validate(self, name: str, raw: str):
        if name not in TOOLS:
            raise ToolError(f"未知工具：{name}")
        try:
            return TOOLS[name][0].model_validate_json(raw)
        except (ValueError, TypeError) as error:
            raise ToolError(f"工具参数无效：{error}") from error

    def relative(self, path: Path) -> str:
        return str(path.relative_to(self.workspace))

    def original(self, path: Path) -> tuple[str, str | None]:
        if not path.exists():
            return "", None
        if not path.is_file():
            raise ToolError("目标不是普通文件")
        if path.stat().st_size > self.limits.read_file_bytes:
            raise ToolError("目标文件超过读取上限，无法生成完整审批差异")
        data = path.read_bytes()
        return data.decode("utf-8"), hashlib.sha256(data).hexdigest()

    def prepare(self, name: str, args) -> dict | None:
        if name == "execute_command":
            return {"command": args.command, "cwd": str(self.workspace), "warning": "命令拥有本机权限，当前目录不是沙箱"}
        if name not in {"write_file", "edit_file"}:
            return None
        path = self.path(args.path)
        old, fingerprint = self.original(path)
        new = args.content if name == "write_file" else self.edited(old, args)
        if len(new.encode("utf-8")) > self.limits.read_file_bytes:
            raise ToolError("文件内容超过写入上限")
        diff_lines = difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile="/dev/null" if fingerprint is None else f"原文件/{self.relative(path)}",
            tofile=f"新文件/{self.relative(path)}",
        )
        diff = "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in diff_lines)
        return {"path": self.relative(path), "fingerprint": fingerprint, "diff": diff, "content": new,
                "operation": "create" if fingerprint is None else "update"}

    def edited(self, old: str, args: EditFile) -> str:
        if old.count(args.old_text) != 1:
            raise ToolError("old_text 必须在目标文件中唯一匹配；请重新读取文件")
        return old.replace(args.old_text, args.new_text, 1)

    async def execute(self, name: str, args, preview: dict | None, output: Callable[[str], Awaitable[None]]) -> dict:
        if name == "list_directory":
            path = self.path(args.path)
            entries = sorted(path.iterdir(), key=lambda item: item.name)
            visible = []
            for entry in entries:
                try:
                    self.path(str(entry))
                except ToolError:
                    continue
                visible.append({"name": entry.name, "directory": entry.is_dir()})
            return {"path": self.relative(path), "entries": visible[:500], "truncated": len(visible) > 500}
        if name == "read_file":
            path = self.path(args.path)
            if not path.is_file():
                raise ToolError("目标不是普通文件")
            data = path.read_bytes() if path.stat().st_size <= self.limits.read_file_bytes else None
            if data is None:
                raise ToolError("文件超过读取上限，请使用搜索或调整读取上限")
            lines = data.decode("utf-8").splitlines()
            return {"path": self.relative(path), "total_lines": len(lines),
                    "start_line": args.start_line, "end_line": min(args.end_line, len(lines)),
                    "content": "\n".join(f"{index + 1}: {line}" for index, line in enumerate(lines) if args.start_line <= index + 1 <= args.end_line)}
        if name == "search_files":
            return await asyncio.to_thread(self.search, args)
        if name in {"write_file", "edit_file"}:
            path = self.path(args.path)
            if self.relative(path) != preview["path"]:
                raise ToolError("目标路径在审批后发生变化，此次修改未执行")
            _, fingerprint = self.original(path)
            if fingerprint != preview["fingerprint"]:
                raise ToolError("文件在审批后已发生变化；此次修改未执行，请重新读取并提出修改")
            path.parent.mkdir(parents=True, exist_ok=True)
            path = self.path(args.path)
            descriptor, filename = tempfile.mkstemp(dir=path.parent, prefix=".zhenagent-")
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    stream.write(preview["content"])
                if path.exists():
                    os.chmod(filename, path.stat().st_mode & 0o777)
                os.replace(filename, path)
            finally:
                if os.path.exists(filename):
                    os.unlink(filename)
            return {"path": self.relative(path), "written_bytes": len(preview["content"].encode("utf-8"))}
        if name == "execute_command":
            return await self.command(args.command, output)
        raise ToolError(f"未知工具：{name}")

    def search(self, args: SearchFiles) -> dict:
        path = self.path(args.path)
        if not path.exists():
            raise ToolError("搜索路径不存在")
        matches: list[dict] = []
        visited = 0
        omitted = {".git", "node_modules", ".venv", "__pycache__"}
        candidates = [path] if path.is_file() else self.walk(path, omitted)
        for candidate in candidates:
            visited += 1
            if visited > 5000:
                return {"matches": matches, "truncated": True, "reason": "扫描达到 5000 个文件"}
            try:
                safe = self.path(str(candidate))
                if not safe.is_file() or safe.stat().st_size > self.limits.read_file_bytes:
                    continue
                for number, line in enumerate(safe.read_text(encoding="utf-8").splitlines(), 1):
                    if args.pattern in line:
                        matches.append({"path": self.relative(safe), "line": number, "text": line[:1000]})
                        if len(matches) >= 100:
                            return {"matches": matches, "truncated": True}
            except (OSError, UnicodeError, ToolError):
                continue
        return {"matches": matches, "truncated": False}

    def walk(self, root: Path, omitted: set[str]):
        for folder, directories, files in os.walk(root, followlinks=False):
            directories[:] = [name for name in directories if name not in omitted and not (Path(folder) / name).resolve().is_relative_to(self.data_dir)]
            for name in files:
                yield Path(folder) / name

    async def kill(self, process: asyncio.subprocess.Process):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), 2)
        except TimeoutError:
            pass
        # shell 退出后，仍需清理同一进程组里持有输出管道的子进程。
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()

    async def command(self, command: str, output: Callable[[str], Awaitable[None]]) -> dict:
        process = await asyncio.create_subprocess_exec(
            "/bin/sh", "-c", command, cwd=self.workspace, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, start_new_session=True,
        )
        chunks: list[bytes] = []
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        count = 0
        problem = None
        try:
            async with asyncio.timeout(self.limits.command_timeout):
                while block := await process.stdout.read(4096):
                    remaining = self.limits.command_output_bytes - count
                    kept = block[:remaining]
                    chunks.append(kept)
                    count += len(kept)
                    if kept:
                        decoded = decoder.decode(kept)
                        if decoded:
                            await output(decoded)
                    if len(block) > remaining:
                        problem = "命令输出达到上限，进程已终止"
                        await self.kill(process)
                        break
                await process.wait()
        except TimeoutError:
            problem = "命令执行超时，进程已终止"
            await self.kill(process)
        except BaseException:
            await self.kill(process)
            raise
        tail = decoder.decode(b"", final=True)
        if tail:
            await output(tail)
        return {"command": command, "exit_code": process.returncode,
                "output": b"".join(chunks).decode("utf-8", errors="replace"),
                "error": problem, "ok": process.returncode == 0 and not problem}


def context_result(result: dict, limit: int) -> str:
    raw = json.dumps(result, ensure_ascii=False)
    data = raw.encode("utf-8")
    if len(data) <= limit:
        return raw
    return json.dumps({"truncated": True, "original_bytes": len(data),
                       "excerpt": data[:limit].decode("utf-8", errors="ignore")}, ensure_ascii=False)
