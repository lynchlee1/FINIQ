"""KIND search POST payload building helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

DisclosureTypeGroupKey = str | int
DisclosureTypeGroupValue = str | Sequence[object]
KindSearchFormData = list[tuple[str, str]]

_DEFAULT_DISCLOSURE_GROUP_SUFFIXES = (
    "01",
    "02",
    "03",
    "04",
    "05",
    "06",
    "07",
    "08",
    "09",
    "10",
    "11",
    "13",
    "14",
    "20",
)

_DISCLOSURE_GROUP_FIELD_PREFIXES = (
    "disclosureTypeArr",
    "disclosureType",
    "pDisclosureType",
)

_STABLE_KIND_SEARCH_DEFAULTS = {
    "method": "searchDetailsSub",
    "orderMode": "1",
    "orderStat": "D",
    "forward": "details_sub",
}

_STABLE_KIND_SEARCH_EMPTY_FIELDS = (
    "currentPageSize",
    "pageIndex",
    "searchCodeType",
    "repIsuSrtCd",
    "allRepIsuSrtCd",
    "oldSearchCorpName",
    "disclosureType",
    "disTypevalue",
    "reportNm",
    "reportCd",
    "searchCorpName",
    "business",
    "marketType",
    "settlementMonth",
    "securities",
    "submitOblgNm",
    "enterprise",
    "fromDate",
    "toDate",
    "reportNmTemp",
    "reportNmPop",
)


def build_default_kind_search_filters() -> dict[str, str]:
    """KIND 기본 검색 payload skeleton을 만든다."""
    request_data = dict(_STABLE_KIND_SEARCH_DEFAULTS)
    request_data.update({field_name: "" for field_name in _STABLE_KIND_SEARCH_EMPTY_FIELDS})
    for suffix in _DEFAULT_DISCLOSURE_GROUP_SUFFIXES:
        request_data[f"disclosureType{suffix}"] = ""
        request_data[f"pDisclosureType{suffix}"] = ""
    return request_data


def _is_repeated_form_value(value: object) -> bool:
    """입력이 반복 전송해야 하는 form 값인지 판별한다."""
    return isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray)


def _normalize_form_value(value: object | None) -> str:
    """form에 넣기 전에 값을 string으로 normalize한다."""
    return "" if value is None else str(value)


def _iter_search_filter_items(
    search_filters: Mapping[str, object] | Sequence[tuple[str, object]] | None,
) -> KindSearchFormData:
    """raw 검색 필터를 순서 있는 `(key, value)` list로 flatten한다.

    sequence 값은 같은 키의 반복 field로 풀어주고,
    나머지 값은 KIND request에 넣기 쉬운 string 값으로 맞춘다.
    """
    if not search_filters:
        return []

    if isinstance(search_filters, Mapping):
        raw_items = search_filters.items()
    else:
        raw_items = search_filters

    normalized_items: KindSearchFormData = []
    for key, value in raw_items:
        normalized_key = str(key)
        if _is_repeated_form_value(value):
            normalized_items.extend(
                (normalized_key, _normalize_form_value(item))
                for item in value
            )
            continue
        normalized_items.append((normalized_key, _normalize_form_value(value)))
    return normalized_items


def _group_form_items(form_items: Sequence[tuple[str, str]]) -> dict[str, list[str]]:
    """같은 key를 가진 form item들을 key별 list로 묶는다."""
    grouped_items: dict[str, list[str]] = {}
    for key, value in form_items:
        grouped_items.setdefault(key, []).append(value)
    return grouped_items


def _ordered_form_keys(form_items: Sequence[tuple[str, str]]) -> list[str]:
    """form item의 key 등장 순서를 중복 없이 보존한다."""
    return list(dict.fromkeys(key for key, _ in form_items))


def _normalize_disclosure_type_group_key(group_key: DisclosureTypeGroupKey) -> str:
    """공시유형 그룹 key를 KIND suffix 형식으로 normalize한다."""
    normalized_key = str(group_key).strip()
    if not normalized_key:
        raise ValueError("disclosure type group key must not be empty")
    if normalized_key.isdigit():
        return normalized_key.zfill(2)
    return normalized_key


def _normalize_disclosure_type_group_value(group_value: DisclosureTypeGroupValue) -> list[str]:
    """공시유형 code 입력을 비어 있지 않은 code list로 정리한다."""
    if isinstance(group_value, str):
        raw_codes = group_value.split("|")
    elif isinstance(group_value, Sequence):
        raw_codes = [str(code) for code in group_value]
    else:
        raw_codes = [str(group_value)]
    return [code.strip() for code in raw_codes if str(code).strip()]


def _normalize_disclosure_codes(values: Sequence[str]) -> list[str]:
    """여러 형식으로 들어온 공시 code를 하나의 code list로 합친다."""
    normalized_codes: list[str] = []
    for value in values:
        normalized_codes.extend(_normalize_disclosure_type_group_value(value))
    return normalized_codes


def _split_disclosure_group_field_name(field_name: str) -> tuple[str, str] | None:
    """공시유형 관련 field name을 prefix와 suffix로 분리한다."""
    for prefix in _DISCLOSURE_GROUP_FIELD_PREFIXES:
        if not field_name.startswith(prefix):
            continue
        suffix = field_name.removeprefix(prefix)
        if suffix:
            return prefix, suffix
    return None


@dataclass(slots=True)
class KindDisclosureGroup:
    """공시유형 그룹 1개를 표현하는 value object다."""

    suffix: str
    codes: list[str]

    @classmethod
    def from_raw(
        cls,
        group_key: DisclosureTypeGroupKey,
        group_value: DisclosureTypeGroupValue,
    ) -> KindDisclosureGroup:
        """외부 입력을 normalize해 공시유형 그룹 object를 만든다."""
        return cls(
            suffix=_normalize_disclosure_type_group_key(group_key),
            codes=_normalize_disclosure_type_group_value(group_value),
        )

    @property
    def serialized_codes(self) -> str:
        """KIND가 기대하는 trailing `|` 형식으로 serialize한다."""
        joined = "|".join(self.codes)
        return f"{joined}|" if joined else ""

    @property
    def disclosure_type_field(self) -> str:
        """현재 공시유형 field name을 만든다."""
        return f"disclosureType{self.suffix}"

    @property
    def previous_disclosure_type_field(self) -> str:
        """이전 공시유형 field name을 만든다."""
        return f"pDisclosureType{self.suffix}"

    @property
    def repeated_field(self) -> str:
        """반복 전송용 공시유형 array field name을 만든다."""
        return f"disclosureTypeArr{self.suffix}"


def _pop_disclosure_group_overrides(
    grouped_raw_filters: dict[str, list[str]],
) -> list[KindDisclosureGroup]:
    """raw override에서 공시유형 3종 세트를 추출해 group object로 바꾼다.

    `disclosureTypeXX`, `pDisclosureTypeXX`, `disclosureTypeArrXX`는
    서로 독립적으로 남겨두지 않고 같은 suffix 기준으로 다시 묶는다.
    """
    grouped_fields_by_suffix: dict[str, dict[str, list[str]]] = {}
    disclosure_group_keys: list[str] = []

    for key, values in grouped_raw_filters.items():
        group_field = _split_disclosure_group_field_name(key)
        if group_field is None:
            continue
        prefix, suffix = group_field
        grouped_fields_by_suffix.setdefault(suffix, {})[prefix] = values
        disclosure_group_keys.append(key)

    for key in disclosure_group_keys:
        grouped_raw_filters.pop(key, None)

    disclosure_groups: list[KindDisclosureGroup] = []
    for suffix, grouped_fields in grouped_fields_by_suffix.items():
        raw_codes = (
            grouped_fields.get("disclosureTypeArr")
            or grouped_fields.get("disclosureType")
            or grouped_fields.get("pDisclosureType")
            or []
        )
        disclosure_groups.append(
            KindDisclosureGroup(
                suffix=suffix,
                codes=_normalize_disclosure_codes(raw_codes),
            )
        )
    return disclosure_groups


@dataclass(slots=True)
class KindSearchPayload:
    """KIND 검색 POST payload를 조립하는 state object다."""

    single_fields: dict[str, str] = field(default_factory=build_default_kind_search_filters)
    repeated_fields: KindSearchFormData = field(default_factory=list)

    def set_field(self, key: str, value: object | None) -> None:
        """단일 값 field를 string 값으로 기록한다."""
        self.single_fields[str(key)] = _normalize_form_value(value)

    def set_optional_toggle(
        self,
        key: str,
        enabled: bool | None,
        *,
        true_value: str,
    ) -> None:
        """선택 toggle field를 omitted / empty / concrete 상태로 반영한다.

        `None`이면 아예 보내지지 않은 상태를 유지하고,
        `False`면 빈 string으로 보내며,
        `True`면 KIND가 기대하는 실제 값을 넣는다.
        """
        if enabled is None:
            return
        self.single_fields[key] = true_value if enabled else ""

    def replace_repeated_field(self, key: str, values: Sequence[str]) -> None:
        """같은 key를 가진 반복 field들을 새 값 list로 교체한다."""
        normalized_key = str(key)
        filtered_fields = [
            (field_key, field_value)
            for field_key, field_value in self.repeated_fields
            if field_key != normalized_key
        ]
        filtered_fields.extend((normalized_key, value) for value in values)
        self.repeated_fields = filtered_fields

    def apply_disclosure_group(self, disclosure_group: KindDisclosureGroup) -> None:
        """공시유형 group 1개를 3종 field set로 payload에 반영한다."""
        self.set_field(disclosure_group.disclosure_type_field, disclosure_group.serialized_codes)
        self.set_field(
            disclosure_group.previous_disclosure_type_field,
            disclosure_group.serialized_codes,
        )
        self.replace_repeated_field(disclosure_group.repeated_field, disclosure_group.codes)

    def apply_raw_overrides(
        self,
        search_filters: Mapping[str, object] | Sequence[tuple[str, object]] | None,
    ) -> None:
        """raw override를 마지막에 적용해 payload를 덮어쓴다.

        일반 field는 단일 값과 반복 값을 구분해서 교체하고,
        공시유형 관련 field는 부분 수정이 들어와도 다시 3종 set로 맞춘다.
        """
        grouped_raw_filters = _group_form_items(_iter_search_filter_items(search_filters))
        if not grouped_raw_filters:
            return

        disclosure_group_overrides = _pop_disclosure_group_overrides(grouped_raw_filters)

        grouped_repeated_fields = _group_form_items(self.repeated_fields)
        repeated_field_order = _ordered_form_keys(self.repeated_fields)

        for key, values in grouped_raw_filters.items():
            self.single_fields.pop(key, None)
            grouped_repeated_fields.pop(key, None)
            if len(values) == 1:
                self.single_fields[key] = values[0]
                continue
            grouped_repeated_fields[key] = values
            if key not in repeated_field_order:
                repeated_field_order.append(key)

        self.repeated_fields = [
            (key, value)
            for key in repeated_field_order
            for value in grouped_repeated_fields.get(key, [])
        ]

        for disclosure_group in disclosure_group_overrides:
            self.apply_disclosure_group(disclosure_group)

    def to_form_data(self) -> KindSearchFormData:
        """최종 payload를 request 전송용 form data로 serialize한다."""
        return [*self.single_fields.items(), *self.repeated_fields]


def build_search_form(
    *,
    page_number: int,
    start_date: str,
    end_date: str,
    page_size: int = 100,
    search_filters: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
    disclosure_type_groups: Mapping[DisclosureTypeGroupKey, DisclosureTypeGroupValue] | None = None,
    last_report_only: bool | None = None,
    include_previous_disclosures: bool | None = None,
) -> KindSearchFormData:
    """KIND 검색 request용 최종 form data를 만든다.

    기본 skeleton을 깔고 structured 옵션을 먼저 반영한 뒤,
    raw override를 마지막에 적용해서 브라우저 request 재현 가능성을 남긴다.
    """
    payload = KindSearchPayload()

    for group_key, group_value in (disclosure_type_groups or {}).items():
        payload.apply_disclosure_group(KindDisclosureGroup.from_raw(group_key, group_value))

    payload.set_optional_toggle("lastReport", last_report_only, true_value="T")
    payload.set_optional_toggle(
        "bfrDsclsType",
        include_previous_disclosures,
        true_value="on",
    )
    payload.apply_raw_overrides(search_filters)
    payload.set_field("fromDate", start_date)
    payload.set_field("toDate", end_date)
    payload.set_field("pageIndex", page_number)
    payload.set_field("currentPageSize", page_size)
    return payload.to_form_data()


__all__ = [
    "DisclosureTypeGroupKey",
    "DisclosureTypeGroupValue",
    "KindDisclosureGroup",
    "KindSearchFormData",
    "build_default_kind_search_filters",
    "build_search_form",
]
