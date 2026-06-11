"""KIND HTTP client: fetch search page and save raw result bodies."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode

import requests

from .payload import (
    DisclosureTypeGroupKey,
    DisclosureTypeGroupValue,
    KindSearchFormData,
    build_search_form,
)

KIND_SEARCH_PAGE_URL = "https://kind.krx.co.kr/disclosure/details.do?method=searchDetailsMain"
KIND_SEARCH_RESULTS_URL = "https://kind.krx.co.kr/disclosure/details.do"
KIND_DISCLOSURE_VIEWER_URL = "https://kind.krx.co.kr/common/disclsviewer.do"
SEARCH_RESULTS_FILENAME_TEMPLATE = "{page_number:03d}_post_page_{page_number:05d}.body"
VIEWER_HTML_FILENAME_TEMPLATE = "{acpt_no}.html"
VIEWER_HTML_WITH_DOC_FILENAME_TEMPLATE = "{acpt_no}_{doc_no}.html"

KindProgressCallback = Callable[[str], None]
KindCancelCheck = Callable[[], bool]
KindSavedFileCallback = Callable[[Path, int | None, KindSearchFormData | None], None]
KindSavedFileValidator = Callable[[Path, int | None, KindSearchFormData | None], None]
KindViewerSavedFileCallback = Callable[[Path, str, str | None], None]


def _save_response_content(output_path: Path, response: requests.Response) -> None:
    """response body를 지정한 경로에 저장한다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)


def _is_valid_html(path: Path) -> bool:
    """Check if the saved file is a valid HTML (basic check)."""
    if not path.exists():
        return False
    if path.stat().st_size < 100:  # Too small to be a valid KIND viewer HTML
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        # Basic check for HTML or KIND specific content
        return "<html" in content.lower() or "openDisclsViewer" in content
    except Exception:
        return False


class _RateLimiter:
    def __init__(self, max_requests_per_minute: int):
        self.lock = threading.Lock()
        self.max_requests_per_minute = max_requests_per_minute
        self.request_timestamps: list[float] = []

    def wait(self, cancel_check: KindCancelCheck | None = None) -> bool:
        while True:
            if cancel_check is not None and cancel_check():
                return True

            now = time.monotonic()
            with self.lock:
                # Remove timestamps older than 60 seconds
                self.request_timestamps = [t for t in self.request_timestamps if now - t < 60]

                if len(self.request_timestamps) < self.max_requests_per_minute:
                    self.request_timestamps.append(now)
                    return False

            time.sleep(0.1)


def _report_progress(progress_callback: KindProgressCallback | None, message: str) -> None:
    """진행 상황 callback이 있으면 메시지를 전달한다."""
    if progress_callback is not None:
        progress_callback(message)


def _sleep_between_requests(wait_seconds: float, cancel_check: KindCancelCheck | None = None) -> bool:
    """요청 사이에 필요한 만큼 대기한다."""
    remaining_seconds = wait_seconds
    while remaining_seconds > 0:
        if cancel_check is not None and cancel_check():
            return True
        sleep_seconds = min(remaining_seconds, 0.2)
        time.sleep(sleep_seconds)
        remaining_seconds -= sleep_seconds
    return bool(cancel_check is not None and cancel_check())


def _report_saved_file(
    saved_file_callback: KindSavedFileCallback | None,
    output_path: Path,
    *,
    page_number: int | None,
    request_data: KindSearchFormData | None,
) -> None:
    """저장 완료 callback이 있으면 file 정보와 request data를 전달한다."""
    if saved_file_callback is not None:
        saved_file_callback(output_path, page_number, request_data)


def _validate_saved_file(
    saved_file_validator: KindSavedFileValidator | None,
    output_path: Path,
    *,
    page_number: int | None,
    request_data: KindSearchFormData | None,
) -> None:
    """저장 직후 validator가 있으면 file 내용을 검증한다."""
    if saved_file_validator is not None:
        saved_file_validator(output_path, page_number, request_data)


def _validate_save_request(
    *,
    page_size: int,
    start_page: int,
    end_page: int,
    timeout: float,
) -> None:
    """기본 parameter를 검증한다."""
    if page_size < 1:
        raise ValueError("page_size must be >= 1")
    if start_page < 1:
        raise ValueError("start_page must be >= 1")
    if end_page < start_page:
        raise ValueError("end_page must be >= start_page")
    if timeout <= 0:
        raise ValueError("timeout must be > 0")


def _build_results_filename(page_number: int) -> str:
    """결과 페이지 번호에 대응하는 file name을 만든다."""
    return SEARCH_RESULTS_FILENAME_TEMPLATE.format(page_number=page_number)


