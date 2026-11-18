#!/usr/bin/env python3
import copy,json,statistics,time
from pathlib import Path
from retrieval_demo import Catalog
P=Path(__file__).parent
cat=Catalog()
def base(cid):
 c=cat.cards[cid]
 return {"game_scope":"wow_forever","catalog_version":cat.version,"intent_id":c["intent"],
 "state_version":7,"current_state_version":7,"preference_version":3,"current_preference_version":3,
 "pending_contradiction":False,"evidence_valid":True,"mode":"reply","validated_conditions":{cid:True},
 **{g["field"]:g.get("value") for g in c.get("guards",[]) if isinstance(g,dict) and "field" in g}}
results=[]
def check(name,got,expected):
 ok=bool(got)==bool(expected);results.append({"name":name,"pass":ok});assert ok,(name,got,expected)
mana=next(c for c in cat.cards.values() if c["intent"]=="mana_empty")
cid=mana["id"];ctx=base(cid)
check("resource_failure_known",cat.gate(cid,ctx)["allowed"],True)
bad=copy.deepcopy(ctx);bad["evidence.cast.failure_insufficient_mana"]=False
check("same_question_different_error",cat.gate(cid,bad)["allowed"],False)
bad=copy.deepcopy(ctx);bad.pop("evidence.cast.failure_insufficient_mana")
check("unknown_is_not_true",cat.gate(cid,bad)["allowed"],False)
bad=copy.deepcopy(ctx);bad["current_state_version"]=8
check("state_changed_rejects_cached_answer",cat.gate(cid,bad)["allowed"],False)
bad=copy.deepcopy(ctx);bad["current_preference_version"]=4
check("late_preference_rejects_cached_answer",cat.gate(cid,bad)["allowed"],False)
bad=copy.deepcopy(ctx);bad["game_scope"]="wow_classic"
check("other_wow_version_rejected",cat.gate(cid,bad)["allowed"],False)
bad=copy.deepcopy(ctx);bad["intent_id"]="other"
check("semantic_match_not_intent_proof",cat.gate(cid,bad)["allowed"],False)
bad=copy.deepcopy(ctx);bad["mode"]="proactive"
check("ordinary_card_not_proactive",cat.gate(cid,bad)["allowed"],False)
bad=copy.deepcopy(ctx);bad["user_requested_silence"]=True
check("explicit_silence_rejected",cat.gate(cid,bad)["allowed"],False)
c=cat.cards["G0011"];ctx=base(c["id"]);check("accept_all_conditions",cat.gate(c["id"],ctx)["allowed"],True)
for key in ["evidence.quest.dialog_open","evidence.quest.same_entity_as_current","evidence.quest.can_accept","evidence.quest.no_pending_choice"]:
 b=copy.deepcopy(ctx);b[key]=False;check("accept_block_"+key,cat.gate(c["id"],b)["allowed"],False)
c=cat.cards["P0001"];ctx=base(c["id"])
check("unnamed_boss_variant_does_not_require_name",cat.gate(c["id"],ctx,1)["allowed"],True)
check("named_boss_variant_requires_grounded_name",cat.gate(c["id"],ctx,0)["allowed"],False)
ctx["slots"]={"enemy_name":"测试首领"};ctx["verified_slot_keys"]=["enemy_name"]
check("grounded_name_renders",cat.gate(c["id"],ctx,0)["allowed"],True)
c=cat.cards["P0177"];ctx=base(c["id"]);ctx["user_requested_silence"]=True;g=cat.gate(c["id"],ctx)
check("strict_silence_is_empty_success",g["allowed"] and g["text"]=="",True)
c=cat.cards["RS001"];ctx=base(c["id"]);ctx["validated_conditions"]={}
check("reference_conditions_require_review",cat.gate(c["id"],ctx)["allowed"],False)
# Handwritten paired states: change one key condition while keeping the same wording.
hp=P/"handwritten_hard_negatives.json"
if hp.exists():
 for case in json.loads(hp.read_text())["cases"]:
  cid=case["candidate_id"];ctx=base(cid)
  for k,v in case["positive_case"]["evidence"].items():ctx["evidence."+k]=v
  ctx["slots"]=case["positive_case"].get("slot_values",{})
  ctx["verified_slot_keys"]=list(ctx["slots"])
  ctx["spoiler_permission_confirmed"]=True
  check(case["id"]+"_positive",cat.gate(cid,ctx)["allowed"],True)
  bad=copy.deepcopy(ctx)
  for k,v in case["hard_negative"]["evidence"].items():bad["evidence."+k]=v
  check(case["id"]+"_negative",cat.gate(cid,bad)["allowed"],False)
# Positive controls are authored aliases, explicitly not a held-out real-world accuracy score.
probes=["我刚出生不知道干什么","技能为什么放不出来","这个东西有用吗","为什么不能和他组队","副本怎么没有经验","你能看我的屏幕吗","不想聊现实","别每杀一只都欢呼"]
timings=[];rows=[]
for q in probes:
 t=time.perf_counter();r=cat.search(q);elapsed=(time.perf_counter()-t)*1000
 rows.append({"query":q,"top_candidates":r[:3],"lookup_ms":elapsed})
for _ in range(20):
 for q in probes:
  t=time.perf_counter();cat.search(q);timings.append((time.perf_counter()-t)*1000)
ordered=sorted(timings)
report={"date":"2026-11-18","scope":"本机内存索引与示例发送门控，非真实游戏、非模型API、非UI端到端",
 "gate_tests":results,"gate_tests_passed":sum(x["pass"] for x in results),"gate_tests_total":len(results),
 "local_lookup_samples":len(timings),"lookup_median_ms":statistics.median(timings),"lookup_p95_ms":ordered[int(.95*(len(ordered)-1))],
 "cards":len(cat.cards),"probes":rows,
 "not_measured":["真实自然语言意图识别准确率","真实流量命中率","完整语义检索召回率","真实玩家自然度","API TTFT","客户端可见延迟","联网游戏适配器"],
 "evaluation_warning":"探针取自已有别名或近似表达，不是盲测；门控条件由测试夹具提供，不证明真实接口已正确识别条件。"}
(P/"retrieval_validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ["gate_tests","probes","not_measured"]},ensure_ascii=False,indent=2))

