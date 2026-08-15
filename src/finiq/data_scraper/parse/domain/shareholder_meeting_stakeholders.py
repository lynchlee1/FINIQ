"""Explicit stakeholder and transaction mentions in shareholder-meeting sources."""

from __future__ import annotations

import re
from typing import Any

from bs4 import Tag


_SECTION_TITLE = "기타 투자판단에 참고할 사항"
_SECTION_LABEL = "기타투자판단에참고할사항"
_CORRECTION_HEADERS = {"정정항목", "정정전", "정정후"}

_AUDITOR_BODY = r"[A-Za-z0-9가-힣&·ㆍ.㈜]{1,30}회계법인"
_AUDITOR_NAME_RE = re.compile(
    rf"(?<![A-Za-z0-9가-힣&·ㆍ.㈜])(?P<name>{_AUDITOR_BODY})"
)
_AUDITOR_CHANGE_RE = re.compile(
    rf"(?<![A-Za-z0-9가-힣&·ㆍ.㈜])(?P<former>{_AUDITOR_BODY})"
    rf"(?:\([^)]{{1,30}}\))?\s*에서\s*"
    rf"(?P<current>{_AUDITOR_BODY})(?:\([^)]{{1,30}}\))?\s*(?:으로|로)\s*"
    rf"(?:변경|교체)"
)
_AUDITOR_CONTEXT_RE = re.compile(
    r"(?:외부|회계)\s*감사인|감사인\s*(?:으로|로)"
)
_AUDITOR_TRANSITION_RE = re.compile(r"변경|교체|→|기존.+(?:종료|만료)")
_AUDITOR_REAPPOINTMENT_RE = re.compile(r"재선임|재선정")
_AUDITOR_DESIGNATION_RE = re.compile(r"지정\s*(?:받|되)")
_AUDITOR_APPOINTMENT_RE = re.compile(r"선임")

_ACTION_PRIORITY = {
    None: 0,
    "appointed": 1,
    "replaced": 1,
    "designated": 2,
    "reappointed": 3,
}

