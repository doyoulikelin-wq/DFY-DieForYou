"""Validate factual provenance and simulation chronology, not backend performance."""
import json
import re
from pathlib import Path
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parent
DIR=ROOT/'design/streaming-plan-20261118'
data=json.loads((DIR/'data.json').read_text())
checks=[]

def check(name, condition):
    checks.append({'name':name,'pass':bool(condition)})
    if not condition: raise AssertionError(name)

modules={m['id'] for m in data['modules']}
sources={s['id'] for s in data['sources']}
check('unique_module_and_scenario_ids',len(modules)==len(data['modules']) and len({s['id'] for s in data['scenarios']})==len(data['scenarios']))
check('all_research_sources_resolve',all(set(r['source_ids'])<=sources for r in data['research']))
check('actual_api_measurements_remain_unknown',all(data['evidence'][k] is None for k in ['actual_api_usage','actual_api_ttft_ms','actual_client_first_useful_ms']))
check('historical_rows_unchanged',data['evidence']['historical_rows']==data['baseline']['rows'])
check('measured_counts_not_query_inflation',data['evidence']['faq_counts']['faq_cards']==958 and data['evidence']['faq_counts']['answer_variants']==1851 and data['evidence']['local_lookup']['samples']==160)
for s in data['scenarios']:
    events=s['events']
    check(s['id']+'_chronology',all(a['at']<=b['at'] for a,b in zip(events,events[1:])) and events[-1]['at']<=s['duration_ms'])
    check(s['id']+'_module_references',set(s['nodes'])<=modules and all(e['node'] in modules for e in events))
    check(s['id']+'_explicit_simulation_label','预算' in s['kind'])
    deliveries=[e for e in events if e.get('delivery_text')]
    if deliveries:
        check(s['id']+'_first_useful_equals_first_visible',s['first_useful_ms']==deliveries[0]['at'])
        check(s['id']+'_foreground_equals_final_text_paint',s['foreground_ms']==deliveries[-1]['at'])
        for d in deliveries:
            preceding=[e for e in events if e['at']<d['at'] and e['node']=='gate']
            check(s['id']+f"_gate_before_{d['at']}",bool(preceding) and preceding[-1]['type']=='gate.accepted')
    else:
        check(s['id']+'_silence_not_zero_latency_text',s['first_useful_ms'] is None)
    if s['background_ms'] is not None:
        check(s['id']+'_background_after_front',s['background_ms']>=s['foreground_ms'])

plan=next(s for s in data['scenarios'] if s['id']=='plan')
front_calls=[e for e in plan['events'] if e['type']=='model.request_sent' and e['lane']=='foreground']
back_calls=[e for e in plan['events'] if e['type']=='model.request_sent' and e['lane']=='background']
check('complex_two_front_two_optional_background_calls',len(front_calls)==2 and len(back_calls)==2)
tool_results=[e['at'] for e in plan['events'] if e['type']=='tool.completed']
check('complex_decision_waits_for_both_tools',front_calls[1]['at']>max(tool_results))
tools=[x for x in plan['segments'] if x['node']=='tools']
check('complex_tools_overlap',len(tools)==2 and tools[0]['start']==tools[1]['start'] and min(x['end'] for x in tools)>tools[0]['start'])
stale=next(s for s in data['scenarios'] if s['id']=='stale')
check('stale_rejected_text_never_delivered',not any('点击接受' in e.get('delivery_text','') for e in stale['events']))
check('quiet_never_speaks',not any(e.get('delivery_text') for e in next(s for s in data['scenarios'] if s['id']=='quiet')['events']))
check('complex_cap_arithmetic',4096+1024==5120 and 8192+2048==10240)
html=(ROOT/'dist/streaming-plan.html').read_text()
embedded=re.search(r'<script id="streaming-data" type="application/json">([\s\S]*?)</script>',html).group(1)
check('exported_data_exactly_matches_source',json.loads(embedded)==data)
check('standalone_has_no_external_scripts_or_stylesheets',not re.search(r'<script[^>]+src=|<link[^>]+stylesheet',html,re.I))
check('all_build_markers_replaced',all(x not in html for x in ['__DATA__','__CSS__','__JS__']))
class IDs(HTMLParser):
    def __init__(self):super().__init__();self.ids=[]
    def handle_starttag(self,tag,attrs):self.ids.extend(v for k,v in attrs if k=='id')
ids=IDs();ids.feed(html)
check('no_duplicate_static_html_ids',len(ids.ids)==len(set(ids.ids)))
result={'as_of':'2026-11-18','scope':'页面数据、预算口径与模拟时序；不是游戏后端/API性能证明','checks':checks,'passed':len(checks),'total':len(checks),'actual_api_test':False,'actual_game_integration_test':False}
if (DIR/'browser-validation.json').exists():result['browser']=json.loads((DIR/'browser-validation.json').read_text())
(DIR/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({'passed':len(checks),'total':len(checks),'scope':result['scope']},ensure_ascii=False))
