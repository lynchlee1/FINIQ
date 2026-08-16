"""KIND disclosure HTML download helpers for the web UI."""

from __future__ import annotations

import codecs
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import date
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
    download_disclosure_external_htmls,
)
from finiq.data_scraper.core.constants import DEFAULT_REQUEST_HEADERS
from finiq.data_scraper.parse._snippets import dart_main_doc_no, search_paths
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    atomic_write_json,
    resolve_disclosure_workspace,
    validate_workspace_mode,
)
from finiq.market_desk.web.features.disclosures.external_compact import (
    _compress_external_html_file,
    _external_html_compress_workers,
    _verify_compressed_external_html_files,
)

HTML_MANIFEST_FILENAME = "kind_disclosure_html_manifest.json"
# v1 gates reuse on a fingerprint of the whole source JSON; v2 drops that gate and
# relies on the per-acpt_no hashes, which stay valid across filter re-runs.
HTML_MANIFEST_FORMAT_V1 = "finiq_disclosure_html_manifest_v1"
HTML_MANIFEST_FORMAT_V2 = "finiq_disclosure_html_manifest_v2"
HTML_MANIFEST_FORMATS = {HTML_MANIFEST_FORMAT_V1, HTML_MANIFEST_FORMAT_V2}
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


def _html_file_integrity(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return {
        "source_sha256": digest.hexdigest(),
        "source_size_bytes": size,
    }


def _html_file_validation_and_integrity(
    path: Path,
) -> tuple[bool, dict[str, Any] | None]:
    digest = hashlib.sha256()
    size = 0
    valid = False
    decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
    text_tail = ""
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
                text = text_tail + decoder.decode(chunk)
                if "<html" in text.lower() or "openDisclsViewer" in text:
                    valid = True
                text_tail = text[-16:]
        text = text_tail + decoder.decode(b"", final=True)
        if "<html" in text.lower() or "openDisclsViewer" in text:
            valid = True
    except Exception:
        return False, None
    if not valid:
        return False, None
    return True, {
        "source_sha256": digest.hexdigest(),
        "source_size_bytes": size,
    }


def _hash_html_files(
    paths_by_acpt_no: dict[str, Path],
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[dict[str, dict[str, Any]], bool]:
    acpt_numbers = list(paths_by_acpt_no)
    if not acpt_numbers:
        return {}, False

    worker_count = _html_output_check_workers(len(acpt_numbers))
    indexed_results: list[tuple[str, dict[str, Any]] | None] = [None] * len(
        acpt_numbers
    )

    def hash_target(item: tuple[int, str]) -> tuple[int, str, dict[str, Any]]:
        index, acpt_no = item
        return index, acpt_no, _html_file_integrity(paths_by_acpt_no[acpt_no])

    with ThreadPoolExecutor(
        max_workers=worker_count, thread_name_prefix="html-integrity"
    ) as executor:
        completed = bounded_as_completed(
            executor,
            enumerate(acpt_numbers),
            lambda item: executor.submit(hash_target, item),
            max_pending=worker_count * 2,
        )
        for completed_count, (future, _item) in enumerate(completed, start=1):
            if cancel_check is not None and cancel_check():
                executor.shutdown(wait=False, cancel_futures=True)
                return {}, True
            index, acpt_no, integrity = future.result()
            indexed_results[index] = (acpt_no, integrity)
            if progress_callback is not None and completed_count % 100 == 0:
                progress_callback(
                    f"HTML 해시 생성 중간 확인: {completed_count}/{len(acpt_numbers)}건 처리."
                )

    return {
        acpt_no: integrity
        for result in indexed_results
        if result is not None
        for acpt_no, integrity in [result]
    }, False


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
    """Read receipt numbers from the canonical top-level disclosures array."""
    if not isinstance(value, dict):
        raise ValueError("disclosure JSON must contain an object")
    disclosures = value.get("disclosures")
    if not isinstance(disclosures, list):
        raise ValueError("disclosure JSON must contain a disclosures array")
    numbers: list[str] = []
    seen: set[str] = set()
    for index, disclosure in enumerate(disclosures):
        if not isinstance(disclosure, dict):
            raise ValueError(f"disclosures[{index}] must be an object")
        normalized = str(disclosure.get("acpt_no") or "").strip()
        if not normalized:
            raise ValueError(f"disclosures[{index}].acpt_no must not be empty")
        if normalized in seen:
            raise ValueError(f"duplicate acpt_no in disclosures: {normalized}")
        seen.add(normalized)
        numbers.append(normalized)
    return numbers


def _collect_disclosure_metadata_from_json(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError("disclosure JSON must contain an object")
    payload_format = value.get("format")
    if payload_format in {
        "kind_disclosure_filter_v1",
        *HTML_MANIFEST_FORMATS,
    }:
        disclosures = value.get("disclosures")
        if not isinstance(disclosures, list):
            raise ValueError("disclosure JSON must contain a disclosures array")
    elif payload_format == "finiq_disclosure_external_html_docs_v1":
        records = value.get("records")
        if not isinstance(records, list):
            raise ValueError("compressed external HTML JSON must contain a records array")
        disclosures = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise ValueError(f"records[{index}] must be an object")
            record_metadata = record.get("metadata")
            if not isinstance(record_metadata, dict):
                raise ValueError(f"records[{index}].metadata must be an object")
            disclosures.append(
                {
                    **record_metadata,
                    "acpt_no": record.get("acpt_no"),
                    "title": record.get("title"),
                }
            )
    else:
        raise ValueError(f"unsupported disclosure JSON format: {payload_format!r}")
    metadata: dict[str, dict[str, Any]] = {}
    for index, disclosure in enumerate(disclosures):
        if not isinstance(disclosure, dict):
            raise ValueError(f"disclosures[{index}] must be an object")
        acpt_no = str(disclosure.get("acpt_no") or "").strip()
        if not acpt_no:
            raise ValueError(f"disclosures[{index}].acpt_no must not be empty")
        if acpt_no in metadata:
            raise ValueError(f"duplicate acpt_no in disclosures: {acpt_no}")
        metadata[acpt_no] = {
            "acpt_no": acpt_no,
            "market": disclosure.get("market"),
            "company_name": disclosure.get("company_name"),
            "company_id": disclosure.get("company_id"),
            "disclosed_at": disclosure.get("disclosed_at"),
            "title": disclosure.get("title"),
        }
    return metadata


def _load_workspace_filtered_payload(body: dict[str, Any]) -> tuple[Any, str]:
    for key in ("json", "payload", "source_json_path"):
        if key in body:
            raise ValueError(f"{key} is not supported; use data_root and mode")
    workspace = resolve_disclosure_workspace(body.get("data_root") or "")
    mode = validate_workspace_mode(body.get("mode"))
    source_path = workspace.filtered / mode / "filtered.json"
    if not source_path.is_file():
        raise ValueError(f"filtered disclosure JSON does not exist: {source_path}")
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format") != "kind_disclosure_filter_v1":
        raise ValueError(f"filtered disclosure JSON has an invalid format: {source_path}")
    collect_acpt_numbers_from_json(payload)
    return payload, str(source_path)


def _year_from_disclosure(
    acpt_no: str, disclosure: dict[str, Any] | None = None
) -> str:
    disclosed_at = str((disclosure or {}).get("disclosed_at") or "").strip()
    if not disclosed_at:
        raise ValueError(f"disclosed_at is required for disclosure year: {acpt_no}")
    try:
        disclosed_date = date.fromisoformat(disclosed_at.split(" ", 1)[0])
    except ValueError as exc:
        raise ValueError(
            f"invalid disclosed_at for disclosure year: {acpt_no} {disclosed_at!r}"
        ) from exc
    return f"{disclosed_date.year:04d}"


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
    candidates = sorted(
        path.resolve()
        for path in resolved_root.glob(f"[0-9][0-9][0-9][0-9]/{filename}")
        if path.is_file() and len(path.parent.name) == 4 and path.parent.name.isdigit()
    )
    if len(candidates) > 1:
        raise ValueError(f"duplicate disclosure HTML files for acpt_no: {normalized_acpt_no}")
    return candidates[0] if candidates else None


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
    target_years: dict[str, str],
) -> Path:
    filename = VIEWER_HTML_FILENAME_TEMPLATE.format(acpt_no=acpt_no)
    year = str(target_years.get(acpt_no) or "").strip()
    if len(year) != 4 or not year.isdigit():
        raise ValueError(f"target year is required for disclosure HTML: {acpt_no}")
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
    acpt_numbers: list[str],
    source_json: Any,
    source_integrity: dict[str, dict[str, Any]] | None = None,
) -> Path:
    metadata = _collect_disclosure_metadata_from_json(source_json)
    missing_metadata = [acpt_no for acpt_no in acpt_numbers if acpt_no not in metadata]
    if missing_metadata:
        raise ValueError(
            "Missing disclosure metadata for acpt_no values: "
            + ", ".join(missing_metadata[:10])
        )
    if source_integrity is not None:
        missing_integrity = [
            acpt_no for acpt_no in acpt_numbers if acpt_no not in source_integrity
        ]
        if missing_integrity:
            raise ValueError(
                "Missing HTML integrity for acpt_no values: "
                + ", ".join(missing_integrity[:10])
            )
    disclosures = [
        {
            **metadata[acpt_no],
            **(source_integrity[acpt_no] if source_integrity is not None else {}),
        }
        for acpt_no in acpt_numbers
    ]
    manifest_path = output_directory / HTML_MANIFEST_FILENAME
    atomic_write_json(
        manifest_path,
        {
            "format": HTML_MANIFEST_FORMAT_V2,
            "disclosures": disclosures,
        },
    )
    return manifest_path


def _source_json_fingerprint(source_json: Any) -> str:
    encoded = json.dumps(
        source_json,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_html_manifest_integrity(
    output_directory: Path,
) -> tuple[str, str, dict[str, dict[str, Any]]]:
    manifest_path = output_directory / HTML_MANIFEST_FILENAME
    if not manifest_path.is_file():
        return "", "", {}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format") not in HTML_MANIFEST_FORMATS:
        raise ValueError(f"invalid HTML manifest format: {manifest_path}")
    manifest_format = str(payload["format"])
    disclosures = payload.get("disclosures")
    if not isinstance(disclosures, list):
        raise ValueError(f"HTML manifest disclosures must be a list: {manifest_path}")

    integrity_by_acpt_no: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for index, disclosure in enumerate(disclosures):
        if not isinstance(disclosure, dict):
            raise ValueError(f"HTML manifest disclosures[{index}] must be an object")
        acpt_no = str(disclosure.get("acpt_no") or "").strip()
        if not acpt_no:
            raise ValueError(
                f"HTML manifest disclosures[{index}].acpt_no must not be empty"
            )
        if acpt_no in seen:
            raise ValueError(f"duplicate acpt_no in HTML manifest: {acpt_no}")
        seen.add(acpt_no)
        sha256 = str(disclosure.get("source_sha256") or "").strip().lower()
        size = disclosure.get("source_size_bytes")
        if not sha256 and size in (None, ""):
            continue
        if (
            len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            raise ValueError(f"invalid HTML integrity metadata for acpt_no: {acpt_no}")
        integrity_by_acpt_no[acpt_no] = {
            "source_sha256": sha256,
            "source_size_bytes": size,
        }
    return (
        manifest_format,
        str(payload.get("source_fingerprint") or ""),
        integrity_by_acpt_no,
    )


def _inspect_html_integrity(
    output_directory: Path,
    acpt_numbers: list[str],
    *,
    source_json: Any,
    structurally_valid_acpt_numbers: list[str],
    actual_integrity_by_acpt_no: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    manifest_format, manifest_source_fingerprint, expected_integrity = (
        _load_html_manifest_integrity(output_directory)
    )
    if manifest_format == HTML_MANIFEST_FORMAT_V2:
        # Per-acpt_no hashes are keyed by receipt number, so they survive filter
        # re-runs that only change the target list. No whole-payload gate needed.
        source_matches = True
    else:
        source_matches = (
            bool(manifest_source_fingerprint)
            and manifest_source_fingerprint == _source_json_fingerprint(source_json)
        )
    structurally_valid = set(structurally_valid_acpt_numbers)
    reusable_acpt_numbers: list[str] = []
    reusable_integrity: dict[str, dict[str, Any]] = {}
    unverified_acpt_numbers: list[str] = []
    hash_mismatch_acpt_numbers: list[str] = []
    for acpt_no in acpt_numbers:
        if acpt_no not in structurally_valid:
            continue
        if not source_matches or acpt_no not in expected_integrity:
            unverified_acpt_numbers.append(acpt_no)
            continue
        actual_integrity = actual_integrity_by_acpt_no[acpt_no]
        if actual_integrity["source_size_bytes"] != expected_integrity[acpt_no][
            "source_size_bytes"
        ]:
            hash_mismatch_acpt_numbers.append(acpt_no)
            continue
        if actual_integrity == expected_integrity[acpt_no]:
            reusable_acpt_numbers.append(acpt_no)
            reusable_integrity[acpt_no] = actual_integrity
        else:
            hash_mismatch_acpt_numbers.append(acpt_no)

    return {
        "hash_manifest_source_matches": source_matches,
        "hash_verified_target_html_count": len(reusable_acpt_numbers),
        "hash_unverified_target_html_count": len(unverified_acpt_numbers),
        "hash_mismatch_target_html_count": len(hash_mismatch_acpt_numbers),
        "hash_verified_target_acpt_numbers": reusable_acpt_numbers,
        "hash_unverified_target_acpt_numbers": unverified_acpt_numbers,
        "hash_mismatch_target_acpt_numbers": hash_mismatch_acpt_numbers,
        "_verified_integrity_by_acpt_no": reusable_integrity,
    }


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
    target_years: dict[str, str],
    allow_unexpected: bool = False,
    collect_integrity: bool = False,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if not output_directory.exists():
        summary = {
            "existing_target_html_count": 0,
            "missing_target_html_count": len(acpt_numbers),
            "existing_target_acpt_numbers": [],
            "missing_target_acpt_numbers": acpt_numbers,
            "invalid_target_html_count": 0,
            "invalid_target_acpt_numbers": [],
            "auxiliary_file_count": 0,
            "total_file_count": 0,
        }
        if collect_integrity:
            summary["_target_integrity_by_acpt_no"] = {}
        return summary
    if not output_directory.is_dir():
        msg = f"output_directory is not a directory: {output_directory}"
        raise ValueError(msg)

    output_directory = output_directory.resolve()
    files = _iter_html_output_files(output_directory)
    existing_paths = set(files)
    worker_count = _html_output_check_workers(len(acpt_numbers))

    def target_status(
        acpt_no: str,
    ) -> tuple[str, Path, bool, bool, dict[str, Any] | None]:
        if cancel_check is not None and cancel_check():
            raise InterruptedError("HTML integrity scan cancelled")
        target_path = _target_html_path(
            output_directory,
            acpt_no,
            target_years=target_years,
        )
        exists = target_path in existing_paths
        if not exists:
            return acpt_no, target_path, False, False, None
        if collect_integrity:
            valid, integrity = _html_file_validation_and_integrity(target_path)
            if cancel_check is not None and cancel_check():
                raise InterruptedError("HTML integrity scan cancelled")
            return acpt_no, target_path, valid, True, integrity
        return acpt_no, target_path, _is_valid_html(target_path), True, None

    if worker_count == 1:
        target_statuses = [target_status(acpt_no) for acpt_no in acpt_numbers]
    else:
        indexed_statuses: list[
            tuple[str, Path, bool, bool, dict[str, Any] | None] | None
        ] = [
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
            for completed_count, (future, (index, _acpt_no)) in enumerate(
                completed,
                start=1,
            ):
                indexed_statuses[index] = future.result()
                if (
                    collect_integrity
                    and progress_callback is not None
                    and completed_count % 100 == 0
                ):
                    progress_callback(
                        "기준 해시 생성 대상 확인: "
                        f"{completed_count}/{len(acpt_numbers)}건 처리."
                    )
        target_statuses = [
            status for status in indexed_statuses if status is not None
        ]

    allowed_paths = {
        target_path for _, target_path, _, _, _integrity in target_statuses
    }
    allowed_paths.update(
        output_directory / filename for filename in HTML_DOWNLOAD_AUXILIARY_FILENAMES
    )
    for year in set(target_years.values()):
        allowed_paths.update(
            output_directory / year / filename
            for filename in HTML_DOWNLOAD_AUXILIARY_FILENAMES
        )
    existing_target_acpt_numbers = [
        acpt_no
        for acpt_no, _, valid, _, _integrity in target_statuses
        if valid
    ]
    missing_target_acpt_numbers = [
        acpt_no
        for acpt_no, _, valid, _, _integrity in target_statuses
        if not valid
    ]
    invalid_target_acpt_numbers = [
        acpt_no
        for acpt_no, _, valid, exists, _integrity in target_statuses
        if exists and not valid
    ]
    allowed_file_count = sum(1 for path in files if path in allowed_paths)
    present_target_count = sum(
        1 for _, _, _, exists, _integrity in target_statuses if exists
    )
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
    summary = {
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
    if collect_integrity:
        summary["_target_integrity_by_acpt_no"] = {
            acpt_no: integrity
            for acpt_no, _, valid, _, integrity in target_statuses
            if valid and integrity is not None
        }
    return summary


def _delete_unexpected_html_output_directory_files(
    output_directory: Path,
    acpt_numbers: list[str],
    *,
    target_years: dict[str, str],
    dry_run: bool = False,
    collect_integrity: bool = False,
) -> dict[str, Any]:
    if not output_directory.exists():
        summary = {
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
        if collect_integrity:
            summary["_target_integrity_by_acpt_no"] = {}
        return summary
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
    for year in set(target_years.values()):
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
        collect_integrity=collect_integrity,
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
            if path.is_file()
        )
    return files


__all__ = [name for name in globals() if not name.startswith("__")]
