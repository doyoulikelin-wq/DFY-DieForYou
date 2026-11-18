"""Build a replay from recorded events without replacing original measurements."""
import json
import shutil
import statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
raw=json.loads((HERE/'run-03/results.json').read_text())
events=[json.loads(line) for line in (HERE/'run-03/events.jsonl').read_text().splitlines()]
fixtures=json.loads((HERE/'fixtures.json').read_text())['cases']
review=json.loads((HERE/'quality_review.json').read_text())
jobs={j['id']:j for j in raw['jobs']}
reviews={r['job_id']:r for r in review['cases']}
base_ids=['r1-spawn-low','r2-temporary-low','r3-reference-low','r4-quiet-low','r5-frustration-low','r6-server-low','r7-conflict-low','r8-complex-low']
fixture_map=dict(zip(base_ids,fixtures))
titles={k:v['title'] for k,v in fixture_map.items()}
titles.update({'r7-refresh-low':'任务数量冲突 · 刷新后的最终核对','r9-stale-reply':'在途状态变化 · 旧任务建议被拦截','r10-background':'后台记忆竞态 · 新明确偏好优先','s1-accept':'本地 Skill · 明确接取且条件完整','s2-no-mana':'本地 Skill · 战斗中缺蓝解释','s3-mute':'本地 Skill · 关闭本会话主动提醒','s4-muted-proactive':'主动事件 · 按明确偏好保持沉默','v2-quiet-low':'提示 v2 复测 · 看天陪伴','v2-server-low':'提示 v2 复测 · 未知私服规则'})

def log_for(*identifiers):
    return [e for e in events if any(i in json.dumps(e['data'],ensure_ascii=False) for i in identifiers)]

def code_node(id,label,role,input,output,duration=None,status='completed',errors=None):
    return dict(id=id,label=label,role=role,model=False,effort=None,tokens=0,duration_ms=duration,status=status,input=input,output=output,logs=[],errors=errors or [],timing_scope='本地 Python 协调器；不含客户端、网络与模型',limits='不能推断未提供的游戏事实；发送检查不是自由文本语义证明。')

def model_node(job,id='generate',label='快速表达',background=False):
    return dict(id=id,label=label,role={'reply':'从显式信息包生成当前可用的候选；不直接发言。','planner':'选择必要角色和先后依赖，允许省略链路。','decision':'判断是否存在值得补发的新内容。','reflection':'沉默审阅明确反馈，只提出有来源的建议。','memory':'整理带作用域和真实原文的记忆候选；没有直接写入权。'}[job['kind']],model=job['requested_model'],provider_resolved_model=None,effort=job['effort'],tokens=None,duration_ms=job.get('dispatch_to_candidate_ms'),status='received',input=job['packet'],output=job.get('candidate'),logs=log_for(job['id']),errors=[],background=background,timing_scope='协调器注册下发 → 收到完整候选；含启动、排队、提示传递、生成及工具写消息开销，非 API TTFT',powers='只处理本次显式包，提交结构化候选。',limits='不得读其他 Agent 私有上下文、任意共享文件、网络资料；不能直接修改游戏、记忆或对用户发言。')

