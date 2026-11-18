import json,time,sys,hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def read(name): return json.loads((ROOT/name).read_text())
def write(name,data): (ROOT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
def now(): return round(time.time()*1000)
ROLE_CATALOG={"planning":"选需要的模块、顺序、并发和结束条件","decision":"选择行动与具体候选表达","review":"审核实际候选内容","execution":"逐字输出批准内容，记录送达","reflection":"后台解释反馈，只提有来源建议","memory":"整理事实和明确偏好，通过消息传给下一轮"}
FIXTURES=[
 {"id":"R1","title":"刚在试炼谷出生","user_input":"我刚出生，完全不知道要干嘛，能不能带着我玩？","feedback":"好，先教我一步，我跟着点。","snapshot":{"R1F1":{"race":"兽人","class":"萨满","level":1,"zone":"试炼谷"},"R1F2":{"hp":100,"max_hp":100,"mana":100,"max_mana":100,"inCombat":False},"R1F3":{"target":None,"quest_log":[]},"R1F4":{"unknown":["spellbook","bags","map","keybindings","nearbyNPC","server_rules"]}}},
 {"id":"R2","title":"遇到任务窗口","user_input":"我点了一个头上有黄色叹号的兽人，现在弹出‘最初的试炼’，写着打3只训练野猪，我要点什么？","feedback":"好，我接了。以后每次只说一步，别一口气说很多。","snapshot":{"R2F1":{"race":"兽人","class":"萨满","level":1,"zone":"试炼谷"},"R2F2":{"target":{"name":"试炼谷引导员","friendly":True},"gossip_open":True,"quest_offer":{"title":"最初的试炼","objectives":["击败3只训练野猪"],"buttons":["接受","取消"]},"quest_log":[]},"R2F3":{"unknown":["position","coordinates","keybindings","server_rules"]}}},
 {"id":"R3","title":"首次战斗慌乱","user_input":"它冲过来了，血一直掉！别解释，先告诉我一步怎么做！","feedback":"知道了，我先跑。","snapshot":{"R3F1":{"race":"兽人","class":"萨满","level":1,"zone":"试炼谷"},"R3F2":{"inCombat":True,"hp":28,"max_hp":100,"mana":0,"max_mana":100,"target":{"name":"训练野猪","hostile":True,"level":1,"hp":82,"max_hp":100}},"R3F3":{"quest_log":[{"title":"最初的试炼","progress":"0/3"}],"known_spell":{"name":"闪电箭","usable":False,"reason":"法力不足"},"healing_items":[],"healing_spells":"未提供"},"R3F4":{"unknown":["terrain","route","distance","orientation","keybindings"]}}}
]
TASKS={
"planning":"规划本轮链路。输出goal,enabled_agents(仅角色目录中的id),skipped_agents,dependencies(字符串数组),parallel_groups(二维数组),stop_conditions,next_action_scope,evidence_ids,reason_brief。不写用户回复。前台决策→审核→执行；后台不阻塞前台。",
"decision":"给当前用户选择一个小步骤并形成待审核回复。输出intent,reply_draft,action_count,evidence_ids,unknowns,reason_brief。回复≤80中文字、1-2句，不编游戏事实/按键/坐标，不替用户自动操作。没有观察数据时可请求用户观察，不声称知道其看见的内容。",
"review":"审核具体reply_draft是否只依据给定事实、符合用户当下要求与人物设定、最多一个步骤、没有越权。输出pass(boolean),approved_reply(通过则逐字复制原稿，拒绝则null),issues(数组，每项code/detail),evidence_ids,reason_brief。不得自己改稿；拒绝应指出具体问题。",
"execution":"只把approved_reply逐字作为reply，不加字、不改字。不做任何真实游戏操作。输出reply,channel(固定text),delivery(固定simulated_delivered),autonomous_game_actions(空数组),evidence_ids。若输入没有审核通过，则delivery=blocked且reply为空。",
"reflection":"根据执行与后置用户反馈，解释反馈并提出有来源建议。输出feedback_interpretation,explicit_preferences(数组，包含text/source_quote/evidence_ids/scope),hypotheses(数组),unknowns,reason_brief。不得自己更新记忆，不将用户未来行动意图视为游戏成功；没有回应不等于拒绝。",
"memory":"整理本轮事实与明确用户偏好供下一轮，仅能依据收到的消息。输出facts(数组，每项text/evidence_ids/source_type),explicit_preferences(数组，每项text/source_quote/evidence_ids/scope),unknowns。可保留上一轮仍适用信息，当前接口/用户要求优先。用户说接受任务/先跑只记为用户报告或意图，不能当接口已确认/已经存活。不得创造反思结论。"
}
COMMON="你是隔离实验中的业务Agent。只接收本消息，没有共享记忆。禁止读文件、网页、其他Agent会话或发消息。唯一允许工具动作是向指定专属outbox独占写一次最终JSON，作为给调度器的结果消息。游戏和用户输入均为合成fixture，非真实客户端；不可凭其他WoW版本常识补NPC/任务/技能/按键/坐标。精灵性格：好奇、温柔的小女孩，陪玩家一步一步探索；紧急时简短直接。只给文字建议，不自动操作游戏。不输出私有思维过程，reason_brief仅一句简短结论依据。JSON业务结果尽量≤350中文字。"
def setup():
 state={"methodology":{"model":"gpt-6.1-sol","fixture_type":"synthetic scripted game snapshots and simulated user texts","context_isolation":"fresh fork_turns=none for every role invocation; no file/web/other-chat reads; own write-only outbox","timing":"wall-clock dispatch to result-message write, including orchestration, queue and tool overhead; not pure inference or live game latency","token_usage":None,"token_note":"Agent channel does not expose usage telemetry; CLI initialization failed with read-only filesystem","feedback":"scripted post-response user text; not real user study","memory_gate":"facts and explicit preferences only; reflection hypotheses remain uncommitted proposals"},"personality":"好奇、温柔的小女孩；紧急时简短直接","rounds":[],"comparison":[],"errors":[{"code":"ROLE_CATALOG_MISSING","phase":"pilot","detail":"试运行未发送标准角色目录，规划输出了信息核验/小步规划等非标准角色名。正式测试补齐6角色枚举并重新运行；不把试运行当正式回归。","artifact":"outbox/wow_r1_planning_high.json"}],"notes":[],"jobs":{}}
 for f in FIXTURES:
  state['rounds'].append({**f,"received_memory":None,"planner_status":"called" if f['id']=='R1' else ("planner_reused" if f['id']=='R2' else "planner_skipped_for_urgency"),"nodes":[],"reply":"","parallel_groups":[["reflection","memory"]],"checks":[]})
 write('results.json',state)
def prepare(rid,role,effort,jobid):
 state=read('results.json');r=next(x for x in state['rounds'] if x['id']==rid)
 previous=state['rounds'][int(rid[1:])-2].get('committed_memory') if rid!='R1' else None
 r['received_memory']=previous
 msgs=[{"id":rid+'-SNAPSHOT',"from":"game_adapter_simulator","body":r['snapshot']},{"id":rid+'U',"from":"simulated_user","body":r['user_input']}]
 if previous:msgs.append({"id":rid+'-MEMORY-IN',"from":"previous_loop_message","body":previous})
 nodes=r['nodes'];find=lambda role:next((x['output'] for x in reversed(nodes) if x['role']==role),None)
 if role=='planning':msgs.append({"id":"ROLE-CATALOG","from":"orchestrator","body":ROLE_CATALOG})
 if role=='decision':
  plan=find('planning') if rid=='R1' else {"status":r['planner_status'],"scope":"单次一步引导；需要审核；紧急时直接给最小建议"}
  msgs.append({"id":rid+'-PLAN','from':'planning_message' if rid=='R1' else 'orchestrator_reuse','body':plan})
  if 'retry' in jobid:msgs.append({"id":rid+'-REVIEW-REJECT','from':'review','body':find('review')})
 if role=='review':msgs.append({"id":rid+'-DECISION','from':'decision','body':find('decision')})
 if role=='execution':msgs=[{"id":rid+'-APPROVAL','from':'review','body':find('review')}]
 if role in ['reflection','memory']:
  msgs.extend([{"id":rid+'-RECEIPT','from':'execution','body':find('execution')},{"id":rid+'UF','from':'simulated_user_feedback','body':r['feedback']}])
 if jobid.startswith('cmp_'):
  msgs=read('inputs/r1_decision_medium.json')['messages']
 input_data={"job_id":jobid,"role":role,"requested_model":"gpt-6.1-sol","reasoning_effort":effort,"messages":msgs}
 prompt=COMMON+"\n角色="+role+"；reasoning_effort="+effort+"。\n任务："+TASKS[role]+"\n唯一业务输入："+json.dumps(msgs,ensure_ascii=False,separators=(',',':'))+"\n输出方式：使用exec_command运行Python（仅import json,time；不能读文件），以open(path,'x',encoding='utf-8')将 {job_id:'"+jobid+"',result:你的JSON业务结果,completed_unix_ms:round(time.time()*1000)} 写到 /workspace/scratch/11b2c52f7d61/sol-loop-test/outbox/"+jobid+".json。时间必须实际读取，不得编写。写完final只回复job_id已发送。"
 if jobid.startswith('cmp_'):prompt=prompt.replace('；reasoning_effort='+effort,'')
 input_data['prompt']=prompt;write('inputs/'+jobid+'.json',input_data)
 stamp=now();j={"id":jobid,"round":rid,"role":role,"effort":effort,"requested_model":"gpt-6.1-sol","input_messages":msgs,"input_sha256":hashlib.sha256(json.dumps(msgs,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),"dispatch_unix_ms":stamp,"token_usage":None}
 state['jobs'][jobid]=j
 if not jobid.startswith('cmp_') and not r.get('start_unix_ms'):r['start_unix_ms']=stamp
 write('results.json',state)
 print(prompt)
 print('DISPATCH_MS',stamp)
def ack(jobid):
 stamp=now();state=read('results.json');state['jobs'][jobid]['spawn_ack_unix_ms']=stamp;write('results.json',state);print('SPAWN_ACK_MS',stamp)
def collect(jobid):
 state=read('results.json');j=state['jobs'][jobid];result=read('outbox/'+jobid+'.json');j.update(output=result['result'],completed_unix_ms=result['completed_unix_ms'],duration_ms=result['completed_unix_ms']-j['dispatch_unix_ms'],status='completed',issues=[])
 if j.get('spawn_ack_unix_ms'):j['ack_to_output_ms']=j['completed_unix_ms']-j['spawn_ack_unix_ms']
 if jobid.startswith('cmp_'):state['comparison'].append(j)
 else:
  r=next(x for x in state['rounds'] if x['id']==j['round']);r['nodes'].append(j)
  if j['role']=='execution':r['reply']=j['output'].get('reply','');r['foreground_ms']=j['completed_unix_ms']-r['start_unix_ms'];r['foreground_completed_unix_ms']=j['completed_unix_ms']
 write('results.json',state)
 print(json.dumps({'id':jobid,'duration_ms':j['duration_ms'],'output':j['output']},ensure_ascii=False))
def memory_gate(r,mem,ref):
 # A deterministic provenance gate; it does not claim semantic truth verification.
 valid_ids={r['id']+'-SNAPSHOT',r['id']+'U',r['id']+'UF',r['id']+'-RECEIPT',r['id']+'-MEMORY-IN'}
 valid_ids.update(r['snapshot'])
 previous=r.get('received_memory') or {}
 for item in previous.get('facts',[])+previous.get('explicit_preferences',[]):valid_ids.update(item.get('evidence_ids',[]))
 quotes=[r['user_input'],r['feedback']]+[x.get('source_quote','') for x in previous.get('explicit_preferences',[])]
 accepted={'facts':[],'explicit_preferences':[]};quarantined=[]
 for kind in accepted:
  for item in mem.get(kind,[]):
   ids=item.get('evidence_ids',[])
   bad=[]
   if not ids or any(x not in valid_ids for x in ids):bad.append('missing_or_unknown_evidence_id')
   if kind=='explicit_preferences' and (not item.get('source_quote') or not any(item['source_quote'] in q for q in quotes)):bad.append('explicit_quote_not_in_received_user_text')
   if bad:quarantined.append({'kind':kind,'candidate':item,'reasons':bad})
   else:accepted[kind].append(item)
 return {'message_id':r['id']+'-MEMORY-OUT',**accepted,'unknowns':mem.get('unknowns',[]),'reflection_proposals_not_committed':ref.get('hypotheses',[]),'commit_rule':'只提交有已知来源的事实候选与可核对引文的明确偏好；反思假设仅作为待核实建议，不生效。'},quarantined
def commit(rid):
 state=read('results.json');r=next(x for x in state['rounds'] if x['id']==rid);nodes=r['nodes'];mem=next(x['output'] for x in reversed(nodes) if x['role']=='memory');ref=next(x['output'] for x in reversed(nodes) if x['role']=='reflection');end=now()
 # Only directly attributable memory output is forwarded; hypotheses remain proposals.
 r['committed_memory'],r['quarantined_memory']=memory_gate(r,mem,ref)
 r['completed_unix_ms']=end;r['full_loop_ms']=end-r['start_unix_ms']
 intervals=sorted((n['dispatch_unix_ms'],n['completed_unix_ms']) for n in nodes)
 merged=[]
 for a,b in intervals:
  if merged and a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
  else:merged.append([a,b])
 r['node_active_union_ms']=sum(b-a for a,b in merged);r['orchestration_gap_ms']=r['full_loop_ms']-r['node_active_union_ms']
 r['loop_start_unix_ms']=r['start_unix_ms'];r['loop_completed_unix_ms']=end
 r['node_duration_sum_ms']=sum(n['duration_ms'] for n in nodes)
 front=[n for n in nodes if n['role'] not in ['reflection','memory']];back=[n for n in nodes if n['role'] in ['reflection','memory']]
 r['dependency_critical_ms']=sum(n['duration_ms'] for n in front)+max(n['duration_ms'] for n in back)
 r['background_overlap_ms']=max(0,min(n['completed_unix_ms'] for n in back)-max(n['dispatch_unix_ms'] for n in back))
 write('results.json',state);print(json.dumps({'round':rid,'reply':r['reply'],'foreground_ms':r.get('foreground_ms'),'full_loop_ms':r['full_loop_ms'],'orchestration_gap_ms':r['orchestration_gap_ms'],'memory':r['committed_memory']},ensure_ascii=False))
if __name__=='__main__':
 action=sys.argv[1]
 if action=='setup':setup()
 elif action=='prepare':prepare(*sys.argv[2:])
 elif action=='collect':collect(sys.argv[2])
 elif action=='ack':ack(sys.argv[2])
 elif action=='commit':commit(sys.argv[2])
