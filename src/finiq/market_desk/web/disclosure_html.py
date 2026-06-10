"""KIND disclosure viewer HTML download helpers for the web UI."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from threading import Lock
from typing import Any, Callable

import requests
from bs4 import Comment, Tag

from finiq.config import PROJECT_ROOT
from finiq.data_scraper.core.client import (
    KIND_DISCLOSURE_VIEWER_URL,
    VIEWER_HTML_FILENAME_TEMPLATE,
    download_disclosure_viewer_htmls,
)
from finiq.data_scraper.core.constants import DEFAULT_REQUEST_HEADERS
from finiq.data_scraper.parse._disclosures import disclosure_file_rows
from finiq.data_scraper.parse._markup import (
    _clean_text,
    get_tag_attributes,
    parse_html_with_recovery,
)
from finiq.data_scraper.parse._snippets import dart_main_doc_no, search_paths, viewer_html
from finiq.data_scraper.storage.result_files import sorted_result_page_paths

ACPT_NUMBER_KEYS = {"acpt_no", "acptno", "acptNo", "acpt_no_list", "acptNumbers"}
HTML_MANIFEST_FILENAME = "kind_disclosure_html_manifest.json"
COMPRESSED_EXTERNAL_HTML_FILENAME = "compressed-external-html.json"
HTML_DOWNLOAD_AUXILIARY_FILENAMES = {
    HTML_MANIFEST_FILENAME,
    COMPRESSED_EXTERNAL_HTML_FILENAME,
    ".DS_Store",
}
HTML_DELETE_CONFIRMATION_TEXT = "확인했습니다."
_CANCELLED_DOWNLOADS: set[str] = set()
_CANCEL_LOCK = Lock()
ProgressCallback = Callable[[str], None]
_SIMPLE_SCRIPT_VAR_RE = re.compile(
    r"\bvar\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?P<value>'[^']*'|\"[^\"]*\"|[-]?\d+(?:\.\d+)?)\s*;"
)
_TEXT_BLOCK_TAGS = {
    "button",
    "caption",
    "dd",
    "dt",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "label",
    "li",
    "p",
    "span",
    "td",
    "th",
}


def _ensure_safe_html_cleanup_directory(output_directory: Path) -> None:
    risky_directories = {
        Path(output_directory.anchor).resolve(),
        Path.home().resolve(),
        PROJECT_ROOT.resolve(),
    }
    risky_directories.update(PROJECT_ROOT.resolve().parents)
    if output_directory in risky_directories:
        msg = f"Refusing to inspect or clean high-risk output_directory: {output_directory}"
        raise ValueError(msg)


def cancel_disclosure_html_download(token: str) -> dict[str, Any]:
    normalized_token = str(token or "").strip()
    if not normalized_token:
        msg = "cancel_token is required"
        raise ValueError(msg)
    with _CANCEL_LOCK:
        _CANCELLED_DOWNLOADS.add(normalized_token)
    return {"cancelled": True, "cancel_token": normalized_token}


def _clear_cancel_token(token: str | None) -> None:
    if not token:
        return
    with _CANCEL_LOCK:
        _CANCELLED_DOWNLOADS.discard(token)


def _is_cancelled(token: str | None) -> bool:
    if not token:
        return False
    with _CANCEL_LOCK:
        return token in _CANCELLED_DOWNLOADS


def collect_acpt_numbers_from_json(value: Any) -> list[str]:
    """Collect unique KIND receipt numbers from nested JSON-like data."""
    numbers: list[str] = []
    seen: set[str] = set()

    def add(raw_value: object) -> None:
        normalized = str(raw_value or "").strip()
        if not normalized or not normalized.isdigit() or normalized in seen:
            return
        seen.add(normalized)
        numbers.append(normalized)

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in ACPT_NUMBER_KEYS:
                    if isinstance(child, list):
                        for child_item in child:
                            add(child_item)
                    else:
                        add(child)
                visit(child)
            return
        if isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return numbers


def _collect_disclosure_metadata_from_json(value: Any) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}

    def acpt_no_from(item: dict[str, Any]) -> str:
        for key in ("acpt_no", "acptno", "acptNo"):
            normalized = str(item.get(key) or "").strip()
            if normalized.isdigit():
                return normalized
        return ""

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            acpt_no = acpt_no_from(item)
            if acpt_no and acpt_no not in metadata:
                metadata[acpt_no] = {
                    "acpt_no": acpt_no,
                    "market": item.get("market"),
                    "company_name": item.get("company_name"),
                    "company_id": item.get("company_id"),
                    "disclosed_at": item.get("disclosed_at"),
                    "title": item.get("title"),
                }
            for child in item.values():
                visit(child)
            return
        if isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return metadata


def _load_result_directory_disclosures(source_directory: Path) -> dict[str, Any]:
    body_paths = sorted_result_page_paths(source_directory)
    if not body_paths:
        msg = f"No KIND result page body files found in source_json_path directory: {source_directory}"
        raise ValueError(msg)
    disclosures: list[dict[str, Any]] = []
    seen: set[str] = set()
    for body_path in body_paths:
        for row in disclosure_file_rows(body_path):
            acpt_no = str(row.get("acpt_no") or "").strip()
            if not acpt_no or acpt_no in seen:
                continue
            disclosures.append(row)
            seen.add(acpt_no)
    if not disclosures:
        msg = f"No acpt_no values found in KIND result page body files: {source_directory}"
        raise ValueError(msg)
    return {
        "format": "kind_disclosure_result_directory_v1",
        "source_json_path": str(source_directory),
        "disclosures": disclosures,
    }


def _load_source_json_path_payload(source_json_path: Any) -> tuple[Any, str]:
    source_path = Path(str(source_json_path)).expanduser().resolve()
    if source_path.is_dir():
        return _load_result_directory_disclosures(source_path), str(source_path)
    if not source_path.is_file():
        msg = f"source_json_path does not exist: {source_path}"
        raise ValueError(msg)
    return json.loads(source_path.read_text(encoding="utf-8")), str(source_path)


def _as_split_by_year(body: dict[str, Any]) -> bool:
    return bool(body.get("split_by_year"))


def _as_named_split_by_year(body: dict[str, Any], key: str) -> bool:
    if key in body:
        return bool(body.get(key))
    return _as_split_by_year(body)


def _as_input_split_by_year(body: dict[str, Any]) -> bool:
    return _as_named_split_by_year(body, "input_split_by_year")


def _as_source_split_by_year(body: dict[str, Any]) -> bool:
    return _as_named_split_by_year(body, "source_split_by_year")


def _as_output_split_by_year(body: dict[str, Any]) -> bool:
    return _as_named_split_by_year(body, "output_split_by_year")


def _year_from_disclosure(acpt_no: str, disclosure: dict[str, Any] | None = None) -> str:
    disclosed_at = str((disclosure or {}).get("disclosed_at") or "").strip()
    if len(disclosed_at) >= 4 and disclosed_at[:4].isdigit():
        return disclosed_at[:4]
    if len(acpt_no) >= 4 and acpt_no[:4].isdigit():
        return acpt_no[:4]
    return "unknown"


def _target_years_from_json(source_json: Any, acpt_numbers: list[str]) -> dict[str, str]:
    metadata = _collect_disclosure_metadata_from_json(source_json)
    return {
        acpt_no: _year_from_disclosure(acpt_no, metadata.get(acpt_no))
        for acpt_no in acpt_numbers
    }


def _target_html_path(
    output_directory: Path,
    acpt_no: str,
    *,
    split_by_year: bool,
    target_years: dict[str, str] | None = None,
) -> Path:
    filename = VIEWER_HTML_FILENAME_TEMPLATE.format(acpt_no=acpt_no)
    if not split_by_year:
        return output_directory / filename
    year = (target_years or {}).get(acpt_no) or _year_from_disclosure(acpt_no)
    return output_directory / year / filename


def _iter_html_output_files(output_directory: Path, *, split_by_year: bool) -> list[Path]:
    if not split_by_year:
        return sorted(path for path in output_directory.iterdir() if path.is_file())

    files = [path for path in output_directory.iterdir() if path.is_file()]
    for child in sorted(path for path in output_directory.iterdir() if path.is_dir()):
        if len(child.name) == 4 and child.name.isdigit():
            files.extend(path for path in child.iterdir() if path.is_file())
    return sorted(files)


def _detect_html_split_by_year(directory: Path) -> bool | None:
    if not directory.is_dir():
        return None
    has_root_html = any(path.is_file() and path.suffix.lower() == ".html" for path in directory.iterdir())
    has_year_html = any(
        child.is_dir()
        and len(child.name) == 4
        and child.name.isdigit()
        and any(path.is_file() and path.suffix.lower() == ".html" for path in child.iterdir())
        for child in directory.iterdir()
    )
    if has_year_html:
        return True
    if has_root_html:
        return False
    return None


def _relative_name(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _write_html_manifest(
    *,
    output_directory: Path,
    source_json_path: str,
    acpt_numbers: list[str],
    source_json: Any,
) -> Path:
    import json

    metadata = _collect_disclosure_metadata_from_json(source_json)
    disclosures = [
        metadata.get(acpt_no, {"acpt_no": acpt_no})
        for acpt_no in acpt_numbers
    ]
    manifest_path = output_directory / HTML_MANIFEST_FILENAME
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "source_json_path": source_json_path,
                "disclosures": disclosures,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def _parse_progress_interval(value: Any) -> int:
    if value in (None, ""):
        return 10
    parsed = int(value)
    if parsed < 1:
        msg = "progress_interval must be >= 1"
        raise ValueError(msg)
    return parsed


def _describe_unexpected_html_output_file(filename: str) -> str:
    if filename.startswith("parsed-") and filename.endswith(".json"):
        return "파싱 결과 JSON"
    if filename.endswith(".html"):
        return "대상 접수번호 목록에 없는 HTML"
    if filename.endswith(".json"):
        return "JSON 파일"
    return "HTML 저장 대상이 아닌 파일"


def _validate_html_output_directory_files(
    output_directory: Path,
    acpt_numbers: list[str],
    *,
    split_by_year: bool = False,
    target_years: dict[str, str] | None = None,
    allow_unexpected: bool = False,
) -> dict[str, Any]:
    if not output_directory.exists():
        return {
            "existing_target_html_count": 0,
            "missing_target_html_count": len(acpt_numbers),
            "existing_target_acpt_numbers": [],
            "missing_target_acpt_numbers": acpt_numbers,
            "auxiliary_file_count": 0,
            "total_file_count": 0,
        }
    if not output_directory.is_dir():
        msg = f"output_directory is not a directory: {output_directory}"
        raise ValueError(msg)

    allowed_paths = {
        _target_html_path(
            output_directory,
            acpt_no,
            split_by_year=split_by_year,
            target_years=target_years,
        )
        for acpt_no in acpt_numbers
    }
    allowed_paths.update(output_directory / filename for filename in HTML_DOWNLOAD_AUXILIARY_FILENAMES)
    if split_by_year:
        for year in set((target_years or {}).values()):
            allowed_paths.update(output_directory / year / filename for filename in HTML_DOWNLOAD_AUXILIARY_FILENAMES)
    files = _iter_html_output_files(output_directory, split_by_year=split_by_year)
    existing_paths = {path.resolve() for path in files}
    existing_target_acpt_numbers = [
        acpt_no
        for acpt_no in acpt_numbers
        if _target_html_path(
            output_directory,
            acpt_no,
            split_by_year=split_by_year,
            target_years=target_years,
        ).resolve()
        in existing_paths
    ]
    missing_target_acpt_numbers = [
        acpt_no
        for acpt_no in acpt_numbers
        if _target_html_path(
            output_directory,
            acpt_no,
            split_by_year=split_by_year,
            target_years=target_years,
        ).resolve()
        not in existing_paths
    ]
    allowed_resolved_paths = {path.resolve() for path in allowed_paths}
    allowed_file_count = sum(1 for path in files if path.resolve() in allowed_resolved_paths)
    target_html_count = len(existing_target_acpt_numbers)
    auxiliary_file_count = allowed_file_count - target_html_count
    unexpected_files = sorted(
        _relative_name(path, output_directory)
        for path in files
        if path.resolve() not in allowed_resolved_paths
    )
    if unexpected_files and not allow_unexpected:
        unexpected_summary = "\n".join(
            f"- {filename} ({_describe_unexpected_html_output_file(filename)})"
            for filename in unexpected_files
        )
        msg = (
            "HTML 저장 디렉토리에 대상 접수번호 HTML이 아닌 파일이 있습니다.\n"
            f"저장 경로: {output_directory}\n"
            "전체 검사 결과:\n"
            f"- 전체 파일: {len(files)}개\n"
            f"- 대상 접수번호 HTML: {target_html_count}개 / {len(acpt_numbers)}개\n"
            f"- 허용 보조 파일: {auxiliary_file_count}개\n"
            f"- 문제 파일: {len(unexpected_files)}개\n"
            "문제 파일 전체:\n"
            f"{unexpected_summary}\n"
            "저장 경로를 비우거나, 대상 HTML만 있는 별도 폴더를 선택하세요."
        )
        raise ValueError(msg)
    return {
        "existing_target_html_count": target_html_count,
        "missing_target_html_count": len(missing_target_acpt_numbers),
        "existing_target_acpt_numbers": existing_target_acpt_numbers,
        "missing_target_acpt_numbers": missing_target_acpt_numbers,
        "auxiliary_file_count": auxiliary_file_count,
        "total_file_count": len(files),
        "unexpected_file_count": len(unexpected_files),
        "unexpected_files": unexpected_files,
    }


def _delete_unexpected_html_output_directory_files(
    output_directory: Path,
    acpt_numbers: list[str],
    *,
    split_by_year: bool = False,
    target_years: dict[str, str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not output_directory.exists():
        return {
            "existing_target_html_count": 0,
            "missing_target_html_count": len(acpt_numbers),
            "existing_target_acpt_numbers": [],
            "missing_target_acpt_numbers": acpt_numbers,
            "auxiliary_file_count": 0,
            "total_file_count": 0,
            "deleted_files": [],
        }
    if not output_directory.is_dir():
        msg = f"output_directory is not a directory: {output_directory}"
        raise ValueError(msg)

    allowed_paths = {
        _target_html_path(
            output_directory,
            acpt_no,
            split_by_year=split_by_year,
            target_years=target_years,
        )
        for acpt_no in acpt_numbers
    }
    allowed_paths.update(output_directory / filename for filename in HTML_DOWNLOAD_AUXILIARY_FILENAMES)
    if split_by_year:
        for year in set((target_years or {}).values()):
            allowed_paths.update(output_directory / year / filename for filename in HTML_DOWNLOAD_AUXILIARY_FILENAMES)
    allowed_resolved_paths = {path.resolve() for path in allowed_paths}
    files = _iter_html_output_files(output_directory, split_by_year=split_by_year)
    deleted_files: list[dict[str, str]] = []
    for path in files:
        if path.resolve() in allowed_resolved_paths:
            continue
        deleted_files.append(
            {
                "path": str(path),
                "name": _relative_name(path, output_directory),
                "reason": _describe_unexpected_html_output_file(path.name),
            }
        )
        if not dry_run:
            path.unlink()

    summary = _validate_html_output_directory_files(
        output_directory,
        acpt_numbers,
        split_by_year=split_by_year,
        target_years=target_years,
        allow_unexpected=dry_run,
    )
    summary["deleted_files"] = deleted_files
    return summary


def _is_delete_confirmed(body: dict[str, Any]) -> bool:
    return (
        body.get("delete_confirmed") is True
        and str(body.get("delete_confirmation_text") or "").strip() == HTML_DELETE_CONFIRMATION_TEXT
    )


def _apply_limit_to_acpt_numbers(acpt_numbers: list[str], limit: Any) -> list[str]:
    if limit in (None, ""):
        return acpt_numbers
    parsed_limit = int(limit)
    if parsed_limit < 1:
        msg = "limit must be >= 1"
        raise ValueError(msg)
    return acpt_numbers[:parsed_limit]


def _apply_limit_to_targets(targets: list[dict[str, str]], limit: Any) -> list[dict[str, str]]:
    limited_acpt_numbers = _apply_limit_to_acpt_numbers(
        [target["acpt_no"] for target in targets],
        limit,
    )
    return targets[: len(limited_acpt_numbers)]


def _parse_merge_limit(value: Any) -> int | None:
    if value in (None, ""):
        return None
    parsed = int(value)
    if parsed < 1:
        msg = "limit must be >= 1"
        raise ValueError(msg)
    return parsed


def _collect_content_html_files(input_directory: Path, *, split_by_year: bool) -> list[tuple[str, Path]]:
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)
    if not split_by_year:
        return [
            (_year_from_disclosure(path.stem), path)
            for path in sorted(input_directory.glob("*.html"))
            if path.is_file() and path.stem.isdigit()
        ]

    files: list[tuple[str, Path]] = []
    for year_directory in sorted(path for path in input_directory.iterdir() if path.is_dir()):
        if len(year_directory.name) != 4 or not year_directory.name.isdigit():
            continue
        files.extend(
            (year_directory.name, path)
            for path in sorted(year_directory.glob("*.html"))
            if path.is_file() and path.stem.isdigit()
        )
    return files


def _collect_external_html_files(input_directory: Path, *, split_by_year: bool) -> list[tuple[str, Path]]:
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)

    if not split_by_year:
        return [
            (_year_from_disclosure(path.stem), path)
            for path in sorted(input_directory.glob("*.html"))
            if path.is_file() and path.stem.isdigit()
        ]

    files: list[tuple[str, Path]] = []
    for year_directory in sorted(path for path in input_directory.iterdir() if path.is_dir()):
        if len(year_directory.name) != 4 or not year_directory.name.isdigit():
            continue
        files.extend(
            (year_directory.name, path)
            for path in sorted(year_directory.glob("*.html"))
            if path.is_file() and path.stem.isdigit()
        )
    return files


def _resolve_content_merge_output_path(output_path_raw: str, input_directory: Path) -> Path:
    if output_path_raw:
        output_path = Path(output_path_raw).expanduser().resolve()
        if output_path.suffix.lower() == ".json":
            return output_path
        return output_path / "merged-content-html.json"
    return input_directory / "merged-content-html.json"


def _resolve_external_compress_output_directory(output_directory_raw: str, input_directory: Path) -> Path:
    if output_directory_raw:
        return Path(output_directory_raw).expanduser().resolve()
    return input_directory


def _compact_tag(tag: Tag, *, text: bool = False) -> dict[str, Any]:
    record: dict[str, Any] = {"attrs": get_tag_attributes(tag)}
    if text:
        record["text"] = _clean_text(tag.get_text(separator=" ", strip=True))
    return record


def _compact_option_tag(option_tag: Tag) -> dict[str, Any]:
    value = str(option_tag.get("value") or "").strip()
    doc_no = value
    latest_flag = None
    if "|" in value:
        doc_no, latest_flag = value.split("|", 1)
    return {
        "attrs": get_tag_attributes(option_tag),
        "text": _clean_text(option_tag.get_text(separator=" ", strip=True)),
        "value": value,
        "doc_no": doc_no.strip(),
        "latest_flag": latest_flag.strip().upper() if latest_flag else None,
        "selected": option_tag.has_attr("selected"),
    }


def _compact_select_tag(select_tag: Tag) -> dict[str, Any]:
    return {
        "attrs": get_tag_attributes(select_tag),
        "id": str(select_tag.get("id") or "").strip(),
        "name": str(select_tag.get("name") or "").strip(),
        "options": [
            _compact_option_tag(option_tag)
            for option_tag in select_tag.find_all("option")
            if isinstance(option_tag, Tag)
        ],
    }


def _direct_text(tag: Tag) -> str:
    return _clean_text(
        " ".join(
            str(item)
            for item in tag.find_all(string=True, recursive=False)
            if not isinstance(item, Comment)
        )
    )


def _compact_anchor_tag(anchor_tag: Tag) -> dict[str, Any]:
    return {
        "attrs": get_tag_attributes(anchor_tag),
        "text": _clean_text(anchor_tag.get_text(separator=" ", strip=True)),
        "images": [
            _compact_tag(image_tag)
            for image_tag in anchor_tag.find_all("img")
            if isinstance(image_tag, Tag)
        ],
    }


def _compact_script_tag(script_tag: Tag) -> dict[str, Any]:
    script_text = "" if script_tag.get("src") else _clean_text(script_tag.get_text() or "")
    return {
        "attrs": get_tag_attributes(script_tag),
        "text": script_text,
        "variables": _extract_simple_script_variables(script_tag.get_text() or "")
        if script_text
        else [],
    }


def _compact_text_block(tag: Tag) -> dict[str, Any] | None:
    text = _direct_text(tag)
    if not text:
        return None
    return {
        "tag": tag.name,
        "attrs": get_tag_attributes(tag),
        "text": text,
    }


def _extract_simple_script_variables(script_text: str) -> list[dict[str, str]]:
    variables: list[dict[str, str]] = []
    for match in _SIMPLE_SCRIPT_VAR_RE.finditer(script_text):
        value = match.group("value").strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        variables.append({"name": match.group("name"), "value": value})
    return variables


def _compact_external_viewer_html(html_markup: str | bytes) -> dict[str, Any]:
    """KIND viewer wrapper HTML에서 저장 가치가 있는 외부 메타데이터만 추출한다."""
    html_bytes = (
        html_markup.encode("utf-8") if isinstance(html_markup, str) else html_markup
    )
    parsed = viewer_html(html_markup)
    soup = parse_html_with_recovery(html_markup)

    title_tag = soup.find("title")
    header_tag = soup.find("h1", class_="ttl")
    forms: list[dict[str, Any]] = []
    for form_tag in soup.find_all("form"):
        if not isinstance(form_tag, Tag):
            continue
        forms.append(
            {
                "attrs": get_tag_attributes(form_tag),
                "inputs": [
                    _compact_tag(input_tag)
                    for input_tag in form_tag.find_all("input")
                    if isinstance(input_tag, Tag)
                ],
                "selects": [
                    _compact_select_tag(select_tag)
                    for select_tag in form_tag.find_all("select")
                    if isinstance(select_tag, Tag)
                ],
                "textareas": [
                    _compact_tag(textarea_tag, text=True)
                    for textarea_tag in form_tag.find_all("textarea")
                    if isinstance(textarea_tag, Tag)
                ],
                "buttons": [
                    _compact_tag(button_tag, text=True)
                    for button_tag in form_tag.find_all("button")
                    if isinstance(button_tag, Tag)
                ],
            }
        )

    script_variables: list[dict[str, str]] = []
    for script_tag in soup.find_all("script"):
        if not isinstance(script_tag, Tag) or script_tag.get("src"):
            continue
        script_variables.extend(
            _extract_simple_script_variables(script_tag.get_text() or "")
        )

    text_blocks: list[dict[str, Any]] = []
    for text_tag in soup.find_all(_TEXT_BLOCK_TAGS):
        if not isinstance(text_tag, Tag):
            continue
        text_block = _compact_text_block(text_tag)
        if text_block is not None:
            text_blocks.append(text_block)

    title = parsed.get("title") or ""
    if not title and isinstance(title_tag, Tag):
        title = _clean_text(title_tag.get_text())

    return {
        "acpt_no": parsed.get("acpt_no"),
        "title": title,
        "header": parsed.get("header") or (
            _clean_text(header_tag.get_text(separator=" ", strip=True))
            if isinstance(header_tag, Tag)
            else ""
        ),
        "selected_main_doc_no": parsed.get("selected_main_doc_no"),
        "main_docs": parsed.get("main_docs") or [],
        "attached_docs": parsed.get("attached_docs") or [],
        "meta": [
            get_tag_attributes(meta_tag)
            for meta_tag in soup.find_all("meta")
            if isinstance(meta_tag, Tag) and get_tag_attributes(meta_tag)
        ],
        "forms": forms,
        "inputs": [
            _compact_tag(input_tag)
            for input_tag in soup.find_all("input")
            if isinstance(input_tag, Tag)
        ],
        "selects": [
            _compact_select_tag(select_tag)
            for select_tag in soup.find_all("select")
            if isinstance(select_tag, Tag)
        ],
        "links": [
            _compact_anchor_tag(anchor_tag)
            for anchor_tag in soup.find_all("a")
            if isinstance(anchor_tag, Tag)
        ],
        "frames": [
            _compact_tag(frame_tag)
            for frame_tag in soup.find_all(["iframe", "frame"])
            if isinstance(frame_tag, Tag)
        ],
        "resources": [
            _compact_tag(resource_tag)
            for resource_tag in soup.find_all(["link", "img", "object", "embed", "source"])
            if isinstance(resource_tag, Tag)
        ],
        "scripts": [
            _compact_script_tag(script_tag)
            for script_tag in soup.find_all("script")
            if isinstance(script_tag, Tag)
        ],
        "text_blocks": text_blocks,
        "script_variables": script_variables,
        "source_sha256": hashlib.sha256(html_bytes).hexdigest(),
        "source_size_bytes": len(html_bytes),
    }


def _verify_compressed_external_html_files(
    *,
    written_files: list[str],
    expected_acpt_numbers: list[str],
) -> dict[str, Any]:
    expected = set(expected_acpt_numbers)
    verified_acpt_numbers: list[str] = []
    missing_files: list[str] = []
    invalid_files: list[dict[str, str]] = []

    for written_file in written_files:
        path = Path(written_file)
        if not path.is_file():
            missing_files.append(written_file)
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            invalid_files.append({"path": written_file, "error": str(exc)})
            continue
        records = payload.get("records")
        if not isinstance(records, list):
            invalid_files.append({"path": written_file, "error": "records is not a list"})
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            acpt_no = str(record.get("acpt_no") or "").strip()
            if acpt_no:
                verified_acpt_numbers.append(acpt_no)

    verified = set(verified_acpt_numbers)
    verified_counts = Counter(verified_acpt_numbers)
    duplicate_acpt_numbers = sorted(acpt_no for acpt_no, count in verified_counts.items() if count > 1)
    missing_acpt_numbers = sorted(expected - verified)
    unexpected_acpt_numbers = sorted(verified - expected)
    passed = not missing_files and not invalid_files and not missing_acpt_numbers and not unexpected_acpt_numbers

    return {
        "passed": passed,
        "expected_records": len(expected_acpt_numbers),
        "verified_records": len(verified_acpt_numbers),
        "missing_records": len(missing_acpt_numbers),
        "unexpected_records": len(unexpected_acpt_numbers),
        "duplicate_records": len(duplicate_acpt_numbers),
        "missing_files": missing_files,
        "invalid_files": invalid_files,
        "missing_acpt_numbers": missing_acpt_numbers,
        "unexpected_acpt_numbers": unexpected_acpt_numbers,
        "duplicate_acpt_numbers": duplicate_acpt_numbers,
    }


def compress_disclosure_external_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Extract compact metadata from downloaded KIND viewer HTML files into one JSON."""
    input_directory_raw = str(body.get("input_directory") or body.get("source_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    input_split_by_year = _as_input_split_by_year(body)
    output_split_by_year = _as_output_split_by_year(body)
    limit = _parse_merge_limit(body.get("limit"))
    output_directory = _resolve_external_compress_output_directory(
        str(body.get("output_directory") or body.get("output_path") or "").strip(),
        input_directory,
    )

    progress_log: list[str] = []

    def emit(message: str) -> None:
        progress_log.append(message)
        if progress_callback is not None:
            progress_callback(message)

    html_files = _collect_external_html_files(input_directory, split_by_year=input_split_by_year)
    if limit is not None:
        html_files = html_files[:limit]
    if not html_files:
        msg = "No external viewer HTML files found in input_directory"
        raise ValueError(msg)

    manifest_path = input_directory / HTML_MANIFEST_FILENAME
    manifest_payload: Any = None
    if manifest_path.is_file():
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata = _collect_disclosure_metadata_from_json(manifest_payload)

    emit(f"외부 HTML 압축 대상 {len(html_files)}건을 찾았습니다.")
    emit(f"입력 경로: {input_directory}")
    emit(f"입력 분할저장: {'예' if input_split_by_year else '아니오'}")
    emit(f"출력 분할저장: {'예' if output_split_by_year else '아니오'}")

    records: list[dict[str, Any]] = []
    for index, (year, html_path) in enumerate(html_files, start=1):
        parsed = _compact_external_viewer_html(html_path.read_bytes())
        acpt_no = str(parsed.get("acpt_no") or html_path.stem).strip()
        records.append(
            {
                "acpt_no": acpt_no,
                "year": year,
                "source_file": str(html_path.resolve()),
                "title": parsed.get("title") or parsed.get("header") or "",
                "header": parsed.get("header") or "",
                "selected_main_doc_no": parsed.get("selected_main_doc_no"),
                "main_docs": parsed.get("main_docs") or [],
                "attached_docs": parsed.get("attached_docs") or [],
                "metadata": metadata.get(acpt_no) or {},
                "external_metadata": {
                    "meta": parsed.get("meta") or [],
                    "forms": parsed.get("forms") or [],
                    "inputs": parsed.get("inputs") or [],
                    "selects": parsed.get("selects") or [],
                    "links": parsed.get("links") or [],
                    "frames": parsed.get("frames") or [],
                    "resources": parsed.get("resources") or [],
                    "scripts": parsed.get("scripts") or [],
                    "text_blocks": parsed.get("text_blocks") or [],
                    "script_variables": parsed.get("script_variables") or [],
                    "source_sha256": parsed.get("source_sha256") or "",
                    "source_size_bytes": parsed.get("source_size_bytes") or 0,
                },
            }
        )
        if index % 100 == 0:
            emit(f"외부 HTML 압축 중간 확인: {index}/{len(html_files)}건 처리.")

    written_files: list[str] = []
    if output_split_by_year:
        records_by_year: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            records_by_year.setdefault(str(record.get("year") or "unknown"), []).append(record)
        for year, year_records in sorted(records_by_year.items()):
            year_output_directory = output_directory / year
            year_output_path = year_output_directory / "compressed-external-html.json"
            payload = {
                "format": "finiq_disclosure_external_html_compress_v1",
                "input_directory": str(input_directory),
                "output_directory": str(output_directory),
                "output_path": str(year_output_path),
                "split_by_year": True,
                "input_split_by_year": input_split_by_year,
                "output_split_by_year": True,
                "year": year,
                "summary": {"found_files": len(year_records), "compressed_files": len(year_records)},
                "records": year_records,
            }
            year_output_directory.mkdir(parents=True, exist_ok=True)
            year_output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            written_files.append(str(year_output_path))
            emit(f"연도별 외부 HTML 압축 JSON 저장 완료: {year_output_path}")
    else:
        output_path = output_directory / "compressed-external-html.json"
        payload = {
            "format": "finiq_disclosure_external_html_compress_v1",
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "output_path": str(output_path),
            "split_by_year": False,
            "input_split_by_year": input_split_by_year,
            "output_split_by_year": False,
            "summary": {"found_files": len(html_files), "compressed_files": len(records)},
            "records": records,
        }
        output_directory.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        written_files.append(str(output_path))
        emit(f"외부 HTML 압축 JSON 저장 완료: {output_path}")

    verification = _verify_compressed_external_html_files(
        written_files=written_files,
        expected_acpt_numbers=[str(record.get("acpt_no") or "") for record in records],
    )
    emit(
        "외부 HTML 압축 결과 재검사: "
        f"{verification['verified_records']}/{verification['expected_records']}건 확인, "
        f"누락 {verification['missing_records']}건."
    )

    return {
        "format": "finiq_disclosure_external_html_compress_result_v1",
        "input_directory": str(input_directory),
        "output_directory": str(output_directory),
        "split_by_year": output_split_by_year,
        "input_split_by_year": input_split_by_year,
        "output_split_by_year": output_split_by_year,
        "summary": {
            "found_files": len(html_files),
            "compressed_files": len(records),
            "written_files": len(written_files),
        },
        "written_files": written_files,
        "verification": verification,
        "progress_log": progress_log[-100:],
    }


def merge_disclosure_content_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Merge downloaded KIND content HTML files into JSON."""
    input_directory_raw = str(body.get("input_directory") or body.get("source_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    input_split_by_year = _as_input_split_by_year(body)
    output_split_by_year = _as_output_split_by_year(body)
    limit = _parse_merge_limit(body.get("limit"))
    output_path = _resolve_content_merge_output_path(str(body.get("output_path") or "").strip(), input_directory)
    output_root = output_path.parent if output_path.suffix.lower() == ".json" else output_path

    progress_log: list[str] = []

    def emit(message: str) -> None:
        progress_log.append(message)
        if progress_callback is not None:
            progress_callback(message)

    html_files = _collect_content_html_files(input_directory, split_by_year=input_split_by_year)
    if limit is not None:
        html_files = html_files[:limit]
    if not html_files:
        msg = "No content HTML files found in input_directory"
        raise ValueError(msg)

    emit(f"내부 HTML 병합 대상 {len(html_files)}건을 찾았습니다.")
    emit(f"입력 경로: {input_directory}")
    emit(f"입력 분할저장: {'예' if input_split_by_year else '아니오'}")
    emit(f"출력 분할저장: {'예' if output_split_by_year else '아니오'}")

    records_by_year: dict[str, list[dict[str, Any]]] = {}
    for index, (year, html_path) in enumerate(html_files, start=1):
        records_by_year.setdefault(year, []).append(
            {
                "acpt_no": html_path.stem,
                "source_file": str(html_path.resolve()),
                "html": html_path.read_text(encoding="utf-8", errors="replace"),
            }
        )
        if index % 100 == 0:
            emit(f"내부 HTML 병합 중간 확인: {index}/{len(html_files)}건 처리.")

    written_files: list[str] = []
    if output_split_by_year:
        output_root.mkdir(parents=True, exist_ok=True)
        for year, records in sorted(records_by_year.items()):
            year_output_path = output_root / f"merged-content-html-{year}.json"
            payload = {
                "format": "finiq_disclosure_content_html_merge_v1",
                "input_directory": str(input_directory),
                "output_path": str(year_output_path),
                "split_by_year": True,
                "input_split_by_year": input_split_by_year,
                "output_split_by_year": True,
                "year": year,
                "summary": {"found_files": len(records), "merged_files": len(records)},
                "records": records,
            }
            year_output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            written_files.append(str(year_output_path))
            emit(f"연도별 JSON 저장 완료: {year_output_path}")
    else:
        records = [record for year in sorted(records_by_year) for record in records_by_year[year]]
        payload = {
            "format": "finiq_disclosure_content_html_merge_v1",
            "input_directory": str(input_directory),
            "output_path": str(output_path),
            "split_by_year": False,
            "input_split_by_year": input_split_by_year,
            "output_split_by_year": False,
            "summary": {"found_files": len(records), "merged_files": len(records)},
            "records": records,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        written_files.append(str(output_path))
        emit(f"내부 HTML 병합 JSON 저장 완료: {output_path}")

    return {
        "format": "finiq_disclosure_content_html_merge_result_v1",
        "input_directory": str(input_directory),
        "output_path": str(output_path),
        "split_by_year": output_split_by_year,
        "input_split_by_year": input_split_by_year,
        "output_split_by_year": output_split_by_year,
        "summary": {
            "found_files": len(html_files),
            "merged_files": len(html_files),
            "written_files": len(written_files),
        },
        "written_files": written_files,
        "progress_log": progress_log[-100:],
    }


def clean_disclosure_html_output_directory_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Delete files that would block HTML download resume from the output directory."""
    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        msg = "output_directory is required"
        raise ValueError(msg)
    source_split_by_year = _as_source_split_by_year(body)
    output_split_by_year = _as_output_split_by_year(body)

    source_json = body.get("json")
    if source_json is None:
        source_json = body.get("payload")
    source_json_path = body.get("source_json_path")
    source_directory_raw = str(body.get("source_directory") or "").strip()

    if source_directory_raw:
        source_directory = Path(source_directory_raw).expanduser().resolve()
        targets, _manifest_payload = _collect_content_targets_from_external_directory(
            source_directory,
            split_by_year=source_split_by_year,
        )
        targets = _apply_limit_to_targets(targets, body.get("limit"))
        acpt_numbers = [target["acpt_no"] for target in targets]
        target_years = {
            target["acpt_no"]: target.get("year") or _year_from_disclosure(target["acpt_no"])
            for target in targets
        }
        source_type = "content"
        source_path = str(source_directory)
    else:
        if not source_json_path and isinstance(source_json, dict):
            source_json_path = source_json.get("source_json_path")
        if source_json_path:
            source_json, source_path = _load_source_json_path_payload(source_json_path)
        else:
            source_path = ""
        if source_json is None:
            msg = "json is required"
            raise ValueError(msg)
        acpt_numbers = collect_acpt_numbers_from_json(source_json)
        if not acpt_numbers:
            msg = "No acpt_no values found in JSON"
            raise ValueError(msg)
        acpt_numbers = _apply_limit_to_acpt_numbers(acpt_numbers, body.get("limit"))
        target_years = _target_years_from_json(source_json, acpt_numbers)
        source_type = "external"

    resolved_output_directory = Path(output_directory).expanduser().resolve()
    _ensure_safe_html_cleanup_directory(resolved_output_directory)
    dry_run = bool(body.get("dry_run", False))
    if not dry_run and not _is_delete_confirmed(body):
        planned_summary = _delete_unexpected_html_output_directory_files(
            resolved_output_directory,
            acpt_numbers,
            split_by_year=output_split_by_year,
            target_years=target_years,
            dry_run=True,
        )
        if planned_summary["deleted_files"]:
            msg = f'파일 삭제 전 "{HTML_DELETE_CONFIRMATION_TEXT}" 입력과 삭제 허가가 필요합니다.'
            raise ValueError(msg)

    summary = _delete_unexpected_html_output_directory_files(
        resolved_output_directory,
        acpt_numbers,
        split_by_year=output_split_by_year,
        target_years=target_years,
        dry_run=dry_run,
    )
    return {
        "format": "kind_disclosure_html_folder_cleanup_v1",
        "source_type": source_type,
        "source_path": source_path,
        "output_directory": str(resolved_output_directory),
        "split_by_year": output_split_by_year,
        "source_split_by_year": source_split_by_year,
        "output_split_by_year": output_split_by_year,
        "dry_run": dry_run,
        "requested_count": len(acpt_numbers),
        "deleted_count": 0 if dry_run else len(summary["deleted_files"]),
        "deletion_candidate_count": len(summary["deleted_files"]),
        "deletion_candidates": summary["deleted_files"],
        **summary,
    }


def check_disclosure_html_output_directory_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Inspect existing HTML download files without deleting anything."""
    payload = dict(body)
    payload["dry_run"] = True
    output_directory_raw = str(body.get("output_directory") or "").strip()
    detected_output_split_by_year = None
    if output_directory_raw:
        detected_output_split_by_year = _detect_html_split_by_year(
            Path(output_directory_raw).expanduser()
        )
        if detected_output_split_by_year is not None:
            payload["split_by_year"] = detected_output_split_by_year
            payload["output_split_by_year"] = detected_output_split_by_year
    source_directory_raw = str(body.get("source_directory") or "").strip()
    detected_source_split_by_year = None
    if source_directory_raw:
        detected_source_split_by_year = _detect_html_split_by_year(
            Path(source_directory_raw).expanduser()
        )
        if detected_source_split_by_year is not None:
            payload["source_split_by_year"] = detected_source_split_by_year
    summary = clean_disclosure_html_output_directory_payload(payload)
    existing_count = int(summary.get("existing_target_html_count") or 0)
    total_file_count = int(summary.get("total_file_count") or 0)
    return {
        **summary,
        "format": "kind_disclosure_html_existing_check_v1",
        "has_existing": existing_count > 0 or total_file_count > 0,
        "detected_output_split_by_year": detected_output_split_by_year,
        "detected_source_split_by_year": detected_source_split_by_year,
    }


def write_disclosure_html_manifest_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Write the HTML manifest for an already materialized output directory."""
    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        msg = "output_directory is required"
        raise ValueError(msg)

    resolved_output_directory = Path(output_directory).expanduser().resolve()
    source_directory_raw = str(body.get("source_directory") or "").strip()
    source_json = body.get("json")
    if source_json is None:
        source_json = body.get("payload")
    source_json_path = body.get("source_json_path")
    resolved_source_path = ""

    if source_directory_raw:
        source_directory = Path(source_directory_raw).expanduser().resolve()
        source_split_by_year = _as_source_split_by_year(body)
        targets, manifest_payload = _collect_content_targets_from_external_directory(
            source_directory,
            split_by_year=source_split_by_year,
        )
        targets = _apply_limit_to_targets(targets, body.get("limit"))
        acpt_numbers = [target["acpt_no"] for target in targets]
        source_json = manifest_payload or {"disclosures": [{"acpt_no": acpt_no} for acpt_no in acpt_numbers]}
        resolved_source_path = str(source_directory)
    else:
        if not source_json_path and isinstance(source_json, dict):
            source_json_path = source_json.get("source_json_path")
        if source_json_path:
            source_json, resolved_source_path = _load_source_json_path_payload(source_json_path)
        if source_json is None:
            msg = "json or source_json_path is required"
            raise ValueError(msg)
        acpt_numbers = collect_acpt_numbers_from_json(source_json)
        if not acpt_numbers:
            msg = "No acpt_no values found in JSON"
            raise ValueError(msg)
        acpt_numbers = _apply_limit_to_acpt_numbers(acpt_numbers, body.get("limit"))

    manifest_path = _write_html_manifest(
        output_directory=resolved_output_directory,
        source_json_path=resolved_source_path,
        acpt_numbers=acpt_numbers,
        source_json=source_json,
    )
    return {
        "format": "finiq_disclosure_html_manifest_write_v1",
        "output_directory": str(resolved_output_directory),
        "source_path": resolved_source_path,
        "requested_count": len(acpt_numbers),
        "manifest_path": str(manifest_path),
    }


def download_disclosure_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Download KIND viewer HTML files for receipt numbers found in the request JSON."""
    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        msg = "output_directory is required"
        raise ValueError(msg)

    source_json = body.get("json")
    if source_json is None:
        source_json = body.get("payload")
    source_json_path = body.get("source_json_path")
    resolved_source_json_path = ""
    if not source_json_path and isinstance(source_json, dict):
        source_json_path = source_json.get("source_json_path")
    if source_json_path:
        source_json, resolved_source_json_path = _load_source_json_path_payload(source_json_path)
    if source_json is None:
        msg = "json is required"
        raise ValueError(msg)

    acpt_numbers = collect_acpt_numbers_from_json(source_json)
    if not acpt_numbers:
        msg = "No acpt_no values found in JSON"
        raise ValueError(msg)

    acpt_numbers = _apply_limit_to_acpt_numbers(acpt_numbers, body.get("limit"))
    split_by_year = _as_output_split_by_year(body)
    target_years = _target_years_from_json(source_json, acpt_numbers)

    cancel_token = str(body.get("cancel_token") or "").strip() or None
    _clear_cancel_token(cancel_token)

    resolved_output_directory = Path(output_directory).expanduser().resolve()
    progress_interval = _parse_progress_interval(body.get("progress_interval"))
    progress_log: list[str] = []
    processed_count = 0

    def emit(message: str) -> None:
        progress_log.append(message)
        if progress_callback is not None:
            progress_callback(message)

    def handle_progress(message: str) -> None:
        nonlocal processed_count
        if message.startswith(("Saved KIND viewer HTML ", "Skipping existing KIND viewer HTML")):
            processed_count += 1
            if processed_count % progress_interval == 0:
                emit(f"HTML 저장 중간 확인: {processed_count}/{len(acpt_numbers)}건 처리.")
            return
        if message.startswith("Fetching KIND viewer HTML "):
            return
        emit(message)

    emit(f"HTML 저장 대상 접수번호 {len(acpt_numbers)}건을 준비했습니다.")
    emit(f"저장 경로: {resolved_output_directory}")
    emit(f"분할저장: {'예' if split_by_year else '아니오'}")
    emit(f"기존 파일 건너뛰기: {'예' if bool(body.get('skip_existing', True)) else '아니오'}")
    emit(f"이어하기 방식: 저장된 HTML 파일 건너뛰기")
    emit(f"진행 확인 간격: {progress_interval}건")
    existing_paths_by_acpt_no: dict[str, Path] = {}
    download_acpt_numbers = acpt_numbers
    if bool(body.get("skip_existing", True)):
        output_summary = _validate_html_output_directory_files(
            resolved_output_directory,
            acpt_numbers,
            split_by_year=split_by_year,
            target_years=target_years,
        )
        existing_acpt_numbers = output_summary["existing_target_acpt_numbers"]
        download_acpt_numbers = output_summary["missing_target_acpt_numbers"]
        existing_paths_by_acpt_no = {
            acpt_no: _target_html_path(
                resolved_output_directory,
                acpt_no,
                split_by_year=split_by_year,
                target_years=target_years,
            )
            for acpt_no in existing_acpt_numbers
        }
        emit("저장 디렉토리 검사 완료: 대상 HTML/메타데이터 외 파일 없음.")
        emit(
            "기존 HTML 겹침 확인: "
            f"{output_summary['existing_target_html_count']}/{len(acpt_numbers)}건."
        )
        if output_summary["existing_target_html_count"] == 0:
            emit("기존 HTML 겹침 없음: 전체 대상이 새로 저장됩니다.")
        elif output_summary["missing_target_html_count"] == 0:
            emit("기존 HTML 겹침: 전체 대상이 이미 저장되어 있습니다.")
        else:
            emit(f"새로 저장할 대상: {output_summary['missing_target_html_count']}건.")
        for acpt_no, path in existing_paths_by_acpt_no.items():
            handle_progress(f"Skipping existing KIND viewer HTML: {path}")
    try:
        downloaded_paths = []
        if download_acpt_numbers:
            grouped_acpt_numbers: dict[str, list[str]] = {"": download_acpt_numbers}
            if split_by_year:
                grouped_acpt_numbers = {}
                for acpt_no in download_acpt_numbers:
                    grouped_acpt_numbers.setdefault(target_years[acpt_no], []).append(acpt_no)
            for year, group_acpt_numbers in grouped_acpt_numbers.items():
                group_output_directory = (
                    resolved_output_directory / year
                    if split_by_year
                    else resolved_output_directory
                )
                downloaded_paths.extend(
                    download_disclosure_viewer_htmls(
                        output_directory=group_output_directory,
                        request_headers=DEFAULT_REQUEST_HEADERS,
                        acpt_numbers=group_acpt_numbers,
                        timeout=float(body.get("timeout") or 20.0),
                        wait_seconds_between_requests=float(body.get("wait_seconds") or 0.0),
                        max_requests_per_minute=int(body.get("max_requests_per_minute") or 90),
                        skip_existing=False,
                        progress_callback=handle_progress,
                        cancel_check=lambda: _is_cancelled(cancel_token),
                        max_workers=int(body.get("max_workers") or 5),
                        max_retries=int(body.get("max_retries") or 2),
                    )
                )
        saved_paths_by_acpt_no = dict(existing_paths_by_acpt_no)
        saved_paths_by_acpt_no.update({path.stem: path for path in downloaded_paths})
        saved_paths = [
            saved_paths_by_acpt_no[acpt_no]
            for acpt_no in acpt_numbers
            if acpt_no in saved_paths_by_acpt_no
        ]
        cancelled = _is_cancelled(cancel_token)
    finally:
        _clear_cancel_token(cancel_token)
    manifest_path = _write_html_manifest(
        output_directory=resolved_output_directory,
        source_json_path=resolved_source_json_path,
        acpt_numbers=acpt_numbers,
        source_json=source_json,
    )
    emit(f"HTML 메타데이터 저장 완료: {manifest_path}")
    emit(f"HTML 저장 {'중지' if cancelled else '완료'}: 저장 파일 {len(saved_paths)}/{len(acpt_numbers)}건.")
    return {
        "format": "kind_disclosure_html_download_v1",
        "output_directory": str(resolved_output_directory),
        "split_by_year": split_by_year,
        "output_split_by_year": split_by_year,
        "requested_count": len(acpt_numbers),
        "saved_count": len(saved_paths),
        "cancelled": cancelled,
        "acpt_numbers": acpt_numbers,
        "saved_files": [str(path) for path in saved_paths],
        "manifest_path": str(manifest_path),
        "progress_log": progress_log[-100:],
    }


def _fetch_content_html(
    session: requests.Session,
    *,
    acpt_no: str,
    doc_no: str,
    request_headers: dict[str, str],
    timeout: float,
) -> bytes:
    contents_response = session.get(
        KIND_DISCLOSURE_VIEWER_URL,
        params={"method": "searchContents", "docNo": doc_no},
        headers=request_headers,
        timeout=timeout,
    )
    contents_response.raise_for_status()
    paths = search_paths(contents_response.content)
    if paths is None or not paths.get("doc_loc_path"):
        msg = f"content path not found for acpt_no={acpt_no} doc_no={doc_no}"
        raise ValueError(msg)

    body_response = session.get(paths["doc_loc_path"], headers=request_headers, timeout=timeout)
    body_response.raise_for_status()
    return body_response.content


def _iter_compressed_external_html_files(source_directory: Path, *, split_by_year: bool) -> list[Path]:
    output_path = source_directory / COMPRESSED_EXTERNAL_HTML_FILENAME
    if output_path.is_file():
        return [output_path]
    if not split_by_year:
        return []
    return [
        year_directory / COMPRESSED_EXTERNAL_HTML_FILENAME
        for year_directory in sorted(path for path in source_directory.iterdir() if path.is_dir())
        if len(year_directory.name) == 4
        and year_directory.name.isdigit()
        and (year_directory / COMPRESSED_EXTERNAL_HTML_FILENAME).is_file()
    ]


def _load_compressed_external_html_payload(source_directory: Path, *, split_by_year: bool) -> dict[str, Any] | None:
    compressed_files = _iter_compressed_external_html_files(source_directory, split_by_year=split_by_year)
    if not compressed_files:
        return None

    records: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    for compressed_file in compressed_files:
        payload = json.loads(compressed_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            msg = f"compressed external HTML JSON is not an object: {compressed_file}"
            raise ValueError(msg)
        payloads.append(payload)
        file_records = payload.get("records")
        if not isinstance(file_records, list):
            msg = f"compressed external HTML JSON records is not a list: {compressed_file}"
            raise ValueError(msg)
        records.extend(record for record in file_records if isinstance(record, dict))

    if len(payloads) == 1:
        payload = dict(payloads[0])
        payload["source_json_path"] = str(compressed_files[0])
        return payload
    return {
        "format": "finiq_disclosure_external_html_compress_collection_v1",
        "source_json_path": str(source_directory),
        "split_by_year": True,
        "records": records,
    }


def _collect_content_targets_from_compressed_payload(payload: dict[str, Any]) -> tuple[list[dict[str, str]], Any]:
    targets: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in payload.get("records") or []:
        if not isinstance(record, dict):
            continue
        acpt_no = str(record.get("acpt_no") or "").strip()
        if not acpt_no.isdigit() or acpt_no in seen:
            continue
        doc_no = str(record.get("selected_main_doc_no") or "").strip()
        if not doc_no:
            for main_doc in record.get("main_docs") or []:
                if not isinstance(main_doc, dict):
                    continue
                candidate = str(main_doc.get("doc_no") or "").strip()
                if candidate:
                    doc_no = candidate
                    break
        if not doc_no:
            msg = f"selected main docNo not found in compressed external HTML JSON: {acpt_no}"
            raise ValueError(msg)
        year = str(record.get("year") or "").strip() or _year_from_disclosure(
            acpt_no,
            record.get("metadata") if isinstance(record.get("metadata"), dict) else None,
        )
        targets.append({"acpt_no": acpt_no, "doc_no": doc_no, "year": year})
        seen.add(acpt_no)
    if not targets:
        msg = "No content targets found in compressed external HTML JSON"
        raise ValueError(msg)
    return targets, payload


def _collect_content_targets_from_external_directory(
    source_directory: Path,
    *,
    split_by_year: bool = False,
) -> tuple[list[dict[str, str]], Any]:
    if not source_directory.is_dir():
        msg = f"source_directory does not exist: {source_directory}"
        raise ValueError(msg)

    import json

    manifest_path = source_directory / HTML_MANIFEST_FILENAME
    manifest_payload: Any = None
    manifest_order: list[str] = []
    if manifest_path.is_file():
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        for disclosure in manifest_payload.get("disclosures") or []:
            if not isinstance(disclosure, dict):
                continue
            acpt_no = str(disclosure.get("acpt_no") or "").strip()
            if acpt_no.isdigit():
                manifest_order.append(acpt_no)

    compressed_payload = _load_compressed_external_html_payload(
        source_directory,
        split_by_year=split_by_year,
    )
    if compressed_payload is not None:
        return _collect_content_targets_from_compressed_payload(compressed_payload)

    target_by_acpt_no: dict[str, dict[str, str]] = {}
    html_paths = sorted(source_directory.glob("*.html"))
    if split_by_year:
        html_paths = []
        for year_directory in sorted(path for path in source_directory.iterdir() if path.is_dir()):
            if len(year_directory.name) == 4 and year_directory.name.isdigit():
                html_paths.extend(sorted(year_directory.glob("*.html")))
    metadata = _collect_disclosure_metadata_from_json(manifest_payload)
    for html_path in html_paths:
        acpt_no = html_path.stem
        if not acpt_no.isdigit():
            continue
        doc_no = dart_main_doc_no(html_path.read_bytes())
        if not doc_no:
            msg = f"selected main docNo not found in external HTML: {html_path}"
            raise ValueError(msg)
        year = html_path.parent.name if split_by_year else _year_from_disclosure(acpt_no, metadata.get(acpt_no))
        target_by_acpt_no[acpt_no] = {"acpt_no": acpt_no, "doc_no": doc_no, "year": year}

    ordered_acpt_numbers = [acpt_no for acpt_no in manifest_order if acpt_no in target_by_acpt_no]
    ordered_acpt_numbers.extend(
        acpt_no for acpt_no in sorted(target_by_acpt_no) if acpt_no not in set(ordered_acpt_numbers)
    )
    targets = [target_by_acpt_no[acpt_no] for acpt_no in ordered_acpt_numbers]
    if not targets:
        if not split_by_year and any(
            child.is_dir() and len(child.name) == 4 and child.name.isdigit()
            for child in source_directory.iterdir()
        ):
            msg = (
                "No external viewer HTML files found in source_directory. "
                "The source directory appears to contain year folders; enable source_split_by_year."
            )
            raise ValueError(msg)
        msg = "No external viewer HTML files found in source_directory"
        raise ValueError(msg)
    return targets, manifest_payload


def download_disclosure_content_htmls(
    *,
    output_directory: Path,
    request_headers: dict[str, object],
    targets: list[dict[str, str]],
    timeout: float = 20.0,
    wait_seconds_between_requests: float = 0.0,
    max_requests_per_minute: int = 90,
    skip_existing: bool = True,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[Path]:
    """Download selected KIND disclosure body HTML files for receipt numbers."""
    if timeout <= 0:
        msg = "timeout must be > 0"
        raise ValueError(msg)
    if wait_seconds_between_requests < 0:
        msg = "wait_seconds_between_requests must be >= 0"
        raise ValueError(msg)
    if max_requests_per_minute < 1 or max_requests_per_minute > 100:
        msg = "max_requests_per_minute must be between 1 and 100"
        raise ValueError(msg)

    import time

    output_directory = output_directory.resolve()
    normalized_headers = {str(key): str(value) for key, value in request_headers.items()}
    saved_paths: list[Path] = []
    min_interval_seconds = 60.0 / max_requests_per_minute
    last_request_started_at = 0.0
    with requests.Session() as session:
        for index, target in enumerate(targets):
            acpt_no = target["acpt_no"]
            doc_no = target["doc_no"]
            if cancel_check is not None and cancel_check():
                break
            output_path = output_directory / VIEWER_HTML_FILENAME_TEMPLATE.format(acpt_no=acpt_no)
            if skip_existing and output_path.exists():
                if progress_callback is not None:
                    progress_callback(f"Skipping existing KIND content HTML: {output_path}")
                saved_paths.append(output_path)
                continue
            if index > 0:
                elapsed = time.time() - last_request_started_at
                sleep_seconds = max(wait_seconds_between_requests, min_interval_seconds - elapsed)
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
            last_request_started_at = time.time()
            if progress_callback is not None:
                progress_callback(f"Fetching KIND content HTML acpt_no={acpt_no} doc_no={doc_no}...")
            content = _fetch_content_html(
                session,
                acpt_no=acpt_no,
                doc_no=doc_no,
                request_headers=normalized_headers,
                timeout=timeout,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(content)
            saved_paths.append(output_path)
            if progress_callback is not None:
                progress_callback(f"Saved KIND content HTML to: {output_path}")
    return saved_paths


def download_disclosure_html_contents_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Download selected KIND disclosure body HTML files for receipt numbers."""
    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        msg = "output_directory is required"
        raise ValueError(msg)

    source_directory_raw = str(body.get("source_directory") or "").strip()
    if not source_directory_raw:
        msg = "source_directory is required"
        raise ValueError(msg)
    source_split_by_year = _as_source_split_by_year(body)
    output_split_by_year = _as_output_split_by_year(body)
    source_directory = Path(source_directory_raw).expanduser().resolve()
    targets, manifest_payload = _collect_content_targets_from_external_directory(
        source_directory,
        split_by_year=source_split_by_year,
    )

    targets = _apply_limit_to_targets(targets, body.get("limit"))
    acpt_numbers = [target["acpt_no"] for target in targets]
    target_years = {
        target["acpt_no"]: target.get("year") or _year_from_disclosure(target["acpt_no"])
        for target in targets
    }
    source_json = manifest_payload or {"disclosures": [{"acpt_no": acpt_no} for acpt_no in acpt_numbers]}

    cancel_token = str(body.get("cancel_token") or "").strip() or None
    _clear_cancel_token(cancel_token)

    resolved_output_directory = Path(output_directory).expanduser().resolve()
    progress_interval = _parse_progress_interval(body.get("progress_interval"))
    progress_log: list[str] = []
    processed_count = 0

    def emit(message: str) -> None:
        progress_log.append(message)
        if progress_callback is not None:
            progress_callback(message)

    def handle_progress(message: str) -> None:
        nonlocal processed_count
        if message.startswith(("Saved KIND content HTML ", "Skipping existing KIND content HTML")):
            processed_count += 1
            emit(message)
            if processed_count % progress_interval == 0:
                emit(f"HTML 내부 저장 중간 확인: {processed_count}/{len(acpt_numbers)}건 처리.")
            return
        if message.startswith("Fetching KIND content HTML "):
            emit(message)
            return
        emit(message)

    emit(f"HTML 내부 저장 대상 접수번호 {len(acpt_numbers)}건을 준비했습니다.")
    emit(f"외부 HTML 경로: {source_directory}")
    emit(f"저장 경로: {resolved_output_directory}")
    emit(f"입력 분할저장: {'예' if source_split_by_year else '아니오'}")
    emit(f"출력 분할저장: {'예' if output_split_by_year else '아니오'}")
    emit(f"기존 파일 건너뛰기: {'예' if bool(body.get('skip_existing', True)) else '아니오'}")
    emit(f"이어하기 방식: 저장된 HTML 파일 건너뛰기")
    emit(f"진행 확인 간격: {progress_interval}건")
    existing_paths_by_acpt_no: dict[str, Path] = {}
    download_acpt_numbers = acpt_numbers
    if bool(body.get("skip_existing", True)):
        output_summary = _validate_html_output_directory_files(
            resolved_output_directory,
            acpt_numbers,
            split_by_year=output_split_by_year,
            target_years=target_years,
        )
        existing_acpt_numbers = output_summary["existing_target_acpt_numbers"]
        download_acpt_numbers = output_summary["missing_target_acpt_numbers"]
        existing_paths_by_acpt_no = {
            acpt_no: _target_html_path(
                resolved_output_directory,
                acpt_no,
                split_by_year=output_split_by_year,
                target_years=target_years,
            )
            for acpt_no in existing_acpt_numbers
        }
        emit("저장 디렉토리 검사 완료: 대상 HTML/메타데이터 외 파일 없음.")
        emit(
            "기존 HTML 겹침 확인: "
            f"{output_summary['existing_target_html_count']}/{len(acpt_numbers)}건."
        )
        if output_summary["existing_target_html_count"] == 0:
            emit("기존 HTML 겹침 없음: 전체 대상이 새로 저장됩니다.")
        elif output_summary["missing_target_html_count"] == 0:
            emit("기존 HTML 겹침: 전체 대상이 이미 저장되어 있습니다.")
        else:
            emit(f"새로 저장할 대상: {output_summary['missing_target_html_count']}건.")
        for acpt_no, path in existing_paths_by_acpt_no.items():
            handle_progress(f"Skipping existing KIND content HTML: {path}")
    try:
        downloaded_paths = []
        if download_acpt_numbers:
            target_by_acpt_no = {target["acpt_no"]: target for target in targets}
            grouped_targets: dict[str, list[dict[str, str]]] = {
                "": [target_by_acpt_no[acpt_no] for acpt_no in download_acpt_numbers]
            }
            if output_split_by_year:
                grouped_targets = {}
                for acpt_no in download_acpt_numbers:
                    target = target_by_acpt_no[acpt_no]
                    grouped_targets.setdefault(target_years[acpt_no], []).append(target)
            for year, group_targets in grouped_targets.items():
                group_output_directory = (
                    resolved_output_directory / year
                    if output_split_by_year
                    else resolved_output_directory
                )
                downloaded_paths.extend(
                    download_disclosure_content_htmls(
                        output_directory=group_output_directory,
                        request_headers=DEFAULT_REQUEST_HEADERS,
                        targets=[
                            {"acpt_no": target["acpt_no"], "doc_no": target["doc_no"]}
                            for target in group_targets
                        ],
                        timeout=float(body.get("timeout") or 20.0),
                        wait_seconds_between_requests=float(body.get("wait_seconds") or 0.0),
                        max_requests_per_minute=int(body.get("max_requests_per_minute") or 90),
                        skip_existing=False,
                        progress_callback=handle_progress,
                        cancel_check=lambda: _is_cancelled(cancel_token),
                    )
                )
        saved_paths_by_acpt_no = dict(existing_paths_by_acpt_no)
        saved_paths_by_acpt_no.update({path.stem: path for path in downloaded_paths})
        saved_paths = [
            saved_paths_by_acpt_no[acpt_no]
            for acpt_no in acpt_numbers
            if acpt_no in saved_paths_by_acpt_no
        ]
        cancelled = _is_cancelled(cancel_token)
    finally:
        _clear_cancel_token(cancel_token)
    manifest_path = _write_html_manifest(
        output_directory=resolved_output_directory,
        source_json_path=str(source_directory),
        acpt_numbers=acpt_numbers,
        source_json=source_json,
    )
    emit(f"HTML 메타데이터 저장 완료: {manifest_path}")
    emit(f"HTML 내부 저장 {'중지' if cancelled else '완료'}: 저장 파일 {len(saved_paths)}/{len(acpt_numbers)}건.")
    return {
        "format": "kind_disclosure_html_content_download_v1",
        "output_directory": str(resolved_output_directory),
        "split_by_year": output_split_by_year,
        "source_split_by_year": source_split_by_year,
        "output_split_by_year": output_split_by_year,
        "requested_count": len(acpt_numbers),
        "saved_count": len(saved_paths),
        "cancelled": cancelled,
        "acpt_numbers": acpt_numbers,
        "saved_files": [str(path) for path in saved_paths],
        "manifest_path": str(manifest_path),
        "progress_log": progress_log[-100:],
    }
