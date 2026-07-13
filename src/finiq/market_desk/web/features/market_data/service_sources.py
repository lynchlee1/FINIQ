"""SQLite manifest and source-folder disclosure readers."""

from __future__ import annotations

from finiq.concurrency import bounded_as_completed
from finiq.data_scraper.parse._markup import decode_html_markup
from finiq.market_desk.web.features.market_data.service_records import *

def _looks_like_sqlite_manifest(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return payload.get("format") == "finiq_disclosure_table_manifest_v1"


def _resolve_sqlite_manifest_path(path: str | Path) -> Path | None:
    candidate = Path(path).expanduser().resolve()
    if candidate.is_file():
        if not _looks_like_sqlite_manifest(candidate):
            return None
        if not candidate.parent.name.endswith("_shards"):
            msg = f"SQLite manifest must be inside a *_shards directory: {candidate}"
            raise ValueError(msg)
        return candidate
    if not candidate.is_dir():
        return None
    if candidate.name.endswith("_shards"):
        nested_manifest = candidate / f"{candidate.name.removesuffix('_shards')}.json"
        if _looks_like_sqlite_manifest(nested_manifest):
            return nested_manifest
        manifests = sorted(candidate.glob("*.sqlite_manifest.json"))
        for manifest_path in manifests:
            if _looks_like_sqlite_manifest(manifest_path):
                return manifest_path
    search_dirs = [candidate, candidate / "kind_sqlite"]
    for search_dir in search_dirs:
        shard_manifests = sorted(search_dir.glob("*_shards/*.sqlite_manifest.json"))
        for manifest_path in shard_manifests:
            if _looks_like_sqlite_manifest(manifest_path):
                return manifest_path
    return None


def _load_sqlite_manifest(manifest_path: Path) -> dict[str, Any]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("format") != "finiq_disclosure_table_manifest_v1":
        msg = f"Not a FINIQ disclosure SQLite manifest: {manifest_path}"
        raise ValueError(msg)
    return payload


def _sqlite_manifest_total_disclosures(manifest: dict[str, Any]) -> int:
    summary_count = manifest.get("summary", {}).get("disclosures")
    if summary_count is not None:
        return int(summary_count)
    return sum(
        int(shard.get("disclosures") or 0)
        for shard in list(manifest.get("shards") or [])
    )


def _quoted_sqlite_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) + chr(34))}"'


def _resolve_sqlite_shard_path(manifest_path: Path, shard: dict[str, Any]) -> Path:
    manifest_parent = manifest_path.parent
    shard_path = Path(str(shard.get("path") or "")).expanduser()
    if not shard_path.is_absolute():
        shard_path = (manifest_parent / shard_path).resolve()
    if shard_path.is_file():
        return shard_path

    relative_path = str(shard.get("relative_path") or "").strip()
    if relative_path:
        same_directory_path = (manifest_parent / relative_path).resolve()
        if same_directory_path.is_file():
            return same_directory_path
    return shard_path


def _validate_sqlite_manifest_counts(
    manifest_path: Path, manifest: dict[str, Any]
) -> None:
    table_name = (
        str(manifest.get("table_name") or "disclosures").strip() or "disclosures"
    )
    quoted_table = _quoted_sqlite_identifier(table_name)
    shard_total = 0
    for shard in list(manifest.get("shards") or []):
        shard_path = _resolve_sqlite_shard_path(manifest_path, shard)
        if not shard_path.is_file():
            msg = f"SQLite shard not found: {shard_path}"
            raise ValueError(msg)
        expected = int(shard.get("disclosures") or 0)
        connection = sqlite3.connect(shard_path)
        try:
            actual = int(
                connection.execute(f"SELECT COUNT(*) FROM {quoted_table}").fetchone()[0]
            )
        finally:
            connection.close()
        if actual != expected:
            msg = (
                "SQLite shard disclosure count mismatch: "
                f"shard={shard_path}, manifest={expected}, rows={actual}"
            )
            raise ValueError(msg)
        shard_total += expected

    summary_total = manifest.get("summary", {}).get("disclosures")
    if summary_total is not None and int(summary_total) != shard_total:
        msg = (
            "SQLite manifest disclosure summary does not match shard totals: "
            f"manifest={manifest_path}, summary={int(summary_total)}, shards={shard_total}"
        )
        raise ValueError(msg)


def _sqlite_table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(
            f"PRAGMA table_info({_quoted_sqlite_identifier(table_name)})"
        ).fetchall()
    }


def _sqlite_select_column(columns: set[str], column_name: str) -> str:
    quoted_column = _quoted_sqlite_identifier(column_name)
    if column_name in columns:
        return quoted_column
    return f"NULL AS {quoted_column}"