_TRANSACTION_NAME = r"[A-Za-z0-9가-힣㈜()&·ㆍ.,'’\- ]{2,100}?"
_SHARE_CONTRACT = r"주식\s*(?:양수도|매매)\s*계약"
_SHARE_OBJECT = (
    r"(?:보유(?:하고\s*있는)?\s*)?주식[^;\n]{0,180}?(?:을|를)\s+"
)
_DIRECTED_TRANSFER_END = (
    rf"\s*(?:에게|에)\s+(?:양도|매도)[^;\n]{{0,100}}?{_SHARE_CONTRACT}"
)
_MAX_SHAREHOLDER_DIRECTED_TRANSFER_RE = re.compile(
    rf"최대주주(?:인)?\s+(?P<seller>{_TRANSACTION_NAME})"
    rf"\s*(?:은|는|이|가)\s+{_SHARE_OBJECT}"
    rf"(?P<buyer>{_TRANSACTION_NAME}){_DIRECTED_TRANSFER_END}"
)
_SUBJECT_DIRECTED_TRANSFER_RE = re.compile(
    rf"^\s*(?:[-*※]\s*)?(?P<seller>{_TRANSACTION_NAME})"
    rf"\s*(?:은|는|이|가)\s+{_SHARE_OBJECT}"
    rf"(?P<buyer>{_TRANSACTION_NAME}){_DIRECTED_TRANSFER_END}"
)
_MAX_SHAREHOLDER_COUNTERPARTY_TRANSFER_RE = re.compile(
    rf"최대주주(?:인)?\s+(?P<seller>{_TRANSACTION_NAME})"
    rf"\s*(?:은|는|이|가)\s+(?P<buyer>{_TRANSACTION_NAME})"
    rf"\s*(?:와|과)\s+[^;\n]{{0,220}}?{_SHARE_CONTRACT}"
)
_EXECUTED_CONTRACT_RE = re.compile(
    r"체결(?:하였|했|한|된|되었|함|하였다|되어|됐)"
)
_TRANSFER_ROLE_RE = re.compile(
    r"(?P<role>양도인|매도인|양수인|매수인)\s*[:：]\s*"
    rf"(?P<name>{_TRANSACTION_NAME})"
    r"(?=\s*(?:[,;/]\s*)?(?:양도인|매도인|양수인|매수인)\s*[:：]|"
    rf"\s*(?:[,;]\s*)?{_SHARE_CONTRACT}|$)"
)
_ALLOTTEE_STATEMENT_RE = re.compile(
    r"(?m)^(?P<statement>[ \t]*(?:[-*][ \t]*)?"
    r"(?:\d+[ \t]*[.)][ \t]*)?배정[ \t]*대상자(?:"
    r"[ \t]*[:：-][ \t]*(?P<inline>[^\n]+)|"
    r"[ \t]*\n[ \t]*(?:[-*][ \t]*)?"
    r"(?P<continuation>(?!\d+[ \t]*[.)])[^\n]+)))$"
)
_ABSORPTION_MERGER_RE = re.compile(
    rf"당사(?:가|는)\s+(?:(?:상장|비상장)\s*법인인\s+)?"
    rf"(?P<name>{_TRANSACTION_NAME})"
    r"\s*(?:를|을)\s+흡수\s*합병"
)
_BUSINESS_REASON_NAME_TOKEN = r"[A-Za-z0-9가-힣&·ㆍ.'’\-]+"
_BUSINESS_REASON_MARKED_NAME = (
    rf"(?:(?:\(주\)|㈜)\s*{_BUSINESS_REASON_NAME_TOKEN}"
    rf"(?:\s+{_BUSINESS_REASON_NAME_TOKEN}){{0,4}}?|"
    rf"주식회사\s*{_BUSINESS_REASON_NAME_TOKEN}"
    rf"(?:\s+{_BUSINESS_REASON_NAME_TOKEN}){{0,4}}?|"
    rf"{_BUSINESS_REASON_NAME_TOKEN}\s*\(주\))"
)
_AGENDA_MARKED_NAME = (
    rf"(?:(?:\(주\)|㈜)\s*{_BUSINESS_REASON_NAME_TOKEN}"
    rf"(?:\s+{_BUSINESS_REASON_NAME_TOKEN}){{0,4}}?|"
    rf"주식회사\s+{_BUSINESS_REASON_NAME_TOKEN}"
    rf"(?:\s+{_BUSINESS_REASON_NAME_TOKEN}){{0,4}}?|"
    rf"{_BUSINESS_REASON_NAME_TOKEN}\s*\(주\))"
)
_AGENDA_MARKED_COUNTERPARTY_RE = re.compile(
    rf"(?P<name>{_AGENDA_MARKED_NAME})(?:와의|과의)\s*"
    r"[^;|\n]{0,80}?(?:흡수\s*)?합병(?:\s*계약)?"
)
_AGENDA_LABELLED_MERGER_RE = re.compile(
    rf"(?:피합병|소멸)\s*(?:법인|회사)\s*[:：]\s*"
    rf"(?P<name>{_AGENDA_MARKED_NAME}?)(?=\s*(?:\)|▶|=>|--?>|→|$))"
)
_AGENDA_MARKED_ABSORPTION_RE = re.compile(
    rf"(?P<name>{_AGENDA_MARKED_NAME})\s+흡수\s*합병(?:\s*계약)?"
)
_AGENDA_TWO_PARTY_MERGER_WITH_PARTICLE_RE = re.compile(
    rf"(?P<left>{_AGENDA_MARKED_NAME})\s*(?:와|과|및|,)\s*"
    rf"(?P<right>{_AGENDA_MARKED_NAME}?)(?:와의|과의|의)\s+"
    r"(?:흡수\s*)?합병(?:\s*계약)?"
)
_AGENDA_TWO_PARTY_MERGER_RE = re.compile(
    rf"(?P<left>{_AGENDA_MARKED_NAME})\s*(?:와|과|및|,)\s*"
    rf"(?P<right>{_AGENDA_MARKED_NAME})\s+"
    r"(?:흡수\s*)?합병(?:\s*계약)?"
)
_BUSINESS_REASON_SINGLE_NAME = rf"(?:{_BUSINESS_REASON_MARKED_NAME}|{_BUSINESS_REASON_NAME_TOKEN})"
_BUSINESS_REASON_TARGET_FIRST_RE = re.compile(
    rf"^\s*(?:[-*]\s*)?(?:당사(?:는|가)\s+)?"
    rf"(?P<name>{_BUSINESS_REASON_SINGLE_NAME})(?:와의|과의)?\s+"
    rf"(?:(?:소규모|간이)\s+)?(?P<action>흡수\s*합병|합병)"
)
_BUSINESS_REASON_SUBSIDIARY_RE = re.compile(
    rf"^\s*(?:[-*]\s*)?종속회사\s*\(\s*"
    rf"(?P<name>{_BUSINESS_REASON_SINGLE_NAME})\s*\)\s*"
    r"(?P<action>흡수\s*합병)"
)
_BUSINESS_REASON_ACTION_FIRST_RE = re.compile(
    rf"^\s*(?:[-*]\s*)?흡수\s*합병(?:한|하는)\s+"
    rf"(?P<name>{_BUSINESS_REASON_MARKED_NAME})(?:의)?(?=\s|$)"
)
_BUSINESS_REASON_MARKED_PARTICLE_MERGER_RE = re.compile(
    rf"^\s*(?:[-*]\s*)?(?:당사(?:는|가)\s+)?"
    rf"(?P<name>{_BUSINESS_REASON_MARKED_NAME})(?:와의|과의|와|과)\s+"
    rf"(?P<action>(?:소규모|간이)\s*합병)"
)
_BUSINESS_REASON_SCHEDULED_MARKED_TARGET_RE = re.compile(
    rf"^\s*(?:[-*]\s*)?(?:19|20)\d{{2}}[./-]\d{{1,2}}[./-]\d{{1,2}}\s+"
    rf"합병\s+예정인\s+(?P<name>{_BUSINESS_REASON_MARKED_NAME})"
    rf"(?:와의|과의|와|과)?\s+(?P<action>합병)"
)
_BUSINESS_REASON_UNMARKED_PARTICLE_MERGER_RE = re.compile(
    rf"^\s*(?:[-*]\s*)?(?P<name>{_BUSINESS_REASON_NAME_TOKEN}?)"
    rf"(?:와의|과의)\s+(?P<action>(?:(?:소규모|간이)\s*)?합병)"
)
_BUSINESS_REASON_ABSORBED_ROSTER_RE = re.compile(
    r"피합병(?:회사|법인)\s*\(\s*(?P<names>(?:(?:\(주\)|[^)])+?))\s*\)\s*의?\s*"
    r"(?:(?:목적\s*사업|사업\s*목적)(?:사항)?).{0,30}?(?:추가|변경|반영)"
)
_BUSINESS_REASON_ABSORBED_DIRECT_RE = re.compile(
    rf"피합병(?:회사|법인)\s+(?P<name>{_BUSINESS_REASON_MARKED_NAME})\s+"
    r"정관상의\s+사업\s*목적\s+반영"
)
_BUSINESS_REASON_CURRENT_COUNTERPARTY_RE = re.compile(
    rf"(?:현\s+)?당사는\s+(?P<name>{_BUSINESS_REASON_NAME_TOKEN})과\s+"
    rf"(?:소규모|간이)\s*합병.{{0,100}}?(?P=name)의\s+사업\s*목적"
)
_BUSINESS_REASON_TWO_PARTY_RE = re.compile(
    rf"(?P<left>{_BUSINESS_REASON_MARKED_NAME})\s*와\s*"
    rf"(?P<right>{_BUSINESS_REASON_MARKED_NAME})의\s+합병.{{0,160}}?"
    rf"(?P<recipient>{_BUSINESS_REASON_MARKED_NAME})\s+사업\s*목적"
)
_BUSINESS_REASON_COMPLETED_FORMER_RE = re.compile(
    rf"합병\s*완료된\s+\(구\)\s*(?P<name>{_BUSINESS_REASON_SINGLE_NAME})"
    r"(?=의\s+사업\s*목적)"
)
_BUSINESS_REASON_DISSOLVED_RE = re.compile(
    rf"(?:합병\s*후\s+)?소멸법인(?:인)?\s*(?P<name>{_BUSINESS_REASON_SINGLE_NAME})"
    r"(?=의\s+(?:(?:정관|업무).{0,60}?반영|업무.{0,60}?정관\s*변경))"
)
_BUSINESS_REASON_POSITIVE_RE = re.compile(
    r"(?:사업\s*목적|사업목적|목적\s*(?:추가|정비|승계)|사업\s*확장|"
    r"사업\s*확장을|영위\s*사업)"
)
_BUSINESS_REASON_NEGATIVE_RE = re.compile(
    r"(?:합병|승계|(?:(?:사업\s*목적|사업목적|목적\s*사업|정관)"
    r".{0,30}?(?:반영|추가|변경))).{0,30}?"
    r"(?:하지\s*(?:않|아니)|아닌|취소|철회|중단|무산|백지화|폐기)"
)
_BUSINESS_REASON_GENERIC_NAME_RE = re.compile(
    r"^(?:(?:완전|연결)?(?:자회사|종속회사|계열회사|관계회사|타법인)"
    r"[A-Za-z0-9가-힣]*|(?:관계|계열|종속|소멸|존속|피합병|대상|신설|"
    r"타|상대|일반|해당)?기업|"
    r"(?:사업|영업|투자|생산|판매|개발)?(?:부문|부)|"
    r"(?:관계|계열)사|(?:소규모|간이)|[가-힣]*(?:회사|법인))$"
)
_BUSINESS_REASON_DATE_NAME_RE = re.compile(
    r"^(?:(?:19|20)\d{2}[./-]\d{1,2}[./-]\d{1,2}|"
    r"(?:19|20)\d{2}년\d{1,2}월\d{1,2}일|(?:19|20)\d{6})$"
)
_AGENDA_STAKE_RE = re.compile(
    r"^\s*(?:[-*①-⑳]\s*)?"
    r"(?:(?:제\s*)?\d+(?:\s*[-－.]\s*\d+)*\s*호?"
    r"\s*(?:의\s*안|의안)?\s*[:：]?\s*)?"
    r"(?:(?:제3자\s*배정(?:\s*방식)?\s*)?유상증자를\s*통한\s+)?"
    r"(?:(?:당사(?:의)?\s+)?(?:자회사|종속회사)\s+)?"
    rf"(?P<name>{_TRANSACTION_NAME})\s+지분"
    r"[^;\n]{0,40}?(?P<action>인수|양도)"
)
_KOREAN_PERSON_RE = re.compile(r"[가-힣]{2,5}")
_CORPORATE_MARKER_RE = re.compile(
    r"(?:\(주\)|㈜|주식회사|유한회사|유한공사|회계법인|법무법인|"
    r"투자조합|조합|은행|증권|파트너스|홀딩스|코퍼레이션|"
    r"Corporation|Corp\.?|Limited|Ltd\.?|Inc\.?|Company|Co\.?)",
    re.IGNORECASE,
)
_GENERIC_TRANSACTION_NAMES = {
    "-",
    "당사",
    "회사",
    "관계회사",
    "계열회사",
    "자회사",
    "완전자회사",
    "종속회사",
    "타법인",
    "최대주주",
    "매수인",
    "매도인",
    "양수인",
    "양도인",
    "배정대상자",
    "대상자",
    "제3자",
    "미정",
    "미확정",
    "없음",
    "해당사항없음",
    "추후결정",
    "추후확정",
    "합병계약",
    "m&a",
}
_GENERIC_ENTITY_ROLE_RE = re.compile(
    r"^(?:당사(?:의)?\s*)?(?:(?:완전|연결)?자회사(?:인)?\s*)?"
    r"(?:회사|관계회사|계열회사|자회사|완전자회사|종속회사|타법인|"
    r"(?:상장|비상장)법인|사업부문|상대방|"
    r"매수인|매도인|양수인|양도인)(?:인)?$"
)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _normalized_label(value: Any) -> str:
    label = _clean_text(value)
    label = re.sub(r"^\s*\d+\s*[.)]\s*", "", label)
    return _compact(label)


