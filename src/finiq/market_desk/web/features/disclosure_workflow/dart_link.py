"""Link KIND disclosure identifiers to OpenDART filing numbers without HTML fetches."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Protocol
from xml.etree import ElementTree

import requests

from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
    atomic_write_json,
)
from finiq.market_desk.web.features.market_data.service_records import (
    _iter_disclosure_records,
    _public_disclosure_record,
)
from finiq.market_desk.web.features.market_data.service_sources import (
    _iter_source_disclosure_records,
    _iter_sqlite_manifest_disclosure_records,
    _load_sqlite_manifest,
    _resolve_sqlite_manifest_path,
    _validate_sqlite_manifest_counts,
)

DART_LINK_FORMAT = "finiq_kind_dart_links_v1"
DART_LINK_BUILD_FORMAT = "finiq_kind_dart_link_build_v1"
DART_LINK_MANIFEST_FORMAT = "finiq_kind_dart_link_manifest_v1"
DART_CORP_CODE_CACHE_FORMAT = "finiq_dart_corp_codes_v1"
DART_LINK_MATCHER_VERSION = 1
DEFAULT_DART_API_BASE_URL = "https://opendart.fss.or.kr/api"
_DART_SUCCESS = "000"
_DART_NO_DATA = "013"
_DART_RETRYABLE_STATUS = {"020", "800", "900"}
_DART_CORRECTION_MARKER_RE = re.compile(
    r"^\s*\[(?:기재정정|첨부정정|첨부추가|변경등록|정정|정정명령|정정요구)\]\s*"
)
_COMPANY_MARKER_RE = re.compile(r"(?:주식회사|\(주\)|㈜)")


class DartClient(Protocol):
    def list_disclosures(
        self, *, corp_code: str, begin_date: str, end_date: str
    ) -> "DartListResult": ...


class DartApiError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(f"OpenDART request failed with status {code}")
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class DartListResult:
    records: list[dict[str, Any]]
    status: str
    message: str
    total_count: int
    total_pages: int
    request_count: int
    complete: bool


class OpenDartClient:
    """Minimal OpenDART metadata client. It never requests disclosure HTML."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_DART_API_BASE_URL,
        timeout: float = 20.0,
        max_attempts: int = 3,
        min_interval_seconds: float = 0.25,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        normalized_key = str(api_key or "").strip()
        if not normalized_key:
            raise ValueError("OpenDART API key is required")
        if len(normalized_key) != 40:
            raise ValueError("OpenDART API key must be 40 characters")
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        if max_attempts < 1 or max_attempts > 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be >= 0")
        self._api_key = normalized_key
        self._base_url = str(base_url).rstrip("/")
        self._timeout = float(timeout)
        self._max_attempts = int(max_attempts)
        self._min_interval_seconds = float(min_interval_seconds)
        self._session = session or requests.Session()
        self._session.max_redirects = 0
        self._sleep = sleep
        self._cancel_check = cancel_check
        self._last_request_started = 0.0

    def _pace(self) -> None:
        elapsed = time.monotonic() - self._last_request_started
        remaining = self._min_interval_seconds - elapsed
        if remaining > 0:
            self._sleep(remaining)
        self._last_request_started = time.monotonic()

    def _get(
        self,
        endpoint: str,
        params: dict[str, object],
        *,
        max_attempts: int | None = None,
    ) -> tuple[requests.Response, int]:
        attempt_limit = self._max_attempts if max_attempts is None else max_attempts
        if attempt_limit < 1:
            raise ValueError("max_attempts must be >= 1")
        for attempt in range(1, attempt_limit + 1):
            if self._cancel_check and self._cancel_check():
                raise RuntimeError("Job cancelled")
            self._pace()
            try:
                response = self._session.get(
                    f"{self._base_url}/{endpoint}",
                    params={"crtfc_key": self._api_key, **params},
                    timeout=self._timeout,
                    allow_redirects=False,
                )
                if response.is_redirect or response.is_permanent_redirect:
                    raise DartApiError("unexpected_redirect", retryable=False)
                if response.status_code in {408, 429, 500, 502, 503, 504}:
                    raise DartApiError(f"http_{response.status_code}", retryable=True)
                if response.status_code != 200:
                    raise DartApiError(f"http_{response.status_code}", retryable=False)
                return response, attempt
            except (requests.Timeout, requests.ConnectionError) as exc:
                error = DartApiError(type(exc).__name__, retryable=True)
            except DartApiError as exc:
                error = exc
            if not error.retryable or attempt == attempt_limit:
                raise error
            self._sleep(min(2 ** (attempt - 1), 4))
        raise AssertionError("unreachable")

    def _get_json(
        self, endpoint: str, params: dict[str, object]
    ) -> tuple[dict[str, Any], int]:
        request_count = 0
        while request_count < self._max_attempts:
            response, attempts = self._get(
                endpoint,
                params,
                max_attempts=self._max_attempts - request_count,
            )
            request_count += attempts
            try:
                payload = response.json()
            except ValueError as exc:
                raise DartApiError("invalid_json", retryable=False) from exc
            if not isinstance(payload, dict):
                raise DartApiError("invalid_json", retryable=False)
            status = str(payload.get("status") or "")
            if status not in _DART_RETRYABLE_STATUS:
                return payload, request_count
            if request_count >= self._max_attempts:
                raise DartApiError(status, retryable=True)
            self._sleep(min(2 ** (request_count - 1), 4))
        raise AssertionError("unreachable")

    def fetch_corp_codes(self) -> list[dict[str, str]]:
        request_count = 0
        while request_count < self._max_attempts:
            response, attempts = self._get(
                "corpCode.xml",
                {},
                max_attempts=self._max_attempts - request_count,
            )
            request_count += attempts
            try:
                return parse_dart_corp_code_payload(response.content)
            except DartApiError as exc:
                if not exc.retryable or request_count >= self._max_attempts:
                    raise
            self._sleep(min(2 ** (request_count - 1), 4))
        raise AssertionError("unreachable")

    def list_disclosures(
        self, *, corp_code: str, begin_date: str, end_date: str
    ) -> DartListResult:
        records: list[dict[str, Any]] = []
        page_no = 1
        total_pages = 1
        total_count = 0
        request_count = 0
        message = ""
        expected_total_count: int | None = None
        expected_total_pages: int | None = None
        while page_no <= total_pages:
            payload, page_request_count = self._get_json(
                "list.json",
                {
                    "corp_code": corp_code,
                    "bgn_de": begin_date,
                    "end_de": end_date,
                    "last_reprt_at": "N",
                    "sort": "date",
                    "sort_mth": "asc",
                    "page_no": page_no,
                    "page_count": 100,
                },
            )
            request_count += page_request_count
            status = str(payload.get("status") or "")
            message = str(payload.get("message") or "")
            if status == _DART_NO_DATA:
                return DartListResult([], status, message, 0, 0, request_count, True)
            if status != _DART_SUCCESS:
                raise DartApiError(
                    status or "missing_status", retryable=status in _DART_RETRYABLE_STATUS
                )
            page_records = payload.get("list") or []
            if not isinstance(page_records, list) or not all(
                isinstance(item, dict) for item in page_records
            ):
                raise DartApiError("invalid_list", retryable=False)
            try:
                response_page_no = int(payload.get("page_no") or page_no)
                total_pages = int(payload.get("total_page") or 1)
                total_count = int(payload.get("total_count") or 0)
            except (TypeError, ValueError) as exc:
                raise DartApiError("invalid_pagination", retryable=False) from exc
            if response_page_no != page_no or total_pages < 1 or total_count < 0:
                raise DartApiError("invalid_pagination", retryable=False)
            if expected_total_count is None:
                expected_total_count = total_count
                expected_total_pages = total_pages
            elif (
                total_count != expected_total_count
                or total_pages != expected_total_pages
            ):
                raise DartApiError("pagination_changed", retryable=True)
            records.extend(page_records)
            page_no += 1
        if len(records) != total_count:
            raise DartApiError("incomplete_pagination", retryable=True)
        rcept_numbers = [str(record.get("rcept_no") or "").strip() for record in records]
        if any(len(value) != 14 or not value.isdigit() for value in rcept_numbers):
            raise DartApiError("invalid_list_record", retryable=False)
        if len(set(rcept_numbers)) != len(rcept_numbers):
            raise DartApiError("duplicate_list_record", retryable=True)
        return DartListResult(
            records,
            _DART_SUCCESS,
            message,
            total_count,
            total_pages,
            request_count,
            True,
        )


