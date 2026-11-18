"""Read immutable experiment messages, verify arithmetic, and build the replay data."""
import json,hashlib,copy
from pathlib import Path
from driver import SNAPS,USERS
P=Path(__file__).resolve().parent
def read(name):return json.loads((P/name).read_text())
def write(name,data):(P/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
jobs={f.stem:json.loads(f.read_text()) for f in (P/'collected').glob('*.json')}
assert len(jobs)==7
for jid,n in jobs.items():
    raw=read('outbox/'+jid+'.json');inp=read('inputs/'+jid+'.json')
    assert n['output']==raw['result'] and n['completed_unix_ms']==raw['completed_unix_ms']
    assert n['input_messages']==inp['input_messages']
    assert abs(n['duration_ms']-(n['completed_unix_ms']-n['dispatch_unix_ms']))<.001
    assert n['token_usage'] is None
    n['input_sha256']=hashlib.sha256(json.dumps(n['input_messages'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
fast=read('deliveries/pair_fast.json');baseline=read('deliveries/pair_baseline.json')
r2=read('deliveries/R2.json');r3=read('deliveries/R3.json');stale=read('deliveries/stale_probe.json');race=read('memory_race_result.json')
events=[json.loads(s) for s in (P/'events.jsonl').read_text().splitlines()]
reply=fast['result']['reply']
assert reply==jobs['pair_review']['output']['approved_reply']==jobs['pair_execution']['output']['reply']==baseline['result']['reply']
assert jobs['pair_review']['output']['pass'] is True
start=jobs['pair_decision']['dispatch_unix_ms'];ready=jobs['pair_decision']['completed_unix_ms']
assert abs(fast['foreground_ms']-(fast['delivered_unix_ms']-start))<.001
assert abs(baseline['foreground_ms']-(baseline['delivered_unix_ms']-start))<.001
normal_bg_end=max(e['time_unix_ms'] for e in events if e.get('job_id') in ['async_memory','async_reflection'] and e['kind'] in ['memory_commit_gate','background_or_review_result'])
overlap=max(0,min(jobs[k]['completed_unix_ms'] for k in ['async_memory','async_reflection'])-max(jobs[k]['dispatch_unix_ms'] for k in ['async_memory','async_reflection']))
def code_nodes(rid,delivery,candidate):
    state=SNAPS[rid];t=delivery['delivered_unix_ms'];out=delivery['result'];before=delivery.get('accepted_unix_ms',t)
    shared={'round':rid,'effort':None,'requested_model':None,'token_usage':{'input':0,'output':0},'status':'completed','issues':[]}
    selected={'id':rid+'-rule-selection','role':'decision','implementation':'已知场景规则选择（测试入口指定事件类型）','input_messages':[{'id':rid+'-EVENT','from':'fixture_adapter','body':{'snapshot':state,'user_input':USERS[rid]}}],'output':candidate,'dispatch_unix_ms':delivery.get('queued_unix_ms',before),'completed_unix_ms':before,'duration_ms':None,**shared}
    gate={'id':rid+'-rule-gate','role':'review','implementation':'FastRuntime.deliver · 状态/证据/模板检查','input_messages':[{'id':rid+'-CANDIDATE','from':'decision','body':candidate}],'output':out,'dispatch_unix_ms':before,'completed_unix_ms':t,'duration_ms':out['processing_ms'],'timing_scope':'仅deliver内部perf_counter计时；包括模板构造，未单独拆分每项检查。',**shared}
    send={'id':rid+'-code-delivery','role':'execution','implementation':'确定性短模板输出到本机交付记录','input_messages':[{'id':rid+'-APPROVED','from':'rules','body':out}],'output':{'reply':out['reply'],'delivery':'simulated_local_record','autonomous_game_actions':[]},'dispatch_unix_ms':t,'completed_unix_ms':t,'duration_ms':None,'timing_scope':'发送为同一代码事务；未单独计时，也没有测网络、浏览器显示或写盘完成。',**shared}
    return [selected,gate,send]
r1_nodes=code_nodes('R1',fast,jobs['pair_decision']['output']);r1_nodes[0]=jobs['pair_decision']
r2_nodes=code_nodes('R2',r2,r2['candidate'])+[jobs['async_reflection'],jobs['async_memory']]
r3_nodes=code_nodes('R3',r3,r3['candidate'])
rules_scope='本机命令入队至闸门返回；不含写盘完成、网络或界面。'
rounds=[
 {'id':'R1','title':'出生引导 · 一次模型','user_input':USERS['R1'],'route':'model','reply':reply,'foreground_ms':fast['foreground_ms'],'full_loop_ms':fast['foreground_ms'],'timing_scope':'从调度请求至本机闸门返回；含独立会话和工具开销，不含记录写盘完成。','background_ms':0,'nodes':r1_nodes,'notes':['本轮首条交付只调用一次low决策；文字由固定模板生成。','本轮未触发规划或后台反思。额外模型审核/执行属于配对对照分支，不计入快速路径。']},
 {'id':'R2','title':'任务窗口 · 规则直达','user_input':USERS['R2'],'route':'rules','reply':r2['result']['reply'],'foreground_ms':r2['foreground_ms'],'full_loop_ms':normal_bg_end-r2['queued_unix_ms'],'timing_scope':rules_scope,'background_ms':normal_bg_end-r2['delivered_unix_ms'],'nodes':r2_nodes,'notes':['后置反馈为“先教我一步”；实际medium记忆正确保存为当前轮次。','正常反思与记忆有实际区间重叠 '+str(round(overlap,3))+' ms。','本轮正常后台结束后才出现R3；R3与单独发起的旧决策探针重叠。']},
 {'id':'R3','title':'战斗提醒 · 规则直达','user_input':USERS['R3'],'route':'rules','reply':r3['result']['reply'],'foreground_ms':r3['foreground_ms'],'full_loop_ms':r3['foreground_ms'],'timing_scope':rules_scope,'background_ms':0,'nodes':r3_nodes,'notes':['这条回复只提醒已确认不可用的技能；没有解决整个战斗，也没有证明玩家脱战。','交付时旧决策stale_decision尚未结束；返回后因状态版本2→3被拒绝。','本轮未启动新的后台任务。']}
]
normal_model_sum=sum(jobs[k]['duration_ms'] for k in ['pair_decision','pair_review','pair_execution'])
checks=[
 {'id':'integrity','title':'7份模型原始结果与输入可复核','pass':True,'evidence':'逐项核对保存输入、outbox输出和原始结束时间戳，未改写模型结果。'},
 {'id':'paired_reply','title':'配对分支使用同一句回复','pass':True,'evidence':'快速模板、模型审核批准、模型执行结果逐字一致。'},
 {'id':'one_model','title':'R1快速路径只调用一次模型','pass':True,'evidence':'decision low之后由确定性规则和模板完成；两个后续模型调用只属于对照。'},
 {'id':'rule_cases','title':'任务与无蓝两个已知规则场景成功交付','pass':r2['result']['accepted'] and r3['result']['accepted'],'evidence':'本机返回耗时分别 '+str(round(r2['foreground_ms'],3))+' ms / '+str(round(r3['foreground_ms'],3))+' ms；不等于用户端时延。'},
 {'id':'foreground_during_old_task','title':'旧决策未结束时仍可处理新前台事件','pass':jobs['stale_decision']['dispatch_unix_ms']<r3['delivered_unix_ms']<jobs['stale_decision']['completed_unix_ms'],'evidence':'按实际时间戳核对，R3交付时stale_decision仍未生成结果。'},
 {'id':'stale_output_blocked','title':'进入战斗后不发送旧的接任务建议','pass':stale['result']['accepted'] is False and stale['result']['reason']=='state_version_mismatch','evidence':stale},
 {'id':'late_memory_blocked','title':'提交前出现新偏好，旧补丁被拒绝','pass':race['commit_result']['accepted'] is False and race['commit_result']['reason']=='memory_version_mismatch','evidence':race},
 {'id':'background_overlap','title':'反思与记忆实际并发','pass':overlap>0,'evidence':'真实任务记录区间重叠 '+str(round(overlap,3))+' ms，仍包含工具开销。'},
 {'id':'runtime_tests','title':'14项确定性业务边界测试','pass':True,'evidence':'详见runtime-tests.txt；包含静音、过期状态、偏好范围、消息副本隔离、受控异步事件。'},
 {'id':'first_useful_target','title':'本次模型路径达到3秒内首个交付目标','pass':fast['foreground_ms']<=3000,'evidence':'本次 '+str(round(fast['foreground_ms']/1000,3))+' 秒，仍未达标；缺少直接API通道，不能推断生产API时延。'},
 {'id':'memory_generation_overlap','title':'真实模型生成期间到达新偏好','pass':race['new_preference_arrived_before_model_result'],'evidence':'本次新偏好晚于模型结果约 '+str(round(race['new_preference_unix_ms']-race['model_completed_unix_ms']))+' ms，只验证结果生成后、提交前的版本冲突。'},
 {'id':'production_e2e','title':'真实游戏与用户界面端到端验证','pass':None,'evidence':'尚未接入真实客户端，也未测API纯推理、用户端显示、语音、真实网络时延。'}
]
meta={'model':'gpt-6.1-sol','requested_model':'gpt-6.1-sol','provider_resolved_model':None,'formal_model_calls':7,'call_count_definition':'这里的调用数指显式发起的独立Agent任务数；未计量任务内部的底层API请求次数。','optimized_business_model_calls':3,'paired_control_calls':2,'stale_result_probe_calls':2,'token_note':'模型通道没有返回Token用量，模型记录保持null；规则和模板没有模型调用。','methodology':'真实Sol独立会话；游戏/用户/事件路由为合成测试；正常前台与后台加配对分支及过期结果探针。','isolation':'所有业务worker都fork_turns=none；只收到显式消息，禁止读取文件、网页、其他Agent会话，仅向专属outbox发送结果。底层文件系统共享，非OS沙箱。','direct_api_available':False,'timing':'模型记录从准备dispatch到worker结果时间，含转交、排队、工具开销；本机规则从命令写队列前时间到deliver返回。交付时间早于交付记录写盘，不含界面和网络。','normal_loop_definition':'R1/R3没有新后台，完成于前台闸门返回；R2结束于正常反思/记忆结果处理完成，不包括独立故障探针。','routing':'已知事件类别由测试入口显式指定；本版只覆盖4个动作模板，未验证开放式自然语言路由、自由聊天或自主动态规划。','model_comparison':'配对分支共用一次低思考决策输出。64.882秒串行分支包含两次额外模型任务和root调度，不可当稳定模型加速比。','memory_race_limitation':race['scope'],'scope_gate_limit':'当前一步/长期一步的规则针对测试短语，并非通用语义审核器。','rules_benchmark_limit':'500次相同已知输入的函数微基准，不能推广为网络或产品P95。'}
pair={'candidate_reply':reply,'fast_ms':fast['delivered_unix_ms']-ready,'baseline_ms':baseline['delivered_unix_ms']-ready,'scope':'两列从共同决策结果的worker时间戳开始，到各分支本机闸门返回；快速分支包含outbox轮询读取，不含交付记录写盘完成。','total_fast_ms':fast['foreground_ms'],'total_baseline_ms':baseline['foreground_ms'],'model_job_intervals_sum_ms':normal_model_sum,'coordinator_gaps_ms':baseline['foreground_ms']-normal_model_sum,'baseline_nodes':[jobs['pair_review'],jobs['pair_execution']],'notes':['从首个调度开始的总等待：快速 '+str(round(fast['foreground_ms']/1000,3))+' 秒；串行对照 '+str(round(baseline['foreground_ms']/1000,3))+' 秒。','串行对照中另含 '+str(round((baseline['foreground_ms']-normal_model_sum)/1000,3))+' 秒跨调用/采集调度间隔；模型任务区间内也含工具开销。','只有单次配对，且使用相同决策产出；不是两套完整系统的独立生产API A/B，也不是自由文本生成对照。']}
notes=['本次展示的回复由固定模板生成，Sol只选择动作；不能把规则场景的速度推广到任意聊天。','普通后台记忆返回及时并提交成功；提交冲突由单独memory_race试验验证，未改写普通记录。','未观察到memory_race中模型计算与新偏好重叠；原先scope文字已按时间戳纠正，原件单独保留。','R3只给出了一个有依据的即时提醒，尚未获得更完整战术建议；玩家后续结果未知。','前台实际调用通道仍未达到1–3秒目标。下一步需要直接API/实际客户端环境测量。']
data={'meta':meta,'rounds':rounds,'pair':pair,'rule_benchmark':read('rule-benchmark.json'),'checks':checks,'event_log':events,'probes':{'stale_decision':jobs['stale_decision'],'stale_delivery':stale,'memory_race':jobs['memory_race'],'memory_race_result':race},'model_jobs':list(jobs.values()),'notes':notes}
write('results.json',data)
write('verification.json',{'raw_model_records_verified':7,'timing_arithmetic_verified':True,'paired_replies_identical':True,'checked_false_items':[c['id'] for c in checks if c['pass'] is False],'unmeasured_items':[c['id'] for c in checks if c['pass'] is None],'results_sha256':hashlib.sha256((P/'results.json').read_bytes()).hexdigest()})
print(json.dumps({'pair_total_fast_ms':pair['total_fast_ms'],'pair_total_baseline_ms':pair['total_baseline_ms'],'pair_after_candidate_fast_ms':pair['fast_ms'],'pair_after_candidate_baseline_ms':pair['baseline_ms'],'rounds':[{k:r[k] for k in ['id','foreground_ms','full_loop_ms','background_ms']} for r in rounds],'failed_checks':[c['id'] for c in checks if c['pass'] is False]},ensure_ascii=False))
