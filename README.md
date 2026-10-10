# zhenAgent

本机使用的 Web 工具 agent。Python/FastAPI 后端负责模型请求、工具执行、审批和历史保存；Node.js 工具链构建 React/TypeScript/Vite 前端，两者独立运行。

首版代码已实现 Responses 流式对话、可展开的模型思考文本、多个模型服务配置、会话历史、文件工具、命令逐次审批、停止与受限重试。新建文件以完整内容预览，已有文件以增删差异预览。默认服务为 DeepSeek，模型为 `deepseek-flash`。当前已做构建、类型和语法检查；功能验证与真实服务联调由使用者完成。

## 启动

需要 uv、Python 3.12 和 Node.js 22.12 或以上版本，前端使用 pnpm 11.4.0。在项目根目录运行：

```sh
cp .env.example .env
uv sync --project backend --locked
pnpm --dir frontend install --frozen-lockfile
```

默认工作目录为本项目的 `workspace`，启动时自动创建。需要处理其他目录时，在 `.env` 中修改 `ZHEN_WORKSPACE_ROOT`。

分别在两个终端启动后端和前端：

```sh
uv run --project backend --locked uvicorn zhenagent.api:app --host 127.0.0.1 --port 8000
```

```sh
pnpm --dir frontend dev
```

打开 [本地工作台](http://127.0.0.1:5173)，进入“模型与运行设置”，在 DeepSeek 配置中保存自己的 API key，然后新建会话。更多配置、工具边界和历史保存方式见 [使用说明](doc/development/usage.md)。

API key 与会话数据库默认保存在被 Git 忽略的 `.local`。文件工具限制在工作目录内；经批准的命令拥有本机权限，工作目录不是沙箱。后端只启动一个进程，不使用 `--workers` 或开发自动重载。

## 开发入口

- [项目规则](AGENTS.md)：开发 agent 需要遵守的规则。
- [文档索引](doc/README.md)：需求、调研、设计、决策、实验和开发记录。
- [开发规范](doc/development/workflow.md)：任务分支、文档更新和交付要求。
- [提交规范](doc/development/commits.md)：中文提交说明和 Git 模板配置。

## 参考项目

本机已克隆以下源码；其他开发环境可在自己的 `~/zhenProject` 下准备相应仓库。

| 项目 | 本地源码路径 |
| --- | --- |
| pi | `~/zhenProject/pi` |
| claude-code | `~/zhenProject/claude-code` |
| codex | `~/zhenProject/codex` |
| opencode | `~/zhenProject/opencode` |
| hermes-agent | `~/zhenProject/hermes-agent` |

这些项目用于研究实现思路，具体调研结论写入 [调研文档](doc/research/README.md)。

## 文档与许可证

编写文档前先加载项目内的 [shuorenhua skill](.agents/skills/shuorenhua/SKILL.md)。本项目以 [MIT](LICENSE) 授权；收录的第三方文件及其独立许可证见 [第三方来源](THIRD_PARTY.md)。