def _validate_kind_identifier(value: str, *, field_name: str) -> str:
    normalized_value = str(value).strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be empty")
    if not normalized_value.isdigit():
        raise ValueError(f"{field_name} must contain only digits")
    return normalized_value


def _build_viewer_html_filename(acpt_no: str, doc_no: str | None = None) -> str:
    if doc_no:
        return VIEWER_HTML_WITH_DOC_FILENAME_TEMPLATE.format(acpt_no=acpt_no, doc_no=doc_no)
    return VIEWER_HTML_FILENAME_TEMPLATE.format(acpt_no=acpt_no)


def _build_disclosure_viewer_url(acpt_no: str, doc_no: str | None = None) -> str:
    query = urlencode(
        {
            "method": "search",
            "acptno": acpt_no,
            "docno": doc_no or "",
            "viewerhost": "",
            "viewerport": "",
        }
    )
    return f"{KIND_DISCLOSURE_VIEWER_URL}?{query}"


def _normalize_request_headers(request_headers: Mapping[str, object]) -> dict[str, str]:
    """request headers를 string dict로 normalize한다."""
    return {str(key): str(value) for key, value in request_headers.items()}


def _request_search_page(
    session: requests.Session,
    *,
    request_headers: Mapping[str, str],
    timeout: float,
) -> requests.Response:
    """검색 메인 페이지를 GET으로 받아온다."""
    response = session.get(KIND_SEARCH_PAGE_URL, headers=request_headers, timeout=timeout)
    response.raise_for_status()
    return response


def _request_disclosure_viewer_page(
    session: requests.Session,
    *,
    request_headers: Mapping[str, str],
    acpt_no: str,
    doc_no: str | None,
    timeout: float,
) -> requests.Response:
    """KIND 공시 뷰어 HTML을 GET으로 받아온다."""
    response = session.get(
        _build_disclosure_viewer_url(acpt_no, doc_no),
        headers=request_headers,
        timeout=timeout,
    )
    response.raise_for_status()
    return response


def _request_search_results_page(
    session: requests.Session,
    *,
    request_headers: Mapping[str, str],
    page_number: int,
    page_size: int,
    start_date: str,
    end_date: str,
    timeout: float,
    search_filters: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
    disclosure_type_groups: Mapping[DisclosureTypeGroupKey, DisclosureTypeGroupValue] | None = None,
    last_report_only: bool | None = None,
    include_previous_disclosures: bool | None = None,
) -> tuple[requests.Response, KindSearchFormData]:
    """검색 조건을 반영한 결과 페이지를 POST로 받아온다.

    page별 query payload를 만든 뒤 KIND 결과 목록 response를 가져온다.
    """
    request_data = build_search_form(
        page_number=page_number,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        search_filters=search_filters,
        disclosure_type_groups=disclosure_type_groups,
        last_report_only=last_report_only,
        include_previous_disclosures=include_previous_disclosures,
    )
    response = session.post(
        KIND_SEARCH_RESULTS_URL,
        headers=request_headers,
        data=request_data,
        timeout=timeout,
    )
    response.raise_for_status()
    return response, request_data


def _fetch_and_save_search_page(
    *,
    session: requests.Session,
    output_directory: Path,
    request_headers: Mapping[str, str],
    timeout: float,
    progress_callback: KindProgressCallback | None,
    saved_file_validator: KindSavedFileValidator | None,
    saved_file_callback: KindSavedFileCallback | None,
) -> None:
    """검색 메인 페이지를 받아서 기본 response file로 저장한다."""
    _report_progress(progress_callback, "Fetching KIND search page...")
    response = _request_search_page(
        session,
        request_headers=request_headers,
        timeout=timeout,
    )
    output_path = output_directory / "000_mainGET.body"
    _save_response_content(output_path, response)
    _validate_saved_file(
        saved_file_validator,
        output_path,
        page_number=None,
        request_data=None,
    )
    _report_saved_file(saved_file_callback, output_path, page_number=None, request_data=None)
    _report_progress(progress_callback, f"Saved KIND search page to: {output_path}")


