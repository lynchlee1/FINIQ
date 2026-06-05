"""Print unique disclosure titles from downloaded KIND result folders.

Usage:
    python scripts/print_unique_disclosure_titles.py
    python scripts/print_unique_disclosure_titles.py --root resources/kind
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path

# Edit these defaults directly when you want fixed filtering without CLI options.
DEFAULT_WHITELIST: list[str] = []
DEFAULT_BLACKLIST: list[str] = []
DEFAULT_STRIP_PARENS_FOR_DEDUP = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Save unique disclosure titles under a KIND output root as JSON.",
    )
    parser.add_argument(
        "--root",
        default="resources/kind",
        help="KIND output root directory (default: resources/kind)",
    )
    parser.add_argument(
        "--output",
        default="resources/kind/unique_disclosure_titles.json",
        help="Output JSON path (default: resources/kind/unique_disclosure_titles.json)",
    )
    parser.add_argument(
        "--whitelist",
        nargs="*",
        default=[],
        help=(
            "Only keep titles that include at least one whitelist keyword. "
            "Example: --whitelist 정정 감사"
        ),
    )
    parser.add_argument(
        "--blacklist",
        nargs="*",
        default=[],
        help=(
            "Exclude titles that include any blacklist keyword. "
            "Example: --blacklist 기재정정 첨부정정"
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, os.cpu_count() or 1),
        help="Number of worker threads for folder parsing (default: CPU count)",
    )
    parser.add_argument(
        "--strip-parens-for-dedup",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_STRIP_PARENS_FOR_DEDUP,
        help=(
            "Remove '(...)' segments before deduplication. "
            "Use --strip-parens-for-dedup / --no-strip-parens-for-dedup"
        ),
    )
    return parser.parse_args()


def _normalize_keywords(words: list[str]) -> list[str]:
    normalized: list[str] = []
    for word in words:
        cleaned = " ".join(str(word).split())
        if cleaned:
            normalized.append(cleaned.casefold())
    return normalized


def _title_matches_filters(
    title: str,
    *,
    whitelist: list[str],
    blacklist: list[str],
) -> bool:
    normalized_title = title.casefold()
    if whitelist and not any(keyword in normalized_title for keyword in whitelist):
        return False
    if blacklist and any(keyword in normalized_title for keyword in blacklist):
        return False
    return True


def _title_for_dedup(title: str, *, strip_parens_for_dedup: bool) -> str:
    candidate = title
    if strip_parens_for_dedup:
        # Remove parenthesized fragments robustly, including malformed cases.
        # - Balanced: "A(BC)D" -> "AD"
        # - Unmatched open: "A(BC" -> "A"
        # - Unmatched close: "A)BC" -> "ABC" (drops dangling ')')
        depth = 0
        kept_chars: list[str] = []
        for char in candidate:
            if char == "(":
                depth += 1
                continue
            if char == ")":
                if depth > 0:
                    depth -= 1
                continue
            if depth == 0:
                kept_chars.append(char)
        candidate = "".join(kept_chars)
    return " ".join(candidate.split())


def _dedupe_titles(
    titles: list[str],
    *,
    strip_parens_for_dedup: bool,
) -> list[str]:
    unique_titles: list[str] = []
    seen_keys: set[str] = set()
    for title in titles:
        key = _title_for_dedup(
            title,
            strip_parens_for_dedup=strip_parens_for_dedup,
        )
        if not key:
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_titles.append(title)
    return unique_titles


def _load_all_disclosure_rows(
    folders: list[Path],
    *,
    workers: int,
    load_folder_disclosure_rows: object,
) -> list[dict[str, object]]:
    worker_count = max(1, min(workers, len(folders)))
    if worker_count == 1:
        rows: list[dict[str, object]] = []
        for folder in folders:
            rows.extend(load_folder_disclosure_rows(folder))
        return rows

    rows = []
    # executor.map keeps input order, so resulting title order stays deterministic.
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="kind-title") as executor:
        for folder_rows in executor.map(load_folder_disclosure_rows, folders):
            rows.extend(folder_rows)
    return rows


def main() -> int:
    from finiq.data_scraper.data.explorer import (  # pylint: disable=import-outside-toplevel
        extract_unique_disclosure_titles,
        find_result_folders,
        load_folder_disclosure_rows,
    )

    args = parse_args()
    root = Path(args.root).resolve()
    whitelist = _normalize_keywords([*DEFAULT_WHITELIST, *args.whitelist])
    blacklist = _normalize_keywords([*DEFAULT_BLACKLIST, *args.blacklist])
    if not root.is_dir():
        print(f"[ERROR] directory not found: {root}")
        return 1

    folders = find_result_folders(root)
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not folders:
        output_path.write_text("[]\n", encoding="utf-8")
        print(f"[INFO] no downloaded body folders found under: {root}")
        print(f"[INFO] wrote empty JSON: {output_path}")
        return 0

    disclosure_rows = _load_all_disclosure_rows(
        folders,
        workers=args.workers,
        load_folder_disclosure_rows=load_folder_disclosure_rows,
    )

    unique_titles = extract_unique_disclosure_titles(disclosure_rows)
    unique_titles = _dedupe_titles(
        unique_titles,
        strip_parens_for_dedup=args.strip_parens_for_dedup,
    )
    filtered_titles = [
        title
        for title in unique_titles
        if _title_matches_filters(
            title,
            whitelist=whitelist,
            blacklist=blacklist,
        )
    ]
    output_titles = _dedupe_titles(
        [
            _title_for_dedup(
                title,
                strip_parens_for_dedup=args.strip_parens_for_dedup,
            )
            for title in filtered_titles
        ],
        strip_parens_for_dedup=False,
    )
    output_path.write_text(
        json.dumps(output_titles, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "[INFO] wrote "
        f"{len(output_titles)} titles to: {output_path} "
        f"(before filter: {len(unique_titles)}, "
        f"strip_parens_for_dedup={args.strip_parens_for_dedup})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
