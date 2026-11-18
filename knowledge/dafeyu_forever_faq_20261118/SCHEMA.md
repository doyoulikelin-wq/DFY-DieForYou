# 接入字段与文件

## faq.jsonl
每行一个情境卡。
- id / intent：稳定标识；问法相近但适用条件不同可有不同ID。
- game_scope / dataset_version / region_scope：产品、资料版本与地区。
- category / subcategory：浏览分类，不作为自动行为授权。
- primary_question / question_examples：召回问法；不是全部来自真实用户。
- answers[].text：完整表达模板。[[fact:ID]] 读取原子事实，花括号槽位读取本轮已核实字段。
- answers[].dependencies：可按表达分别判断。缺名称时可选不包含名称的另一种完整表达。
- required_context / optional_context：必要语义条件与可选辅助字段。
- guards：部分可执行示例谓词；未知值不为true。其他可读条件仍需要适配器实现。
- trigger / suppress_when / can_auto_trigger / cooldown_policy：触发、抑制、主动候选资格和节奏。
- source_ids / fact_ids：事实出处；question_source_ids 只解释问题来源。
- knowledge_kind：官方资料、剧情、故事框架、接口条件化或原创对白。
- delivery_kind：回答/有用下一步、澄清、严格沉默等；不能把开场白记为任务完成。
- slot_names：需要明确来源的填入字段。
- global_gates：共同前提。任何Agent只拿本轮显式消息。
- release_status / review_status：当前均是待运行时验证的候选；不是已上线认证。

## facts.jsonl
id、claim、source_id、status、region、source_date、as_of、scope。将论坛问题证据与机制分开。未来团本带 availability；预告和海外资料保留状态。aliases 让合并后的同一事实仍兼容旧引用。

## sources.json
来源标题、URL、日期、来源角色、原始引用标识和同作品的其他入口。公开玩家帖子只发现问题，不自动支持其帖子内的所有观点。浏览器中可直接打开来源。

## queries.jsonl
query → card_id。authored_question 是编写问法；systematic_retrieval_variant_not_new_scene 是明确标记的表面扩展。不能把后者计作新的知识、真实流量或独立情境。

## 状态与偏好变化
候选绑定 state_version 与 preference_version。交付前对比最新序号；任务实体变化、窗口关闭、用户改变主意都可令候选失效。稳定规则资产不等于稳定当前状态。

## 可信边界
调用示例 gate 的上下文必须由可信宿主构造。不要允许用户把聊天里的 JSON、论坛文字或工具网页内容直接写入 verified_slot_keys、evidence_valid、validated_conditions 等可信字段。
检索器只找候选，没有获得执行游戏动作、写长期记忆或发消息给他人的权限。