def _fetch_and_save_results_page(
    *,
    session: requests.Session,
    output_directory: Path,
    request_headers: Mapping[str, str],
    page_number: int,
    page_offset: int,
    total_pages: int,
    start_date: str,
    end_date: str,
    page_size: int,
    timeout: float,
    search_filters: Mapping[str, object] | Sequence[tuple[str, object]] | None,
    disclosure_type_groups: Mapping[DisclosureTypeGroupKey, DisclosureTypeGroupValue] | None,
    last_report_only: bool | None,
    include_previous_disclosures: bool | None,
    progress_callback: KindProgressCallback | None,
    saved_file_validator: KindSavedFileValidator | None,
    saved_file_callback: KindSavedFileCallback | None,
) -> None:
    """결과 페이지 1개를 request하고 지정된 file name으로 저장한다.

    진행 message 출력과 query payload 생성, response 저장까지
    page 단위 작업을 한곳에서 묶어 처리한다.
    """
    _report_progress(
        progress_callback,
        f"Fetching results page {page_number} ({page_offset}/{total_pages})...",
    )
    response, request_data = _request_search_results_page(
        session,
        request_headers=request_headers,
        page_number=page_number,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        timeout=timeout,
        search_filters=search_filters,
        disclosure_type_groups=disclosure_type_groups,
        last_report_only=last_report_only,
        include_previous_disclosures=include_previous_disclosures,
    )
    output_path = output_directory / _build_results_filename(page_number)
    _save_response_content(output_path, response)
    _validate_saved_file(
        saved_file_validator,
        output_path,
        page_number=page_number,
        request_data=request_data,
    )
    _report_saved_file(
        saved_file_callback,
        output_path,
        page_number=page_number,
        request_data=request_data,
    )
    _report_progress(
        progress_callback,
        f"Saved results page {page_number} ({page_offset}/{total_pages}) to: {output_path}",
    )


def download_pages(
    *,
    output_directory: Path,
    request_headers: Mapping[str, object],
    start_date: str = "",
    end_date: str = "",
    start_page: int = 1,
    end_page: int = 1,
    search_filters: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
    disclosure_type_groups: Mapping[DisclosureTypeGroupKey, DisclosureTypeGroupValue] | None = None,
    last_report_only: bool | None = None,
    include_previous_disclosures: bool | None = None,
    page_size: int = 100,
    wait_seconds_between_requests: float = 1.0,
    timeout: float = 20.0,
    session: requests.Session | None = None,
    progress_callback: KindProgressCallback | None = None,
    saved_file_validator: KindSavedFileValidator | None = None,
    saved_file_callback: KindSavedFileCallback | None = None,
    cancel_check: KindCancelCheck | None = None,
) -> None:
    """KIND 검색 결과를 순서대로 내려받아 file로 저장한다.

    먼저 검색 메인 페이지를 확보하고,
    이후 각 결과 페이지를 request 간 간격을 두며 저장한다.
    """
    _validate_save_request(
        page_size=page_size,
        start_page=start_page,
        end_page=end_page,
        timeout=timeout,
    )

    output_directory = output_directory.resolve()
    normalized_request_headers = _normalize_request_headers(request_headers)
    owns_session = session is None
    active_session = session or requests.Session()

    try:
        if cancel_check is not None and cancel_check():
            _report_progress(progress_callback, "Download cancelled before search page request.")
            return
        _fetch_and_save_search_page(
            session=active_session,
            output_directory=output_directory,
            request_headers=normalized_request_headers,
            timeout=timeout,
            progress_callback=progress_callback,
            saved_file_validator=saved_file_validator,
            saved_file_callback=saved_file_callback,
        )

        total_pages = end_page - start_page + 1
        for page_offset, page_number in enumerate(range(start_page, end_page + 1), start=1):
            if _sleep_between_requests(wait_seconds_between_requests, cancel_check):
                _report_progress(progress_callback, "Download cancelled between result page requests.")
                return
            if cancel_check is not None and cancel_check():
                _report_progress(progress_callback, "Download cancelled before result page request.")
                return
            _fetch_and_save_results_page(
                session=active_session,
                output_directory=output_directory,
                request_headers=normalized_request_headers,
                page_number=page_number,
                page_offset=page_offset,
                total_pages=total_pages,
                start_date=start_date,
                end_date=end_date,
                page_size=page_size,
                timeout=timeout,
                search_filters=search_filters,
                disclosure_type_groups=disclosure_type_groups,
                last_report_only=last_report_only,
                include_previous_disclosures=include_previous_disclosures,
                progress_callback=progress_callback,
                saved_file_validator=saved_file_validator,
                saved_file_callback=saved_file_callback,
            )
    finally:
        if owns_session:
            active_session.close()