def _direct_cells(row: Tag) -> list[Tag]:
    return list(row.find_all(["th", "td"], recursive=False))


def _is_correction_table(table: Tag) -> bool:
    for row in table.find_all("tr"):
        labels = {
            _compact(cell.get_text(" ", strip=True)) for cell in _direct_cells(row)
        }
        if _CORRECTION_HEADERS <= labels:
            return True
    return False


def _inside_correction_context(tag: Tag) -> bool:
    return any(_is_correction_table(table) for table in tag.find_parents("table"))


def _table_index(soup: Any, table: Tag) -> int:
    tables = [soup] if isinstance(soup, Tag) and soup.name == "table" else []
    tables.extend(soup.find_all("table"))
    for index, candidate in enumerate(tables):
        if candidate is table:
            return index
    return -1


def _row_index(table: Tag, row: Tag) -> int:
    for index, candidate in enumerate(table.find_all("tr")):
        if candidate is row:
            return index
    return -1


def _reference_note_cells(soup: Any) -> list[tuple[Tag, dict[str, Any]]]:
    """Return the first canonical value cell with stable source coordinates."""
    for label_row in soup.find_all("tr"):
        label_cells = _direct_cells(label_row)
        if not label_cells:
            continue
        if _normalized_label(label_cells[0].get_text(" ", strip=True)) != _SECTION_LABEL:
            continue
        if _inside_correction_context(label_row):
            continue
        if len(label_cells) != 1:
            return []

        value_row = label_row.find_next_sibling("tr")
        if not isinstance(value_row, Tag):
            return []
        value_cells = _direct_cells(value_row)
        if len(value_cells) != 1:
            return []
        table = label_row.find_parent("table")
        if not isinstance(table, Tag) or value_row.find_parent("table") is not table:
            return []
        return [
            (
                value_cells[0],
                {
                    "section_title": _SECTION_TITLE,
                    "table_index": _table_index(soup, table),
                    "row_index": _row_index(table, value_row),
                    "field": _SECTION_TITLE,
                },
            )
        ]
    return []


