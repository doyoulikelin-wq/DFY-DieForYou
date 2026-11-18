# 技术索引与接手说明

依据第 8 版站点源码、历史实验与 FAQ 原包整理。详细设计与原始记录保留在下列位置；研究设想不视为已实现功能。

## 架构

| 层 / 角色 | 职责 | 资料位置 |
|---|---|---|
| 事件 / 快照 | 事实来源、状态版本、当前用户文字与偏好 | `workbench/src/simple-data.js`、`workbench/design/latency-spec.html` |
| 规划 | 选择必要模块、顺序、并发与终止条件 | 同上；`workbench/src/engine.js` |
| 决策 | 选择动作或生成有依据的候选 | `workbench/experiments/sol-loop-20261115/harness.py` |
| 审核 | 候选、权限、状态、偏好与证据检查 | `fast-loop-20261115/runtime.py`、`natural-loop-20261117/runtime_v2.py`（均在 experiments 下） |
| 执行 / 交付 | 交付通过审核的内容，记录实际送达 | 实验 deliveries、events、results |
| 反思 | 后台解释反馈，提出有出处建议 | 实验 inputs、outbox、receipts 的 reflection |
| 记忆 | 整理事实与明确偏好，通过版本检查提交 | `runtime_v2.py`、`runtime_v3.py` 及测试 |

各 Agent 通过明确的信息包交接内容，不隐式共享私人会话记忆。独立会话不等于操作系统级隔离。历史实验的游戏快照为合成数据，模拟交付标记保持原样。

## 工作台与保存

第 8 版默认首页是简化的六 Agent 图。早期完整版源码保留但默认不加载。本次以原 `shell.html + catalog.js + engine.js + app.js` 生成独立的 `workbench/dist/design-board.html`，两个入口均可用。

完整看板包含功能定义与状态、节点依赖、并发资源、时限、主动试探设置、模拟运行、验收证据、版本记录、JSON 导入导出。编辑由当前浏览器保存，不是服务器保存或多人实时同步。团队应导出 JSON / HTML，并将确认的文件纳入 Git。原站点其他浏览器中未导出的改动无法由源码恢复。

## 实验与证据

| experiments 下的目录 | 内容 | 限制 |
|---|---|---|
| `sol-loop-20261115/` | 19 次正式角色调用，三轮与思考档位对照，ledger / inputs / outbox / REPORT / trace ZIP | 合成游戏快照；token 未采集 |
| `fast-loop-20261115/` | 7 次独立模型任务、规则模板、串行对照、后台反思与记忆、过期结果 | 本地规则耗时不是客户端端到端 |
| `natural-loop-20261117/` | 16 次业务任务与一次独立离线质量审阅；冲突刷新、偏好修复、JSONL 时间线 | TTFT / usage / 客户端延迟未测；自然感有失败项 |

v2 的 22 项边界测试、v3 的 8 项偏好测试和 7 项时间线测试是不同测试集。原失败记录不改写为修复后的成功。历史 harness / driver 中的旧工作路径是当时派发契约；新实验需改成新的隔离输出目录，不得覆盖现有证据。统一验证只运行离线测试，不发起新模型任务。

## Streaming 路径

完整规格见 [DESIGN.md](../workbench/design/streaming-plan-20261118/DESIGN.md)。数据 `data.json`、研究依据 `evidence.json`、前端 `workbench/src/streaming-plan*`。

设计分为：条件完整的本地直答、单次快速决策与表达、需要新证据的工具 / 规划路径、后台反思与记忆。首个有用交付与首 delta 分开计时；完整语义段经过检查后发布；旧状态结果不能交付。后台必须有实际未完成产物，不能因角色存在就调用。

预算区分输入 I、可见输出 O 和隐藏推理 R。API output_tokens 已含 R 时不能重复加；cached_tokens 属于输入；取消不证明零费用。历史协调器耗时、本地检索毫秒数与未来端到端预算分别保存。

`make_data.py` 保留原始绝对 FAQ 路径供追溯。正常页面重建使用已归档 `data.json`，无需运行它。若重新生成设计数据，先将该脚本 FAQ 路径改为本仓库知识库，再审阅数据变更。

## 无限服知识与人设

见 [知识库 README](../knowledge/dafeyu_forever_faq_20261118/README.md)、[SCHEMA](../knowledge/dafeyu_forever_faq_20261118/SCHEMA.md)、[SOURCES](../knowledge/dafeyu_forever_faq_20261118/SOURCES.md)、[PERSONA](../knowledge/dafeyu_forever_faq_20261118/PERSONA.md)。

958 张情境卡、1,851 种表达、3,127 条编写问法、9,255 条检索变体、181 条官方原子事实、4 条社区问题证据、40 个去重来源组。这些维度不能相加成知识总量。

大肥鱼以主动、好奇、轻盈、体贴为创作方向，胜利时欢呼、剧情中讲述、受挫时调整语气，允许沉默。人格不等于所有场景固定话术，不声称看见现实环境，也不要求玩家安抚角色。

召回仅产生候选。直答还要检查规则集、意图、当前状态、偏好、事实、槽位和抑制条件。部分可读条件尚待真实适配器实现，不能因相似度高就自动放行。覆盖缺口见 `coverage_gaps.json`。

## 后续接入

1. 对接真实游戏事件，确定快照字段、来源、版本、消息传输和显示回执。
2. 分批批准 FAQ，将可读条件实现为可验证的判断；使用留出问法和同问不同状态反例。
3. 接入真实模型流，记录请求、首 delta、语义段审核、客户端显示、usage 和取消确认。
4. 验证后台裁剪、偏好范围、记忆并发与用户拒绝后的主动停止。
5. 通过真实玩家盲评检查自然感。离线反馈 / Skill 修订及训练属后续研究；当前没有在线 RL 或训练权重。

已有 AIRI / WoW 客户端项目见 <https://github.com/LoveWood233/wow-airi-companion>。本仓库归档该 session 的设计、知识与实验，未复制外部客户端全部依赖与素材历史。