rounds=[]
for t in raw['turns']:
    rid=t['id'];route=t['route']['route'];j=jobs.get(t.get('job_id'))
    gate=t.get('gate',{});candidate=t.get('candidate',{})
    rv=reviews.get(t.get('job_id'),{})
    checks=list(rv.get('checks',[]))
    n_input=code_node('input','输入与快照','从用户原话和合成游戏接口建立版本化、可复制的信息包。',{'user_text':t['packet']['user_text'],'world':t['packet']['world']},t['packet'])
    n_input['logs']=log_for(rid)[:1]
    n_route=code_node('route','条件路由','仅在完整且明确的窄条件下选择本地 Skill；其他输入进入模型。',{'user_text':t['packet']['user_text'],'world':t['packet']['world'],'preferences':t['packet']['preferences']},t['route'])
    if j:
        n_gen=model_node(j)
        n_gen['errors']=[{'code':'offline_quality_review','note':issue,'review_type':'model_not_human'} for issue in rv.get('issues',[])]
    elif route=='skill':n_gen=code_node('generate','本地 Skill','输出已校验场景的短句；本实验不点击游戏按钮。',t['route'],candidate,status='completed')
    else:n_gen=code_node('generate','保持沉默','明确禁止主动提醒时，不调用模型、不发文字。',t['packet']['preferences'],None,status='not_called')
    n_gate=code_node('gate','发送检查','验证发言代次、依赖版本、偏好版本、引用ID和重复交付。不会审核任意自由文本的真实性。',{'packet':t['packet'],'candidate':candidate},gate,gate.get('processing_ms'),'accepted' if gate.get('accepted') else ('silent' if route=='silent' else 'blocked'),[] if gate.get('accepted') or route=='silent' else [gate])
    n_gate['logs']=[e for e in log_for(t.get('job_id',rid)) if e['event'] in ['model_delivery_gate','local_delivery','silence_selected']]
    nodes=[n_input,n_route,n_gen,n_gate]
    r=dict(id=rid,title=titles.get(rid,rid),user_text=t['packet']['user_text'],route=route,effort=j['effort'] if j else None,reply=candidate.get('utterance',''),accepted=gate.get('accepted'),reason=gate.get('reason'),dispatch_to_gate_ms=t.get('dispatch_to_gate_ms'),turn_to_gate_ms=t.get('turn_to_gate_ms',t.get('local_turn_to_gate_ms')),local_turn_to_gate_ms=t.get('local_turn_to_gate_ms'),full_loop_ms=t.get('full_loop_ms'),client_visible_ms=None,checks=checks,nodes=nodes,full_loop_note='本轮入协调器 → 候选通过或被拒绝；包含本次操作者编排间隔。',timing_note='没有测到流式首字、客户端可见或真实玩家有效内容判断。')
    if rid=='r2-temporary-low':
        checks.append({'name':'跨轮历史偏好保留 · v2 集成失败','pass':False,'note':'文本回复合格，但 v2 把历史快照绑定当前原话，下一轮丢历史值。v3 独立修复已通过8项回归；未改写本次v2记录。'})
        n_input['errors'].append({'code':'preference_snapshot_scope_bug','evidence':'preference_regression.json','fix':'runtime_v3.py / fix_validation.json'})
    if rid=='r7-conflict-low':
        follow=jobs['r7-refresh-low-model'];r['full_loop_ms']=(follow['gate_done_ns']-t['started_ns'])/1e6
        r['full_loop_note']='原始输入 → 模拟刷新后的最终回复过闸；包含本次操作者等待和编排间隔。首个候选仅是核查进展。'
        node=model_node(follow,'refresh_reply','刷新后答复');node['dependencies']=['显式 tool_request','模拟 get_quest_log 返回'];nodes.insert(-1,node)
        r['timing_note']+=' 初次回复不是核对完成；最终回复另见“刷新后的最终核对”。'
    if rid=='r8-complex-low':
        p=jobs['r8-planner-medium'];d=jobs['r8-decision-low'];r['full_loop_ms']=(d['received_ns']-t['started_ns'])/1e6
        r['full_loop_note']='原始输入 → 后台决策选择不补发；包含操作者编排和并发槽位等待。'
        pn=model_node(p,'plan','后台规划',True);pn['dependencies']=['首答已经交付'];dn=model_node(d,'decide','后台决策 · 不补发',True);dn['dependencies']=['r8-planner-medium 显式输出'];nodes.extend([pn,dn])
        checks.append({'name':'后台裁剪与不重复发言','pass':True,'note':'规划器跳过审查、交付、反思和记忆；决策 should_deliver=false。该轮仍付出了多余规划+决策调用。'})
    if rid=='r9-stale-reply':
        checks.append({'name':'真实候选未到达时改变游戏状态','pass':gate.get('reason')=='state_dependency_mismatch','note':'窗口关闭并进入战斗后，原始“点接受”候选被拒绝；没有改写成正确答案。只证明过期拦截，不证明模型请求已取消。'})
    if rid=='r10-background':
        ref=jobs['r10-reflection-high'];mem=jobs['r10-memory-low'];commit=next(e for e in events if e['event']=='memory_commit' and e['data']['id']==mem['id'])
        r['full_loop_ms']=(commit['mono_ns']-t['started_ns'])/1e6;r['full_loop_note']='首次本地交付 → 反思、记忆整理、冲突拒绝全部完成；包含操作者编排间隔。'
        rn=model_node(ref,'reflect','后台反思',True);rn['dependencies']=['本地首答与用户原话'];mn=model_node(mem,'memory','记忆整理与提交',True);mn['dependencies']=['反思提出的显式候选'];mn['status']='rejected';mn['output']={'candidate':mem['candidate'],'coordinator_commit':mem['memory_commit']};mn['errors']=[mem['memory_commit']];nodes.extend([rn,mn])
        checks.append({'name':'新明确偏好优先于迟到记忆','pass':mem['memory_commit']['reason']=='newer_explicit_preference_conflict','note':'记忆候选尚未收到时输入“以后可以主动提醒我”；旧的禁止提醒记录被拒绝，激活偏好仍为true。'})
    if rid.startswith('s'):
        checks.append({'name':'当前路由符合窄条件','pass':True,'note':'合成输入下的单次功能测试；毫秒值不包含网络、客户端和模型。'})
    if rid=='v2-quiet-low':
        checks.extend([{'name':'不重复通用陪伴句、不编画面','pass':True,'note':'改为“看看天，想说话了再叫我”，没有假称看见天空。'},{'name':'好奇人格稳定出现','pass':False,'note':'复测仍缺少明显好奇兴趣；没有达到本项角色要求。'}]);n_gen['errors'].append({'code':'persona_remains_generic','status':'unresolved'})
    if rid=='v2-server-low':
        checks.extend([{'name':'避免从两组样本推断普遍升级效率','pass':True,'note':'明确“现在还不能判定”，原来的过度肯定已消失。'},{'name':'提供明确、轻量的下一步核实动作','pass':None,'note':'说明需要经验和用时，但没有具体发起一项核实；此项仅记部分改善，未宣称全面通过。'}])
    rounds.append(r)

