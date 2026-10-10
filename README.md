# zhenAgent

计划使用 Python 和 Node.js 实现一个 agent，参考已有 agent 项目的实现思路。

当前阶段建立项目文档、Git 追踪和开发规范。Python 与 Node.js 的职责、首个功能、工具链、运行时版本、测试框架和 CI 将在后续设计中确定。

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
