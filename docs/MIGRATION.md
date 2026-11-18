# 迁移与来源

迁移日期：2026-11-18（北京时间）。目标：doyoulikelin-wq/DFY-DieForYou。

## 原始来源

- 陪伴精灵 · 协作设计台，第 8 版：源提交 `279d3fb04c3495920fc29dddc3fbccf11671f5cc`。
- 原站点：<https://companion-agent-studio-nov15.mylssssdddd.chatgpt.site>。
- 将该提交的 251 个跟踪文件逐字节复制到 `workbench/`，保留上一版完整看板源码、最新页面、设计、实验与日志。
- `dafeyu_forever_faq_20261118.zip` 原包复制到 `archives/`，包内 23 文件解压到 `knowledge/`。原包 `checksums.json` 覆盖其中 22 文件。
- 完整 SHA-256、大小和来源见 [source-manifest.json](source-manifest.json)：共 275 个原始文件（含原 ZIP）。

## 本次新增

统一入口、根 README、技术索引、启动 / 构建 / 验证脚本、迁移校验清单与报告。
`workbench/dist/design-board.html` 由原先保留的完整版设计台源码生成，便于直接打开；未改动原始源码。

## 完整性与复现

运行 `python3 tools/verify.py`，检查原文件散列、FAQ 原校验和、ZIP 与解压内容、SQLite、页面链接、JS 语法、模拟引擎、运行时与偏好测试、Streaming 和 FAQ 门控，并在临时副本重建页面比较字节。当前结果见 [migration-check.json](../validation/migration-check.json)。测试不调用模型，不重新生成历史模型输出，不把本机新时间覆盖历史测量。

统一构建输出到 `build/workbench/dist/`，不覆盖归档。两张较早的实验回放页重建时会采用最新公共外壳的导航与响应式样式；验证要求其内嵌脚本和实验数据与原页一致，其余五页要求字节一致。

原始代码和源数据不等于完整会话逐字转录。此次恢复来自已保存的站点源码与交付文件；未恢复其他浏览器中没有导出的 localStorage 改动。旧工作路径作为原始实验记录保留，复用新模型实验时需显式配置新的输出位置。

原站点托管配置随原源码保留，仅用于来源追溯；根目录无自动部署配置。本次没有发布新站点、修改旧站点权限或迁移其浏览器个人状态。