def fetch_search_page(
    *,
    output_directory: Path,
    request_headers: Mapping[str, object],
    timeout: float = 20.0,
    session: requests.Session | None = None,
    progress_callback: KindProgressCallback | None = None,
    saved_file_validator: KindSavedFileValidator | None = None,
    saved_file_callback: KindSavedFileCallback | None = None,
) -> Path:
    """KIND 검색 메인 페이지(GET)만 다시 받아 저장한다."""
    if timeout <= 0:
        raise ValueError("timeout must be > 0")

    output_directory = output_directory.resolve()
    normalized_request_headers = _normalize_request_headers(request_headers)
    owns_session = session is None
    active_session = session or requests.Session()

    try:
        _fetch_and_save_search_page(
            session=active_session,
            output_directory=output_directory,
            request_headers=normalized_request_headers,
            timeout=timeout,
            progress_callback=progress_callback,
            saved_file_validator=saved_file_validator,
            saved_file_callback=saved_file_callback,
        )
    finally:
        if owns_session:
            active_session.close()

    return output_directory / "000_mainGET.body"


def fetch_disclosure_viewer_html(
    *,
    output_directory: Path,
    request_headers: Mapping[str, object],
    acpt_no: str,
    doc_no: str | None = None,
    timeout: float = 20.0,
    session: requests.Session | None = None,
    skip_existing: bool = True,
    progress_callback: KindProgressCallback | None = None,
) -> Path:
    """KIND 접수번호로 공시 뷰어 HTML 전체를 저장한다.

    ``acpt_no``는 KIND 검색 결과의 ``openDisclsViewer`` 첫 번째 인자이고,
    ``doc_no``를 지정하면 같은 KIND 뷰어 내 특정 본문 문서를 선택한 HTML을 저장한다.
    """
    if timeout <= 0:
        raise ValueError("timeout must be > 0")
    normalized_acpt_no = _validate_kind_identifier(acpt_no, field_name="acpt_no")
    normalized_doc_no = (
        _validate_kind_identifier(doc_no, field_name="doc_no") if doc_no is not None else None
    )

    output_directory = output_directory.resolve()
    output_path = output_directory / _build_viewer_html_filename(
        normalized_acpt_no,
        normalized_doc_no,
    )
    if skip_existing and output_path.exists():
        _report_progress(progress_callback, f"Skipping existing KIND viewer HTML: {output_path}")
        return output_path

    normalized_request_headers = _normalize_request_headers(request_headers)
    owns_session = session is None
    active_session = session or requests.Session()

    try:
        _report_progress(
            progress_callback,
            f"Fetching KIND viewer HTML acpt_no={normalized_acpt_no} doc_no={normalized_doc_no or '-'}...",
        )
        response = _request_disclosure_viewer_page(
            active_session,
            request_headers=normalized_request_headers,
            acpt_no=normalized_acpt_no,
            doc_no=normalized_doc_no,
            timeout=timeout,
        )
        _save_response_content(output_path, response)
        _report_progress(progress_callback, f"Saved KIND viewer HTML to: {output_path}")
    finally:
        if owns_session:
            active_session.close()

    return output_path


