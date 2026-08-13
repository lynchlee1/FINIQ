"""Document-local entities and relationships for shareholder-meeting disclosures."""

from __future__ import annotations

import re
from typing import Any


_EMPTY_NAMES = {
    "",
    "-",
    "미정",
    "미확정",
    "후보자미정",
    "해당사항없음",
    "없음",
    "상근",
    "비상근",
    "후보자",
    "사퇴",
    "선임의",
    "위원",
    "위원회",
    "신규",
    "중임",
    "재선임",
}
_KOREAN_PERSON_NAME = r"(?:[가-힣]{2,5}|[가-힣]{1,5}(?:\s+[가-힣]{1,5}){1,4})"
_ENGLISH_PERSON_NAME = r"[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,5}"
_PERSON_NAME_RE = re.compile(rf"(?:{_KOREAN_PERSON_NAME}|{_ENGLISH_PERSON_NAME})")
_CANDIDATE_PERSON_NAME = (
    rf"(?:[가-힣]{{2,5}}|{_ENGLISH_PERSON_NAME}|"
    rf"[가-힣]{{1,5}}(?:\s+[가-힣]{{1,5}}){{1,4}})"
)
_APPOINTMENT_QUALIFIER = r"(?:신규\s*선임|재\s*선임|중임|신규)"
_APPOINTMENT_MODIFIER_RE = re.compile(r"(?:분리|일괄|추가)(?:선임)?")
_OFFICE_PATTERNS = (
    ("audit_committee_member", re.compile(r"감사위원")),
    ("outside_director", re.compile(r"사외이사|독립이사")),
    (
        "auditor",
        re.compile(
            r"(?:상근|비상근)?감사(?!위원|위원회|보고|의견|보수)"
            r"(?:의)?(?=(?:후보|선임|재선임|해임|"
            r"[가-힣A-Za-z.'-]{2,30}(?:신규|재)?선임|$))"
        ),
    ),
    (
        "director",
        re.compile(
            r"사내이사|기타비상무이사|비상무이사|비상임이사|"
            r"(?<!사외)(?<!독립)(?<!사내)(?<!비상무)(?<!비상임)(?<!기타비상무)이사(?!회|보수)"
        ),
    ),
)
_POSITION_ATOM = (
    r"(?:대표이사|사외이사|사내이사|기타비상무이사|비상무이사|"
    r"상근\s*감사|비상근\s*감사|감사위원회\s*위원장|감사위원장|"
    r"감사위원|감사|부사장|부회장|사장|회장|이사|CEO|CFO|COO)"
)
_POSITION_SEQUENCE = (
    rf"{_POSITION_ATOM}(?:"
    rf"\s*\(\s*{_POSITION_ATOM}\s*\)|"
    rf"\s+(?:(?:및|겸)\s+)?{_POSITION_ATOM}|"
    rf"\s*[/·ㆍ,]\s*{_POSITION_ATOM}"
    rf")*"
)
_OTHER_COMPANY_POSITION_RE = re.compile(
    rf"^(?:(?:現\s+|현[.)]\s*))?(?P<org>.+?)(?:"
    rf"\s*\(\s*(?P<wrapped>{_POSITION_SEQUENCE})\s*\)|\s+"
    rf"(?P<position>{_POSITION_SEQUENCE}))$"
)
_OTHER_COMPANY_CURRENT_PERIOD_RE = re.compile(
    r"^(?:19|20)\d{2}년\s*\d{1,2}월\s*[-–—~]\s*현재\s*[:：]\s*"
)
_MAJOR_CAREER_CURRENT_RE = re.compile(
    r"^\s*(?:[-*○●ㆍ·]\s*)?(?:"
    r"\(\s*(?:現|현)\s*\)|"
    r"(?:現|현)(?:\s*[):：.]\s*|\s+|"
    r"\s*[,，]\s*(?=(?:\(주\)|㈜|주식회사|유한회사|\(유\)))|"
    r"(?=\s*(?:\(주\)|㈜|주식회사|유한회사|\(유\)))))"
    r"(?P<body>.+)$"
)
_MAJOR_CAREER_STATUS_RE = re.compile(
    r"(?:^|\s)(?:現|현|前|전)\s*[):：.]"
)
_MAJOR_CAREER_GENERIC_ORG_RE = re.compile(
    r"^(?:당사|회사|본사|현직|재직|근무|없음|해당사항\s*없음)$"
)
_MAJOR_CAREER_ORG_NOISE_RE = re.compile(
    r"(?:본부|부문|사업부|팀|실)(?:장)?(?:\s|$)|"
    r"(?:담당|총괄|변호사|교수|고문|소장|원장|위원|재직)(?:\s|$)|"
    r"(?:^|\s)(?:개발|기획|영업|연구|재무|법무|마케팅|전략|생산|운영|경영|관리|인사|총무)(?:\s|$)"
)
_MAJOR_CAREER_UNIT_SUFFIX_RE = re.compile(
    r"^(?P<org>.+?)\s+(?P<unit>(?:연구개발|경영지원|품질관리|"
    r"경영기획|사업개발|영업기획|제품개발|기술개발|"
    r"개발|기획|영업|연구|재무|법무|마케팅|전략|생산|운영|"
    r"경영|관리|인사|총무)(?:부|본부|부문|사업부|팀|실)?)$"
)
_MAJOR_CAREER_ORG_PREFIX_RE = re.compile(
    r"^(?:(?:\(주\)|㈜|주식회사|유한회사|\(유\))\s*\S|"
    r"(?:\S*(?:회사|법인))\s+\S)",
    re.IGNORECASE,
)
_MAJOR_CAREER_ORG_SUFFIX_RE = re.compile(
    r"(?:\(주\)|㈜|\(유\)|회사|법인|은행|증권|보험|캐피탈|파트너스|"
    r"홀딩스|그룹|재단|협회|학회|대학교|대학|공사|공단|조합|병원|"
    r"의료원|연구소|"
    r"Co\.?|Ltd\.?|Inc\.?|LLC|Corp\.?)$",
    re.IGNORECASE,
)
_MAJOR_CAREER_LEGAL_FORM_RE = re.compile(
    r"(?:\(주\)|㈜|주식회사|유한회사|\(유\)|회계법인|법무법인)"
)
_MAJOR_CAREER_FUSED_WORK_UNIT_RE = re.compile(
    r"^(?:법인|증권|보험|은행)"
    r"(?:영업|기획|관리|개발|지원|마케팅|운영|전략|재무|법무|인사|총무)"
    r"(?:부|본부|팀|실)?$"
)
_CORPORATE_MARKERS = re.compile(
    r"(?:\(주\)|㈜|주식회사|유한회사|회계법인|법무법인|투자조합|은행|증권|파트너스)"
)
_NON_PERSON_TOKENS = {
    "이사",
    "사내이사",
    "사외이사",
    "독립이사",
    "비상임이사",
    "비상무이사",
    "기타비상무이사",
    "감사",
    "감사위원",
    "감사위원회",
    "임시의장",
    "선임",
    "선임의",
    "재선임",
    "해임",
    "후보",
    "후보자",
    "위원",
    "위원회",
    "신규",
    "중임",
    "사퇴",
}
_ROLE_DERIVED_TOKEN_RE = re.compile(
    r"^(?:(?:사내|사외|독립|기타비상무|비상무|비상임)?이사|"
    r"감사(?:위원|위원회)?|위원(?:회)?)(?:인|인감사위원|가|이|는|겸)?$"
)
_PLACEHOLDER_CANDIDATE_RE = re.compile(
    r"^(?:후보자?\s*)?(?:미정|미확정)(?:\s*[,·ㆍ/]?\s*추후\s+확정)?$"
)
_CANDIDATE_LEADING_OFFICE_RE = re.compile(
    r"^(?:(?:사내|사외|독립|기타\s*비상무|비상무|비상임)\s*이사|"
    r"(?:상근|비상근|비상임)?\s*감사(?!의원회|위원회|위원)|"
    r"감사위원회\s*위원(?:장)?|감사위원(?:장)?)\s+"
)
_CANDIDATE_LEADING_ACTION_RE = re.compile(
    r"^(?:선임|재선임|해임)(?:의)?\s*건\s+"
)
_CANDIDATE_ROLE_CLAUSE_RE = re.compile(
    r"(?:감사(?:의원회|위원회)\s*의?원(?:장)?이?\s*되는|"
    r"감사위원(?:회)?\s*위원(?:장)?이?\s*되는)"
)
_AGENDA_PREFIX_RE = re.compile(
    r"^\s*[-*○]?\s*(?:제\s*)?\d+(?:\s*[-의]\s*\d+)?\s*호"
    r"\s*(?:의안|안건)?\s*[:：.)-]?\s*"
)
_CAUSE_CLAUSE_RE = re.compile(
    r"\s+[가-힣 ]+(?:에|로|으로)\s+따른$"
)
_TERMINATION_GRAMMAR_SURFACE_RE = re.compile(
    r"^(?:의안(?:인)?|인한|"
    r"(?:(?:사내|사외|독립|등기|대표|기타|비상무|비상임|전대표|"
    r"상근|비상근|비상임)(?:이사|감사)?))$"
)
_TERMINATION_CAUSAL_SURFACE_RE = re.compile(
    r"(?:에|로|으로)\s*(?:따른|인한)$"
)
_PROPOSER_DESCRIPTION_RE = re.compile(
    r"(?:^|\s)(?:후보자?|선임|재선임|해임|사임|취득|매입|매수|처분|"
    r"금액|예정|승인|의안|안건|보수|한도|건)(?:\s|$)"
)
_PROPOSER_ROLE_PREFIX_RE = re.compile(
    r"^(?:(?:사내|사외|독립|기타비상무|비상무|비상임)?이사|"
    r"(?:상근|비상근|비상임)?감사|감사위원(?:회)?|선임)"
    r"(?:후보(?:자)?)?(?:\s|$)"
)
_PROPOSER_COMPACT_DESCRIPTION_RE = re.compile(
    r"^(?:(?:취득|매입|매수|처분|승인|선임|재선임|해임|사임|"
    r"후보자?|예정|금액|보수|한도|의안|안건|건)){2,}$"
)
_PROPOSER_COMPACT_ROLE_RE = re.compile(
    r"^(?:후보(?:자)?[가-힣]{2,5}|[가-힣]{2,5}후보(?:자)?|"
    r"(?:선임|감사|이사)[가-힣]{2,5})$"
)
_CORRECTION_PROPOSER_RE = re.compile(
    r"^\s*(?:[-*ㆍ·]\s*[.]?\s*)?"
    r"(?P<office>이사|사내이사|사외이사|독립이사|기타\s*비상무이사|"
    r"비상무이사|비상임이사|감사|감사위원)\s*선임\s*후보자\s*중\s*"
    r"(?P<candidates>[^():：]+?)\s*"
    r"(?:이상\s*(?P<count>\d+)\s*명)?\s*(?:은|는)\s*"
    r"주주\s*제안\s*\(\s*(?:제안자|제안인)\s*[:：]\s*"
    r"(?P<proposer>[^():：]+?)\s*\)\s*에\s*의한\s*"
    r"후보자(?:임|입니다)?\s*[.]?\s*$"
)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _name_key(value: str) -> str:
    return re.sub(r"[\s·ㆍ,]", "", value).casefold()