def _iter_sqlite_manifest_disclosure_records(
    manifest_path: Path,
    manifest: dict[str, Any],
) -> Any:
    table_name = (
        str(manifest.get("table_name") or "disclosures").strip() or "disclosures"
    )
    quoted_table = _quoted_sqlite_identifier(table_name)
    for shard in sorted(
        list(manifest.get("shards") or []), key=lambda item: str(item.get("year") or "")
    ):
        shard_path = _resolve_sqlite_shard_path(manifest_path, shard)
        if not shard_path.is_file():
            msg = f"SQLite shard not found: {shard_path}"
            raise ValueError(msg)
        connection = sqlite3.connect(shard_path)
        connection.row_factory = sqlite3.Row
        try:
            columns = _sqlite_table_columns(connection, table_name)
            selected_columns = ",\n                    ".join(
                _sqlite_select_column(columns, column_name)
                for column_name in [
                    "row_no",
                    "company_key",
                    "company_name",
                    "company_id",
                    "market",
                    "disclosed_at",
                    "disclosed_date",
                    "title",
                    "title_attr",
                    "title_base",
                    "title_display",
                    "title_flags_json",
                    "is_correction_report",
                    "has_later_correction",
                    "acpt_no",
                    "doc_no",
                    "submitter",
                    "source_file",
                    "source_page",
                ]
            )
            cursor = connection.execute(
                f"""
                SELECT
                    {selected_columns}
                FROM {quoted_table}
                """
            )
            for row in cursor:
                record = dict(row)
                record["title_flags"] = list(
                    json.loads(str(record.get("title_flags_json") or "[]"))
                )
                yield _prepare_filter_record(record)
        finally:
            connection.close()


def _element_text(node: html.HtmlElement | None) -> str:
    if node is None:
        return ""
    return _clean_text(" ".join(text for text in node.itertext()))


def _display_text(node: html.HtmlElement | None) -> str:
    if node is None:
        return ""
    return _clean_text(node.text_content())


def _title_flags(title: str) -> list[str]:
    flags: list[str] = []
    for match in _TITLE_FLAG_RE.finditer(title):
        flag = _clean_text(match.group(1))
        if flag and flag not in flags:
            flags.append(flag)
    return flags


def _has_later_correction(disclosure_cell: html.HtmlElement) -> bool:
    return any(
        _clean_text(image_tag.get("alt")) == _LATER_CORRECTION_LABEL
        for image_tag in disclosure_cell.xpath(".//img")
    )


def _companysummary_onclick(onclick_value: object) -> str | None:
    match = _COMPANYSUMMARY_OPEN_RE.search(str(onclick_value or ""))
    if match is None:
        return None
    return match.group("company_id").strip() or None


def _disclosure_onclick(onclick_value: object) -> tuple[str | None, str | None]:
    match = _OPEN_DISCLS_VIEWER_RE.search(str(onclick_value or ""))
    if match is None:
        return (None, None)
    return (
        match.group("acpt_no").strip() or None,
        match.group("doc_no").strip() or None,
    )


def _find_disclosure_results_table(root: html.HtmlElement) -> html.HtmlElement | None:
    for table_tag in root.xpath("//table"):
        summary = _clean_text(table_tag.get("summary"))
        if "회사명" in summary and "공시제목" in summary:
            return table_tag
    tables = root.xpath(
        "//table[contains(concat(' ', normalize-space(@class), ' '), ' list ')]"
    )
    return tables[0] if tables else None


def _build_source_disclosure_row(row_tag: html.HtmlElement) -> dict[str, Any] | None:
    cells = row_tag.xpath("./td")
    if len(cells) < 5:
        return None

    company_cell = cells[2]
    disclosure_cell = cells[3]
    submitter_cell = cells[4]
    company_links = company_cell.xpath(".//a[@id='companysum']") or company_cell.xpath(
        ".//a"
    )
    company_link = company_links[0] if company_links else None
    disclosure_links = disclosure_cell.xpath(".//a")
    disclosure_link = disclosure_links[0] if disclosure_links else None

    company_name = ""
    company_id = None
    if company_link is not None:
        company_name = _clean_text(
            company_link.get("title") or _element_text(company_link)
        )
        company_id = _companysummary_onclick(company_link.get("onclick"))
    if not company_name:
        company_name = _element_text(company_cell)

    labels = [
        _clean_text(image_tag.get("alt")) for image_tag in company_cell.xpath(".//img")
    ]
    labels = [label for label in labels if label]
    market = labels[0] if labels else None
    badges = labels[1:] if len(labels) > 1 else []

    acpt_no, doc_no = _disclosure_onclick(
        disclosure_link.get("onclick") if disclosure_link is not None else None
    )
    title_attr = ""
    title_display = ""
    if disclosure_link is not None:
        title_attr = _clean_text(disclosure_link.get("title"))
        title_display = _display_text(disclosure_link)
    title = title_display or title_attr
    if not title:
        title = _display_text(disclosure_cell)
        title_display = title
    title_flags = _title_flags(title_display or title)

    return {
        "company_key": _clean_text(company_id or company_name),
        "row_no": _element_text(cells[0]),
        "company_name": company_name,
        "company_id": company_id,
        "market": market,
        "badges": badges,
        "disclosed_at": _element_text(cells[1]),
        "title": title,
        "title_attr": title_attr,
        "title_base": title_attr,
        "title_display": title_display or title,
        "title_flags": title_flags,
        "is_correction_report": "정정" in title_flags,
        "has_later_correction": _has_later_correction(disclosure_cell),
        "acpt_no": acpt_no,
        "doc_no": doc_no,
        "submitter": _element_text(submitter_cell),
    }


