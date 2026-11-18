(function () {
  'use strict';
  window.CompanionSimpleData = {
    schemaVersion: 1,
    note: '职责与链路为设计方案；模型尚未选择，Token 尚未采集，日志和错误历史均为示例。',
    agents: [
      {
        id: 'planning', title: '规划 Agent', subtitle: '决定调用谁、如何配合', color: '#8b5cf6', thinking: '重思考 · 按需调用',
        summary: '把本轮目标拆成所需任务，明确先后、并发和结束条件。',
        duties: ['明确本轮目标、可用时间和停止条件。', '选择需要的 Agent，说明哪些可以复用或跳过。', '安排任务依赖，标明可以并发的工作。'],
        powers: ['启用或跳过可选任务，复用仍然有效的结果。', '提出任务链路、调用预算与并发安排。'],
        limits: ['不能删除内容审核、发布前检查等必要环节。', '不能直接发言、执行动作或修改人物核心设定。'],
        model: { name: '待选择', route: '复杂目标使用重思考；已有有效计划时可以跳过。' },
        tokens: { input: null, output: null, source: '未接入真实运行' },
        inputs: [{ from: '用户 / 场景事件', data: '本轮目标、当前状态与明确要求。' }, { from: '记忆整理 Agent', data: '相关经历、偏好和可复用计划。' }],
        outputs: [{ to: '决策 Agent', data: '任务清单、依赖顺序、调用理由与预算。' }],
        parallel: '可以与独立的资料读取并发；需要这些结果的决策必须等待。',
        logs: [{ time: '示例 00:00.000', level: 'info', message: '接收复盘目标，确认当前没有可复用计划。', run: 'DEMO-001' }, { time: '示例 00:01.700', level: 'info', message: '生成链路：资料可并行读取，决策等待资料齐备。', run: 'DEMO-001' }],
        errors: [{ time: '示例 00:01.300', code: 'DEPENDENCY_CYCLE', message: '候选任务链路出现循环依赖。', cause: '两项任务互相等待对方结果。', fix: '移除错误依赖，重新通过链路检查后再执行。', status: '已处理（示例）' }]
      },
      {
        id: 'decision', title: '决策 Agent', subtitle: '选择本轮行为与表达', color: '#3184f5', thinking: '轻 / 重思考 · 按需路由',
        summary: '结合人物性格、计划和当前情境，选择回应、等待、试探或保持安静。',
        duties: ['判断此刻是否适合介入，并选择具体行动。', '按复杂程度与不确定性选择思考档位。', '准备行动意图和即将输出的候选表达。'],
        powers: ['在获准选项中选择、推迟或放弃行动。', '请求必要资料，或把复杂问题升级为重思考。'],
        limits: ['候选表达必须交给审核，不能直接对用户输出。', '人物性格影响行为选择，不得改变已确定的权限边界。'],
        model: { name: '待选择', route: '熟悉场景走规则或轻思考；复杂、冲突或信息不足时用重思考。' },
        tokens: { input: null, output: null, source: '未接入真实运行' },
        inputs: [{ from: '规划 Agent', data: '目标、候选路径、所需资料与剩余预算。' }, { from: '记忆整理 Agent', data: '人物设定、相关偏好与历史事实。' }, { from: '用户 / 场景事件', data: '最新要求、场景变化和互动时机。' }],
        outputs: [{ to: '审核 Agent', data: '选定行动、具体候选表达与选择依据。' }],
        parallel: '决策要等待本次必需的信息；与当前行动无关的后台整理可以继续。',
        logs: [{ time: '示例 00:01.700', level: 'info', message: '计划与资料已齐备，开始比较本轮候选行动。', run: 'DEMO-001' }, { time: '示例 00:02.800', level: 'info', message: '选择简短回应，并提交具体表达供审核。', run: 'DEMO-001' }],
        errors: [{ time: '示例 00:02.200', code: 'MISSING_CONTEXT', message: '缺少选择行动所需的信息。', cause: '必需资料未返回，无法判断行动是否适合当前场景。', fix: '等待资料；超过截止时间时放弃本轮行动。', status: '已处理（示例）' }]
      },
      {
        id: 'review', title: '审核 Agent', subtitle: '检查内容与更新依据', color: '#e5a037', thinking: '规则优先 · 轻思考',
        summary: '检查真正准备输出的内容，以及后台准备写入的更新建议。',
        duties: ['核对具体表达、行动权限和用户明确要求。', '必要时检查语义与当前情境是否冲突。', '核对记忆更新的证据、适用范围与有效性。'],
        powers: ['通过、退回修改或拒绝本次内容与更新。', '指出违反的规则和需要修正的具体部分。'],
        limits: ['不能自行放宽规则或增加执行权限。', '内容修改后必须重新审核，不能沿用旧通过结果。'],
        model: { name: '待选择', route: '确定性条件由规则检查；语义与情境判断按需用轻思考。' },
        tokens: { input: null, output: null, source: '未接入真实运行' },
        inputs: [{ from: '决策 Agent', data: '即将输出的具体内容、行动意图与依据。' }, { from: '反馈反思 Agent / 记忆整理 Agent', data: '待写入的更新建议、来源与适用范围。' }],
        outputs: [{ to: '执行 Agent', data: '已批准的内容与执行范围，或拒绝原因。' }, { to: '记忆整理 Agent', data: '已审核的更新建议，或退回修改意见。' }],
        parallel: '可独立审核不同任务；同一任务必须先有具体内容，再审核，再执行。',
        logs: [{ time: '示例 00:02.800', level: 'info', message: '开始核对候选表达、当前要求和行动权限。', run: 'DEMO-001' }, { time: '示例 00:02.980', level: 'info', message: '审核通过，将批准内容交给执行。', run: 'DEMO-001' }],
        errors: [{ time: '示例 00:02.900', code: 'CONTENT_REJECTED', message: '候选表达与用户的明确要求冲突。', cause: '用户要求简短回应，草稿仍包含多次追问。', fix: '退回精简，并重新审核修改后的完整内容。', status: '已处理（示例）' }]
      },
      {
        id: 'execution', title: '执行 Agent', subtitle: '输出批准内容并记录结果', color: '#12a991', thinking: '规则执行 · 必要时轻思考',
        summary: '按审核结果输出文字、声音或动作，并记录是否真正送达。',
        duties: ['在发布前状态检查通过后执行获准行动。', '保持输出内容与审核版本一致。', '记录实际输出、送达状态和失败原因。'],
        powers: ['通过获准的渠道输出内容或执行动作。', '遇到停止指令、情境失效或送达失败时结束本轮执行。'],
        limits: ['不能自行更改已审核内容；需要改动时返回审核。', '不能发起额外互动，也不能把未送达当作已送达。'],
        model: { name: '待选择', route: '按批准内容输出以程序执行为主；必要的格式转换可用轻思考。' },
        tokens: { input: null, output: null, source: '未接入真实运行' },
        inputs: [{ from: '审核 Agent', data: '已批准的具体内容、版本与执行范围。' }, { from: '用户 / 场景事件', data: '发布前最新状态、停止要求与互动额度。' }],
        outputs: [{ to: '用户', data: '本次获准的表达或动作。' }, { to: '反馈反思 Agent / 记忆整理 Agent', data: '实际输出、送达回执与对应事件标识。' }],
        parallel: '完成前台交付后，反馈反思与事实整理可在后台并行；本轮回应无需等待它们。',
        logs: [{ time: '示例 00:03.020', level: 'info', message: '发布前检查通过，按批准内容开始输出。', run: 'DEMO-001' }, { time: '示例 00:03.110', level: 'info', message: '记录已送达回执，交付本轮实际输出。', run: 'DEMO-001' }],
        errors: [{ time: '示例 00:03.080', code: 'DELIVERY_FAILED', message: '内容没有实际送达。', cause: '输出渠道不可用或任务已被取消。', fix: '记录未送达，不消耗试探额度，也不生成偏好学习样本。', status: '已处理（示例）' }]
      },
      {
        id: 'reflection', title: '反馈反思 Agent', subtitle: '在后台理解反馈与改进', color: '#d866b4', thinking: '重思考 · 后台静默',
        summary: '根据真实发生的互动与反馈，提出有证据的改进建议。',
        duties: ['判断反馈指向内容、态度、时机还是功能。', '保留替代解释与不确定性，避免过度归因。', '提出下一轮可验证的改进或低打扰试探问题。'],
        powers: ['提出策略、偏好或互动方式的更新建议。', '建议保留未知、补充证据或暂缓学习。'],
        limits: ['不能主动发言或直接覆盖长期记忆。', '没有回应保持未知，不能自动解释为讨厌或负反馈。'],
        model: { name: '待选择', route: '纠正、冲突或阶段结束后使用重思考；普通互动可只记录。' },
        tokens: { input: null, output: null, source: '未接入真实运行' },
        inputs: [{ from: '执行 Agent', data: '实际送达的内容、时间与执行结果。' }, { from: '用户 / 场景事件', data: '用户原话、明确反馈与后续场景变化。' }, { from: '记忆整理 Agent', data: '相关历史事实、偏好和现有版本。' }],
        outputs: [{ to: '审核 Agent', data: '更新建议、证据、置信程度与适用范围。' }, { to: '记忆整理 Agent', data: '待审核的反思草案；通过审核后才可提交更新。' }],
        parallel: '可与记忆模块的事实整理并行；最终偏好或策略更新要等待建议审核。',
        logs: [{ time: '示例 00:03.710', level: 'info', message: '读取本轮送达回执；暂未获得明确回应。', run: 'DEMO-001' }, { time: '示例 00:05.610', level: 'info', message: '反馈保持未知，建议仅归档事实，不更新长期偏好。', run: 'DEMO-001' }],
        errors: [{ time: '示例 00:04.200', code: 'EVIDENCE_MISSING', message: '反思引用的事件证据缺失。', cause: '建议无法关联到实际输出或用户原话。', fix: '撤回无依据推断，保留待核实问题；补齐证据后再分析。', status: '已处理（示例）' }]
      },
      {
        id: 'memory', title: '记忆整理 Agent', subtitle: '保存有来源、可追溯的记忆', color: '#6374db', thinking: '轻思考 · 规则提交',
        summary: '区分事实、明确偏好和暂定假设，为下一轮提供可靠上下文。',
        duties: ['按当前情境读取相关记忆与人物设定。', '整理本轮事实和原话，处理重复与冲突。', '保存来源、适用范围和版本，受控提交审核后的更新。'],
        powers: ['提出新增、合并、过期或待核实的记忆整理建议。', '在审核与版本检查通过后提交更新，供下一轮读取。'],
        limits: ['不能把暂定假设升级为已确认事实。', '旧版本不得覆盖新指令；最终提交保持单一写入顺序。'],
        model: { name: '待选择', route: '读取和整理使用轻思考；版本检查与写入由程序完成。' },
        tokens: { input: null, output: null, source: '未接入真实运行' },
        inputs: [{ from: '执行 Agent / 用户', data: '实际发生的事件、送达回执和用户原话。' }, { from: '反馈反思 Agent', data: '待核实的解释与更新建议。' }, { from: '审核 Agent', data: '已通过审核的更新内容与适用范围。' }],
        outputs: [{ to: '规划 Agent / 决策 Agent', data: '下一轮所需的人物设定、相关事实与有效偏好。' }, { to: '反馈反思 Agent', data: '可追溯的历史证据与版本信息。' }],
        parallel: '可先与反思并行整理事实；最终更新等待建议审核，并按版本顺序提交。',
        logs: [{ time: '示例 00:03.710', level: 'info', message: '开始整理送达事实，与后台反思并行。', run: 'DEMO-001' }, { time: '示例 00:05.950', level: 'info', message: '审核与版本检查通过，仅归档事实，供下一轮读取。', run: 'DEMO-001' }],
        errors: [{ time: '示例 00:05.900', code: 'VERSION_CONFLICT', message: '更新所依据的记忆版本已过期。', cause: '后台整理期间，用户给出了更新的明确要求。', fix: '保留新指令，将旧建议标为待重算，不覆盖现有记忆。', status: '已处理（示例）' }]
      }
    ]
  };
}());
