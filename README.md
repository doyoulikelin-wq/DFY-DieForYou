# DFY · Die For You / 大肥鱼

“强化学习陪伴精灵”的技术资料、协作设计工作台、实验记录与魔兽世界「无限」情境 FAQ。归档日期：2026-11-18（北京时间）。

**从 [统一入口](index.html) 开始。** 下载仓库后直接用浏览器打开 `index.html`，或运行 `python3 tools/serve.py`，访问 <http://127.0.0.1:8765>。页面已内嵌数据，不需要 API Key。GitHub 文件页显示源码，交互页面需在本地打开。

## 内容入口

| 内容 | 入口 | 说明 |
|---|---|---|
| 可编辑协作设计台 | [design-board.html](workbench/dist/design-board.html) | 原版功能看板、链路规划、并发调度、运行预演、验收、规则与版本、角色分工 |
| 最新六 Agent 架构 | [index.html](workbench/dist/index.html) | 模块职责、模型配置、信息边界与示例日志 |
| Streaming 路径 | [streaming-plan.html](workbench/dist/streaming-plan.html) | 现状、难点、调研、方案、时间与 token 预算、预期成果 |
| 提速与自然感设计 | [latency-design.html](workbench/dist/latency-design.html) | 详细工程规格、消息边界与验收路线 |
| 自然交互实测回放 | [natural-test.html](workbench/dist/natural-test.html) | 协调器日志、时间线、偏好失败与修复 |
| 首轮模型实验 | [experiment.html](workbench/dist/experiment.html) | 19 次正式角色调用及思考档位对照 |
| 快速路径实验 | [fast-experiment.html](workbench/dist/fast-experiment.html) | 7 次独立模型任务、规则交付与后台记忆竞态 |
| 无限服 FAQ | [dafeyu_forever_faq.html](knowledge/dafeyu_forever_faq_20261118/dafeyu_forever_faq.html) | 958 张情境卡、1,851 种回答表达、12,382 条索引 |
| 技术接手说明 | [TECHNICAL_OVERVIEW.md](docs/TECHNICAL_OVERVIEW.md) | 架构、实现位置、验证边界和后续接入 |
| 迁移说明 | [MIGRATION.md](docs/MIGRATION.md) | 来源、版本、文件清单与完整性 |

现有在线版：[陪伴精灵 · 协作设计台](https://companion-agent-studio-nov15.mylssssdddd.chatgpt.site)。沿用原访问权限，本次未更改站点权限或部署。

## 当前完成边界

- 已有：设计台、模拟调度引擎、真实模型调用记录、合成游戏场景下的运行时测试、偏好修复、离线 FAQ 与检索门控。
- 尚未完成：真实魔兽客户端联调、生产 API 流式交付、真实玩家自然度验证、在线强化学习或模型训练。
- 历史耗时含会话、工具与编排开销。未采集的 token / TTFT 保持未知；Streaming 延迟与 token 为设计预算。
- 设计台编辑保存在当前浏览器，可导出 / 导入方案；**没有多人实时同步后端**。团队通过导出方案与 Git 共享。其他浏览器未导出的个人改动不在本次归档范围。
- FAQ 不是全任务、全 NPC、全技能或实时拍卖数据库；缺口见 [coverage_gaps.json](knowledge/dafeyu_forever_faq_20261118/coverage_gaps.json)。

## 构建和验证

Python 3.10+、Node.js 18+，无需第三方依赖：

```bash
python3 tools/build.py
python3 tools/verify.py
python3 knowledge/dafeyu_forever_faq_20261118/retrieval_demo.py "技能为什么放不出来"
```

构建输出到 `build/workbench/dist/`，不覆盖已归档页面。验证在临时副本运行会写入报告的原始脚本，避免覆盖历史实测。结果保存在 `validation/migration-check.json`。

## 目录

- `workbench/`：第 8 版站点源码、设计与历史实验。
- `knowledge/dafeyu_forever_faq_20261118/`：FAQ、事实、来源、人设、故事、SQLite 和示例代码。
- `archives/`：FAQ 原始 ZIP。
- `docs/`：技术索引、迁移说明、逐文件 SHA-256 清单。
- `tools/`：启动、重建和离线验证。
- `validation/`：本次验证结果。

第三方资料归属保留在原来源记录中；未新增第三方内容的再许可声明。
