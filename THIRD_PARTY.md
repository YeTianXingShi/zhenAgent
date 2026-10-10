# 第三方来源

## shadcn/ui

- 来源：[shadcn-ui/ui](https://github.com/shadcn-ui/ui)。
- 获取日期：2026-10-10，官方 `new-york-v4` registry 快照。
- 源码位置：`frontend/src/components/ui/`，包含 Button、Input、Textarea、NativeSelect、Dialog、Tabs。
- 原始文件入口：`https://ui.shadcn.com/r/styles/new-york-v4/{组件名}.json`，组件名为 `button`、`input`、`textarea`、`native-select`、`dialog`、`tabs`。
- 授权：[原有 MIT 许可证](frontend/SHADCN-LICENSE.md)，版权归 `2023 shadcn`。

本项目把 registry 中的 `cn` 导入改为本地 `@/lib/utils`，调整 Dialog 内部 Button 导入，并将默认关闭文案改为中文。主题和布局适配位于 `frontend/src/ui.css` 与 `styles.css`。组件源码随本项目维护；更新时检查本地改动并保留上游版权声明。Radix、Lucide、Tailwind 等依赖版本保存在 `frontend/pnpm-lock.yaml`。

## shuorenhua

- 来源：[MrGeDiao/shuorenhua](https://github.com/MrGeDiao/shuorenhua)。
- 存放位置：`.agents/skills/shuorenhua/`。
- 安装快照版本：`2.5.1`，来自安装目录中的插件元数据。
- 授权：[原有 MIT 许可证](.agents/skills/shuorenhua/LICENSE)，版权归 `2026 MrGeDiao`。

本项目完整追踪已安装的 skill 目录，包括参考文件、安装说明、评测材料和资源。实际编写文档时加载 `SKILL.md`，参考文件按需读取。上游评测结果属于 shuorenhua 项目，不代表本项目的实验或验证结果。

更新 skill 时保留来源和原有版权声明，并更新这里的快照版本。
