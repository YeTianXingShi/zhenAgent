# 文档索引

本目录保存开发过程中形成的需求、调研、方案、决策、实验和结果。正式文档随代码公开，私人材料存入被 Git 忽略的 `.local`。

## 分类

| 目录 | 内容 | 入口 |
| --- | --- | --- |
| `requirements` | 需求、验收标准、变更原因 | [说明与模板](requirements/README.md) |
| `research` | 调研来源、源码位置、发现 | [说明与模板](research/README.md) |
| `design` | 方案、备选方案及取舍 | [说明与模板](design/README.md) |
| `decisions` | 编号的架构决策记录 | [说明与模板](decisions/README.md) |
| `experiments` | 消融实验计划、条件、指标和结果 | [说明与模板](experiments/README.md) |
| `development` | 开发规范、任务结果、验证和遗留问题 | [说明与模板](development/README.md) |

## 已有记录

- [架构问题与演进方向](design/2026-10-10-架构问题与演进方向.md)
- [架构问题梳理](development/2026-10-10-架构问题梳理.md)

- [会话操作菜单改版](development/2026-10-10-会话操作菜单.md)

- [会话名称与物理删除](development/2026-10-10-会话管理.md)

- [响应接收上限文案](development/2026-10-10-响应接收上限文案.md)

- [shadcn/ui 接入](development/2026-10-10-shadcn接入.md)

- [上下文与温度设计](design/2026-10-10-上下文与温度.md)
- [上下文与温度开发记录](development/2026-10-10-上下文与温度.md)

- [UI 组件库调研](research/2026-10-10-ui组件库.md)
- [UI 组件接入消融计划](experiments/2026-10-10-ui组件接入消融计划.md)

- [项目初始化需求](requirements/2026-10-10-项目初始化.md)
- [0001：项目初始化与文档管理](decisions/0001-项目初始化与文档管理.md)
- [项目初始化记录](development/2026-10-10-项目初始化.md)

- [agent 首版需求](requirements/2026-10-10-agent首版.md)
- [agent 参考实现调研](research/2026-10-10-agent参考实现.md)
- [OpenCode 模型默认参数来源](research/2026-10-10-opencode模型默认参数.md)
- [Models.dev 公共接口调研](research/2026-10-10-models-dev接口.md)
- [模型信息与默认参数设计](design/2026-10-10-模型目录默认参数.md)
- [模型信息接入记录](development/2026-10-10-模型目录默认参数.md)
- [模型信息文案修正](development/2026-10-10-模型信息文案.md)
- [agent 首版设计](design/2026-10-10-agent首版.md)
- [0002：agent 首版实现选择](decisions/0002-agent首版.md)
- [工具消融实验计划](experiments/2026-10-10-工具消融计划.md)
- [启动与使用说明](development/usage.md)
- [agent 首版开发记录](development/2026-10-10-agent首版.md)
- [运行上限输入校验修复](development/2026-10-10-运行上限输入校验.md)
- [文件预览与思考展示设计](design/2026-10-10-文件预览与思考展示.md)
- [文件预览与思考展示记录](development/2026-10-10-文件预览与思考展示.md)

## 使用方式

新增记录时先阅读该分类的说明，从 `template.md` 复制文件，填写实际内容，并在分类索引中添加链接。日期采用 `YYYY-MM-DD`；决策编号连续递增。具体任务流程见 [开发规范](development/workflow.md)。
