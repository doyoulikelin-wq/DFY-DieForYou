"""Validate the archive offline without rewriting historical evidence."""
import hashlib
from html.parser import HTMLParser
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
checks = []

def check(name, ok, detail=None):
    checks.append({'name': name, 'pass': bool(ok), 'detail': detail})
    if not ok:
        raise AssertionError(f'{name}: {detail}')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(name, argv, cwd):
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True)
    check(name, result.returncode == 0, (result.stdout + result.stderr).strip())
    return result.stdout

class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
    def handle_starttag(self, tag, attrs):
        self.refs += [v for k, v in attrs if k in ('href', 'src') and v]

def main():
    manifest = json.loads((ROOT / 'docs/source-manifest.json').read_text())
    for item in manifest['files']:
        path = ROOT / item['path']
        check('original:' + item['path'], path.is_file() and sha(path) == item['sha256'])
    faq = ROOT / 'knowledge/dafeyu_forever_faq_20261118'
    expected = json.loads((faq / 'checksums.json').read_text())
    check('FAQ original checksums', all(sha(faq / p) == h for p, h in expected.items()), len(expected))
    with zipfile.ZipFile(ROOT / 'archives/dafeyu_forever_faq_20261118.zip') as archive:
        check('FAQ ZIP CRC', archive.testzip() is None)
        check('FAQ ZIP equals extracted files', all((ROOT / 'knowledge' / i.filename).read_bytes() == archive.read(i) for i in archive.infolist() if not i.is_dir()))
    import sqlite3
    with sqlite3.connect((faq / 'faq.sqlite').as_uri() + '?mode=ro', uri=True) as db:
        check('SQLite integrity', db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok')
    for p in [ROOT / 'index.html', *sorted((ROOT / 'workbench/dist').glob('*.html')), faq / 'dafeyu_forever_faq.html']:
        parser = References()
        parser.feed(p.read_text())
        missing = []
        for value in parser.refs:
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            if not (p.parent / unquote(parsed.path)).is_file():
                missing.append(value)
        check('links:' + str(p.relative_to(ROOT)), not missing, missing)
    with tempfile.TemporaryDirectory(prefix='dfy-verify-') as temp:
        copy = Path(temp)
        for dirname in ['workbench', 'knowledge', 'tools']:
            shutil.copytree(ROOT / dirname, copy / dirname, ignore=shutil.ignore_patterns('__pycache__'))
        wb = copy / 'workbench'
        run('seven pages rebuild', [sys.executable, str(copy / 'tools/build.py')], copy)
        generated = copy / 'build/workbench/dist'
        for p in sorted((ROOT / 'workbench/dist').glob('*.html')):
            new = generated / p.name
            if p.name in ('experiment.html', 'fast-experiment.html'):
                scripts = lambda text: re.findall(r'<script\b[^>]*>([\s\S]*?)</script>', text, re.I)
                check('rebuild script/data equality:' + p.name, scripts(p.read_text()) == scripts(new.read_text()), 'Shared shell navigation and responsive CSS update on rebuild; embedded scripts and evidence must remain identical.')
            else:
                check('rebuild byte equality:' + p.name, p.read_bytes() == new.read_bytes())
        for p in sorted((wb / 'src').glob('*.js')):
            run('JS syntax:' + p.name, ['node', '--check', str(p)], wb)
        run('simulation engine assertions', ['node', 'src/engine.test.cjs'], wb)
        for folder, test in [('fast-loop-20261115', 'runtime_test.py'), ('natural-loop-20261117', 'runtime_v2_test.py'), ('natural-loop-20261117', 'runtime_v3_test.py'), ('natural-loop-20261117', 'timeline_test.py')]:
            run(test, [sys.executable, str(wb / 'experiments' / folder / test)], wb)
        run('Streaming 52 checks', [sys.executable, 'validate_streaming_plan.py'], wb)
        run('FAQ 59 gate checks', [sys.executable, str(copy / 'knowledge/dafeyu_forever_faq_20261118/validate_retrieval.py')], copy)
    check('source hashes unchanged after verification', all(sha(ROOT / item['path']) == item['sha256'] for item in manifest['files']))

if __name__ == '__main__':
    failure = None
    try:
        main()
    except Exception as exc:
        failure = str(exc)
    report = {'date': '2026-11-18', 'scope': 'Offline migration verification; no model calls or game integration', 'passed': sum(c['pass'] for c in checks), 'total': len(checks), 'error': failure, 'checks': checks}
    out = ROOT / 'validation/migration-check.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'checks'}, ensure_ascii=False))
    if failure:
        sys.exit(1)