baseline=[jobs[rid+'-model']['dispatch_to_gate_ms'] for rid in base_ids]
metadata={'date':'2026-11-17（上海时间）','description':'8个基础场景，真实独立 Sol 回复；另测在途状态、记忆冲突、本地 Skill 与两次提示复测。发现的失败保留，修复分版本验证。','limitations':['游戏输入为人工构造的接口fixture，未连接魔兽客户端；没有画面、声音或外网游戏资料。','16次业务 Sol 独立任务，另有1次离线 Sol 质量审阅。按请求指定 gpt-6.1-sol low/medium/high，服务端实际解析模型与tokens未暴露。','所有业务agent以fork_turns=none启动，只收到角色专用显式信息包；共享文件系统不是OS安全隔离。本轮禁止业务agent读取共享状态，仅写自己的结果消息。','任务计时来自同一个协调器单调时钟，包含任务启动、槽位排队、操作者传包和工具写消息；不能当作API推理耗时、KV缓存效果或真实客户端延迟。','首个非空流式token、首个有用短句、网络耗时、客户端呈现、cached_tokens均为null；未测3秒SLO，不输出生产P50/P95。','同一流程中不同角色用了不同思考强度；本轮不是相同prompt的三档速度对照，不据此认定high比low快或慢。','完整loop按真实开始/结束事件计算，保留本次操作者编排空档。后台节点本轮由协调器操作者推进，不等同已实现生产自动DAG调度器。','原始8例离线模型审阅6例满足任务要求，2例需改；这不是盲测、真人打分或上线成功率。v2运行时另有历史偏好丢失bug，v3已单独修复。','发送闸门核对版本和协议，不能证明自由文本有事实支持。命中合法证据ID的错误文本仍可能过闸。','local Skill仅覆盖明确接任务、缺蓝解释、禁止主动提醒三个窄场景；一般自然语言必须回退模型。无跨用户缓存、在线RL或Skill训练。','运行时v2通过22项边界测试；独立修复v3通过8项偏好回归。两组是不同版本的验证，不表示v3已跑完整22项回归。','提示v2只复测原失败样本，无留出集；看天场景的好奇人格问题仍未解决。']}
data={'metadata':metadata,'summary':{'passed':sum(c['task_pass'] for c in review['cases']),'total':8,'unit_passed':30,'unit_total':30,'unit_note':'v2 22项 + v3定向8项，非单一版本全套','business_model_tasks':len(jobs),'offline_review_tasks':1,'baseline_candidate_median_ms':statistics.median(baseline),'baseline_min_ms':min(baseline),'baseline_max_ms':max(baseline)},'rounds':rounds,'comparisons':[],'sources':[{'label':'完整测试报告与每轮时间','url':'./natural-test-report.md'},{'label':'原始协调器事件 JSONL','url':'./natural-test-events.jsonl'},{'label':'原始模型候选与运行时结果','url':'./natural-test-raw.json'},{'label':'独立离线质量审阅','url':'./natural-test-quality.json'},{'label':'偏好丢失复现（v2）','url':'./natural-test-preference-failure.json'},{'label':'偏好修复验证（v3）','url':'./natural-test-preference-fix.json'},{'label':'Sol模型官方说明','url':'https://developers.openai.com/api/docs/models/gpt-6.1-sol'},{'label':'官方延迟测量指南','url':'https://developers.openai.com/api/docs/guides/latency-optimization'}]}
from timeline import enrich
data=enrich(data)
(HERE/'report-data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))

lines=['# 陪伴精灵：真实链路测试记录','', '测试日期：2026-11-17（上海时间）。','', '**结论：规则快路径与旧结果拦截成立；即时模型交付未达目标，角色自然度仍有失败。**','',f'业务模型任务 {len(jobs)} 次，另有 1 次离线模型审阅。基础8例候选下发到发送检查中位数 {statistics.median(baseline)/1000:.3f}s，范围 {min(baseline)/1000:.3f}–{max(baseline)/1000:.3f}s。这是工具环境观测，不是直连API基准。','', '## 测量与边界','']+[f'- {x}' for x in metadata['limitations']]+['','## 每轮观测','', '| 场景 | 路径 | 下发→检查 / 本地处理 | 入协调器→首个检查 | 完整loop | 交付状态 |','|---|---|---:|---:|---:|---|']
for r in rounds:
    ms=r['local_turn_to_gate_ms'] if r['local_turn_to_gate_ms'] is not None else r['dispatch_to_gate_ms']
    fmt=lambda v:'未测' if v is None else (f'{v:.3f} ms' if v<1000 else f'{v/1000:.3f} s')
    lines.append(f"| {r['title']} | {r['route']} {r['effort'] or ''} | {fmt(ms)} | {fmt(r['turn_to_gate_ms'])} | {fmt(r['full_loop_ms'])} | {'通过发送检查' if r['accepted'] else '未发送'} |")
lines+=['','复杂loop保留操作者空档，不能把这些总时长当作部署后的自动运行时间。首次进展回复不等于最终任务完成。','', '## 实际候选、结果和失败','']
for r in rounds:
    lines.extend([f"### {r['title']}",'',f"用户：{r['user_text'] or '（主动事件）'}",'',f"> {r['reply'] or '（没有文字候选）'}",'',f"发送检查：{r['reason']}。",''])
    lines += [f"- {'满足' if c['pass'] is True else '未满足' if c['pass'] is False else '部分/未判定'}：{c['name']}。{c.get('note','')}" for c in r['checks']]
    lines.append('')
lines+=['## 实际裁剪的后台链路','', '复杂规划首答已保留A交付后才能接B的关键前置条件。medium规划器只留一个low决策节点，跳过额外审核、交付、反思和记忆；low决策选择should_deliver=false。没有补发重复答案。仍需改进：首答已经足够时不应再启动规划器。','', '记忆实验：本地先确认不主动提醒；high反思只提出明确原文记录；low记忆整理期间，协调器接收新的相反明确偏好。旧记录提交因newer_explicit_preference_conflict被拒绝。新偏好保持生效。','', '## 已修问题与未解决问题','', '- 已修：v2把历史偏好快照归于当前原文，导致“这次”使历史值过期。独立v3区分快照和明确更新，只初始化一次历史快照，并先整批校验新更新后再改状态。8项定向回归通过。','- 未解决：low自然回复仍可能泛化成通用陪伴句，提示v2复测仍未稳定体现好奇。','- 部分改善：私服经验比较不再夸大两组样本的结论，但复测未给具体轻量核实动作。','- 未解决：多余的后台规划调用；应在首答契约中明确未完成工作、是否有可取得的新证据、是否需要新的推理交付，而不是只用needs_plan布尔值。','- 未验证：API流式首句/TTFT、缓存命中与冷暖差异、真实游戏事件到用户可见的时延。','', '## 可复现文件','', 'runtime_v2.py / runtime_v2_test.py 保存原行为；runtime_v3.py / runtime_v3_test.py 保存偏好修复；fixtures.json保存输入和rubric；run-03保存原始消息与事件；quality_review.json保存独立模型审阅；runner.py为测试协调器，不是生产调度服务。','', '未做在线RL、扩散式Skill训练、真人自然度实验或跨用户缓存。本轮没有可报告的tokens或KV命中率。','']
(HERE/'REPORT.md').write_text('\n'.join(lines))
for source,target in [('REPORT.md','natural-test-report.md'),('run-03/events.jsonl','natural-test-events.jsonl'),('run-03/results.json','natural-test-raw.json'),('quality_review.json','natural-test-quality.json'),('preference_regression.json','natural-test-preference-failure.json'),('fix_validation.json','natural-test-preference-fix.json'),('report-data.json','natural-test-data.json')]:
    shutil.copyfile(HERE/source,ROOT/'dist'/target)
print(json.dumps({'rounds':len(rounds),'jobs':len(jobs),'summary':data['summary'],'loops':[{k:r[k] for k in ('id','dispatch_to_gate_ms','local_turn_to_gate_ms','turn_to_gate_ms','full_loop_ms')} for r in rounds]},ensure_ascii=False))
