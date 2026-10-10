# 项目规则

本项目计划使用 Python 和 Node.js 实现一个 agent。两者的职责划分随方案设计确定。

## 文档

编写或修改本项目任何文档前，必须先加载并阅读 [shuorenhua](.agents/skills/shuorenhua/SKILL.md)，按照该 skill 的规则输出。遇到编辑边界不清楚的情况，按需阅读其参考文件。

开始开发任务、记录需求、方案或结果时，先阅读 [开发规范](doc/development/workflow.md)，按 [文档索引](doc/README.md) 留存相关文档。含私人信息或凭证的材料放入 `.local`；正式文档随仓库公开。

## 设计与调研

实现时参考 pi、claude-code、codex、opencode、hermes-agent 的思路。这些源码已克隆到 `~/zhenProject`，具体路径见 [项目说明](README.md#参考项目)。调研具体实现时阅读对应源码，在调研记录中注明文件位置。

设计方案时使用消融实验：设定基线，逐项移除或替换待验证的机制，在相同条件下比较结果，判断各项机制的作用。记录实验条件、结果和结论；尚未运行的实验标明为计划。记录格式见 [实验文档](doc/experiments/README.md)。

## 提交

使用短期任务分支，每次提交围绕一个完整改动。提交前阅读 [提交规范](doc/development/commits.md)，采用英文类型标记和中文说明、正文，技术名称保留原文。