def _clauses(cell: Tag) -> list[str]:
    return [
        clause
        for line in cell.get_text("\n", strip=True).splitlines()
        if (clause := _clean_text(line))
    ]


def _mention(
    *,
    name: str,
    relationship_type: str,
    target_ref: str,
    attributes: dict[str, Any],
    evidence_base: dict[str, Any],
    raw_text: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "entity_type": "organization",
        "relationship_type": relationship_type,
        "target_ref": target_ref,
        "attributes": attributes,
        "evidence": {**evidence_base, "raw_text": raw_text},
    }


def _transaction_name(value: Any) -> str | None:
    name = _clean_text(value).strip("-–—,;:： ")
    name = re.sub(
        r"^(?:당사(?:의)?\s+)?최대주주(?:인)?\s+",
        "",
        name,
    )
    key = re.sub(r"\s+", "", name).casefold()
    if (
        not name
        or len(name) > 100
        or re.fullmatch(r"[A-Za-z0-9가-힣㈜()&·ㆍ.,'’\- ]+", name) is None
        or key in _GENERIC_TRANSACTION_NAMES
        or _GENERIC_ENTITY_ROLE_RE.fullmatch(name) is not None
        or re.search(r"\s+외\s*\d+\s*(?:인|명)(?:\s|$)", name) is not None
    ):
        return None
    return name


def _explicit_label_name(value: Any) -> str | None:
    name = _transaction_name(value)
    if name is None:
        return None
    if (
        _CORPORATE_MARKER_RE.search(name) is not None
        or _KOREAN_PERSON_RE.fullmatch(name) is not None
        or " " not in name
    ):
        return name
    if re.fullmatch(
        r"[A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,5}",
        name,
    ) is not None:
        return name
    return None


def _expanded_named_parties(value: Any) -> list[str]:
    expression = _clean_text(value).strip("-–—,;:： ")
    explicit_others: list[str] = []
    group = re.fullmatch(
        r"(?P<primary>.+?)\s+외\s*\d+\s*(?:인|명)\s*\((?P<others>.*)\)",
        expression,
    )
    if group is not None:
        expression = group.group("primary")
        explicit_others = re.split(
            r"\s*(?:,|;|/|\s및\s)\s*",
            group.group("others"),
        )
    else:
        expression = re.sub(
            r"\s+외\s*\d+\s*(?:인|명)\s*$",
            "",
            expression,
        )

    names: list[str] = []
    for candidate in (expression, *explicit_others):
        name = _transaction_name(candidate)
        if name is not None and name not in names:
            names.append(name)
    return names


def _transaction_entity_type(name: str, *, organization_context: bool = False) -> str:
    if organization_context or _CORPORATE_MARKER_RE.search(name) is not None:
        return "organization"
    if _KOREAN_PERSON_RE.fullmatch(name) is not None:
        return "person"
    return "organization"


def _transaction_mention(
    *,
    name: str,
    relationship_type: str,
    target_ref: str,
    attributes: dict[str, Any],
    evidence: dict[str, Any],
    organization_context: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "entity_type": _transaction_entity_type(
            name,
            organization_context=organization_context,
        ),
        "relationship_type": relationship_type,
        "target_ref": target_ref,
        "attributes": attributes,
        "evidence": evidence,
    }


def _transaction_evidence(
    evidence_base: Any,
    *,
    raw_text: str,
    field: str | None = None,
    section_title: str | None = None,
) -> dict[str, Any]:
    evidence = dict(evidence_base) if isinstance(evidence_base, dict) else {}
    if section_title is not None:
        evidence.setdefault("section_title", section_title)
    if field is not None:
        evidence["field"] = field
    evidence["raw_text"] = _clean_text(raw_text)
    return evidence


def _share_transfer_parties(raw_text: str) -> tuple[list[str], list[str]]:
    if (
        re.search(_SHARE_CONTRACT, raw_text) is None
        or _EXECUTED_CONTRACT_RE.search(raw_text) is None
    ):
        return [], []

    candidates: list[tuple[list[str], list[str]]] = []
    for pattern in (
        _MAX_SHAREHOLDER_DIRECTED_TRANSFER_RE,
        _SUBJECT_DIRECTED_TRANSFER_RE,
        _MAX_SHAREHOLDER_COUNTERPARTY_TRANSFER_RE,
    ):
        match = pattern.search(raw_text)
        if match is not None and not (
            pattern is _SUBJECT_DIRECTED_TRANSFER_RE
            and re.search(
                r"(?:^|\s)(?:19|20)\d{2}년|(?:^|\s)최대주주(?:인)?(?:\s|$)",
                match.group("seller"),
            )
            is not None
        ):
            candidates.append(
                (
                    _expanded_named_parties(match.group("seller")),
                    _expanded_named_parties(match.group("buyer")),
                )
            )

    sellers: list[str] = []
    buyers: list[str] = []
    for match in _TRANSFER_ROLE_RE.finditer(raw_text):
        target = sellers if match.group("role") in {"양도인", "매도인"} else buyers
        for name in _expanded_named_parties(match.group("name")):
            if name not in target:
                target.append(name)
    if sellers or buyers:
        candidates.append((sellers, buyers))

    unique_candidates: list[tuple[list[str], list[str]]] = []
    candidate_keys: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for candidate_sellers, candidate_buyers in candidates:
        key = (tuple(candidate_sellers), tuple(candidate_buyers))
        if key in candidate_keys:
            continue
        candidate_keys.add(key)
        unique_candidates.append((candidate_sellers, candidate_buyers))
    return unique_candidates[0] if len(unique_candidates) == 1 else ([], [])


