from pathlib import Path
import re

root = Path(__file__).resolve().parent
html = (root / 'src/simple-shell.html').read_text(encoding='utf-8')
for marker, name in [('DATA', 'simple-data.js'), ('APP', 'simple-app.js')]:
    source = (root / 'src' / name).read_text(encoding='utf-8')
    if re.search(r'</script', source, re.I):
        raise ValueError(f'Unexpected closing script token in {name}')
    html = html.replace(f'<!--{marker}-->', '<script>\n' + source + '\n</script>')
out = root / 'dist/index.html'
out.parent.mkdir(exist_ok=True)
out.write_text(html, encoding='utf-8')
print(f'Built single self-contained HTML: {out.stat().st_size:,} bytes')
