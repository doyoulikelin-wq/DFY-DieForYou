"""Embed recorded experiment data into a dependency-free static replay page.

The builder deliberately refuses missing data and does not create demo results.
Usage: python build_natural_test.py [--data PATH] [--output PATH]
"""
import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "src" / "natural-test-shell.html"
DEFAULT_DATA = ROOT / "experiments" / "natural-loop-20261117" / "report-data.json"
DEFAULT_OUTPUT = ROOT / "dist" / "natural-test.html"
PLACEHOLDER = "__NATURAL_TEST_DATA__"


def build(data_path: Path, output_path: Path) -> dict:
    if not data_path.is_file():
        raise FileNotFoundError(f"Recorded test data is required: {data_path}")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("rounds"), list):
        raise ValueError("Expected an object containing a rounds array")
    if any(not isinstance(record, dict) for record in data["rounds"]):
        raise ValueError("Each recorded round must be an object")
    ids = [record.get("id") for record in data["rounds"]]
    if any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("Every recorded round needs a nonempty string id")
    if len(ids) != len(set(ids)):
        raise ValueError("Recorded round ids must be unique")
    shell = TEMPLATE.read_text(encoding="utf-8")
    if shell.count(PLACEHOLDER) != 1:
        raise ValueError("Template must contain exactly one data placeholder")
    for marker, filename in [("__NATURAL_STREAM_CSS__", "natural-stream.css"),
                              ("__NATURAL_STREAM_JS__", "natural-stream.js")]:
        if shell.count(marker) != 1:
            raise ValueError(f"Template must contain exactly one {marker}")
        shell = shell.replace(marker, (ROOT / "src" / filename).read_text(encoding="utf-8"))
    # HTML raw-text elements must not be terminable by user / model text.
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    encoded = encoded.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = shell.replace(PLACEHOLDER, encoded)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return {"output": str(output_path), "rounds": len(ids), "bytes": output_path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        result = build(args.data.resolve(), args.output.resolve())
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"Not built: {exc}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
