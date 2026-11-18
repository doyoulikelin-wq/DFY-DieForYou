from pathlib import Path
import json
import re

root = Path(__file__).resolve().parent
data_path = root / 'experiments/fast-loop-20261115/results.json'
data = json.loads(data_path.read_text(encoding='utf-8')) if data_path.exists() else {}
if not isinstance(data, dict):
    raise ValueError('Fast experiment results must be a JSON object')
html = (root / 'src/simple-shell.html').read_text(encoding='utf-8')
styles = (root / 'src/fast-experiment-style.css').read_text(encoding='utf-8')
catalog = (root / 'src/simple-data.js').read_text(encoding='utf-8')
app = (root / 'src/fast-experiment-app.js').read_text(encoding='utf-8')
if re.search(r'</script', app, re.I):
    raise ValueError('Unexpected script terminator')
encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
html = html.replace('</head>', '<style>\n' + styles + '\n</style>\n</head>')
html = html.replace('<!--DATA-->', '<script>\n' + catalog + '\n</script>\n<script id="fast-results">window.FastExperiment=' + encoded + ';</script>')
html = html.replace('<!--APP-->', '<script>\n' + app + '\n</script>')
html = html.replace('<title>陪伴精灵 · Agent 流程图</title>', '<title>陪伴精灵 · 快速交付实测</title>')
html = html.replace('陪伴精灵的六个 Agent 协作流程，点击模块查看职责权限、基座模型、Token、信息链路、日志和错误历史。', '快速交付实测：前台决策、规则审核与代码发送，后台规划、反思与记忆整理。点击模块查看真实消息和计时。')
out = root / 'dist/fast-experiment.html'
out.parent.mkdir(exist_ok=True)
out.write_text(html, encoding='utf-8')
print(f'Built fast experiment: {out.stat().st_size:,} bytes; data: {"loaded" if data_path.exists() else "not yet available"}')
