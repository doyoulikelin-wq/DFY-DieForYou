"""Rebuild six published pages and the preserved editable design board."""
from pathlib import Path
import re
import subprocess
import sys
import shutil

ROOT = Path(__file__).resolve().parents[1]
WB = ROOT / 'build/workbench'
BUILDERS = ['build.py', 'build_experiment.py', 'build_fast_experiment.py',
            'build_latency_design.py', 'build_natural_test.py', 'build_streaming_plan.py']

def build():
    shutil.copytree(ROOT / 'workbench', WB, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    for script in BUILDERS:
        subprocess.run([sys.executable, str(WB / script)], cwd=WB, check=True)
    html = (WB / 'src/shell.html').read_text(encoding='utf-8')
    for marker, filename in [('CATALOG', 'catalog.js'), ('ENGINE', 'engine.js'), ('APP', 'app.js')]:
        source = (WB / 'src' / filename).read_text(encoding='utf-8')
        if re.search(r'</script', source, re.I):
            raise ValueError(f'Unexpected script terminator: {filename}')
        placeholder = f'<!--{marker}-->'
        if html.count(placeholder) != 1:
            raise ValueError(f'Expected one marker: {marker}')
        html = html.replace(placeholder, '<script>\n' + source + '\n</script>')
    (WB / 'dist/design-board.html').write_text(html, encoding='utf-8')
    print(f'Built seven pages at {WB / "dist"}; archived originals unchanged.')

if __name__ == '__main__':
    build()
