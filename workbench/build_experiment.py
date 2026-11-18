from pathlib import Path
import json,re

root=Path(__file__).resolve().parent
data_path=root/'experiments/sol-loop-20261115/results.json'
data=json.loads(data_path.read_text(encoding='utf-8'))
html=(root/'src/simple-shell.html').read_text(encoding='utf-8')
styles=(root/'src/experiment-style.css').read_text(encoding='utf-8')
html=html.replace('</head>','<style>\n'+styles+'\n</style>\n</head>')
catalog=(root/'src/simple-data.js').read_text(encoding='utf-8')
encoded=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
html=html.replace('<!--DATA-->','<script>\n'+catalog+'\n</script>\n<script>window.CompanionExperiment='+encoded+';</script>')
app=(root/'src/experiment-app.js').read_text(encoding='utf-8')
if re.search(r'</script',app,re.I): raise ValueError('Unexpected script terminator')
html=html.replace('<!--APP-->','<script>\n'+app+'\n</script>')
html=html.replace('<title>陪伴精灵 · Agent 流程图</title>','<title>陪伴精灵 · Sol 实测回放</title>')
out=root/'dist/experiment.html'
out.parent.mkdir(exist_ok=True)
out.write_text(html,encoding='utf-8')
print(f'Built experiment replay: {out.stat().st_size:,} bytes')