def _organization_key(value: str) -> str:
    name = _clean_text(value)
    name = re.sub(r"^(?:\(주\)|㈜|주식회사)\s*", "", name)
    name = re.sub(r"\s*\(주\)$", "", name)
    return re.sub(r"[\s·ㆍ,.]", "", name).casefold()


def _person_name_and_aliases(value: str) -> tuple[str, list[str]]:
    name = _clean_text(value)
    alias_match = re.fullmatch(r"(?P<base>.+?)\s*\((?P<alias>[A-Za-z][A-Za-z .'-]+)\)", name)
    if alias_match is None:
        return name, []
    return _clean_text(alias_match.group("base")), [_clean_text(alias_match.group("alias"))]


def _person_key(value: str) -> str:
    base_name, _ = _person_name_and_aliases(value)
    return _name_key(base_name)


def _is_empty_name(value: str) -> bool:
    return (
        _name_key(value) in _EMPTY_NAMES
        or _PLACEHOLDER_CANDIDATE_RE.fullmatch(_clean_text(value)) is not None
    )


def _is_candidate_name(value: str) -> bool:
    name = _name_key(value)
    return (
        bool(name)
        and name not in _NON_PERSON_TOKENS
        and _ROLE_DERIVED_TOKEN_RE.fullmatch(name) is None
        and _APPOINTMENT_MODIFIER_RE.fullmatch(name) is None
    )


def _candidate_surface(value: str) -> str:
    name = re.sub(
        r"\s+(?:(?:후보자?)(?:의)?|신규|재)\s*$",
        "",
        _clean_text(value),
    )
    while True:
        stripped = _CANDIDATE_LEADING_OFFICE_RE.sub("", name, count=1)
        stripped = _CANDIDATE_LEADING_ACTION_RE.sub("", stripped, count=1)
        if stripped == name:
            return name
        name = stripped


def _is_candidate_surface(value: str) -> bool:
    """Accept a person-shaped surface, not the grammar around a role or action."""
    name = _candidate_surface(value)
    if _is_empty_name(name) or not _is_candidate_name(name):
        return False
    if _PERSON_NAME_RE.fullmatch(name) is None:
        return False
    if _CAUSE_CLAUSE_RE.search(name):
        return False
    if _CANDIDATE_ROLE_CLAUSE_RE.search(name):
        return False
    if re.match(r"^(?:이\s+되는|의\s+)", name):
        return False
    return re.search(r"\s+(?:및|[와과])$", name) is None


def _candidate_agenda_text(value: str) -> str:
    text = _AGENDA_PREFIX_RE.sub("", _clean_text(value))
    return re.sub(
        r"(?:기타\s*비상무|사외|사내|독립|비상무|비상임)\s*이사",
        lambda match: re.sub(r"\s+", "", match.group(0)),
        text,
    )


def _evidence(value: Any, *, field: str | None = None) -> dict[str, Any]:
    evidence = dict(value) if isinstance(value, dict) else {}
    if field is not None:
        evidence["field"] = field
    evidence["raw_text"] = _clean_text(evidence.get("raw_text"))
    return evidence