def _parse_source_body_file(file_path: Path) -> list[dict[str, Any]]:
    markup = decode_html_markup(file_path.read_bytes())
    parser = html.HTMLParser(recover=True, huge_tree=True)
    try:
        root = html.document_fromstring(markup, parser=parser)
    except etree.ParserError as exc:
        raise ValueError(f"Failed to parse KIND disclosure result page: {file_path}") from exc
    table_tag = _find_disclosure_results_table(root)
    if table_tag is None:
        raise ValueError(f"KIND disclosure result table is missing: {file_path}")

    parent_tags = table_tag.xpath("./tbody") or [table_tag]
    rows: list[dict[str, Any]] = []
    for parent_tag in parent_tags:
        for row_tag in parent_tag.xpath("./tr"):
            row = _build_source_disclosure_row(row_tag)
            if row is not None:
                row["source_file"] = str(file_path)
                row["source_page"] = _result_page_number(file_path)
                rows.append(row)
    return rows


def _find_source_body_files(root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in root.rglob("*_post_page_*.body")
            if not any(
                part.startswith(".")
                for part in path.relative_to(root).parts[:-1]
            )
        ),
        key=lambda path: (
            str(path.parent.relative_to(root)),
            _result_page_number(path),
            path.name,
        ),
    )


def _ensure_safe_source_root_directory(root: Path) -> None:
    risky_directories = {
        Path(root.anchor).resolve(),
        Path.home().resolve(),
        PROJECT_ROOT.resolve(),
    }
    risky_directories.update(PROJECT_ROOT.resolve().parents)
    if root in risky_directories:
        msg = f"Refusing to recursively inspect high-risk root_directory: {root}"
        raise ValueError(msg)


def _source_cache_key(root: Path, body_paths: list[Path]) -> tuple[str, int, int, int]:
    latest_modified_ns = 0
    total_size = 0
    for body_path in body_paths:
        stat_result = body_path.stat()
        latest_modified_ns = max(latest_modified_ns, stat_result.st_mtime_ns)
        total_size += stat_result.st_size
    return (str(root), len(body_paths), latest_modified_ns, total_size)


@lru_cache(maxsize=4)
def _parse_source_body_files_cached(
    root_path: str,
    body_count: int,
    latest_modified_ns: int,
    total_size: int,
    workers: int,
) -> tuple[tuple[dict[str, Any], ...], int]:
    root = Path(root_path)
    body_paths = _find_source_body_files(root)
    if not body_paths:
        return ((), 0)

    worker_count = _resolve_filter_workers(workers, len(body_paths))
    parsed_by_path: dict[Path, list[dict[str, Any]]] = {}
    if worker_count == 1:
        for body_path in body_paths:
            parsed_by_path[body_path] = _parse_source_body_file(body_path)
    else:
        with ThreadPoolExecutor(
            max_workers=worker_count, thread_name_prefix="kind-filter"
        ) as executor:
            completed = bounded_as_completed(
                executor,
                body_paths,
                lambda body_path: executor.submit(
                    _parse_source_body_file, body_path
                ),
                max_pending=worker_count * 2,
            )
            for future, body_path in completed:
                parsed_by_path[body_path] = future.result()

    records: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    for body_path in body_paths:
        for record in parsed_by_path.get(body_path, []):
            key = (
                str(record.get("acpt_no") or ""),
                str(record.get("company_id") or ""),
                str(record.get("disclosed_at") or ""),
                str(record.get("title") or ""),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            records.append(_prepare_filter_record(record))
    return (tuple(records), len(body_paths))


def _iter_source_disclosure_records(
    root_directory: str | Path,
    *,
    progress_callback: ProgressCallback | None = None,
    progress_interval: int = 100,
    workers: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    root = Path(root_directory).expanduser().resolve()
    if not root.is_dir():
        msg = f"root_directory is not a directory: {root}"
        raise ValueError(msg)
    _ensure_safe_source_root_directory(root)
    body_paths = _find_source_body_files(root)
    folders: dict[Path, list[Path]] = {}
    for body_path in body_paths:
        folders.setdefault(body_path.parent, []).append(body_path)
    records_tuple, body_file_count = _parse_source_body_files_cached(
        *_source_cache_key(root, body_paths),
        _resolve_filter_workers(workers, len(body_paths)),
    )
    records = list(records_tuple)
    for index, folder_path in enumerate(sorted(folders), start=1):
        _emit_progress(
            progress_callback,
            source_type="source_folder",
            unit_label="폴더",
            completed=index,
            total=len(folders),
            records=len(records),
            progress_interval=progress_interval,
        )
    return (records, body_file_count)




__all__ = [name for name in globals() if not name.startswith("__")]
