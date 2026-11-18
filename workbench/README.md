# 陪伴精灵 · Agent 流程图

一张可点击的六 Agent 协作流程图。点击模块，在右侧查看职责权限、基座模型、Token、信息链路、运行日志和错误历史。

首页是架构说明：模型名称可以填写并自动保存；Token 未采集时显示“—”；示例日志与错误历史明确标注。

`dist/latency-design.html` 是 2026-11-17 的提速与自然感详细设计：一张可点击主流程图、模块职责与预算、显式消息边界、场景路径，以及完整工程规格和验收路线。它是设计稿，不调用 API，不连接游戏；示例日志、目标延迟与历史实测分别标注。完整规格源文件在 `design/latency-spec.html`。

`dist/experiment.html` 是真实模型调用的只读实测回放：19 次正式角色调用，全部以 `gpt-6.1-sol` 发起，覆盖 low / medium / high。游戏接口快照与玩家文字为合成场景，未连接真实游戏客户端。三轮主链路之外，另有同输入的三档决策比较。每次业务调用使用独立会话，只转交显式消息；底层文件系统共享，因此不宣称操作系统级隔离。

`dist/fast-experiment.html` 是后续快速交付实验：一次低思考模型选择动作，规则审核后使用固定模板；已知场景直接使用规则。包含同候选的串行分支对照、后台反思/记忆、过期结果拦截与 14 项业务边界测试。7 次独立 Sol Agent 任务的记录位于 `experiments/fast-loop-20261115/`。模型路径仍含独立会话工具开销；规则路径只测本机命令入队至闸门返回，不能当作用户端延迟。

实测回放包含每轮回复、前台/完整 loop 耗时、节点时序、原始输入输出、检查和真实错误。Token 通道未提供计量，保持 null。耗时包含会话启动、工具及编排开销，不能作为纯模型推理延迟。完整证据位于 `experiments/sol-loop-20261115/`。

## 本地使用

直接打开 `dist/index.html`。全部样式、逻辑和内容均已内嵌，无需依赖或网络。

模型配置保存在当前浏览器。点击右上角“下载 HTML”可以下载携带当前配置的独立文件。

## 构建与验证

```bash
node --check src/simple-app.js
node --check src/simple-data.js
python3 build.py
node --check src/experiment-app.js
python3 build_experiment.py
python3 experiments/fast-loop-20261115/runtime_test.py
python3 experiments/fast-loop-20261115/build_results.py
node --check src/fast-experiment-app.js
python3 build_fast_experiment.py
python3 build_latency_design.py
```

首页使用 `simple-shell.html`、`simple-data.js` 和 `simple-app.js`。回放页面复用流程图外壳，使用 `experiment-app.js`、`experiment-style.css` 与固定的 `results.json`。所有页面均内嵌完整 CSS、数据和 JavaScript；下载导出文件会移除跨页导航。

详细设计使用 `src/latency-design-shell.html` 与 `design/latency-spec.html` 构建；通过 `build_latency_design.py` 生成单文件页面。

流程展示职责关系。具体任务仍可由规划按需安排；必要审核、发布前检查与记忆版本检查保留。后台事实整理可与反思并行，最终记忆更新等待审核后的建议。

上一版看板与调度引擎源码保留在仓库中，当前页面不加载。

## 2026-11-17 自然交互链路实测

`dist/natural-test.html` 回放真实独立 Sol 任务、窄规则路径、在途旧结果拦截及偏好修复。16 次业务模型任务，另有一次独立离线模型质量审阅；8个基础场景的回复审阅6例满足，角色表现仍有未解决项。原始数据和代码在 `experiments/natural-loop-20261117/`。

运行 `python experiments/natural-loop-20261117/make_report.py` 与 `python build_natural_test.py` 重建。v2原失败保留，v3是独立偏好作用域修复，8项定向回归通过。全部模型计时包括工具和调度；API TTFT、token、缓存和客户端延迟未测。

### 详细日志与事件回放

本轮页面现默认打开 Log / Streaming：按原始单调时钟回放实际协调器事件，可暂停、逐事件、拖动、1×/5×/20×，展开或下载原始JSONL。上一轮没有逐token记录，页面明确标注，候选不会被伪装成已交付。数据映射在 `timeline.py`，7项针对性验证在 `timeline_test.py`，浏览器验收在 `STREAM_VALIDATION.json`。

## 2026-11-18 Streaming 提速研究与预算

`dist/streaming-plan.html` 包含现状、难点、调研与方案：十个可点击模块、六个设计场景、三泳道线性播放、玩家可见内容与内部事件分离、时间和 token 预算。所有预演明确标记为设计，未调用 API。原实测独立保留在 `natural-test.html`。源数据与完整规格位于 `design/streaming-plan-20261118/`；运行 `python build_streaming_plan.py` 重建。