def _share_transfer_mentions(
    raw_text: str,
    evidence_base: dict[str, Any],
    disclosure_phase: str,
) -> list[dict[str, Any]]:
    sellers, buyers = _share_transfer_parties(raw_text)
    evidence = _transaction_evidence(evidence_base, raw_text=raw_text)
    attributes = {"disclosure_phase": disclosure_phase}
    maximum_shareholder = (
        sellers[0]
        if sellers
        and re.search(r"(?:당사(?:의)?\s+)?최대주주(?:인)?\s+", raw_text)
        is not None
        else None
    )
    maximum_attributes = {
        "disclosure_phase": disclosure_phase,
        "maximum": True,
        **(
            {"is_current": True}
            if re.search(r"당사(?:의)?\s+(?:현재\s*)?최대주주(?:인)?\s+", raw_text)
            is not None
            else {}
        ),
    }
    return [
        *[
            _transaction_mention(
                name=name,
                relationship_type="transferor_of",
                target_ref="@reporting_company",
                attributes=dict(attributes),
                evidence=dict(evidence),
            )
            for name in sellers
        ],
        *(
            [
                _transaction_mention(
                    name=maximum_shareholder,
                    relationship_type="shareholder_of",
                    target_ref="@reporting_company",
                    attributes=maximum_attributes,
                    evidence=dict(evidence),
                )
            ]
            if maximum_shareholder is not None
            else []
        ),
        *[
            _transaction_mention(
                name=name,
                relationship_type="transferee_of",
                target_ref="@reporting_company",
                attributes=dict(attributes),
                evidence=dict(evidence),
            )
            for name in buyers
        ],
    ]


def _allottee_mentions(
    raw_text: str,
    evidence_base: dict[str, Any],
    disclosure_phase: str,
) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    for statement in _ALLOTTEE_STATEMENT_RE.finditer(raw_text):
        preceding_lines = raw_text[: statement.start()].splitlines()[-2:]
        allocation_context = " ".join(
            [*preceding_lines, _clean_text(statement.group("statement"))]
        )
        if re.search(r"제3자\s*배정", allocation_context) is None:
            continue
        value = _clean_text(
            statement.group("inline") or statement.group("continuation")
        )
        statement_text = _clean_text(statement.group("statement"))
        value = re.sub(r"^\s*[-*]\s*", "", value)
        maximum_shareholder = re.match(
            r"^(?:당사(?:의)?\s+)?최대주주(?:인)?\s+",
            value,
        ) is not None
        value = re.sub(
            r"^(?:당사(?:의)?\s+)?최대주주(?:인)?\s+",
            "",
            value,
        )
        evidence = _transaction_evidence(evidence_base, raw_text=statement_text)
        for candidate in _expanded_named_parties(value):
            name = _explicit_label_name(candidate)
            if name is None:
                continue
            mentions.append(
                _transaction_mention(
                    name=name,
                    relationship_type="proposed_allottee_of",
                    target_ref="@reporting_company",
                    attributes={"disclosure_phase": disclosure_phase},
                    evidence=dict(evidence),
                )
            )
            if maximum_shareholder:
                mentions.append(
                    _transaction_mention(
                        name=name,
                        relationship_type="shareholder_of",
                        target_ref="@reporting_company",
                        attributes={
                            "disclosure_phase": disclosure_phase,
                            "maximum": True,
                            "is_current": True,
                        },
                        evidence=dict(evidence),
                    )
                )
    return mentions


def _reference_transaction_mentions(
    soup: Any,
    disclosure_phase: str,
) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    for cell, evidence_base in _reference_note_cells(soup):
        clauses = _clauses(cell)
        for window_size in (1, 2, 3):
            for start in range(len(clauses) - window_size + 1):
                raw_text = " ".join(clauses[start : start + window_size])
                mentions.extend(
                    _share_transfer_mentions(
                        raw_text,
                        evidence_base,
                        disclosure_phase,
                    )
                )
        mentions.extend(
            _allottee_mentions(
                "\n".join(clauses),
                evidence_base,
                disclosure_phase,
            )
        )
    return mentions


def _agenda_merger_names(
    raw_text: str,
    reporting_company_name: str | None,
) -> list[str]:
    names: list[str] = []

    def add(raw_name: str) -> None:
        name = _transaction_name(raw_name)
        if name is None:
            return
        if (
            re.search(r"(?:를|을)$", name) is not None
            or re.search(r"[,;/]", name) is not None
            or len(_CORPORATE_MARKER_RE.findall(name)) > 1
            or re.search(r"(?:와|과)\s+(?:\(주\)|㈜|주식회사)", name)
            is not None
            or re.search(r"(?:와|과)\s+\S", name) is not None
            or re.search(
                r"(?:와|과)\s*(?:관계|계열|자|종속|타)?(?:회사|법인)",
                name,
            )
            is not None
        ):
            return
        generic_core = _business_name_core(name)
        if (
            _BUSINESS_REASON_GENERIC_NAME_RE.fullmatch(generic_core)
            is not None
            or _BUSINESS_REASON_DATE_NAME_RE.fullmatch(generic_core)
            is not None
            or re.search(
                r"(?:^|\s)(?:외|등|포함|기타|및)(?:\s|$)|"
                r"(?:외|등)\s*(?:다수|복수|\d+\s*(?:개\s*)?"
                r"(?:사|곳|법인|회사))|(?:총\s*)?\d+\s*(?:개\s*)?"
                r"(?:사|곳|법인|회사)(?:\s|$)",
                name,
            )
            is not None
        ):
            return
        if name not in names:
            names.append(name)

    absorption = _ABSORPTION_MERGER_RE.search(raw_text)
    if absorption is not None and not (
        re.search(r"[,;/]", absorption.group("name"))
        or re.search(r"(?:와|과)\s+\S", absorption.group("name"))
        or re.search(
            r"(?:와|과)\s+(?:\(주\)|㈜|주식회사)",
            absorption.group("name"),
        )
    ):
        add(absorption.group("name"))

    for labelled in _AGENDA_LABELLED_MERGER_RE.finditer(raw_text):
        add(labelled.group("name"))

    two_party = (
        _AGENDA_TWO_PARTY_MERGER_WITH_PARTICLE_RE.search(raw_text)
        or _AGENDA_TWO_PARTY_MERGER_RE.search(raw_text)
    )
    if two_party is not None and reporting_company_name:
        left = _transaction_name(two_party.group("left"))
        right = _transaction_name(two_party.group("right"))
        if (
            two_party.re is _AGENDA_TWO_PARTY_MERGER_WITH_PARTICLE_RE
            and right is not None
            and right.endswith(("와", "과"))
        ):
            right = _transaction_name(right[:-1])
        if left is not None and right is not None:
            left_key = _business_party_key(left)
            right_key = _business_party_key(right)
            reporting_key = _business_party_key(reporting_company_name)
            if left_key != right_key and (left_key == reporting_key) != (
                right_key == reporting_key
            ):
                add(right if left_key == reporting_key else left)

    if len(_CORPORATE_MARKER_RE.findall(raw_text)) == 1:
        marked_counterparty = _AGENDA_MARKED_COUNTERPARTY_RE.search(raw_text)
        if marked_counterparty is not None:
            add(marked_counterparty.group("name"))
        marked_absorption = _AGENDA_MARKED_ABSORPTION_RE.search(raw_text)
        if marked_absorption is not None:
            add(marked_absorption.group("name"))
    return names


