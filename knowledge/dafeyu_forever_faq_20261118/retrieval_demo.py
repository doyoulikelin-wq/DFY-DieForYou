#!/usr/bin/env python3
"""Offline candidate lookup and fail-closed example gate. No model, network or live WoW connection."""
import argparse,collections,json,re,time,math
from pathlib import Path
TOKEN=re.compile(r"\[\[fact:([^\]]+)\]\]")
SLOT=re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_.]*)\}(?!\})")
def norm(s):return re.sub(r"[\W_]+","",s.lower(),flags=re.UNICODE)
def grams(s):
    s=norm(s)
    return set(s[i:i+2] for i in range(len(s)-1)) or ({s} if s else set())
class Catalog:
    def __init__(self,path=None):
        self.path=Path(path or Path(__file__).parent)
        self.cards={r["id"]:r for r in self.lines("faq.jsonl")}
        self.facts={r["id"]:r for r in self.lines("facts.jsonl")}
        self.questions=collections.defaultdict(list);self.postings=collections.defaultdict(set)
        # Only authored aliases index actual semantic content; surface variants are not needed for speed.
        for row in self.lines("queries.jsonl"):
            if row["origin"]!="authored_question":continue
            cid=row["card_id"];q=norm(row["query"]);g=grams(q)
            self.questions[cid].append((q,g))
            for term in g:self.postings[term].add(cid)
        self.version=json.loads((self.path/"manifest.json").read_text())["version"]
    def lines(self,n):
        with (self.path/n).open() as f:
            for l in f:
                if l.strip():yield json.loads(l)
    def search(self,query,k=8):
        q=norm(query);g=grams(q)
        scores=collections.Counter()
        for term in g:scores.update(self.postings.get(term,()))
        out=[]
        for cid,_ in scores.most_common(160):
            best=0
            for alias,ag in self.questions[cid]:
                if alias==q:sim=1.0
                elif q and q in alias:sim=.83+.16*len(q)/max(1,len(alias))
                else:sim=2*len(g&ag)/max(1,len(g)+len(ag))
                best=max(best,sim)
            if best>0:out.append({"card_id":cid,"lexical_score":round(best,5),"question":self.cards[cid]["primary_question"],"category":self.cards[cid]["category"]})
        return sorted(out,key=lambda x:(-x["lexical_score"],x["card_id"]))[:k]
    def value(self,ctx,path):
        if path in ctx:return ctx[path]
        cur=ctx
        for p in path.split("."):
            if not isinstance(cur,dict) or p not in cur:return None
            cur=cur[p]
        return cur
    def gate(self,cid,context,variant=0):
        """context is trusted host output; never populate guard facts by parsing arbitrary user assertions."""
        c=self.cards[cid];reasons=[]
        if context.get("game_scope")!="wow_forever":reasons.append("wrong_game_version")
        if context.get("catalog_version")!=self.version:reasons.append("catalog_version_unacknowledged")
        if context.get("intent_id")!=c["intent"]:reasons.append("intent_not_confirmed")
        for name in ["state","preference"]:
            if context.get(name+"_version") is None or context.get(name+"_version")!=context.get("current_"+name+"_version"):reasons.append(name+"_changed_or_unknown")
        if context.get("pending_contradiction") is not False:reasons.append("contradiction_not_cleared")
        if context.get("evidence_valid") is not True:reasons.append("evidence_not_validated")
        if context.get("mode","reply")=="proactive":
            for key in ["proactive_allowed","safe_idle","frequency_budget_available","event_not_delivered","no_unanswered_probe"]:
                if context.get(key) is not True:reasons.append(key+"_not_confirmed")
            if not c.get("can_auto_trigger"):reasons.append("card_not_proactive")
        if context.get("user_requested_silence") and c.get("delivery_kind")!="silence":reasons.append("explicit_silence")
        # Natural-language conditions must be compiled and checked in the application adapter.
        if not c.get("guards") or c["id"].startswith("P") or c["knowledge_kind"] in ["official_reference","lore_reference","story_frame"]:
            if context.get("validated_conditions",{}).get(cid) is not True:reasons.append("adapter_conditions_unverified")
        for guard in c.get("guards",[]):
            if not isinstance(guard,dict) or "field" not in guard or guard.get("op")!="eq":
                reasons.append("unsupported_guard_requires_adapter");continue
            actual=self.value(context,guard["field"]);expected=guard.get("value")
            if actual is None or type(actual)!=type(expected) or actual!=expected:reasons.append("condition_missing_or_false:"+guard["field"])
        if c.get("spoiler_level") not in [0,"none","premise",None]:
            if not context.get("spoiler_permission_confirmed"):reasons.append("spoiler_permission_missing")
        if not 0<=variant<len(c["answers"]):reasons.append("invalid_variant");variant=0
        template=c["answers"][variant]["text"]
        for slot in SLOT.findall(template):
            if slot not in context.get("slots",{}) or slot not in context.get("verified_slot_keys",[]):reasons.append("slot_not_grounded:"+slot)
        if any(f not in self.facts for f in TOKEN.findall(template)):reasons.append("missing_fact")
        if reasons:return {"allowed":False,"reasons":list(dict.fromkeys(reasons)),"text":None}
        text=TOKEN.sub(lambda m:self.facts[m.group(1)]["claim"],template)
        # Bound slots are inserted as plain text; never interpreted as instructions or markup.
        text=SLOT.sub(lambda m:str(context["slots"][m.group(1)]),text)
        return {"allowed":True,"reasons":[],"text":text,"delivery_kind":c.get("delivery_kind"),"card_id":cid,"variant":variant}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("query");p.add_argument("--top",type=int,default=5);a=p.parse_args()
    t=time.perf_counter();cat=Catalog();load_ms=(time.perf_counter()-t)*1000;t=time.perf_counter();result=cat.search(a.query,a.top);search_ms=(time.perf_counter()-t)*1000
    print(json.dumps({"query":a.query,"index_build_ms":round(load_ms,3),"lookup_ms":round(search_ms,3),"candidates":result,"note":"本地字面检索；候选不是可直接发送的答案，未测客户端或API延迟。"},ensure_ascii=False,indent=2))

