"""Build the source-backed, explicitly simulated latency design page."""
from pathlib import Path
import json
import re
import shutil

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'dist'
DESIGN = ROOT / 'design' / 'streaming-plan-20261118'

def main():
    data = json.loads((DESIGN / 'data.json').read_text())
    shell = (ROOT / 'src/streaming-plan-shell.html').read_text()
    css = (ROOT / 'src/streaming-plan.css').read_text()
    js = (ROOT / 'src/streaming-plan.js').read_text()
    if re.search(r'</script', js, re.I):
        raise ValueError('Unexpected script terminator')
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    html = shell.replace('__CSS__', css).replace('__DATA__', payload).replace('__JS__', js)
    assert '__DATA__' not in html and '__CSS__' not in html and '__JS__' not in html
    OUT.mkdir(exist_ok=True)
    (OUT / 'streaming-plan.html').write_text(html)
    (OUT / 'streaming-plan-data.json').write_text(json.dumps(data, ensure_ascii=False, indent=2))
    for name, dest in [('DESIGN.md', 'streaming-plan.md'), ('validation.json', 'streaming-plan-validation.json')]:
        if (DESIGN / name).exists():
            shutil.copyfile(DESIGN / name, OUT / dest)
    print(json.dumps({'html_bytes': len(html.encode()), 'scenarios': len(data['scenarios']), 'modules': len(data['modules']), 'sources': len(data['sources'])}))

if __name__ == '__main__':
    main()