def _agenda_transaction_mentions(
    agenda_records: list[dict[str, Any]],
    disclosure_phase: str,
    reporting_company_name: str | None,
) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    for agenda in agenda_records:
        evidence_base = agenda.get("evidence")
        agenda_ref = _clean_text(agenda.get("agenda_ref"))
        sources = (
            ("title", _clean_text(agenda.get("title"))),
            ("remarks", _clean_text(agenda.get("remarks"))),
        )
        for source, raw_text in sources:
            if not raw_text:
                continue
            field = "비고" if source == "remarks" else None
            evidence = _transaction_evidence(
                evidence_base,
                raw_text=raw_text,
                field=field,
            )
            for name in _agenda_merger_names(raw_text, reporting_company_name):
                mentions.append(
                    _transaction_mention(
                        name=name,
                        relationship_type="merger_target_of",
                        target_ref="@reporting_company",
                        attributes={"disclosure_phase": disclosure_phase},
                        evidence=dict(evidence),
                        organization_context=True,
                    )
                )

            stake = _AGENDA_STAKE_RE.search(raw_text)
            if stake is None or not agenda_ref:
                continue
            name = _transaction_name(stake.group("name"))
            if name is None:
                continue
            relationship_type = (
                "acquisition_target_of"
                if stake.group("action") == "인수"
                else "divestment_target_of"
            )
            mentions.append(
                _transaction_mention(
                    name=name,
                    relationship_type=relationship_type,
                    target_ref=agenda_ref,
                    attributes={
                        "disclosure_phase": disclosure_phase,
                        "outcome": _clean_text(agenda.get("status")) or None,
                    },
                    evidence=dict(evidence),
                    organization_context=True,
                )
            )
    return mentions


def _business_reason_name(value: Any, *, allow_unmarked: bool = False) -> str | None:
    raw_name = _clean_text(value)
    if _CORPORATE_MARKER_RE.search(raw_name) is not None:
        raw_name = re.sub(r"(?:와의|과의|의)$", "", raw_name)
    name = _transaction_name(raw_name)
    if name is None:
        return None
    generic_core = re.sub(r"^(?:\(주\)|㈜|주식회사)\s*", "", name)
    generic_core = re.sub(r"\s*\(주\)$", "", generic_core)
    if (
        re.search(r"(?:위한|따른|목적|관련|승인|합병|당사)", name) is not None
        or re.search(r"(?:와|과)\s+(?:\(주\)|㈜|주식회사)", name) is not None
        or _BUSINESS_REASON_GENERIC_NAME_RE.fullmatch(_compact(generic_core)) is not None
        or _BUSINESS_REASON_DATE_NAME_RE.fullmatch(_compact(generic_core)) is not None
    ):
        return None
    if _CORPORATE_MARKER_RE.search(name) is not None:
        return name
    if allow_unmarked and re.fullmatch(_BUSINESS_REASON_NAME_TOKEN, name) is not None:
        return name
    if re.fullmatch(
        r"[A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,5}",
        name,
    ) is not None:
        return name
    return None


def _business_party_key(value: str) -> str:
    key = _compact(value).casefold()
    key = re.sub(r"^(?:\(주\)|㈜|주식회사)", "", key)
    return re.sub(r"\(주\)$", "", key)


def _business_name_core(value: str) -> str:
    core = _clean_text(value)
    core = re.sub(r"^(?:\(주\)|㈜|주식회사)\s*", "", core)
    core = re.sub(r"\s*(?:\(주\)|㈜|주식회사)$", "", core)
    return _compact(core)