def download_disclosure_viewer_htmls(
    *,
    output_directory: Path,
    request_headers: Mapping[str, object],
    acpt_numbers: Sequence[str],
    timeout: float = 20.0,
    wait_seconds_between_requests: float = 0.0,
    max_requests_per_minute: int = 90,
    session: requests.Session | None = None,
    skip_existing: bool = True,
    progress_callback: KindProgressCallback | None = None,
    saved_file_callback: KindViewerSavedFileCallback | None = None,
    cancel_check: KindCancelCheck | None = None,
    max_workers: int = 5,
    max_retries: int = 2,
) -> list[Path]:
    """여러 KIND 접수번호의 뷰어 HTML을 병렬로 처리하며 무결성을 보장한다."""
    if timeout <= 0:
        raise ValueError("timeout must be > 0")
    if wait_seconds_between_requests < 0:
        raise ValueError("wait_seconds_between_requests must be >= 0")
    if max_requests_per_minute < 1 or max_requests_per_minute > 100:
        raise ValueError("max_requests_per_minute must be between 1 and 100")

    normalized_acpt_numbers = [
        _validate_kind_identifier(acpt_no, field_name="acpt_no")
        for acpt_no in acpt_numbers
    ]
    output_directory = output_directory.resolve()
    normalized_request_headers = _normalize_request_headers(request_headers)
    owns_session = session is None
    active_session = session or requests.Session()
    
    # Increase connection pool size for parallel requests
    if not owns_session and hasattr(active_session, "mount"):
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=max_workers,
            pool_maxsize=max_workers
        )
        active_session.mount("https://", adapter)
        active_session.mount("http://", adapter)

    rate_limiter = _RateLimiter(max_requests_per_minute)
    saved_paths: dict[str, Path] = {}
    valid_acpt_numbers: set[str] = set()
    errors: dict[str, str] = {}
    
    total_count = len(normalized_acpt_numbers)
    lock = threading.Lock()
    request_spacing_lock = threading.Lock()
    next_request_time = time.monotonic()

    def wait_for_request_spacing() -> bool:
        nonlocal next_request_time
        if wait_seconds_between_requests <= 0:
            return bool(cancel_check is not None and cancel_check())
        with request_spacing_lock:
            now = time.monotonic()
            sleep_seconds = max(0.0, next_request_time - now)
            next_request_time = max(now, next_request_time) + wait_seconds_between_requests
        return _sleep_between_requests(sleep_seconds, cancel_check)

    def download_task(acpt_no: str, current_retry: int = 0) -> Path | None:
        if cancel_check is not None and cancel_check():
            return None

        output_path = output_directory / _build_viewer_html_filename(acpt_no)
        
        if skip_existing and output_path.exists():
            _report_progress(progress_callback, f"Skipping existing KIND viewer HTML: {output_path}")
            with lock:
                saved_paths[acpt_no] = output_path
                valid_acpt_numbers.add(acpt_no)
            return output_path

        # Wait for rate limit
        if rate_limiter.wait(cancel_check):
            return None
        if wait_for_request_spacing():
            return None

        try:
            _report_progress(
                progress_callback,
                f"Fetching KIND viewer HTML acpt_no={acpt_no} (retry={current_retry})...",
            )
            response = _request_disclosure_viewer_page(
                active_session,
                request_headers=normalized_request_headers,
                acpt_no=acpt_no,
                doc_no=None,
                timeout=timeout,
            )
            _save_response_content(output_path, response)
            
            if not _is_valid_html(output_path):
                raise ValueError(f"Downloaded content for {acpt_no} is invalid")

            with lock:
                saved_paths[acpt_no] = output_path
                valid_acpt_numbers.add(acpt_no)
            
            if saved_file_callback is not None:
                saved_file_callback(output_path, acpt_no, None)
            
            return output_path
        except Exception as e:
            _report_progress(progress_callback, f"Failed to download {acpt_no}: {str(e)}")
            return None

    try:
        # First Pass: Parallel Download
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(download_task, acpt_no): acpt_no 
                for acpt_no in normalized_acpt_numbers
            }
            for future in as_completed(futures):
                if cancel_check is not None and cancel_check():
                    break
        
        # Integrity Check & Retries
        for retry in range(1, max_retries + 1):
            missing_or_invalid = [
                acpt_no for acpt_no in normalized_acpt_numbers 
                if acpt_no not in valid_acpt_numbers
            ]
            
            if not missing_or_invalid:
                break
                
            _report_progress(
                progress_callback, 
                f"Integrity check failed for {len(missing_or_invalid)} files. Retrying (attempt {retry}/{max_retries})..."
            )
            
            with ThreadPoolExecutor(max_workers=min(max_workers, len(missing_or_invalid))) as executor:
                futures = {
                    executor.submit(download_task, acpt_no, retry): acpt_no 
                    for acpt_no in missing_or_invalid
                }
                for future in as_completed(futures):
                    if cancel_check is not None and cancel_check():
                        break

        # Final check
        final_missing = [
            acpt_no for acpt_no in normalized_acpt_numbers 
            if acpt_no not in valid_acpt_numbers
        ]
        
        if final_missing:
            error_msg = f"Permanently failed to download {len(final_missing)} files: {', '.join(final_missing)}"
            _report_progress(progress_callback, error_msg)

    finally:
        if owns_session:
            active_session.close()

    # Return paths in original order
    return [saved_paths[acpt_no] for acpt_no in normalized_acpt_numbers if acpt_no in saved_paths]


__all__ = [
    "KIND_DISCLOSURE_VIEWER_URL",
    "KIND_SEARCH_PAGE_URL",
    "KIND_SEARCH_RESULTS_URL",
    "SEARCH_RESULTS_FILENAME_TEMPLATE",
    "VIEWER_HTML_FILENAME_TEMPLATE",
    "VIEWER_HTML_WITH_DOC_FILENAME_TEMPLATE",
    "download_disclosure_viewer_htmls",
    "fetch_disclosure_viewer_html",
    "fetch_search_page",
    "KindCancelCheck",
    "KindProgressCallback",
    "KindSavedFileCallback",
    "KindSavedFileValidator",
    "KindViewerSavedFileCallback",
    "download_pages",
]
