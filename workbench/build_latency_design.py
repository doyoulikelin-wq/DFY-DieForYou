"""Build the self-contained design document from its shell and full specification."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
shell = (ROOT / "src/latency-design-shell.html").read_text()
spec = (ROOT / "design/latency-spec.html").read_text()
marker = "<!-- FULL_SPEC -->"
if shell.count(marker) != 1:
    raise SystemExit("Expected exactly one full-spec insertion marker")
styles = """<style>
.engineering-spec { max-width: 100%; line-height: 1.9; font-size: 15px; color: #29332f; }
.engineering-spec h2 { font-size: 24px; margin: 8px 0 18px; letter-spacing: -.02em; }
.engineering-spec h3 { font-size: 18px; margin: 34px 0 12px; color: #142c25; }
.engineering-spec p { margin: 12px 0; }
.engineering-spec table { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; margin: 18px 0; font-size: 13px; }
.engineering-spec th,.engineering-spec td { text-align: left; vertical-align: top; padding: 11px 12px; border: 1px solid #dce2dd; min-width: 118px; }
.engineering-spec th { background: #eff4f0; font-weight: 650; }
.engineering-spec pre { white-space: pre-wrap; overflow-wrap: anywhere; padding: 18px; border: 1px solid #dce2dd; border-radius: 9px; background: #f3f5f2; font-size: 12px; line-height: 1.65; }
.engineering-spec a { color: #246150; text-underline-offset: 3px; }
.engineering-spec li { margin: 10px 0; }
@media (max-width: 600px) { .engineering-spec { font-size: 14px; } .engineering-spec h2 { font-size: 21px; } }
</style>"""
result = shell.replace(marker, styles + spec)
(ROOT / "dist/latency-design.html").write_text(result)
print("Built dist/latency-design.html")
