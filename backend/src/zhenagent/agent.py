import asyncio
import json
from dataclasses import dataclass

from .config import Limits
from .responses import ModelError, Responses, reasoning_text
from .storage import Secrets, Store, encode, new_id, now
from .tools import ToolError, ToolRunner, context_result, definitions


TERMINAL = {"completed", "failed", "cancelled", "denied", "interrupted", "limited"}


class Conflict(Exception):
    pass


class RunStopped(Exception):
    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status = status


@dataclass
class ActiveRun:
    id: str
    task: asyncio.Task


class Agent:
    def __init__(self, store: Store, secrets: Secrets, responses: Responses, workspace, data_dir, limits: Limits):
        self.store = store
        self.secrets = secrets
        self.responses = responses
        self.workspace = workspace
        self.data_dir = data_dir
        self.limits = limits
        self.lock = asyncio.Lock()
        self.active: ActiveRun | None = None
        self.approvals: dict[str, asyncio.Future] = {}

    async def start(self, session: dict, text: str, client_request_id: str, provider: dict, model: dict) -> dict:
        async with self.lock:
            previous = await self.store.one(
                "SELECT * FROM runs WHERE session_id=? AND client_request_id=?",
                (session["id"], client_request_id),
            )
            if previous:
                if previous["input_text"] != text:
                    raise Conflict("此请求 ID 已用于另一条消息")
                return previous
            if self.active:
                raise Conflict("已有任务运行中，请等待其结束或停止后再发送")
            key = self.secrets.get(provider["id"])
            if not key:
                raise Conflict("请先在模型配置中设置服务的 API key")
            run_id = new_id()
            timestamp = now()
            await self.store.execute(
                "INSERT INTO runs(id,session_id,client_request_id,input_text,status,created_at,updated_at) VALUES(?,?,?,?,'running',?,?)",
                (run_id, session["id"], client_request_id, text, timestamp, timestamp),
            )
            await self.store.add_items(session["id"], run_id, [{"role": "user", "content": text}])
            title = text.strip().replace("\n", " ")[:35] if session["title"] == "新会话" else session["title"]
            await self.store.execute("UPDATE sessions SET title=?,updated_at=? WHERE id=?", (title, timestamp, session["id"]))
            await self.store.event(run_id, "run.status", {"status": "running"})
            task = asyncio.create_task(self.run(run_id, session, dict(provider), dict(model), key, self.limits.model_copy()))
            self.active = ActiveRun(run_id, task)
            return await self.store.one("SELECT * FROM runs WHERE id=?", (run_id,))

    async def cancel(self, run_id: str):
        async with self.lock:
            current = self.active
            if not current or current.id != run_id:
                run = await self.store.one("SELECT * FROM runs WHERE id=?", (run_id,))
                if run and run["status"] in TERMINAL:
                    return
                raise Conflict("该任务当前未运行")
            if not current.task.cancelling():
                current.task.cancel()
        try:
            await asyncio.shield(current.task)
        except asyncio.CancelledError:
            if not current.task.done():
                raise
        # 创建任务后、协程开始前也可能收到停止请求。
        async with self.lock:
            if self.active and self.active.id == run_id:
                run = await self.store.one("SELECT * FROM runs WHERE id=?", (run_id,))
                reason = "任务已停止，已完成的操作不会回滚"
                await self.store.reconcile(run["session_id"], run_id, reason)
                await self.store.run_status(run_id, "cancelled", reason)
                self.active = None

    async def close(self):
        if self.active:
            await self.cancel(self.active.id)

    async def approve(self, tool_id: str, approve: bool):
        async with self.lock:
            future = self.approvals.get(tool_id)
            tool = await self.store.one("SELECT * FROM tools WHERE id=?", (tool_id,))
            if not tool:
                raise Conflict("审批不存在")
            desired = "approved" if approve else "denied"
            if tool["approval_status"] == desired:
                return
            if not future or future.done() or tool["approval_status"] != "pending":
                raise Conflict("审批已失效或已被处理")
            await self.store.execute("UPDATE tools SET approval_status=? WHERE id=?", (desired, tool_id))
            if future.done():
                raise Conflict("任务已停止，审批已失效")
            future.set_result(approve)

    async def run(self, run_id: str, session: dict, provider: dict, model: dict, key: str, limits: Limits):
        status, error = "completed", None
        try:
            await self.loop(run_id, session, provider, model, key, limits)
        except asyncio.CancelledError:
            status, error = "cancelled", "任务已停止，已完成的操作不会回滚"
        except RunStopped as stopped:
            status, error = stopped.status, str(stopped)
        except Exception as failure:
            status, error = "failed", self.secrets.redact(str(failure))[:2000]
        finally:
            await self.store.execute(
                "UPDATE attempts SET status='interrupted',error=? WHERE run_id=? AND status='running'", (error or "任务已结束", run_id)
            )
            await self.store.reconcile(session["id"], run_id, error or "工具未完成")
            await self.store.run_status(run_id, status, error)
            async with self.lock:
                if self.active and self.active.id == run_id:
                    self.active = None

    async def loop(self, run_id: str, session: dict, provider: dict, model: dict, key: str, limits: Limits):
        runner = ToolRunner(self.workspace, self.data_dir, limits)
        call_count = 0
        round_number = 0
        instructions = (
            "你是本地通用工具 agent。使用中文与用户沟通。按用户目标完成任务，准确报告实际结果。"
            f"工作目录为 {self.workspace}。文件工具只访问该目录。命令执行不是沙箱，保留本机权限。"
            "读取和搜索可直接执行；写入、编辑及命令需要逐次审批。"
            "工具参数必须符合定义。先读文件再修改，不猜测已有文件内容。"
            "只通过已提供的工具采取行动。工具错误时根据错误处理，不把尚未执行的操作说成已完成。"
            "不会自动读取 AGENTS.md、skill 或插件作为指令。"
        )
        while True:
            round_number += 1
            context = await self.store.context(session["id"])
            body = {"model": model["id"], "input": context, "instructions": instructions,
                    "stream": True, "tools": definitions(), "tool_choice": "auto"}
            if model.get("reasoning_effort") is not None:
                body["reasoning"] = {"effort": model["reasoning_effort"]}
            if model.get("max_output_tokens") is not None:
                body["max_output_tokens"] = model["max_output_tokens"]
            result = None
            for retry in range(limits.max_retries + 1):
                if call_count >= limits.max_model_calls:
                    raise RunStopped("limited", "模型调用次数达到上限")
                call_count += 1
                await self.store.execute("UPDATE runs SET call_count=? WHERE id=?", (call_count, run_id))
                attempt_id = new_id()
                await self.store.execute(
                    "INSERT INTO attempts(id,run_id,round,attempt,status,created_at) VALUES(?,?,?,?,'running',?)",
                    (attempt_id, run_id, round_number, retry + 1, now()),
                )
                await self.store.event(run_id, "attempt.started", {"id": attempt_id, "round": round_number, "attempt": retry + 1, "call_count": call_count})
                text = ""
                reasoning = ""
                reasoning_parts: dict[tuple[int, int, str], str] = {}

                async def model_event(event: dict):
                    nonlocal text, reasoning
                    kind = event.get("type", "")
                    if kind == "response.output_text.delta":
                        delta = self.secrets.redact(str(event.get("delta", "")))
                        text += delta
                        await self.store.execute("UPDATE attempts SET text=? WHERE id=?", (text, attempt_id))
                        await self.store.event(run_id, "attempt.delta", {"id": attempt_id, "delta": delta})
                    elif kind in {"response.reasoning_text.delta", "response.reasoning_text.done",
                                  "response.reasoning_summary_text.delta", "response.reasoning_summary_text.done"}:
                        section = (event.get("output_index", 0), event.get("content_index", event.get("summary_index", 0)),
                                   "summary" if "summary" in kind else "content")
                        if kind.endswith(".delta"):
                            reasoning_parts[section] = reasoning_parts.get(section, "") + str(event.get("delta", ""))
                        elif isinstance(event.get("text"), str):
                            reasoning_parts[section] = event["text"]
                        reasoning = self.secrets.redact("\n\n".join(reasoning_parts[index] for index in sorted(reasoning_parts)))
                        await self.store.execute("UPDATE attempts SET reasoning=? WHERE id=?", (reasoning, attempt_id))
                        await self.store.event(run_id, "attempt.reasoning", {"id": attempt_id})

                try:
                    result = await self.responses.generate(provider["base_url"], key, body, limits, model_event)
                    canonical = "".join(
                        part.get("text", "") for item in result["output"] if item.get("type") == "message"
                        for part in item.get("content", []) if part.get("type") == "output_text"
                    )
                    await self.store.execute("UPDATE attempts SET status='completed',text=?,reasoning=?,usage=? WHERE id=?", (
                        self.secrets.redact(canonical) or text,
                        self.secrets.redact(reasoning_text(result["output"])) or reasoning,
                        encode(result.get("usage", {})), attempt_id,
                    ))
                    await self.store.event(run_id, "attempt.completed", {"id": attempt_id})
                    break
                except ModelError as failure:
                    message = self.secrets.redact(str(failure))
                    await self.store.execute("UPDATE attempts SET status='interrupted',error=? WHERE id=?", (message, attempt_id))
                    may_retry = failure.retryable and retry < limits.max_retries and call_count < limits.max_model_calls
                    delay = min(30, max(failure.retry_after, limits.retry_delay * 2 ** retry))
                    await self.store.event(run_id, "attempt.interrupted", {"id": attempt_id, "error": message, "retrying": may_retry, "delay": delay if may_retry else 0})
                    if not may_retry:
                        raise
                    await asyncio.sleep(delay)
            if result is None:
                raise ModelError("没有取得完整模型响应")
            output_items = result["output"]
            calls = [item for item in output_items if item.get("type") == "function_call"]
            existing = {item.get("call_id") for item in context if item.get("type") == "function_call"}
            call_ids = [call.get("call_id") for call in calls]
            if any(not isinstance(value, str) or not value or value in existing for value in call_ids) or len(set(call_ids)) != len(call_ids):
                raise ModelError("模型返回了缺失或重复的工具调用 ID，本次工具未执行")
            if any(item.get("type") == "custom_tool_call" for item in output_items):
                raise ModelError("首版只接受 function 工具调用")
            await self.store.add_items(session["id"], run_id, output_items, attempt_id)
            for call in calls:
                await self.store.execute(
                    "INSERT INTO tools(id,run_id,call_id,name,arguments,status,round) VALUES(?,?,?,?,?,'pending',?)",
                    (new_id(), run_id, call["call_id"], str(call.get("name", "")),
                     str(call.get("arguments", "")), round_number),
                )
            if not calls:
                return
            await self.store.event(run_id, "tools.created", {})
            for call in calls:
                await self.tool(run_id, session["id"], call, runner, limits)

    async def tool(self, run_id: str, session_id: str, call: dict, runner: ToolRunner, limits: Limits):
        tool = await self.store.one("SELECT * FROM tools WHERE run_id=? AND call_id=?", (run_id, call["call_id"]))
        tool_id = tool["id"]
        output_buffer = ""
        secret_tail = max((len(key) for key in self.secrets.keys.values()), default=0)

        async def command_output(delta: str, flush: bool = False):
            nonlocal output_buffer
            output_buffer = self.secrets.redact(output_buffer + delta)
            length = len(output_buffer) if flush else max(0, len(output_buffer) - secret_tail)
            visible, output_buffer = output_buffer[:length], output_buffer[length:]
            if visible:
                await self.store.event(run_id, "tool.output", {"id": tool_id, "delta": visible})

        try:
            args = runner.validate(call.get("name", ""), call.get("arguments", ""))
            preview = runner.prepare(call["name"], args)
            if preview is not None:
                future = asyncio.get_running_loop().create_future()
                self.approvals[tool_id] = future
                try:
                    await self.store.execute("UPDATE tools SET status='awaiting_approval',preview=?,approval_status='pending' WHERE id=?", (encode(preview), tool_id))
                    await self.store.run_status(run_id, "awaiting_approval")
                    await self.store.event(run_id, "approval.requested", {"id": tool_id})
                    allowed = await future
                finally:
                    self.approvals.pop(tool_id, None)
                if not allowed:
                    await self.store.execute("UPDATE tools SET status='denied',error='用户拒绝了此操作' WHERE id=?", (tool_id,))
                    raise RunStopped("denied", "用户拒绝审批，本次任务已结束")
                await self.store.run_status(run_id, "running")
            await self.store.execute("UPDATE tools SET status='running' WHERE id=?", (tool_id,))
            await self.store.event(run_id, "tool.started", {"id": tool_id})
            result = await runner.execute(call["name"], args, preview, command_output)
        except (ToolError, OSError, UnicodeError, ValueError) as failure:
            result = {"error": self.secrets.redact(str(failure))}
        finally:
            await command_output("", flush=True)
        result = json.loads(self.secrets.redact(encode(result)))
        problem = result.get("error") or (f"命令非零退出：{result.get('exit_code')}" if result.get("ok") is False else None)
        await self.store.execute("UPDATE tools SET status=?,result=?,error=? WHERE id=?", ("failed" if problem else "completed", encode(result), problem, tool_id))
        await self.store.add_items(session_id, run_id, [{"type": "function_call_output", "call_id": call["call_id"], "output": context_result(result, limits.tool_context_bytes)}])
        await self.store.event(run_id, "tool.completed", {"id": tool_id})