class _Registry:
    def __init__(self) -> None:
        self.entities: list[dict[str, Any]] = []
        self.relationships: list[dict[str, Any]] = []
        self._entity_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._people_by_name: dict[str, list[dict[str, Any]]] = {}
        self._relationship_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    def person(self, name: str, birth_month: str, evidence: dict[str, Any]) -> str | None:
        name, aliases = _person_name_and_aliases(name)
        if _is_empty_name(name) or not _is_candidate_name(name):
            return None
        birth_month = "" if _is_empty_name(birth_month) else _clean_text(birth_month)
        normalized_name = _person_key(name)
        key = ("person", normalized_name, birth_month)
        entity = self._entity_by_key.get(key)
        if entity is None:
            entity = {
                "entity_ref": f"person:{len([item for item in self.entities if item['entity_type'] == 'person'])}",
                "entity_type": "person",
                "name": name,
                "attributes": {
                    **({"birth_month": birth_month} if birth_month else {}),
                    **({"aliases": aliases} if aliases else {}),
                },
                "mentions": [],
            }
            self.entities.append(entity)
            self._entity_by_key[key] = entity
            self._people_by_name.setdefault(normalized_name, []).append(entity)
        elif aliases:
            current_aliases = entity["attributes"].setdefault("aliases", [])
            for alias in aliases:
                if alias not in current_aliases:
                    current_aliases.append(alias)
        self._add_mention(entity, evidence)
        return str(entity["entity_ref"])

    def organization(
        self,
        name: str,
        evidence: dict[str, Any],
        attributes: dict[str, Any] | None = None,
    ) -> str | None:
        name = _clean_text(name).strip("-–—,; ")
        if _is_empty_name(name):
            return None
        attributes = dict(attributes or {})
        key = ("organization", _name_key(name), "")
        entity = self._entity_by_key.get(key)
        if entity is None:
            entity = {
                "entity_ref": f"organization:{len([item for item in self.entities if item['entity_type'] == 'organization'])}",
                "entity_type": "organization",
                "name": name,
                "attributes": attributes,
                "mentions": [],
            }
            self.entities.append(entity)
            self._entity_by_key[key] = entity
        else:
            for attribute, value in attributes.items():
                if value is None or value == "":
                    continue
                if attribute == "aliases" and isinstance(value, list):
                    aliases = entity["attributes"].setdefault("aliases", [])
                    for alias in value:
                        if alias not in aliases:
                            aliases.append(alias)
                else:
                    entity["attributes"].setdefault(attribute, value)
        self._add_mention(entity, evidence)
        return str(entity["entity_ref"])

    def relation(
        self,
        source_ref: str,
        target_ref: str,
        relationship_type: str,
        attributes: dict[str, Any],
        evidence: dict[str, Any],
    ) -> None:
        if relationship_type == "subject_of":
            discriminator = _clean_text(attributes.get("action"))
        elif relationship_type == "serves_at":
            discriminator = _clean_text(attributes.get("position"))
        elif relationship_type == "external_auditor_of":
            discriminator = _clean_text(attributes.get("state"))
        else:
            discriminator = _clean_text(
                attributes.get("office_type") or attributes.get("action") or ""
            )
        key = (source_ref, target_ref, relationship_type, discriminator)
        existing = self._relationship_by_key.get(key)
        if existing is not None:
            if relationship_type == "subject_of" and discriminator == "appointment":
                office_types: list[str] = []
                for candidate_attributes in (existing["attributes"], attributes):
                    plural = candidate_attributes.get("office_types")
                    if isinstance(plural, list):
                        for office_type in plural:
                            if office_type and office_type not in office_types:
                                office_types.append(str(office_type))
                    singular = _clean_text(candidate_attributes.get("office_type"))
                    if singular and singular not in office_types:
                        office_types.append(singular)
                if len(office_types) > 1:
                    existing["attributes"].pop("office_type", None)
                    existing["attributes"]["office_types"] = office_types
                    attributes = {
                        attribute: value
                        for attribute, value in attributes.items()
                        if attribute not in {"office_type", "office_types"}
                    }
            existing["attributes"].update(
                {
                    key: value
                    for key, value in attributes.items()
                    if value is not None and value != ""
                }
            )
            if attributes.get("outcome"):
                existing["evidence"] = dict(evidence)
            return
        relation = {
            "source_ref": source_ref,
            "target_ref": target_ref,
            "relationship_type": relationship_type,
            "attributes": dict(attributes),
            "evidence": dict(evidence),
        }
        self.relationships.append(relation)
        self._relationship_by_key[key] = relation

    @staticmethod
    def _add_mention(entity: dict[str, Any], evidence: dict[str, Any]) -> None:
        if evidence not in entity["mentions"]:
            entity["mentions"].append(evidence)


def _office_type(text: str) -> str | None:
    office_types = _office_types(text)
    return office_types[0] if office_types else None


def _office_types(text: str) -> list[str]:
    compact_text = re.sub(r"\s+", "", text)
    office_types = [
        office_type
        for office_type, pattern in _OFFICE_PATTERNS
        if pattern.search(compact_text)
    ]
    if "사외이사가아닌감사위원" in compact_text:
        office_types = [item for item in office_types if item != "outside_director"]
    if (
        "director" in office_types
        and "outside_director" in office_types
        and re.search(r"사내이사|기타비상무이사|비상무이사|비상임이사", compact_text)
        is None
    ):
        office_types.remove("director")
    return office_types


def _candidate_names(record: dict[str, Any]) -> list[str]:
    names: list[str] = []
    canonical_name_keys: set[str] = set()

    def append_name(value: str) -> None:
        name = _candidate_surface(value)
        if (
            not _is_candidate_surface(name)
            or _office_types(name)
            or any(_person_key(existing) == _person_key(name) for existing in names)
        ):
            return
        if any(
            name.startswith(existing)
            and name[len(existing) :] in {"신규", "재", "중임"}
            for existing in names
        ):
            return
        names.append(name)

    explicit = _clean_text(record.get("candidate"))
    if explicit and not _is_empty_name(explicit):
        for part in re.split(r"\s*(?:,|·|ㆍ|/| 및 )\s*", explicit):
            append_name(part)
            canonical_name = _candidate_surface(part)
            if _is_candidate_surface(canonical_name):
                canonical_name_keys.add(_person_key(canonical_name))

    text = _candidate_agenda_text(record.get("title"))
    for match in re.finditer(
        rf"\(\s*주주\s*제안\s*[:：]\s*후보자?\s*"
        rf"(?P<name>{_CANDIDATE_PERSON_NAME})\s*\)",
        text,
    ):
        append_name(match.group("name"))
    for match in re.finditer(
        rf"\(\s*후보자?\s*[:：]?\s*(?P<name>{_CANDIDATE_PERSON_NAME})"
        rf"(?:\s*{_APPOINTMENT_QUALIFIER})?\s*(?:선임의?\s*건)?\s*\)",
        text,
    ):
        append_name(
            re.sub(
                r"^(?:[가-힣]+국인|외국인)\s+",
                "",
                _candidate_surface(match.group("name")),
            )
        )
    text_for_name_first = text

    role_atom = (
        r"(?:감사위원회\s*위원장|감사위원장|감사위원회\s*위원|감사위원(?!회)|"
        r"사내이사|사외이사|독립이사|기타\s*비상무이사|"
        r"비상무이사|비상임이사|"
        r"(?:상근|비상근)?\s*감사(?!위원|\s*보수))"
    )
    role = rf"(?:{role_atom})(?:\s*겸\s*(?:{role_atom}))?"
    qualified_action = (
        rf"{_APPOINTMENT_QUALIFIER}\s*"
        r"(?:선임)?(?:\s*승인)?(?:의)?(?:\s*건)?"
    )
    simple_action = (
        r"(?:선임|재선임|해임)(?:\s*승인)?(?:의)?(?:\s*건)?"
    )
    approval_action = r"승인(?:의)?(?:\s*건)?"
    cause_action = (
        rf"임기\s*만료(?:에|로|으로)\s*따른\s*"
        rf"(?:{qualified_action}|{simple_action})"
    )
    terminator = r"(?=\s*(?:\)|\([^)]*\))?\s*(?:☞|→|⇒|=>|->|$))"
    name_first_patterns = (
        re.compile(
            rf"(?<![A-Za-z0-9가-힣])(?P<name>{_CANDIDATE_PERSON_NAME})\s+{role}\s*"
            rf"(?:후보(?:자)?\s*)?{qualified_action}{terminator}"
        ),
        re.compile(
            rf"(?<![A-Za-z0-9가-힣])(?P<name>{_CANDIDATE_PERSON_NAME})\s+{role}\s*"
            rf"(?:후보(?:자)?\s*)?{simple_action}{terminator}"
        ),
        re.compile(
            rf"(?<![A-Za-z0-9가-힣])(?P<name>{_CANDIDATE_PERSON_NAME})\s*후보(?:자)?\s*"
            rf"{role}\s*(?:{qualified_action}|{simple_action}|{approval_action})"
            rf"{terminator}"
        ),
    )
    role_first_patterns = (
        re.compile(
            rf"(?<![A-Za-z0-9가-힣])(?:후보(?:자)?\s*)?{role}\s*(?:후보(?:자)?\s*)?"
            rf"(?P<name>{_CANDIDATE_PERSON_NAME})\s*"
            rf"(?:후보(?:자)?\s*)?{qualified_action}{terminator}"
        ),
        re.compile(
            rf"(?<![A-Za-z0-9가-힣])(?:후보(?:자)?\s*)?{role}\s*(?:후보(?:자)?\s*)?"
            rf"(?P<name>{_CANDIDATE_PERSON_NAME})\s*"
            rf"(?:후보(?:자)?\s*)?{simple_action}{terminator}"
        ),
        re.compile(
            rf"(?<![A-Za-z0-9가-힣])(?:후보(?:자)?\s*)?{role}\s*"
            rf"(?P<name>{_CANDIDATE_PERSON_NAME})\s*{cause_action}{terminator}"
        ),
        re.compile(
            rf"(?<![A-Za-z0-9가-힣]){role}\s*(?P<name>{_CANDIDATE_PERSON_NAME})\s*"
            rf"후보(?:자)?\s*{approval_action}{terminator}"
        ),
    )
    for candidate_pattern in name_first_patterns:
        for match in candidate_pattern.finditer(text_for_name_first):
            if _office_types(text_for_name_first[: match.start("name")]):
                continue
            append_name(match.group("name"))
    for candidate_pattern in role_first_patterns:
        for match in candidate_pattern.finditer(text):
            append_name(match.group("name"))
    for labelled in re.finditer(
        rf"후보(?:자)?\s*[:：]\s*(?:{role}\s*)?"
        rf"(?P<names>{_CANDIDATE_PERSON_NAME}(?:\s*[,·ㆍ/]\s*{_CANDIDATE_PERSON_NAME})*)",
        text,
    ):
        for part in re.split(r"\s*[,·ㆍ/]\s*", labelled.group("names")):
            append_name(part)
    for match in re.finditer(
        rf"임시의장\s*(?P<name>{_PERSON_NAME_RE.pattern})"
        r"(?:\s*\(\s*\d{4}\s*년\s*\d{1,2}\s*월\s*생\s*\))?\s*선임",
        text,
    ):
        append_name(match.group("name"))
    return [
        name
        for name in names
        if _person_key(name) in canonical_name_keys
        or not any(
            canonical_key.startswith(_person_key(name))
            and canonical_key != _person_key(name)
            for canonical_key in canonical_name_keys
        )
    ]