def parse_dart_corp_code_payload(content: bytes) -> list[dict[str, str]]:
    if zipfile.is_zipfile(io.BytesIO(content)):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml_names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
            if len(xml_names) != 1:
                raise DartApiError("invalid_corp_code_archive", retryable=False)
            content = archive.read(xml_names[0])
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise DartApiError("invalid_corp_code_xml", retryable=False) from exc
    status_node = root.find("status")
    if status_node is not None and str(status_node.text or "") != _DART_SUCCESS:
        status = str(status_node.text or "missing_status")
        raise DartApiError(status, retryable=status in _DART_RETRYABLE_STATUS)
    records: list[dict[str, str]] = []
    for item in root.findall(".//list"):
        record = {
            "corp_code": str(item.findtext("corp_code") or "").strip(),
            "corp_name": str(item.findtext("corp_name") or "").strip(),
            "stock_code": str(item.findtext("stock_code") or "").strip(),
            "modify_date": str(item.findtext("modify_date") or "").strip(),
        }
        if len(record["corp_code"]) == 8 and record["corp_code"].isdigit():
            records.append(record)
    if not records:
        raise DartApiError("empty_corp_code_list", retryable=False)
    return records


def _normalized_company_name(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    normalized = _COMPANY_MARKER_RE.sub("", normalized)
    return "".join(char.casefold() for char in normalized if char.isalnum())


def _is_correction_title(value: object) -> bool:
    title = unicodedata.normalize("NFKC", str(value or ""))
    return bool(
        re.search(r"\[(?:기재정정|첨부정정|첨부추가|변경등록|정정|정정명령|정정요구)\]", title)
    )


def _normalized_title(value: object) -> str:
    title = unicodedata.normalize("NFKC", str(value or ""))
    while True:
        stripped = _DART_CORRECTION_MARKER_RE.sub("", title)
        if stripped == title:
            break
        title = stripped
    return "".join(char.casefold() for char in title if char.isalnum())


def _normalized_person(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return "".join(char.casefold() for char in normalized if char.isalnum())


def _kind_date(record: dict[str, Any]) -> date | None:
    raw = str(record.get("disclosed_at") or record.get("disclosed_date") or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _dart_date(record: dict[str, Any]) -> date | None:
    raw = str(record.get("rcept_dt") or "").strip()
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _kind_correction(record: dict[str, Any]) -> bool:
    if bool(record.get("is_correction_report")):
        return True
    flags = [str(value) for value in record.get("title_flags") or []]
    return any("정정" in flag or "첨부" in flag or "변경" in flag for flag in flags) or _is_correction_title(
        record.get("title")
    )


def _input_fingerprint(record: dict[str, Any]) -> str:
    semantic = {
        "matcher_version": DART_LINK_MATCHER_VERSION,
        "acpt_no": str(record.get("acpt_no") or ""),
        "doc_no": str(record.get("doc_no") or "").strip(),
        "company_id": str(record.get("company_id") or "").strip(),
        "company_name": str(record.get("company_name") or "").strip(),
        "disclosed_at": str(record.get("disclosed_at") or "").strip(),
        "title": str(record.get("title") or "").strip(),
        "title_flags": list(record.get("title_flags") or []),
        "is_correction_report": bool(record.get("is_correction_report")),
        "submitter": str(record.get("submitter") or "").strip(),
    }
    encoded = json.dumps(
        semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class _CorpCodeIndex:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._by_corp_code: dict[str, list[dict[str, Any]]] = {}
        self._by_stock_code: dict[str, list[dict[str, Any]]] = {}
        self._by_name: dict[str, list[dict[str, Any]]] = {}
        for source in records:
            record = {
                "corp_code": str(source.get("corp_code") or "").strip(),
                "corp_name": str(source.get("corp_name") or "").strip(),
                "stock_code": str(source.get("stock_code") or "").strip(),
                "modify_date": str(source.get("modify_date") or "").strip(),
            }
            if len(record["corp_code"]) != 8 or not record["corp_code"].isdigit():
                continue
            self._by_corp_code.setdefault(record["corp_code"], []).append(record)
            if len(record["stock_code"]) == 6 and record["stock_code"].isdigit():
                self._by_stock_code.setdefault(record["stock_code"], []).append(record)
            name = _normalized_company_name(record["corp_name"])
            if name:
                self._by_name.setdefault(name, []).append(record)

    def resolve(self, record: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        company_id = str(record.get("company_id") or "").strip()
        if len(company_id) == 8 and company_id.isdigit():
            candidates = self._by_corp_code.get(company_id, [])
            if len(candidates) == 1:
                return candidates[0], "corp_code"
        if len(company_id) == 6 and company_id.isdigit():
            candidates = self._by_stock_code.get(company_id, [])
            if len(candidates) == 1:
                return candidates[0], "stock_code"
            if len(candidates) > 1:
                name = _normalized_company_name(record.get("company_name"))
                narrowed = [
                    candidate
                    for candidate in candidates
                    if _normalized_company_name(candidate["corp_name"]) == name
                ]
                if len(narrowed) == 1:
                    return narrowed[0], "stock_code_and_name"
                return None, "company_ambiguous"
        name = _normalized_company_name(record.get("company_name"))
        candidates = self._by_name.get(name, []) if name else []
        if len(candidates) == 1:
            return candidates[0], "company_name"
        if len(candidates) > 1:
            return None, "company_ambiguous"
        return None, "company_not_resolved"


def _candidate_score(
    kind_record: dict[str, Any], dart_record: dict[str, Any], *, tolerance_days: int
) -> dict[str, Any] | None:
    rcept_no = str(dart_record.get("rcept_no") or "").strip()
    if len(rcept_no) != 14 or not rcept_no.isdigit():
        return None
    kind_date = _kind_date(kind_record)
    dart_date = _dart_date(dart_record)
    if kind_date is None or dart_date is None:
        return None
    date_delta = abs((dart_date - kind_date).days)
    if date_delta > tolerance_days:
        return None
    kind_title = _normalized_title(kind_record.get("title"))
    dart_title = _normalized_title(dart_record.get("report_nm"))
    if not kind_title or not dart_title:
        return None
    similarity = SequenceMatcher(None, kind_title, dart_title, autojunk=False).ratio()
    correction_matches = _kind_correction(kind_record) == _is_correction_title(
        dart_record.get("report_nm")
    )
    score = 30
    score += 25 if date_delta == 0 else 20
    if similarity == 1.0:
        score += 45
    elif similarity >= 0.94:
        score += 40
    elif similarity >= 0.85:
        score += 30
    elif similarity >= 0.70:
        score += 15
    if correction_matches:
        score += 5
    else:
        score -= 20
    submitter_matches = bool(
        _normalized_person(kind_record.get("submitter"))
        and _normalized_person(kind_record.get("submitter"))
        == _normalized_person(dart_record.get("flr_nm"))
    )
    if submitter_matches:
        score += 5
    return {
        "rcept_no": rcept_no,
        "report_nm": str(dart_record.get("report_nm") or "").strip(),
        "rcept_dt": str(dart_record.get("rcept_dt") or "").strip(),
        "flr_nm": str(dart_record.get("flr_nm") or "").strip(),
        "score": score,
        "title_similarity": round(similarity, 6),
        "date_delta_days": date_delta,
        "correction_matches": correction_matches,
        "submitter_matches": submitter_matches,
        "eligible": similarity >= 0.85 and correction_matches and score >= 90,
    }


def _base_link(
    record: dict[str, Any], *, checked_at: str, company: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "matcher_version": DART_LINK_MATCHER_VERSION,
        "acpt_no": str(record.get("acpt_no") or ""),
        "doc_no": str(record.get("doc_no") or "").strip() or None,
        "rcept_no": None,
        "status": "unresolved",
        "reason_code": "",
        "retryable": False,
        "input_fingerprint": _input_fingerprint(record),
        "checked_at": checked_at,
        "kind": {
            "company_id": str(record.get("company_id") or "").strip() or None,
            "company_name": str(record.get("company_name") or "").strip() or None,
            "disclosed_at": str(record.get("disclosed_at") or "").strip() or None,
            "title": str(record.get("title") or "").strip() or None,
            "submitter": str(record.get("submitter") or "").strip() or None,
        },
        "dart_company": company,
        "query": None,
        "candidate_count": 0,
        "candidates": [],
        "match": None,
    }


def _dart_query_is_complete(query: DartListResult) -> bool:
    if not query.complete or query.total_count != len(query.records):
        return False
    if query.total_count < 0 or query.total_pages < 0 or query.request_count < 1:
        return False
    return query.total_count == 0 or query.total_pages >= 1


def link_kind_disclosures(
    records: list[dict[str, Any]],
    *,
    corp_code_records: list[dict[str, Any]],
    client: DartClient | None,
    now: datetime | None = None,
    date_tolerance_days: int = 1,
    progress_callback: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    if date_tolerance_days < 0 or date_tolerance_days > 7:
        raise ValueError("date_tolerance_days must be between 0 and 7")
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    corp_index = _CorpCodeIndex(corp_code_records)
    links_by_acpt_no: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any], str]]] = {}
    seen_acpt_numbers: set[str] = set()

    for record in records:
        acpt_no = str(record.get("acpt_no") or "")
        if not acpt_no:
            raise ValueError("Every KIND record must have acpt_no")
        if acpt_no in seen_acpt_numbers:
            raise ValueError(f"Duplicate KIND acpt_no: {acpt_no}")
        seen_acpt_numbers.add(acpt_no)
        company, company_method = corp_index.resolve(record)
        link = _base_link(record, checked_at=checked_at, company=company)
        if company is None:
            link["reason_code"] = company_method
            links_by_acpt_no[acpt_no] = link
            continue
        disclosed_date = _kind_date(record)
        if disclosed_date is None:
            link["reason_code"] = "invalid_disclosed_date"
            links_by_acpt_no[acpt_no] = link
            continue
        link["match"] = {"company_method": company_method}
        grouped.setdefault(company["corp_code"], []).append(
            (record, link, company_method)
        )
        links_by_acpt_no[acpt_no] = link

    if grouped and client is None:
        raise ValueError("OpenDART client is required for resolved KIND records")

    for group_index, (corp_code, group_records) in enumerate(
        sorted(grouped.items()), start=1
    ):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        group_dates = [
            disclosed_date
            for record, _link, _method in group_records
            if (disclosed_date := _kind_date(record)) is not None
        ]
        begin = min(group_dates) - timedelta(days=date_tolerance_days)
        end = max(group_dates) + timedelta(days=date_tolerance_days)
        begin_date = begin.strftime("%Y%m%d")
        end_date = end.strftime("%Y%m%d")
        if progress_callback:
            progress_callback(
                f"DART 공시목록 조회 {group_index}/{len(grouped)}: "
                f"corp_code={corp_code}, period={begin_date}-{end_date}"
            )
        try:
            query = client.list_disclosures(
                corp_code=corp_code, begin_date=begin_date, end_date=end_date
            )
        except Exception as exc:
            if isinstance(exc, RuntimeError) and str(exc) == "Job cancelled":
                raise
            retryable = getattr(exc, "retryable", True)
            error_code = getattr(exc, "code", type(exc).__name__)
            for _record, link, _method in group_records:
                link.update(
                    {
                        "status": "lookup_failed",
                        "reason_code": "dart_query_failed",
                        "retryable": bool(retryable),
                        "query": {
                            "corp_code": corp_code,
                            "begin_date": begin_date,
                            "end_date": end_date,
                            "complete": False,
                            "error_code": str(error_code),
                        },
                    }
                )
            continue

        query_complete = _dart_query_is_complete(query)
        query_evidence = {
            "corp_code": corp_code,
            "begin_date": begin_date,
            "end_date": end_date,
            "status": query.status,
            "complete": query_complete,
            "total_count": query.total_count,
            "total_pages": query.total_pages,
            "request_count": query.request_count,
        }
        if not query_complete:
            for _record, link, _method in group_records:
                link.update(
                    {
                        "status": "lookup_failed",
                        "reason_code": "incomplete_dart_query",
                        "retryable": True,
                        "query": query_evidence,
                    }
                )
            continue
        for record, link, company_method in group_records:
            disclosed_date = _kind_date(record)
            invalid_candidate_dates = any(
                _dart_date(dart_record) is None for dart_record in query.records
            )
            window_records = [
                dart_record
                for dart_record in query.records
                if disclosed_date is not None
                and (candidate_date := _dart_date(dart_record)) is not None
                and abs((candidate_date - disclosed_date).days) <= date_tolerance_days
            ]
            scored = [
                candidate
                for candidate in (
                    _candidate_score(
                        record,
                        dart_record,
                        tolerance_days=date_tolerance_days,
                    )
                    for dart_record in window_records
                )
                if candidate is not None and candidate["rcept_no"]
            ]
            scored.sort(key=lambda item: (-int(item["score"]), str(item["rcept_no"])))
            link["query"] = query_evidence
            link["candidate_count"] = len(scored)
            link["candidates"] = scored[:5]
            if invalid_candidate_dates or len(scored) != len(window_records):
                link.update(
                    {
                        "status": "unresolved",
                        "reason_code": "invalid_dart_candidate_metadata",
                        "retryable": True,
                    }
                )
                continue
            if not window_records:
                link.update(
                    {
                        "status": "confirmed_absent",
                        "reason_code": "no_dart_candidate_in_date_window",
                        "retryable": False,
                    }
                )
                continue
            if not scored:
                link.update(
                    {
                        "status": "unresolved",
                        "reason_code": "invalid_dart_candidate_metadata",
                        "retryable": True,
                    }
                )
                continue
            confident = [candidate for candidate in scored if candidate["eligible"]]
            if not confident:
                link.update(
                    {
                        "status": "unresolved",
                        "reason_code": "no_confident_match",
                        "retryable": True,
                    }
                )
                continue
            top = confident[0]
            second = confident[1] if len(confident) > 1 else None
            if second is not None and int(top["score"]) - int(second["score"]) < 10:
                link.update(
                    {
                        "status": "ambiguous",
                        "reason_code": "multiple_confident_matches",
                        "retryable": True,
                    }
                )
                continue
            link.update(
                {
                    "status": "matched",
                    "reason_code": "unique_confident_match",
                    "rcept_no": top["rcept_no"],
                    "retryable": False,
                    "match": {
                        "company_method": company_method,
                        "score": top["score"],
                        "title_similarity": top["title_similarity"],
                        "date_delta_days": top["date_delta_days"],
                        "correction_matches": top["correction_matches"],
                        "submitter_matches": top["submitter_matches"],
                    },
                }
            )
    return [links_by_acpt_no[str(record.get("acpt_no") or "")] for record in records]


def _load_source_json(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read KIND source JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("KIND source JSON must contain an object")
    disclosures = payload.get("disclosures")
    if disclosures is not None:
        return _validated_dict_records(disclosures, label="disclosures")
    if isinstance(payload.get("companies"), list):
        return [_public_disclosure_record(record) for record in _iter_disclosure_records(payload)]
    raise ValueError("KIND source JSON has no disclosures or companies")


def _load_kind_records(body: dict[str, Any]) -> list[dict[str, Any]]:
    records = body.get("records")
    if records is not None:
        return _validated_dict_records(records, label="records")
    source_json_path = str(body.get("source_json_path") or "").strip()
    if source_json_path:
        return _load_source_json(Path(source_json_path).expanduser().resolve())
    classification_path = str(body.get("classification_path") or "").strip()
    root_directory = str(body.get("root_directory") or "").strip()
    sqlite_manifest_path = None
    if classification_path:
        sqlite_manifest_path = _resolve_sqlite_manifest_path(classification_path)
    if sqlite_manifest_path is None and root_directory:
        sqlite_manifest_path = _resolve_sqlite_manifest_path(root_directory)
    if sqlite_manifest_path is not None:
        manifest = _load_sqlite_manifest(sqlite_manifest_path)
        _validate_sqlite_manifest_counts(sqlite_manifest_path, manifest)
        return [
            _public_disclosure_record(record)
            for record in _iter_sqlite_manifest_disclosure_records(
                sqlite_manifest_path, manifest
            )
        ]
    if classification_path:
        return _load_source_json(Path(classification_path).expanduser().resolve())
    if root_directory:
        records, _body_count = _iter_source_disclosure_records(root_directory)
        return [_public_disclosure_record(record) for record in records]
    raise ValueError(
        "records, source_json_path, classification_path or root_directory is required"
    )


def _validated_dict_records(value: object, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    records: list[dict[str, Any]] = []
    for index, record in enumerate(value):
        if not isinstance(record, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        records.append(dict(record))
    return records


def _json_artifact_format(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return str(payload.get("format") or "") or None


def _assert_owned_json_artifact(path: Path, *, expected_format: str) -> None:
    if path.exists() and _json_artifact_format(path) != expected_format:
        raise ValueError(f"Existing path is not a FINIQ DART link artifact: {path}")


def _validate_output_ownership(output_directory: Path) -> None:
    _assert_owned_json_artifact(
        output_directory / "manifest.json",
        expected_format=DART_LINK_MANIFEST_FORMAT,
    )
    _assert_owned_json_artifact(
        output_directory / "undated.json",
        expected_format=DART_LINK_FORMAT,
    )
    years_directory = output_directory / "years"
    if years_directory.is_dir():
        for path in years_directory.glob("[0-9][0-9][0-9][0-9].json"):
            _assert_owned_json_artifact(path, expected_format=DART_LINK_FORMAT)
    _assert_owned_json_artifact(
        output_directory / "cache" / "corp-codes.json",
        expected_format=DART_CORP_CODE_CACHE_FORMAT,
    )


def _load_existing_links(output_directory: Path) -> dict[str, dict[str, Any]]:
    links: dict[str, dict[str, Any]] = {}
    years_directory = output_directory / "years"
    if not years_directory.is_dir():
        return links
    for path in sorted(years_directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("format") != DART_LINK_FORMAT:
            continue
        partition_links = payload.get("links")
        if not isinstance(partition_links, list):
            raise ValueError(f"Invalid DART link partition: {path}")
        for index, link in enumerate(partition_links):
            if not isinstance(link, dict):
                raise ValueError(f"Invalid DART link at {path}:{index}")
            acpt_no = str(link.get("acpt_no") or "")
            if not acpt_no:
                raise ValueError(f"DART link has no acpt_no at {path}:{index}")
            if acpt_no in links:
                raise ValueError(f"Duplicate cached DART link acpt_no: {acpt_no}")
            links[acpt_no] = link
    return links


def _negative_link_is_fresh(
    link: dict[str, Any], *, now: datetime, negative_cache_days: int
) -> bool:
    if link.get("status") != "confirmed_absent":
        return False
    try:
        checked_at = datetime.fromisoformat(str(link.get("checked_at") or ""))
    except ValueError:
        return False
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    age = now.astimezone(timezone.utc) - checked_at.astimezone(timezone.utc)
    return timedelta(0) <= age < timedelta(days=negative_cache_days)


def _link_is_reusable(
    link: dict[str, Any],
    record: dict[str, Any],
    *,
    now: datetime,
    negative_cache_days: int,
) -> bool:
    if link.get("input_fingerprint") != _input_fingerprint(record):
        return False
    query = link.get("query")
    if not isinstance(query, dict) or query.get("complete") is not True:
        return False
    if link.get("status") == "matched":
        rcept_no = str(link.get("rcept_no") or "").strip()
        return len(rcept_no) == 14 and rcept_no.isdigit()
    return _negative_link_is_fresh(
        link,
        now=now,
        negative_cache_days=negative_cache_days,
    )


def _link_year(link: dict[str, Any]) -> str | None:
    disclosed_at = str((link.get("kind") or {}).get("disclosed_at") or "")
    return (
        disclosed_at[:4]
        if len(disclosed_at) >= 4 and disclosed_at[:4].isdigit()
        else None
    )


def _status_summary(links: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(links),
        "matched": 0,
        "confirmed_absent": 0,
        "unresolved": 0,
        "ambiguous": 0,
        "lookup_failed": 0,
    }
    for link in links:
        status = str(link.get("status") or "")
        if status in summary:
            summary[status] += 1
    return summary


def _option_value(payload: dict[str, Any], key: str, default: object) -> object:
    value = payload.get(key)
    return default if value is None or value == "" else value


def _validate_unique_kind_records(records: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for record in records:
        acpt_no = str(record.get("acpt_no") or "")
        if not acpt_no:
            raise ValueError("Every KIND record must have acpt_no")
        if acpt_no in seen:
            raise ValueError(f"Duplicate KIND acpt_no: {acpt_no}")
        seen.add(acpt_no)


def _records_require_dart_query(
    records: list[dict[str, Any]], corp_code_records: list[dict[str, Any]]
) -> bool:
    corp_index = _CorpCodeIndex(corp_code_records)
    return any(
        corp_index.resolve(record)[0] is not None and _kind_date(record) is not None
        for record in records
    )


def _load_corp_codes_from_cache(
    path: Path, *, now: datetime, max_age_days: int
) -> list[dict[str, Any]] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("format") != DART_CORP_CODE_CACHE_FORMAT:
        return None
    try:
        fetched_at = datetime.fromisoformat(str(payload.get("fetched_at") or ""))
    except ValueError:
        return None
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    age = now.astimezone(timezone.utc) - fetched_at.astimezone(timezone.utc)
    if age < timedelta(0) or age >= timedelta(days=max_age_days):
        return None
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        return None
    cached_records: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            return None
        corp_code = str(record.get("corp_code") or "").strip()
        corp_name = str(record.get("corp_name") or "").strip()
        if len(corp_code) != 8 or not corp_code.isdigit() or not corp_name:
            return None
        cached_records.append(dict(record))
    return cached_records


def build_dart_links_payload(
    body: dict[str, Any],
    *,
    client: OpenDartClient | DartClient | None = None,
    now: datetime | None = None,
    progress_callback: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    payload = apply_workspace_defaults("dart_link", body)
    output_raw = str(payload.get("output_directory") or "").strip()
    if not output_raw:
        raise ValueError("output_directory or data_root is required")
    output_directory = Path(output_raw).expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    _validate_output_ownership(output_directory)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    negative_cache_days = int(_option_value(payload, "negative_cache_days", 7))
    if negative_cache_days < 0 or negative_cache_days > 365:
        raise ValueError("negative_cache_days must be between 0 and 365")
    corp_code_cache_days = int(_option_value(payload, "corp_code_cache_days", 7))
    if corp_code_cache_days < 1 or corp_code_cache_days > 365:
        raise ValueError("corp_code_cache_days must be between 1 and 365")
    records = _load_kind_records(payload)
    _validate_unique_kind_records(records)
    existing = _load_existing_links(output_directory)
    reusable: dict[str, dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []
    for record in records:
        acpt_no = str(record.get("acpt_no") or "")
        prior = existing.get(acpt_no)
        if prior and _link_is_reusable(
            prior,
            record,
            now=current_time,
            negative_cache_days=negative_cache_days,
        ):
            reusable[acpt_no] = prior
        else:
            pending.append(record)

    resolved_client = client
    corp_code_records = payload.get("corp_code_records")
    if corp_code_records is not None and not isinstance(corp_code_records, list):
        raise ValueError("corp_code_records must be a list")
    corp_cache_path = output_directory / "cache" / "corp-codes.json"
    if pending and not isinstance(corp_code_records, list):
        if corp_cache_path.is_file() and not bool(payload.get("refresh_corp_codes")):
            corp_code_records = _load_corp_codes_from_cache(
                corp_cache_path,
                now=current_time,
                max_age_days=corp_code_cache_days,
            )
        if not isinstance(corp_code_records, list):
            if resolved_client is None:
                api_key = str(
                    payload.get("dart_api_key") or os.environ.get("OPENDART_API_KEY") or ""
                ).strip()
                resolved_client = OpenDartClient(
                    api_key,
                    timeout=float(_option_value(payload, "timeout", 20.0)),
                    max_attempts=int(_option_value(payload, "max_attempts", 3)),
                    min_interval_seconds=float(
                        _option_value(payload, "min_interval_seconds", 0.25)
                    ),
                    cancel_check=cancel_check,
                )
            if not hasattr(resolved_client, "fetch_corp_codes"):
                raise ValueError("corp_code_records are required for this DART client")
            corp_code_records = resolved_client.fetch_corp_codes()  # type: ignore[attr-defined]
            atomic_write_json(
                corp_cache_path,
                {
                    "format": DART_CORP_CODE_CACHE_FORMAT,
                    "fetched_at": current_time.astimezone(timezone.utc).isoformat(),
                    "records": corp_code_records,
                },
            )
    normalized_corp_codes = [
        dict(record) for record in (corp_code_records or []) if isinstance(record, dict)
    ]
    if (
        pending
        and resolved_client is None
        and _records_require_dart_query(pending, normalized_corp_codes)
    ):
        api_key = str(
            payload.get("dart_api_key") or os.environ.get("OPENDART_API_KEY") or ""
        ).strip()
        resolved_client = OpenDartClient(
            api_key,
            timeout=float(_option_value(payload, "timeout", 20.0)),
            max_attempts=int(_option_value(payload, "max_attempts", 3)),
            min_interval_seconds=float(
                _option_value(payload, "min_interval_seconds", 0.25)
            ),
            cancel_check=cancel_check,
        )
    new_links = (
        link_kind_disclosures(
            pending,
            corp_code_records=normalized_corp_codes,
            client=resolved_client,
            now=current_time,
            date_tolerance_days=int(
                _option_value(payload, "date_tolerance_days", 1)
            ),
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        if pending
        else []
    )
    resolved_by_acpt_no = {
        str(link.get("acpt_no") or ""): link for link in new_links
    }
    links = [
        reusable.get(str(record.get("acpt_no") or ""))
        or resolved_by_acpt_no[str(record.get("acpt_no") or "")]
        for record in records
    ]

    partitions: dict[str | None, list[dict[str, Any]]] = {}
    for link in links:
        partitions.setdefault(_link_year(link), []).append(link)
    years_directory = output_directory / "years"
    years_directory.mkdir(parents=True, exist_ok=True)
    desired_paths: set[Path] = set()
    partition_entries: list[dict[str, Any]] = []
    undated_path = output_directory / "undated.json"
    for year, year_links in sorted(
        partitions.items(), key=lambda item: (item[0] is None, item[0] or "")
    ):
        year_path = undated_path if year is None else years_directory / f"{year}.json"
        desired_paths.add(year_path)
        year_payload = {
            "format": DART_LINK_FORMAT,
            "schema_version": 1,
            "year": year,
            "generated_at": current_time.astimezone(timezone.utc).isoformat(),
            "contains_dart_html": False,
            "summary": _status_summary(year_links),
            "links": year_links,
        }
        atomic_write_json(year_path, year_payload)
        partition_entries.append(
            {"year": year, "path": str(year_path), "links": len(year_links)}
        )
    for stale_path in years_directory.glob("*.json"):
        if (
            stale_path not in desired_paths
            and _json_artifact_format(stale_path) == DART_LINK_FORMAT
        ):
            stale_path.unlink()
    if undated_path not in desired_paths:
        undated_path.unlink(missing_ok=True)

    summary = _status_summary(links)
    summary["reused"] = len(reusable)
    summary["queried"] = len(new_links)
    manifest_path = output_directory / "manifest.json"
    manifest = {
        "format": DART_LINK_MANIFEST_FORMAT,
        "schema_version": 1,
        "matcher_version": DART_LINK_MATCHER_VERSION,
        "generated_at": current_time.astimezone(timezone.utc).isoformat(),
        "output_directory": str(output_directory),
        "contains_dart_html": False,
        "summary": summary,
        "partitions": partition_entries,
    }
    atomic_write_json(manifest_path, manifest)
    return {
        "format": DART_LINK_BUILD_FORMAT,
        "output_directory": str(output_directory),
        "manifest_path": str(manifest_path),
        "contains_dart_html": False,
        "summary": summary,
        "partitions": partition_entries,
    }


__all__ = [
    "DartApiError",
    "DartListResult",
    "OpenDartClient",
    "build_dart_links_payload",
    "link_kind_disclosures",
    "parse_dart_corp_code_payload",
]
