"""KIND disclosure viewer HTML download helpers for the web UI."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any, Callable

import requests

from finiq.concurrency import bounded_as_completed, resolve_worker_count
from finiq.config import PROJECT_ROOT
from finiq.data_scraper.core.client import (
    KIND_DISCLOSURE_VIEWER_URL,
    VIEWER_HTML_FILENAME_TEMPLATE,
    _is_valid_html,
    download_disclosure_viewer_htmls,
)
from finiq.data_scraper.core.constants import DEFAULT_REQUEST_HEADERS
from finiq.data_scraper.parse._snippets import dart_main_doc_no, search_paths
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    resolve_disclosure_workspace,
    validate_workspace_mode,
)
from finiq.market_desk.web.features.disclosures.external_compact import (
    _compress_external_html_file,
    _external_html_compress_workers,
    _verify_compressed_external_html_files,
)

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


def _load_workspace_filtered_payload(body: dict[str, Any]) -> tuple[Any, str]:
    workspace = resolve_disclosure_workspace(body.get("data_root") or "")
    requested_mode = str(body.get("mode") or "").strip()
    if requested_mode:
        mode = validate_workspace_mode(requested_mode)
        source_paths = [workspace.filtered / mode / "filtered.json"]
    else:
        source_paths = []
        if workspace.filtered.is_dir():
            for mode_directory in sorted(workspace.filtered.iterdir()):
                if not mode_directory.is_dir() or mode_directory.name.startswith("."):
                    continue
                source_path = mode_directory / "filtered.json"
                if not source_path.is_file():
                    continue
                validate_workspace_mode(mode_directory.name)
                source_paths.append(source_path)
    if not source_paths or any(not path.is_file() for path in source_paths):
        expected = (
            source_paths[0]
            if source_paths
            else workspace.filtered / "<mode>" / "filtered.json"
        )
        raise ValueError(f"filtered disclosure JSON does not exist: {expected}")

    mode_payloads = {
        path.parent.name: json.loads(path.read_text(encoding="utf-8"))
        for path in source_paths
    }
    if len(source_paths) == 1:
        return next(iter(mode_payloads.values())), str(source_paths[0])
    return {
        "format": "kind_disclosure_filter_collection_v1",
        "modes": mode_payloads,
    }, str(workspace.filtered)


def _year_from_disclosure(
    acpt_no: str, disclosure: dict[str, Any] | None = None
) -> str:
    disclosed_at = str((disclosure or {}).get("disclosed_at") or "").strip()
    if len(disclosed_at) >= 4 and disclosed_at[:4].isdigit():
        return disclosed_at[:4]
    if len(acpt_no) >= 4 and acpt_no[:4].isdigit():
        return acpt_no[:4]
    raise ValueError(f"disclosure year not found: {acpt_no}")


def resolve_disclosure_html_file(
    input_directory: Path, acpt_no: str
) -> Path | None:
    """접수번호로 연도별 저장 HTML을 찾는다."""
    normalized_acpt_no = str(acpt_no or "")
    if (
        not normalized_acpt_no
        or normalized_acpt_no in {".", ".."}
        or "/" in normalized_acpt_no
        or "\\" in normalized_acpt_no
        or "\x00" in normalized_acpt_no
    ):
        return None

    filename = VIEWER_HTML_FILENAME_TEMPLATE.format(acpt_no=normalized_acpt_no)
    resolved_root = input_directory.resolve()
    if not resolved_root.is_dir():
        return None
    candidate = (
        resolved_root / _year_from_disclosure(normalized_acpt_no) / filename
    ).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _target_years_from_json(
    source_json: Any, acpt_numbers: list[str]
) -> dict[str, str]:
    metadata = _collect_disclosure_metadata_from_json(source_json)
    return {
        acpt_no: _year_from_disclosure(acpt_no, metadata.get(acpt_no))
        for acpt_no in acpt_numbers
    }


def _target_html_path(
    output_directory: Path,
    acpt_no: str,
    *,
    target_years: dict[str, str] | None = None,
) -> Path:
    filename = VIEWER_HTML_FILENAME_TEMPLATE.format(acpt_no=acpt_no)
    year = (target_years or {}).get(acpt_no) or _year_from_disclosure(acpt_no)
    return output_directory / year / filename


def _html_output_check_workers(total_targets: int) -> int:
    return resolve_worker_count(item_count=total_targets)


def _iter_html_output_files(output_directory: Path) -> list[Path]:
    files = [path for path in output_directory.iterdir() if path.is_file()]
    for child in sorted(path for path in output_directory.iterdir() if path.is_dir()):
        if len(child.name) == 4 and child.name.isdigit():
            files.extend(path for path in child.iterdir() if path.is_file())
    return sorted(files)


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
    missing_metadata = [acpt_no for acpt_no in acpt_numbers if acpt_no not in metadata]
    if missing_metadata:
        raise ValueError(
            "Missing disclosure metadata for acpt_no values: "
            + ", ".join(missing_metadata[:10])
        )
    disclosures = [metadata[acpt_no] for acpt_no in acpt_numbers]
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
    target_years: dict[str, str] | None = None,
    allow_unexpected: bool = False,
) -> dict[str, Any]:
    if not output_directory.exists():
        return {
            "existing_target_html_count": 0,
            "missing_target_html_count": len(acpt_numbers),
            "existing_target_acpt_numbers": [],
            "missing_target_acpt_numbers": acpt_numbers,
            "invalid_target_html_count": 0,
            "invalid_target_acpt_numbers": [],
            "auxiliary_file_count": 0,
            "total_file_count": 0,
        }
    if not output_directory.is_dir():
        msg = f"output_directory is not a directory: {output_directory}"
        raise ValueError(msg)

    output_directory = output_directory.resolve()
    files = _iter_html_output_files(output_directory)
    existing_paths = set(files)
    worker_count = _html_output_check_workers(len(acpt_numbers))

    def target_status(acpt_no: str) -> tuple[str, Path, bool, bool]:
        target_path = _target_html_path(
            output_directory,
            acpt_no,
            target_years=target_years,
        )
        exists = target_path in existing_paths
        return acpt_no, target_path, exists and _is_valid_html(target_path), exists

    if worker_count == 1:
        target_statuses = [target_status(acpt_no) for acpt_no in acpt_numbers]
    else:
        indexed_statuses: list[tuple[str, Path, bool, bool] | None] = [
            None
        ] * len(acpt_numbers)
        with ThreadPoolExecutor(
            max_workers=worker_count, thread_name_prefix="html-output-check"
        ) as executor:
            completed = bounded_as_completed(
                executor,
                enumerate(acpt_numbers),
                lambda item: executor.submit(target_status, item[1]),
                max_pending=worker_count * 2,
            )
            for future, (index, _acpt_no) in completed:
                indexed_statuses[index] = future.result()
        target_statuses = [
            status for status in indexed_statuses if status is not None
        ]

    allowed_paths = {target_path for _, target_path, _, _ in target_statuses}
    allowed_paths.update(
        output_directory / filename for filename in HTML_DOWNLOAD_AUXILIARY_FILENAMES
    )
    for year in set((target_years or {}).values()):
        allowed_paths.update(
            output_directory / year / filename
            for filename in HTML_DOWNLOAD_AUXILIARY_FILENAMES
        )
    existing_target_acpt_numbers = [
        acpt_no for acpt_no, _, valid, _ in target_statuses if valid
    ]
    missing_target_acpt_numbers = [
        acpt_no for acpt_no, _, valid, _ in target_statuses if not valid
    ]
    invalid_target_acpt_numbers = [
        acpt_no
        for acpt_no, _, valid, exists in target_statuses
        if exists and not valid
    ]
    allowed_file_count = sum(1 for path in files if path in allowed_paths)
    present_target_count = sum(1 for _, _, _, exists in target_statuses if exists)
    target_html_count = len(existing_target_acpt_numbers)
    auxiliary_file_count = allowed_file_count - present_target_count
    unexpected_files = sorted(
        _relative_name(path, output_directory)
        for path in files
        if path not in allowed_paths
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
            f"- 손상된 대상 HTML: {len(invalid_target_acpt_numbers)}개\n"
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
        "invalid_target_html_count": len(invalid_target_acpt_numbers),
        "invalid_target_acpt_numbers": invalid_target_acpt_numbers,
        "auxiliary_file_count": auxiliary_file_count,
        "total_file_count": len(files),
        "unexpected_file_count": len(unexpected_files),
        "unexpected_files": unexpected_files,
    }


def _delete_unexpected_html_output_directory_files(
    output_directory: Path,
    acpt_numbers: list[str],
    *,
    target_years: dict[str, str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not output_directory.exists():
        return {
            "existing_target_html_count": 0,
            "missing_target_html_count": len(acpt_numbers),
            "existing_target_acpt_numbers": [],
            "missing_target_acpt_numbers": acpt_numbers,
            "invalid_target_html_count": 0,
            "invalid_target_acpt_numbers": [],
            "auxiliary_file_count": 0,
            "total_file_count": 0,
            "deleted_files": [],
        }
    if not output_directory.is_dir():
        msg = f"output_directory is not a directory: {output_directory}"
        raise ValueError(msg)

    output_directory = output_directory.resolve()
    allowed_paths = {
        _target_html_path(
            output_directory,
            acpt_no,
            target_years=target_years,
        )
        for acpt_no in acpt_numbers
    }
    allowed_paths.update(
        output_directory / filename for filename in HTML_DOWNLOAD_AUXILIARY_FILENAMES
    )
    for year in set((target_years or {}).values()):
        allowed_paths.update(
            output_directory / year / filename
            for filename in HTML_DOWNLOAD_AUXILIARY_FILENAMES
        )
    files = _iter_html_output_files(output_directory)
    deleted_files: list[dict[str, str]] = []
    for path in files:
        if path in allowed_paths:
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
        target_years=target_years,
        allow_unexpected=dry_run,
    )
    summary["deleted_files"] = deleted_files
    return summary


def _is_delete_confirmed(body: dict[str, Any]) -> bool:
    return (
        body.get("delete_confirmed") is True
        and str(body.get("delete_confirmation_text") or "").strip()
        == HTML_DELETE_CONFIRMATION_TEXT
    )


def _apply_limit_to_acpt_numbers(acpt_numbers: list[str], limit: Any) -> list[str]:
    if limit in (None, ""):
        return acpt_numbers
    parsed_limit = int(limit)
    if parsed_limit < 1:
        msg = "limit must be >= 1"
        raise ValueError(msg)
    return acpt_numbers[:parsed_limit]


def _apply_limit_to_targets(
    targets: list[dict[str, str]], limit: Any
) -> list[dict[str, str]]:
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


def _collect_yearly_html_files(input_directory: Path) -> list[tuple[str, Path]]:
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)
    files: list[tuple[str, Path]] = []
    for year_directory in sorted(
        path for path in input_directory.iterdir() if path.is_dir()
    ):
        if len(year_directory.name) != 4 or not year_directory.name.isdigit():
            continue
        files.extend(
            (year_directory.name, path)
            for path in sorted(year_directory.glob("*.html"))
            if path.is_file() and path.stem.isdigit()
        )
    return files


def _resolve_content_merge_output_directory(
    output_directory_raw: str, input_directory: Path
) -> Path:
    output_directory = (
        Path(output_directory_raw).expanduser().resolve()
        if output_directory_raw
        else input_directory / "merged"
    )
    if output_directory.suffix.lower() == ".json":
        raise ValueError("output_directory must be a directory path")
    return output_directory


__all__ = [name for name in globals() if not name.startswith("__")]