def _termination_subjects(
    record: dict[str, Any],
) -> list[tuple[str, str, list[str]]]:
    """Return people explicitly named in a removal or resignation agenda."""
    text = _candidate_agenda_text(record.get("title"))
    role_atom = (
        r"(?:감사위원회\s*위원장|감사위원장|감사위원회\s*위원|감사위원(?!회)|"
        r"대표이사|사내이사|사외이사|독립이사|기타\s*비상무이사|"
        r"비상무이사|비상임이사|이사|"
        r"(?:상근|비상근|비상임)?\s*감사(?!위원))"
    )
    compact_korean_name = r"[가-힣]{2,5}"
    spaced_korean_name = r"[가-힣]{1,2}(?:\s+[가-힣]{1,2}){1,3}"
    korean_transliteration = r"[가-힣]{3,5}\s+[가-힣]{2,5}"
    direct_name_pattern = (
        rf"(?:{compact_korean_name}|{spaced_korean_name}|"
        rf"{korean_transliteration}|{_ENGLISH_PERSON_NAME})"
    )
    roster_name_pattern = rf"(?:[가-힣]{{2,3}}|{_ENGLISH_PERSON_NAME})"
    direct_name_re = re.compile(direct_name_pattern)
    roster_name_re = re.compile(roster_name_pattern)
    subjects: list[tuple[str, str, list[str]]] = []

    def add(
        name: str,
        action: str,
        office_text: str,
        *,
        allowed_name_re: re.Pattern[str] = direct_name_re,
    ) -> None:
        name = _clean_text(name)
        office_types = _office_types(office_text)
        item = (name, action, office_types)
        if (
            office_types
            and allowed_name_re.fullmatch(name) is not None
            and _is_candidate_surface(name)
            and not _office_types(name)
            and _TERMINATION_GRAMMAR_SURFACE_RE.fullmatch(_name_key(name)) is None
            and _TERMINATION_CAUSAL_SURFACE_RE.search(name) is None
            and item not in subjects
        ):
            subjects.append(item)

    wrapped_pattern = re.compile(
        rf"(?<![A-Za-z0-9가-힣])(?P<role>{role_atom})\s*"
        rf"\(\s*(?:전\s*대표이사\s*)?(?P<name>{direct_name_pattern})\s*\)\s*"
        rf"(?P<action>해임|사임)(?:의)?\s*건"
    )
    plain_pattern = re.compile(
        rf"(?<![A-Za-z0-9가-힣])(?P<role>{role_atom})\s+"
        rf"(?:"
        rf"(?P<korean_particle_name>[가-힣]{{3}})의|"
        rf"(?P<explicit_particle_name>(?:{spaced_korean_name}|"
        rf"{korean_transliteration}|{_ENGLISH_PERSON_NAME}))의|"
        rf"(?P<name>{direct_name_pattern})"
        rf")\s+"
        rf"(?P<action>해임|사임)(?:의)?\s*건"
    )
    name_first_pattern = re.compile(
        rf"(?<![A-Za-z0-9가-힣])(?:(?P<scope_role>{role_atom})\s+)?"
        rf"(?P<name>{direct_name_pattern})\s+(?P<role>{role_atom})\s*"
        rf"(?P<action>해임|사임)(?:의)?\s*건"
    )
    compact_name_first_pattern = re.compile(
        rf"(?<![A-Za-z0-9가-힣])(?P<name>[가-힣]{{2,5}}?)"
        rf"(?P<role>{role_atom})\s+(?P<action>해임|사임)(?:의)?\s*건"
    )
    compound_role_atom = (
        r"(?:감사위원회\s*위원장|감사위원장|감사위원회\s*위원|"
        r"감사위원(?!회)|대표이사|사내이사|사외이사|독립이사|"
        r"기타\s*비상무이사|비상무이사|비상임이사|"
        r"(?:상근|비상근|비상임)\s*감사(?!위원))"
    )
    compact_compound_name_first_pattern = re.compile(
        rf"(?<![A-Za-z0-9가-힣])(?P<name>[가-힣]{{2,5}}?)"
        rf"(?P<role>{compound_role_atom})\s+"
        rf"(?P<action>해임|사임)(?:의)?\s*건"
    )
    compact_terminal_bare_pattern = re.compile(
        rf"(?<![A-Za-z0-9가-힣])(?P<name>[가-힣]{{2,5}}?)"
        r"(?P<role>"
        r"(?<!대표)(?<!사내)(?<!사외)(?<!독립)(?<!비상무)"
        r"(?<!비상임)(?<!기타비상무)이사|"
        r"(?<!상근)(?<!비상근)(?<!비상임)감사)\s*"
        r"(?P<action>해임|사임)(?:의)?\s*건\s*$"
    )
    for match in wrapped_pattern.finditer(text):
        add(
            match.group("name"),
            "removal" if match.group("action") == "해임" else "resignation",
            match.group("role"),
        )
    for match in plain_pattern.finditer(text):
        name = (
            match.group("korean_particle_name")
            or match.group("explicit_particle_name")
            or match.group("name")
        )
        add(
            name,
            "removal" if match.group("action") == "해임" else "resignation",
            match.group("role"),
        )
    for match in name_first_pattern.finditer(text):
        add(
            match.group("name"),
            "removal" if match.group("action") == "해임" else "resignation",
            match.group("scope_role") or match.group("role"),
        )
    for match in compact_compound_name_first_pattern.finditer(text):
        add(
            match.group("name"),
            "removal" if match.group("action") == "해임" else "resignation",
            match.group("role"),
        )
    for match in compact_terminal_bare_pattern.finditer(text):
        add(
            match.group("name"),
            "removal" if match.group("action") == "해임" else "resignation",
            match.group("role"),
        )
    if _clean_text(record.get("status")) == "passed":
        for match in compact_name_first_pattern.finditer(text):
            add(
                match.group("name"),
                "removal" if match.group("action") == "해임" else "resignation",
                match.group("role"),
            )

    roster_pattern = re.compile(
        rf"(?<![A-Za-z0-9가-힣])(?P<role>{role_atom})\s*전원\s*해임(?:의)?\s*건"
        rf"\s*\((?P<names>[^)]+)\)"
    )
    for match in roster_pattern.finditer(text):
        if re.search(r"[,·ㆍ/]", match.group("names")) is None:
            continue
        for name in re.split(r"\s*(?:,|·|ㆍ|/)\s*", match.group("names")):
            add(
                name,
                "removal",
                match.group("role"),
                allowed_name_re=roster_name_re,
            )
    return [subject for subject in subjects if _name_key(subject[0]) != "전원"]