def _business_reason_names(reason: str) -> list[str]:
    if _BUSINESS_REASON_NEGATIVE_RE.search(reason) is not None:
        return []

    candidate_sets: list[list[str]] = []
    roster_match = _BUSINESS_REASON_ABSORBED_ROSTER_RE.search(reason)
    if roster_match is not None:
        roster = [
            part.strip()
            for part in re.split(r"\s*[,;]\s*", roster_match.group("names"))
            if part.strip()
        ]
        invalid_group_text = any(
            re.search(
                r"(?:포함|및|기타)|(?:^|\s)(?:등|외)(?:\s|$)|"
                r"(?:외|등)\s*(?:다수|복수|\d+\s*(?:개\s*)?"
                r"(?:사|곳|법인|회사))|(?:총\s*)?\d+\s*(?:개\s*)?"
                r"(?:사|곳|법인|회사)(?:\s|$)",
                part,
            )
            is not None
            or len(_CORPORATE_MARKER_RE.findall(part)) > 1
            for part in roster
        )
        if (
            invalid_group_text
            or not all(
                re.fullmatch(_BUSINESS_REASON_SINGLE_NAME, part) is not None
                for part in roster
            )
            or (
                len(roster) > 1
                and not all(
                    re.fullmatch(_BUSINESS_REASON_MARKED_NAME, part) is not None
                    for part in roster
                )
            )
        ):
            return []
        candidate_sets.append(roster)

    two_party_match = _BUSINESS_REASON_TWO_PARTY_RE.search(reason)
    if two_party_match is not None:
        left = _business_reason_name(two_party_match.group("left"))
        right = _business_reason_name(two_party_match.group("right"))
        recipient = _business_reason_name(two_party_match.group("recipient"))
        if left is None or right is None or recipient is None:
            return []
        left_key = _business_party_key(left)
        right_key = _business_party_key(right)
        recipient_key = _business_party_key(recipient)
        if left_key == right_key:
            return []
        if recipient_key == left_key:
            candidate_sets.append([right])
        elif recipient_key == right_key:
            candidate_sets.append([left])
        else:
            return []

    for pattern in (
        _BUSINESS_REASON_CURRENT_COUNTERPARTY_RE,
        _BUSINESS_REASON_COMPLETED_FORMER_RE,
        _BUSINESS_REASON_DISSOLVED_RE,
        _BUSINESS_REASON_ABSORBED_DIRECT_RE,
        _BUSINESS_REASON_SCHEDULED_MARKED_TARGET_RE,
        _BUSINESS_REASON_MARKED_PARTICLE_MERGER_RE,
        _BUSINESS_REASON_UNMARKED_PARTICLE_MERGER_RE,
    ):
        direct_match = pattern.search(reason)
        if direct_match is not None:
            candidate_sets.append([direct_match.group("name")])

    target_match = _BUSINESS_REASON_TARGET_FIRST_RE.search(reason)
    if target_match is not None and (
        _BUSINESS_REASON_POSITIVE_RE.search(reason) is not None
        or _CORPORATE_MARKER_RE.search(target_match.group("name")) is not None
    ):
        candidate_sets.append(
            [re.sub(r"(?:와의|과의)$", "", target_match.group("name"))]
        )

    if _BUSINESS_REASON_POSITIVE_RE.search(reason) is not None:
        for pattern in (
            _BUSINESS_REASON_SUBSIDIARY_RE,
            _BUSINESS_REASON_ACTION_FIRST_RE,
        ):
            baseline_match = pattern.search(reason)
            if baseline_match is not None:
                candidate_sets.append([baseline_match.group("name")])

    normalized_sets: list[list[str]] = []
    normalized_keys: set[tuple[str, ...]] = set()
    for raw_names in candidate_sets:
        names: list[str] = []
        for raw_name in raw_names:
            name = _business_reason_name(raw_name, allow_unmarked=True)
            if name is None:
                names = []
                break
            if name not in names:
                names.append(name)
        if not names:
            continue
        key = tuple(_business_party_key(name) for name in names)
        if key in normalized_keys:
            continue
        normalized_keys.add(key)
        normalized_sets.append(names)

    return normalized_sets[0] if len(normalized_sets) == 1 else []


def _business_purpose_transaction_mentions(
    business_purpose_changes: list[dict[str, Any]],
    disclosure_phase: str,
) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    for change in business_purpose_changes:
        reason = _clean_text(change.get("reason"))
        names = _business_reason_names(reason)
        if not names:
            continue
        evidence = _transaction_evidence(
            change.get("evidence"),
            raw_text=reason,
            field="이유",
            section_title="사업목적 변경 세부내역",
        )
        for name in names:
            mentions.append(
                _transaction_mention(
                    name=name,
                    relationship_type="merger_target_of",
                    target_ref="@reporting_company",
                    attributes={"disclosure_phase": disclosure_phase},
                    evidence=dict(evidence),
                    organization_context=True,
                )
            )
    return mentions


def _unique_auditor_names(raw_text: str) -> list[str]:
    names: list[str] = []
    for match in _AUDITOR_NAME_RE.finditer(raw_text):
        name = match.group("name")
        if name not in names:
            names.append(name)
    return names


def _arrow_transition(raw_text: str) -> tuple[str, str] | None:
    arrow_index = raw_text.find("→")
    if arrow_index < 0:
        return None
    former = list(_AUDITOR_NAME_RE.finditer(raw_text[:arrow_index]))
    current = list(_AUDITOR_NAME_RE.finditer(raw_text[arrow_index + 1 :]))
    if not former or not current:
        return None
    return former[-1].group("name"), current[0].group("name")


def _existing_auditor_transition(raw_text: str) -> tuple[str, str] | None:
    existing_index = raw_text.find("기존")
    termination = re.search(r"종료|만료", raw_text)
    if existing_index < 0 or termination is None or termination.start() <= existing_index:
        return None
    former = list(
        _AUDITOR_NAME_RE.finditer(raw_text, existing_index, termination.start())
    )
    current = list(_AUDITOR_NAME_RE.finditer(raw_text, termination.end()))
    if not former or not current:
        return None
    return former[-1].group("name"), current[0].group("name")


def _auditor_transition(raw_text: str, names: list[str]) -> tuple[str, str] | None:
    candidates: list[tuple[str, str]] = []
    change = _AUDITOR_CHANGE_RE.search(raw_text)
    if change is not None:
        candidates.append((change.group("former"), change.group("current")))

    for directed in (
        _arrow_transition(raw_text),
        _existing_auditor_transition(raw_text),
    ):
        if directed is not None:
            candidates.append(directed)
    if len(names) == 2 and re.search(r"변경|교체", raw_text) is not None:
        candidates.append((names[0], names[1]))

    unique_candidates = list(dict.fromkeys(candidates))
    return unique_candidates[0] if len(unique_candidates) == 1 else None


def _explicit_current_change(raw_text: str, name: str) -> bool:
    escaped_name = re.escape(name)
    return any(
        pattern.search(raw_text) is not None
        for pattern in (
            re.compile(
                rf"(?:외부|회계)?\s*감사인(?:을|를)?\s*{escaped_name}"
                rf"\s*(?:으로|로)\s*변경"
            ),
            re.compile(
                rf"{escaped_name}\s*(?:으로|로)\s*(?:외부\s*)?"
                rf"감사인(?:이|을|를)?\s*변경"
            ),
        )
    )


