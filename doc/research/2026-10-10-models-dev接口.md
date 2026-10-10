# Models.dev 公共目录接口

- 日期：2026-10-10
- 状态：已完成
- 本地源码：`~/zhenProject/models.dev`，提交 `80bb5530bf460456a78df3f6c0ee96adbac86839`

本次阅读仓库 README 的 API、Schema Reference 与 `base_model` 说明，以及 `packages/core/src/schema.ts`、`providers/deepseek/provider.toml` 和 `providers/deepseek/models/deepseek-flash.toml`。README 明确提供 `curl https://models.dev/api.json`。该接口按服务组织模型，生成时已合并基础模型资料和服务覆盖；消费者无需自行解析 TOML 继承。[README](https://github.com/anomalyco/models.dev/blob/80bb5530bf460456a78df3f6c0ee96adbac86839/README.md)

`api.json` 顶层键是 provider ID，每个 provider 有 `name`、`api`、`models`。模型对象提供 `name`、`limit`、`reasoning_options`、能力和模态。`temperature` 是支持能力，不是默认采样温度；思考档位列表没有指定默认值。`toggle` 提供关闭选项，`effort` 提供可选字符串，预算型选项不能直接当成 Responses 的 effort。[schema](https://github.com/anomalyco/models.dev/blob/80bb5530bf460456a78df3f6c0ee96adbac86839/packages/core/src/schema.ts)

已用 curl 下载公共 JSON，读取到 226 个服务。当天 `deepseek-flash` 的名称为 DeepSeek V4.1 Flash，`limit.context` 为 1000000，`limit.output` 为 393216，思考选项为 toggle 及 low/high/max。这是目录查询结果，不代表已验证 DeepSeek Responses 接受该上限；该接口的实际限制仍由模型服务决定。[公共目录](https://models.dev/api.json)，[模型定义](https://github.com/anomalyco/models.dev/blob/80bb5530bf460456a78df3f6c0ee96adbac86839/providers/deepseek/models/deepseek-flash.toml)

因此本项目使用目录提供的输出上限和选项，未提供的默认参数留空，用户可覆盖。目录数据会变更，以上具体数值只记录本次下载结果。

- [OpenCode 参数来源](2026-10-10-opencode模型默认参数.md)
- [接入设计](../design/2026-10-10-模型目录默认参数.md)