def _record_evidence(record: dict[str, Any], *, field: str | None = None) -> dict[str, Any]:
    return _evidence(record.get("evidence"), field=field)


def _candidate_withdrew(
    agenda: dict[str, Any],
    name: str,
    candidate_names: list[str],
) -> bool:
    remarks = _clean_text(agenda.get("remarks"))
    if not remarks:
        return False

    candidate_name, _ = _person_name_and_aliases(name)
    escaped_name = re.escape(candidate_name)
    withdrawal_action = (
        r"(?:사퇴|사임(?:서)?|"
        r"취임(?:의사|승낙)(?:을|를)?\s*(?:철회|거부|하지\s*아니))"
    )
    withdrawal_reason = r"(?:(?:일신상(?:의)?|개인)\s*(?:사유|이유)로\s*)?"
    named_withdrawal = re.search(
        rf"{escaped_name}\s*(?:후보자?)?(?:가|는|은|이)?"
        rf"\s*{withdrawal_reason}{withdrawal_action}",
        remarks,
    ) is not None

    distinct_candidates = {_person_key(candidate) for candidate in candidate_names}
    self_withdrawal = (
        distinct_candidates == {_person_key(candidate_name)}
        and re.search(
            rf"(?:본인|후보자\s*자신)(?:이|은|는|가)?"
            rf"\s*{withdrawal_reason}{withdrawal_action}",
            remarks,
        )
        is not None
    )
    return named_withdrawal or self_withdrawal