def _named_auditor_declaration(raw_text: str, name: str) -> bool:
    escaped_name = re.escape(name)
    return re.search(
        rf"(?:외부|회계)\s*감사인\s*"
        rf"(?:\(\s*{escaped_name}(?:\([^)]*\))?\s*\)|[:：]\s*{escaped_name})",
        raw_text,
    ) is not None


def _single_auditor_action(
    window_clauses: list[str], name: str
) -> tuple[bool, str | None]:
    named_clauses = [clause for clause in window_clauses if name in clause]
    named_text = " ".join(named_clauses)
    candidates: list[tuple[int, bool, str | None]] = []
    if _AUDITOR_REAPPOINTMENT_RE.search(named_text) is not None:
        candidates.append((0, True, "reappointed"))
    if _AUDITOR_TRANSITION_RE.search(named_text) is not None:
        candidates.append(
            (1, _explicit_current_change(named_text, name), "appointed")
        )
    if _AUDITOR_DESIGNATION_RE.search(named_text) is not None:
        candidates.append((2, True, "designated"))
    if _AUDITOR_APPOINTMENT_RE.search(named_text) is not None:
        candidates.append((3, True, "appointed"))
    if re.search(r"지정", named_text) is not None:
        candidates.append((4, True, "designated"))

    for index, clause in enumerate(window_clauses):
        if name not in clause or index == 0:
            continue
        header = window_clauses[index - 1]
        if _AUDITOR_CONTEXT_RE.search(header) is None:
            continue
        if _AUDITOR_DESIGNATION_RE.search(header) is not None:
            candidates.append((5, True, "designated"))
        if _AUDITOR_APPOINTMENT_RE.search(header) is not None:
            candidates.append((6, True, "appointed"))
        if re.search(r"지정", header) is not None:
            candidates.append((7, True, "designated"))
    if _named_auditor_declaration(named_text, name):
        candidates.append((8, True, None))
    if not candidates:
        return False, None
    _, matched, action = min(candidates, key=lambda candidate: candidate[0])
    return matched, action


def _auditor_window_mentions(
    window_clauses: list[str], evidence_base: dict[str, Any]
) -> list[dict[str, Any]]:
    raw_text = " ".join(window_clauses)
    if _AUDITOR_CONTEXT_RE.search(raw_text) is None:
        return []
    names = _unique_auditor_names(raw_text)
    if not names or len(names) > 2:
        return []

    if len(names) == 1 and any(
        names[0] in clause and _AUDITOR_REAPPOINTMENT_RE.search(clause) is not None
        for clause in window_clauses
    ):
        return [
            _mention(
                name=names[0],
                relationship_type="external_auditor_of",
                target_ref="@reporting_company",
                attributes={"state": "current", "action": "reappointed"},
                evidence_base=evidence_base,
                raw_text=raw_text,
            )
        ]

    transition = _auditor_transition(raw_text, names)
    if transition is not None:
        former, current = transition
        if former == current:
            return []
        return [
            _mention(
                name=former,
                relationship_type="external_auditor_of",
                target_ref="@reporting_company",
                attributes={"state": "former", "action": "replaced"},
                evidence_base=evidence_base,
                raw_text=raw_text,
            ),
            _mention(
                name=current,
                relationship_type="external_auditor_of",
                target_ref="@reporting_company",
                attributes={"state": "current", "action": "appointed"},
                evidence_base=evidence_base,
                raw_text=raw_text,
            ),
        ]

    if len(names) != 1:
        return []
    matched, action = _single_auditor_action(window_clauses, names[0])
    if not matched:
        return []
    attributes: dict[str, Any] = {"state": "current"}
    if action is not None:
        attributes["action"] = action
    return [
        _mention(
            name=names[0],
            relationship_type="external_auditor_of",
            target_ref="@reporting_company",
            attributes=attributes,
            evidence_base=evidence_base,
            raw_text=raw_text,
        )
    ]


def _external_auditor_mentions(
    clauses: list[str], evidence_base: dict[str, Any]
) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    by_identity: dict[tuple[str, str], int] = {}
    for window_size in (1, 2, 3):
        for start in range(len(clauses) - window_size + 1):
            window_clauses = clauses[start : start + window_size]
            for mention in _auditor_window_mentions(window_clauses, evidence_base):
                state = str(mention["attributes"]["state"])
                key = (str(mention["name"]), state)
                existing_index = by_identity.get(key)
                if existing_index is None:
                    by_identity[key] = len(mentions)
                    mentions.append(mention)
                    continue
                current_action = mentions[existing_index]["attributes"].get("action")
                candidate_action = mention["attributes"].get("action")
                if _ACTION_PRIORITY[candidate_action] > _ACTION_PRIORITY[current_action]:
                    mentions[existing_index] = mention
    return mentions


def extract_stakeholder_mentions(soup: Any) -> list[dict[str, Any]]:
    """Extract only explicitly named external auditors."""
    mentions: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for cell, evidence_base in _reference_note_cells(soup):
        clauses = _clauses(cell)
        candidates = _external_auditor_mentions(clauses, evidence_base)
        for mention in candidates:
            attributes = mention["attributes"]
            key = (
                mention["name"],
                mention["relationship_type"],
                str(attributes.get("state", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            mentions.append(mention)
    return mentions


def extract_transaction_mentions(
    soup: Any,
    agenda_records: list[dict[str, Any]],
    business_purpose_changes: list[dict[str, Any]],
    disclosure_phase: str,
    *,
    reporting_company_name: str | None = None,
) -> list[dict[str, Any]]:
    """Extract explicitly named transaction parties from canonical sources."""
    phase = _clean_text(disclosure_phase).lower()
    candidates = _reference_transaction_mentions(soup, phase)
    candidates.extend(
        _agenda_transaction_mentions(
            agenda_records,
            phase,
            reporting_company_name,
        )
    )
    candidates.extend(
        _business_purpose_transaction_mentions(business_purpose_changes, phase)
    )

    mentions: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for mention in candidates:
        key = (
            re.sub(r"\s+", "", str(mention["name"])).casefold(),
            str(mention["relationship_type"]),
            str(mention["target_ref"]),
        )
        if key in seen:
            continue
        seen.add(key)
        mentions.append(mention)
    return mentions
