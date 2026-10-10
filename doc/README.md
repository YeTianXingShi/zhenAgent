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

- [项目初始化需求](requirements/2026-10-10-项目初始化.md)
- [0001：项目初始化与文档管理](decisions/0001-项目初始化与文档管理.md)
- [项目初始化记录](development/2026-10-10-项目初始化.md)

调研、设计和实验目录目前提供说明与模板；后续工作产生实际内容时再新增记录。

## 使用方式

新增记录时先阅读该分类的说明，从 `template.md` 复制文件，填写实际内容，并在分类索引中添加链接。日期采用 `YYYY-MM-DD`；决策编号连续递增。具体任务流程见 [开发规范](development/workflow.md)。