def _agendas_for_election(
    election: dict[str, Any],
    agenda_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    raw_name = _clean_text(election.get("name"))
    name, _ = _person_name_and_aliases(raw_name)
    exact_name = re.compile(
        rf"(?<![A-Za-z0-9가-힣]){re.escape(name)}(?![A-Za-z0-9가-힣])",
        re.IGNORECASE,
    )
    office_type = _clean_text(election.get("section_type"))
    compatible_matches: list[dict[str, Any]] = []
    for agenda in agenda_records:
        title = _clean_text(agenda.get("title"))
        if "해임" in title:
            continue
        if not re.search(r"선임|재선임|후보", title):
            continue
        agenda_candidate_keys = {
            _person_key(candidate) for candidate in _candidate_names(agenda)
        }
        if _person_key(name) not in agenda_candidate_keys and exact_name.search(title) is None:
            continue
        agenda_offices = _office_types(title)
        if not agenda_offices or office_type in agenda_offices:
            compatible_matches.append(agenda)
    return compatible_matches


def _parse_other_company_line(line: str) -> tuple[str, str] | None:
    line = _clean_text(line).lstrip("-–— ")
    line = re.sub(r"^\d+\s*[.)]\s*", "", line)
    line = _OTHER_COMPANY_CURRENT_PERIOD_RE.sub("", line, count=1)
    line = re.sub(r"\s*\([^)]*\d{4}[^)]*\)\s*$", "", line)
    if _is_empty_name(line):
        return None

    match = _OTHER_COMPANY_POSITION_RE.fullmatch(line)
    if match is None:
        return None
    position = match.group("wrapped") or match.group("position")
    organization = _clean_text(match.group("org"))
    if _is_empty_name(organization) or _office_types(organization):
        return None
    return organization, _clean_text(position)


def _parse_other_company_lines(lines: list[str]) -> list[tuple[str, str]]:
    parsed = [
        parsed
        for line in lines
        if (parsed := _parse_other_company_line(_clean_text(line))) is not None
    ]
    for index in range(len(lines) - 1):
        organization = _clean_text(lines[index]).lstrip("-–— ")
        position_line = _clean_text(lines[index + 1]).lstrip("-–— ")
        wrapped = re.fullmatch(
            rf"\(\s*(?P<position>{_POSITION_SEQUENCE})\s*\)",
            position_line,
        )
        position = (
            _clean_text(wrapped.group("position"))
            if wrapped is not None
            else position_line
            if re.fullmatch(_POSITION_SEQUENCE, position_line)
            else None
        )
        if (
            position is None
            or _is_empty_name(organization)
            or _office_types(organization)
            or re.fullmatch(
                _POSITION_SEQUENCE,
                f"{organization.rsplit(maxsplit=1)[-1]}{position}",
            )
            is not None
            or _parse_other_company_line(organization) is not None
        ):
            continue
        item = (organization, position)
        if item not in parsed:
            parsed.append(item)
    return parsed


def _parse_major_career_line(
    line: str,
    reporting_company_name: str | None = None,
) -> tuple[str, str] | None:
    raw_line = _clean_text(line)
    marker = _MAJOR_CAREER_CURRENT_RE.fullmatch(raw_line)
    if marker is None:
        return None
    body = _clean_text(marker.group("body"))
    if _MAJOR_CAREER_STATUS_RE.search(body) is not None:
        return None
    parsed = _parse_other_company_line(body)
    if parsed is None:
        return None
    organization_name, position = parsed
    unit_suffix = _MAJOR_CAREER_UNIT_SUFFIX_RE.fullmatch(organization_name)
    if unit_suffix is not None:
        base_organization = _clean_text(unit_suffix.group("org"))
        if (
            not reporting_company_name
            or _organization_key(base_organization)
            != _organization_key(reporting_company_name)
        ):
            return None
        organization_name = base_organization
    if (
        _MAJOR_CAREER_GENERIC_ORG_RE.fullmatch(organization_name) is not None
        or _MAJOR_CAREER_FUSED_WORK_UNIT_RE.fullmatch(organization_name) is not None
        or _MAJOR_CAREER_ORG_NOISE_RE.search(organization_name) is not None
        or re.search(_POSITION_ATOM, organization_name) is not None
        or re.search(r"(?:\s및\s|\s겸\s|[/,;])", organization_name) is not None
        or len(_MAJOR_CAREER_LEGAL_FORM_RE.findall(organization_name)) > 1
        or _is_composite_major_career_org(organization_name)
    ):
        return None
    return organization_name, position


def _has_major_career_org_designator(name: str) -> bool:
    return bool(
        _MAJOR_CAREER_ORG_PREFIX_RE.search(name)
        or _MAJOR_CAREER_ORG_SUFFIX_RE.search(name)
    )


def _is_composite_major_career_org(name: str) -> bool:
    ampersand_parts = re.split(r"\s*&\s*", name)
    if (
        len(ampersand_parts) > 1
        and sum(
            _has_major_career_org_designator(part) for part in ampersand_parts
        )
        > 1
    ):
        return True
    middot_parts = re.split(r"\s*[·ㆍ]\s*", name)
    if len(middot_parts) > 1 and (
        sum(_has_major_career_org_designator(part) for part in middot_parts) > 1
        or (
            _MAJOR_CAREER_LEGAL_FORM_RE.match(middot_parts[0]) is not None
            and all(re.search(r"[가-힣]", part) for part in middot_parts)
        )
    ):
        return True
    for connector in re.finditer(r"(?:와|과)\s+", name):
        left = name[: connector.start()].strip()
        right = name[connector.end() :].strip()
        if left and right and (
            _has_major_career_org_designator(left)
            or _MAJOR_CAREER_LEGAL_FORM_RE.match(right) is not None
        ):
            return True
    return False


def _proposer_entity(raw_name: str) -> tuple[str, str] | None:
    name = re.sub(
        r"\s*외\s*\d+\s*(?:인|명)\s*$",
        "",
        _clean_text(raw_name),
    )
    name = name.strip("-_:： ")
    if re.match(r"^후보자?(?:\s|$)", name) or _is_empty_name(name):
        return None
    proposer_core = re.sub(r"^(?:\(주\)|㈜|주식회사)\s*", "", name)
    proposer_core = re.sub(r"\s*\(주\)$", "", proposer_core)
    compact_core = re.sub(r"\s+", "", proposer_core)
    if (
        _PROPOSER_DESCRIPTION_RE.search(name) is not None
        or _PROPOSER_ROLE_PREFIX_RE.match(name) is not None
        or _PROPOSER_DESCRIPTION_RE.search(proposer_core) is not None
        or _PROPOSER_ROLE_PREFIX_RE.match(proposer_core) is not None
        or _PROPOSER_COMPACT_DESCRIPTION_RE.fullmatch(compact_core) is not None
        or _PROPOSER_COMPACT_ROLE_RE.fullmatch(compact_core) is not None
    ):
        return None
    if _CORPORATE_MARKERS.search(name):
        return "organization", name
    if (
        _candidate_surface(name) == name
        and _PERSON_NAME_RE.fullmatch(name)
        and _is_candidate_name(name)
    ):
        return "person", name
    return None


def _proposers(record: dict[str, Any]) -> list[tuple[str, str]]:
    text = _clean_text(record.get("title"))
    proposers: list[tuple[str, str]] = []

    def add(raw_name: str) -> None:
        proposer = _proposer_entity(raw_name)
        if proposer is not None and proposer not in proposers:
            proposers.append(proposer)

    for match in re.finditer(
        r"\(\s*주주\s*제안\s*[-_:：]\s*"
        r"(?P<names>(?:(?:\(주\))|[^)])+)\)",
        text,
    ):
        for name in re.split(
            r"\s*(?:,|·|ㆍ|/|\s+및\s+)\s*",
            match.group("names"),
        ):
            add(name)

    patterns = (
        re.compile(
            rf"\(\s*(?P<name>{_PERSON_NAME_RE.pattern})"
            r"(?:\s*외\s*\d+\s*(?:인|명))?\s+주주\s+제안\s*\)"
        ),
        re.compile(
            rf"\(\s*(?P<name>{_PERSON_NAME_RE.pattern})"
            r"\s*외\s*\d+\s*(?:인|명)\s*주주\s*제안\s*\)"
        ),
    )
    for pattern in patterns:
        for match in pattern.finditer(text):
            add(match.group("name"))
    return proposers


def _correction_proposer_statements(
    source: dict[str, Any],
) -> list[tuple[tuple[str, str], str, list[str]]]:
    if source.get("source_type") != "correction_after_reference_note":
        return []
    lines = source.get("lines")
    if not isinstance(lines, list):
        return []
    statements: list[tuple[tuple[str, str], str, list[str]]] = []
    for raw_line in lines:
        match = _CORRECTION_PROPOSER_RE.fullmatch(_clean_text(raw_line))
        if match is None:
            continue
        proposer = _proposer_entity(match.group("proposer"))
        office_type = _office_type(match.group("office"))
        if proposer is None or office_type is None:
            continue
        candidate_names = [
            _clean_text(name)
            for name in re.split(
                r"\s*(?:,|·|ㆍ|/|\s+및\s+)\s*",
                match.group("candidates"),
            )
            if _clean_text(name)
        ]
        if (
            not candidate_names
            or any(
                _PERSON_NAME_RE.fullmatch(name) is None
                or not _is_candidate_name(name)
                for name in candidate_names
            )
            or (
                match.group("count") is not None
                and int(match.group("count")) != len(candidate_names)
            )
        ):
            continue
        statements.append(
            (proposer, office_type, list(dict.fromkeys(candidate_names)))
        )
    return statements


def _stock_option_names(record: dict[str, Any]) -> list[str]:
    title = _clean_text(record.get("title"))
    if "주식매수선택권" not in title or "부여" not in title:
        return []
    names: list[str] = []

    def append_name(value: str) -> None:
        name = _clean_text(value)
        if (
            _PERSON_NAME_RE.fullmatch(name)
            and not _is_empty_name(name)
            and not any(_person_key(existing) == _person_key(name) for existing in names)
        ):
            names.append(name)

    explicit = _clean_text(record.get("candidate"))
    for part in re.split(r"\s*(?:,|·|ㆍ|/| 및 )\s*", explicit):
        append_name(part)
    for match in re.finditer(
        rf"(?:부여\s*대상자|대상자)\s*[:：\-]?\s*(?P<name>{_PERSON_NAME_RE.pattern})",
        title,
    ):
        append_name(match.group("name"))
    return names


def extract_semantic_contract(
    *,
    agenda_records: list[dict[str, Any]],
    elections: list[dict[str, Any]],
    disclosure_phase: str,
    explicit_mentions: list[dict[str, Any]] | None = None,
    correction_sources: list[dict[str, Any]] | None = None,
    reporting_company_name: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build document-local semantic records without assigning global graph IDs."""
    registry = _Registry()

    election_identity: dict[tuple[str, str], list[tuple[str, str]]] = {}
    election_birth_months_by_name: dict[str, set[str]] = {}
    election_offices_by_name: dict[str, list[str]] = {}
    for election in elections:
        name = _clean_text(election.get("name"))
        birth_month = _clean_text(election.get("birth_month"))
        office_type = _clean_text(election.get("section_type"))
        if not name or not office_type:
            continue
        identity = (birth_month, office_type)
        identities = election_identity.setdefault((_person_key(name), office_type), [])
        if identity not in identities:
            identities.append(identity)
        if birth_month:
            election_birth_months_by_name.setdefault(_person_key(name), set()).add(
                birth_month
            )
        name_offices = election_offices_by_name.setdefault(_person_key(name), [])
        if office_type not in name_offices:
            name_offices.append(office_type)

    def agenda_person(
        name: str,
        office_types: list[str] | None,
        evidence: dict[str, Any],
    ) -> str | None:
        birth_months = {
            identity[0]
            for office_type in office_types or []
            for identity in election_identity.get((_person_key(name), office_type), [])
            if identity[0]
        }
        if len(birth_months) == 1:
            birth_month = next(iter(birth_months))
            return registry.person(name, birth_month, evidence)
        if len(birth_months) > 1:
            return None
        return registry.person(name, "", evidence)

    def appointment_person(
        name: str,
        evidence: dict[str, Any],
    ) -> str | None:
        birth_months = election_birth_months_by_name.get(_person_key(name), set())
        if len(birth_months) == 1:
            return registry.person(name, next(iter(birth_months)), evidence)
        if len(birth_months) > 1:
            return None
        return registry.person(name, "", evidence)

    def election_person(
        name: str,
        birth_month: str,
        evidence: dict[str, Any],
    ) -> str | None:
        if birth_month:
            return registry.person(name, birth_month, evidence)
        return appointment_person(name, evidence)

    unambiguous_agenda_by_election_id: dict[int, dict[str, Any]] = {}
    for office_type in {str(election.get("section_type") or "") for election in elections}:
        if not office_type:
            continue
        role_elections = [
            election
            for election in elections
            if election.get("section_type") == office_type
        ]
        unnamed_role_agendas = [
            agenda
            for agenda in agenda_records
            if _office_types(_clean_text(agenda.get("title"))) == [office_type]
            and re.search(r"선임|재선임", _clean_text(agenda.get("title")))
            and "해임" not in _clean_text(agenda.get("title"))
            and not _candidate_names(agenda)
        ]
        if len(role_elections) == 1 and len(unnamed_role_agendas) == 1:
            unambiguous_agenda_by_election_id[id(role_elections[0])] = unnamed_role_agendas[0]

    agenda_by_election_id: dict[int, dict[str, Any]] = {}
    election_names_by_agenda_id: dict[int, list[str]] = {}
    for election in elections:
        named_agendas = _agendas_for_election(election, agenda_records)
        agenda = named_agendas[0] if len(named_agendas) == 1 else None
        if not named_agendas:
            agenda = unambiguous_agenda_by_election_id.get(id(election))
        if agenda is None:
            continue
        agenda_by_election_id[id(election)] = agenda
        election_name, _ = _person_name_and_aliases(_clean_text(election.get("name")))
        agenda_names = election_names_by_agenda_id.setdefault(id(agenda), [])
        if election_name and election_name not in agenda_names:
            agenda_names.append(election_name)

    elections_by_name_and_office: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for election in elections:
        key = (
            _person_key(_clean_text(election.get("name"))),
            _clean_text(election.get("section_type")),
        )
        if all(key):
            elections_by_name_and_office.setdefault(key, []).append(election)
    appointment_agendas_by_office: dict[str, list[dict[str, Any]]] = {}
    for office_type in {key[1] for key in elections_by_name_and_office}:
        appointment_agendas_by_office[office_type] = [
            agenda
            for agenda in agenda_records
            if _office_types(_clean_text(agenda.get("title"))) == [office_type]
            and re.search(r"선임|재선임", _clean_text(agenda.get("title")))
            and "해임" not in _clean_text(agenda.get("title"))
        ]

    for agenda in agenda_records:
        agenda_ref = _clean_text(agenda.get("agenda_ref"))
        if not agenda_ref:
            continue
        agenda_evidence = _record_evidence(agenda)
        registry.relation("@meeting", agenda_ref, "includes", {}, agenda_evidence)

        title = _clean_text(agenda.get("title"))
        office_types = _office_types(title)
        outcome = _clean_text(agenda.get("status")) or None
        termination_subjects = _termination_subjects(agenda)
        for name, action, subject_offices in termination_subjects:
            person_ref = agenda_person(
                name,
                list(subject_offices),
                _record_evidence(agenda, field="회의목적사항"),
            )
            if person_ref is None:
                continue
            subject_attributes = {
                "action": action,
                "office_types": list(subject_offices),
                "disclosure_phase": disclosure_phase,
                "outcome": outcome,
            }
            registry.relation(
                person_ref,
                agenda_ref,
                "subject_of",
                subject_attributes,
                agenda_evidence,
            )
            if disclosure_phase != "result" or outcome != "passed":
                continue
            relationship_type = (
                "removed_from" if action == "removal" else "resigned_from"
            )
            for office_type in subject_offices:
                registry.relation(
                    person_ref,
                    "@reporting_company",
                    relationship_type,
                    {
                        "office_type": office_type,
                        "disclosure_phase": disclosure_phase,
                        "outcome": outcome,
                    },
                    agenda_evidence,
                )
        is_termination_agenda = re.search(r"(?:해임|사임)(?:의)?\s*건", title) is not None
        candidate_names = (
            [] if termination_subjects or is_termination_agenda else _candidate_names(agenda)
        )
        candidate_context = list(candidate_names)
        for election_name in election_names_by_agenda_id.get(id(agenda), []):
            if election_name not in candidate_context:
                candidate_context.append(election_name)
        if office_types and re.search(r"선임|재선임|후보", title):
            for name in candidate_names:
                candidate_offices = list(office_types)
                if len(candidate_names) > 1 and len(office_types) > 1:
                    detailed_offices = election_offices_by_name.get(
                        _person_key(name),
                        [],
                    )
                    candidate_offices = [
                        office_type
                        for office_type in office_types
                        if office_type in detailed_offices
                    ]
                candidate_withdrew = _candidate_withdrew(
                    agenda,
                    name,
                    candidate_context,
                )
                person_ref = appointment_person(
                    name,
                    _record_evidence(agenda, field="후보자"),
                )
                if person_ref is None:
                    continue
                for office_type in candidate_offices:
                    attributes = {
                        "office_type": office_type,
                        "disclosure_phase": disclosure_phase,
                        "outcome": outcome,
                        **(
                            {"candidate_status": "withdrawn"}
                            if candidate_withdrew
                            else {}
                        ),
                    }
                    registry.relation(
                        person_ref,
                        "@reporting_company",
                        "candidate_for",
                        attributes,
                        agenda_evidence,
                    )
                    if (
                        disclosure_phase == "result"
                        and outcome == "passed"
                        and not candidate_withdrew
                    ):
                        registry.relation(
                            person_ref,
                            "@reporting_company",
                            "elected_as",
                            attributes,
                            agenda_evidence,
                        )
                registry.relation(
                    person_ref,
                    agenda_ref,
                    "subject_of",
                    {
                        "action": "appointment",
                        "office_types": list(candidate_offices),
                        "disclosure_phase": disclosure_phase,
                        "outcome": outcome,
                        **(
                            {"candidate_status": "withdrawn"}
                            if candidate_withdrew
                            else {}
                        ),
                    },
                    agenda_evidence,
                )

        elif candidate_names:
            for name in candidate_names:
                person_ref = appointment_person(
                    name,
                    _record_evidence(agenda, field="후보자"),
                )
                if person_ref is not None:
                    registry.relation(
                        person_ref,
                        agenda_ref,
                        "subject_of",
                        {
                            "action": "agenda_candidate",
                            "disclosure_phase": disclosure_phase,
                            "outcome": outcome,
                        },
                        agenda_evidence,
                    )

        for proposer in _proposers(agenda):
            entity_type, name = proposer
            proposer_ref = (
                registry.organization(name, _record_evidence(agenda, field="제안자"))
                if entity_type == "organization"
                else registry.person(name, "", _record_evidence(agenda, field="제안자"))
            )
            if proposer_ref is not None:
                registry.relation(
                    proposer_ref,
                    agenda_ref,
                    "proposed",
                    {"disclosure_phase": disclosure_phase},
                    agenda_evidence,
                )

        for name in _stock_option_names(agenda):
            person_ref = registry.person(name, "", _record_evidence(agenda, field="부여대상자"))
            if person_ref is None:
                continue
            registry.relation(
                person_ref,
                agenda_ref,
                "subject_of",
                {
                    "action": "stock_option_grant",
                    "disclosure_phase": disclosure_phase,
                    "outcome": outcome,
                },
                agenda_evidence,
            )
            if disclosure_phase == "result" and outcome == "passed":
                registry.relation(
                    person_ref,
                    "@reporting_company",
                    "option_granted_by",
                    {"outcome": outcome},
                    agenda_evidence,
                )

    for election in elections:
        evidence = _record_evidence(election, field="성명")
        person_ref = election_person(
            _clean_text(election.get("name")),
            _clean_text(election.get("birth_month")),
            evidence,
        )
        if person_ref is None:
            continue
        office_type = _clean_text(election.get("section_type"))
        agenda = agenda_by_election_id.get(id(election))
        outcome = _clean_text(agenda.get("status")) if agenda is not None else ""
        candidate_context = _candidate_names(agenda) if agenda is not None else []
        if agenda is not None:
            for election_name in election_names_by_agenda_id.get(id(agenda), []):
                if election_name not in candidate_context:
                    candidate_context.append(election_name)
        candidate_withdrew = bool(
            agenda is not None
            and _candidate_withdrew(
                agenda,
                _clean_text(election.get("name")),
                candidate_context,
            )
        )
        attributes = {
            "office_type": office_type,
            "disclosure_phase": disclosure_phase,
            "outcome": outcome or None,
            "term": _clean_text(election.get("term")) or None,
            "appointment_type": _clean_text(election.get("is_new")) or None,
            **(
                {"candidate_status": "withdrawn"}
                if candidate_withdrew
                else {}
            ),
        }
        registry.relation(
            person_ref,
            "@reporting_company",
            "candidate_for",
            attributes,
            _record_evidence(agenda) if agenda is not None else evidence,
        )
        if agenda is not None:
            registry.relation(
                person_ref,
                _clean_text(agenda.get("agenda_ref")),
                "subject_of",
                {"action": "appointment", **attributes},
                _record_evidence(agenda),
            )
        if (
            disclosure_phase == "result"
            and outcome == "passed"
            and not candidate_withdrew
        ):
            registry.relation(
                person_ref,
                "@reporting_company",
                "elected_as",
                attributes,
                _record_evidence(agenda),
            )

        other_company_lines = election.get("other_company_lines")
        if not isinstance(other_company_lines, list):
            other_company_lines = []
        other_company_roles = _parse_other_company_lines(
            [str(line) for line in other_company_lines]
        )
        other_company_org_keys = {
            _organization_key(organization_name)
            for organization_name, _ in other_company_roles
        }
        for organization_name, position in other_company_roles:
            organization_ref = registry.organization(
                organization_name,
                _evidence(election.get("other_company_evidence"), field="other_company"),
            )
            if organization_ref is None:
                continue
            registry.relation(
                person_ref,
                organization_ref,
                "serves_at",
                {"position": position, "is_current": True},
                _evidence(election.get("other_company_evidence"), field="other_company"),
            )

        major_career_lines = election.get("major_career_lines")
        if not isinstance(major_career_lines, list):
            major_career_lines = []
        for raw_line in major_career_lines:
            parsed_career = _parse_major_career_line(
                str(raw_line),
                reporting_company_name,
            )
            if parsed_career is None:
                continue
            organization_name, position = parsed_career
            organization_key = _organization_key(organization_name)
            if organization_key in other_company_org_keys:
                continue
            is_reporting_company = bool(
                reporting_company_name
                and organization_key == _organization_key(reporting_company_name)
            )
            if (
                not is_reporting_company
                and not _has_major_career_org_designator(organization_name)
            ):
                continue
            evidence = _evidence(
                election.get("major_career_evidence"),
                field="주요경력(현직포함)",
            )
            evidence["raw_text"] = _clean_text(raw_line)
            if is_reporting_company:
                target_ref = "@reporting_company"
            else:
                target_ref = registry.organization(organization_name, evidence) or ""
            if not target_ref:
                continue
            registry.relation(
                person_ref,
                target_ref,
                "serves_at",
                {"position": position, "is_current": True},
                evidence,
            )

    for source in correction_sources or []:
        evidence = _evidence(source.get("evidence"), field="정정후")
        for proposer, office_type, candidate_names in _correction_proposer_statements(
            source
        ):
            target_agendas: list[dict[str, Any]] = []
            for candidate_name in candidate_names:
                candidate_elections = elections_by_name_and_office.get(
                    (_person_key(candidate_name), office_type),
                    [],
                )
                if not candidate_elections:
                    continue
                compatible_agendas = [
                    agenda
                    for agenda in appointment_agendas_by_office.get(office_type, [])
                    if (
                        not _candidate_names(agenda)
                        or _person_key(candidate_name)
                        in {
                            _person_key(name)
                            for name in _candidate_names(agenda)
                        }
                    )
                ]
                if (
                    len(compatible_agendas) == 1
                    and compatible_agendas[0] not in target_agendas
                ):
                    target_agendas.append(compatible_agendas[0])
            if not target_agendas:
                continue
            entity_type, proposer_name = proposer
            proposer_ref = (
                registry.organization(proposer_name, evidence)
                if entity_type == "organization"
                else registry.person(proposer_name, "", evidence)
            )
            if proposer_ref is None:
                continue
            for agenda in target_agendas:
                agenda_ref = _clean_text(agenda.get("agenda_ref"))
                if agenda_ref:
                    registry.relation(
                        proposer_ref,
                        agenda_ref,
                        "proposed",
                        {"disclosure_phase": disclosure_phase},
                        evidence,
                    )

    fixed_mention_targets = {
        "external_auditor_of": "@reporting_company",
        "electronic_voting_manager_for": "@meeting",
        "electronic_voting_system_provider_for": "@meeting",
        "transferor_of": "@reporting_company",
        "transferee_of": "@reporting_company",
        "proposed_allottee_of": "@reporting_company",
        "merger_target_of": "@reporting_company",
        "shareholder_of": "@reporting_company",
    }
    agenda_refs = {
        _clean_text(agenda.get("agenda_ref"))
        for agenda in agenda_records
        if _clean_text(agenda.get("agenda_ref"))
    }
    agenda_target_types = {"acquisition_target_of", "divestment_target_of"}
    for mention in explicit_mentions or []:
        relationship_type = _clean_text(mention.get("relationship_type"))
        target_ref = _clean_text(mention.get("target_ref"))
        expected_target = fixed_mention_targets.get(relationship_type)
        if relationship_type in agenda_target_types:
            expected_target = target_ref if target_ref in agenda_refs else None
        if expected_target is None or target_ref != expected_target:
            continue
        evidence = _evidence(mention.get("evidence"))
        name = _clean_text(mention.get("name"))
        entity_type = _clean_text(mention.get("entity_type")).lower()
        if entity_type == "person":
            entity_ref = registry.person(name, "", evidence)
        elif entity_type == "organization":
            entity_ref = registry.organization(
                name,
                evidence,
                {"aliases": mention.get("aliases", [])}
                if mention.get("aliases")
                else None,
            )
        else:
            entity_ref = None
        if entity_ref is None:
            continue
        attributes = mention.get("attributes")
        registry.relation(
            entity_ref,
            expected_target,
            relationship_type,
            dict(attributes) if isinstance(attributes, dict) else {},
            evidence,
        )

    return registry.entities, registry.relationships
