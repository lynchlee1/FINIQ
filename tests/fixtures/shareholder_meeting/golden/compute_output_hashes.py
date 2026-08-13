"""Print canonical parser-output hashes for the tracked golden source pairs.

This helper is intentionally read-only. Run it explicitly after an approved parser
change, review the semantic diff, and then update ``manifest.json`` in a normal code
review. Tests never rewrite golden expectations and never call an LLM.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from finiq.data_scraper.parse.domain.shareholder_meeting import parse_shareholder_meeting


GOLDEN_ROOT = Path(__file__).resolve().parent


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def main() -> None:
    manifest = json.loads((GOLDEN_ROOT / "manifest.json").read_text(encoding="utf-8"))
    hashes: dict[str, str] = {}
    for case in manifest["cases"]:
        source = case["source"]
        external_html = (GOLDEN_ROOT / source["external_fixture"]).read_bytes()
        internal_html = (GOLDEN_ROOT / source["internal_fixture"]).read_bytes()
        result = parse_shareholder_meeting(external_html, internal_html)
        hashes[case["acpt_no"]] = hashlib.sha256(
            canonical_json_bytes(result)
        ).hexdigest()
    print(json.dumps(hashes, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
