# HTML 파서 공통 데이터 구조

- 공통 parsing 동작은
[HTML 파서 공통 로직 규칙](./common-html-parser-logic-rules.md)을 따른다.
- 상태, 경고, 실행 오류 처리는
[HTML 파서 공통 예외 처리 규칙](./common-html-parser-exception-handling.md)을 따른다.

- 이 문서에서 `record`는 HTML 파일 한 건을 parsing한 결과이고,
`payload`는 여러 record와 warning, error를 한 파일에 모은 최종 결과를 뜻한다.

### 공통 table 구조
1. **raw_tables**
- `raw_tables`는 HTML에 있는 모든 table을 원문 순서대로 담은 목록이다.
- table 하나는 아래 필드를 가진다.

| 필드 | 값 | 설명 |
|---|---|---|
| `index` | 0부터 시작하는 정수 | HTML 안에서 몇 번째 table인지 표시한다. |
| `chapter_title` | 문자열 | table보다 앞에 있는 가장 가까운 section 제목이다. 찾지 못하면 빈 문자열이다. |
| `cells` | 2차원 목록 | span을 펼친 cell의 text와 위치 정보이다. |
| `positional_rows` | 2차원 문자열 목록 | 실제 column 위치와 반복값을 보존한 row이다. |
| `logical_rows` | 2차원 문자열 목록 | label 검색이 쉽도록 빈값과 연속 중복값을 줄인 row이다. |

- `chapter_title`은 앞쪽의 `h1`부터 `h6`까지의 제목이나 `CORRECTION`, `SECTION-`, `COVER-TITLE` class를 가진 `p` 중 가장 가까운 하나에서 가져온다.
  - 의도 : table의 원래 순서와 주변 제목을 함께 남겨 원문에서 어느 부분인지 확인할 수 있게 한다.
2. **cells**
- `cells`는 row와 column으로 이루어진 격자이다. `rowspan`과 `colspan`으로 합쳐진 원문 cell은 차지하는 각 위치에 같은 text를 가진 slot으로 펼쳐진다.
- text가 하나도 없는 row는 `cells`, `positional_rows`, `logical_rows`에 넣지 않는다.
- slot 하나는 아래 필드를 가진다.

| 필드 | 값 | 설명 |
|---|---|---|
| `text` | 정리된 문자열 | 원문 cell 안의 모든 text를 합치고 연속 공백을 하나로 줄인 값 |
| `row_index` | 0부터 시작하는 정수 | 원문 table의 `tr` 순서 |
| `col_index` | 0부터 시작하는 정수 | span을 펼친 뒤 이 slot이 놓인 column |
| `source_row` | 0부터 시작하는 정수 | 원문 cell이 실제로 선언된 `tr` 순서 |
| `source_col` | 0부터 시작하는 정수 | 해당 `tr` 안에서 원문 cell이 실제로 선언된 순서 |
| `rowspan` | 양의 정수 | 원문 cell의 `rowspan`, 속성이 없으면 1 |
| `colspan` | 양의 정수 | 원문 cell의 `colspan`, 속성이 없으면 1 |
| `from_span` | `true` 또는 `false` | 앞 row의 `rowspan`에서 이어진 slot이면 `true` |

- `colspan` 때문에 같은 row 안에 복사된 slot은 앞 row에서 내려온 것이 아니므로 `from_span`이 `false`이다.
  - 의도 : 화면에 보이는 위치와 실제 원문 cell의 위치를 둘 다 확인할 수 있게 한다.
3. **positional_rows**
- `positional_rows`는 `cells`에서 text만 꺼낸 목록이다.
- 빈 문자열, `rowspan`·`colspan`으로 반복된 text, 실제 column 순서를 그대로 유지한다.
- 예를 들어 위치가 `['구분', '', '금액']`이면 가운데 빈 문자열도 남는다.
  - 의도 : header에서 찾은 column 번호로 data row의 같은 column을 정확히 읽게 한다.
4. **logical_rows**
- `logical_rows`는 각 row에서 빈 문자열을 제거하고 바로 이어지는 같은 text를 하나만 남긴 목록이다.
- 예를 들어 `['구분', '구분', '', '금액']`은 `['구분', '금액']`이 된다.
- 떨어져 있는 같은 text는 제거하지 않으며, 정리한 결과가 빈 row이면 목록에서 제외한다.
  - 의도 : span을 펼치며 생긴 반복은 줄이되 원문의 text 순서는 유지해 label을 쉽게 찾게 한다.
5. **raw_rows**
- `raw_rows`는 모든 `raw_tables[].logical_rows`를 table 순서대로 이어 붙인 목록이다.
- table 경계 정보는 `raw_rows`에 남지 않는다. 어느 table의 row인지 알아야 할 때는 `raw_tables`를 사용한다.
  - 의도 : 문서 전체에서 row를 찾는 간단한 경우와 table 경계를 지켜야 하는 경우를 구분한다.

### 공통 base record
1. **record 생성**
- `build_base_record()`는 HTML을 한 번 parsing해 아래 필드를 만든 뒤 개별 parser에 전달한다.

| 필드 | 공통 생성 값 | 역할 |
|---|---|---|
| `correction_families` | 빈 객체 | workflow가 정정공시 묶음을 연결하기 전의 내부 자리 |
| `acpt_no` | 파일명에서 계산한 문자열 | KIND 공시를 구분하는 번호 |
| `source_file` | 입력 HTML 파일의 절대 경로 | 원문 미리보기와 오류 확인에 쓰는 진단 정보 |
| `mode` | 호출한 parser의 mode | 어떤 parser로 만든 record인지 표시 |
| `title` | 빈 문자열 | 외부에서 주입할 제목의 자리 |
| `상장구분` | `null` | 외부 metadata에서 연결할 시장 구분의 자리 |
| `raw_tables` | 모든 HTML table의 공통 구조 | table별 검색과 원문 확인에 사용 |
| `raw_rows` | 모든 `logical_rows`를 합친 목록 | 문서 전체 row 검색에 사용 |

- `acpt_no`는 확장자를 제거한 파일명의 `_` 앞 문자열이 모두 숫자일 때만 그 문자열을 사용한다. 아니면 빈 문자열이다.
- 기본 `title` 추출 함수는 HTML의 `<title>`이나 본문 제목을 읽지 않고 항상 빈 문자열을 반환한다.
  - 의도 : 공통 단계는 파일 식별자와 원문 구조만 만들고, 외부 metadata와 공시별 업무 필드는 정해진 다음 단계에서 연결한다.
2. **개별 parser의 직접 반환값**
- 개별 `parse_*()`는 base record에 공시 유형별 필드, `field_parse_status`, warning 목록 등을 추가해 반환할 수 있다.
- 직접 호출한 결과에는 `source_file`, `raw_tables`, `raw_rows`, 내부 `correction_families`가 남아 있을 수 있다.
  - 의도 : parser 단위 test와 분석에서는 어떤 원문에서 어떤 값을 읽었는지 확인할 수 있게 한다.

### parser 반환값에서 저장 record까지
1. **원문 분석용 필드 제거**
- 웹 parsing workflow는 parser 반환값을 받은 직후 `raw_tables`와 `raw_rows`를 제거한다.
- 최상위와 중첩된 객체·목록에 있는 `rcept_no`도 재귀적으로 모두 제거한다.
- 이 단계에서는 `source_file`과 내부 `correction_families`를 아직 유지한다.
  - 의도 : 저장 대상이 아닌 큰 원문 구조와 KIND workflow에서 사용하지 않는 DART 식별자를 먼저 제외한다.
2. **외부 metadata 연결**
- 내부 필드를 줄인 record에 외부 metadata의 저장 필드와 정정공시 family를 연결한다.
- 외부 필드의 출처는 [외부 메타데이터 병합 규칙](../external-metadata.md)을 따른다.
  - 의도 : 본문 parser 결과와 외부에서 확인한 정보를 서로 다른 단계로 구분한다.
3. **최종 records 변환**
- payload의 최종 `records[]`를 만들 때 `source_file`과 내부 `correction_families`를 제거한다.
- 정정공시 family가 있는 record에는 전체 family 대신 `family_id`, `current_sequence`, `family_member_count`만 추가한다.
- parser가 만든 `field_parse_status`, `field_parse_status_detail`, `parse_warnings`, `weak_warning`, `medium_warning`, `strong_warning`과 공시별 업무 필드는 `records[]`에 그대로 남는다.
- payload 최상위의 `warnings[]`는 record의 warning을 없애고 옮긴 목록이 아니라, 파일 위치·경고 수준·`warning_code`를 더해 별도로 정리한 목록이다.
  - 의도 : 업무 record에는 필요한 값만 남기고 원문 경로와 반복되는 family 전체 정보는 분리한다.

### 정정공시 family 구조
정정공시 family는 하나의 원공시와 그 뒤에 이어진 정정공시들을 한 묶음으로 나타낸 구조이다.

1. **내부 구조**
- metadata 연결 단계에서는 record의 `correction_families`에 아래 구조를 임시로 둔다.

```text
{
  family_id: {
    current_sequence: 현재 record의 순서,
    members: [구성원, ...]
  }
}
```

- `family_id`는 순서상 마지막 구성원의 `acpt_no`이다.
- `current_sequence`와 각 구성원의 `sequence`는 첫 번째가 0인 정수이다.
  - 의도 : 현재 record의 순서와 family 전체 구성원을 저장 전 단계에서 함께 확인할 수 있게 한다.
2. **구성원 필드**
- 최종 `families[family_id].members[]`의 구성원은 아래 필드를 가진다.

| 필드 | 값 |
|---|---|
| `sequence` | family 안의 0부터 시작하는 순서 |
| `acpt_no` | 해당 구성원 record의 KIND 접수번호 |
| `doc_no` | 해당 구성원이 선택한 `mainDoc` 번호 |
| `title` | `mainDoc.text` |
| `disclosed_at` | 외부 record metadata의 공시 시각, 없으면 빈 문자열 |
| `is_correction_report` | `mainDoc` text에 `정정`이 들어 있으면 `true` |

  - 의도 : 각 구성원의 식별자, 순서, 제목, 정정 여부를 같은 형태로 확인하게 한다.
3. **최종 저장 위치**
- family 전체는 payload 최상위 `families`에 family별로 한 번만 저장한다.
- 각 `records[]`에는 아래 세 참조 필드만 저장한다.

| 필드 | 값 |
|---|---|
| `family_id` | 최상위 `families`에서 찾을 key |
| `current_sequence` | 현재 record가 family에서 몇 번째인지 나타내는 0부터 시작하는 순서 |
| `family_member_count` | family의 전체 구성원 수 |

  - 의도 : 같은 구성원 목록을 record마다 반복하지 않고, record에서 필요할 때 최상위 family를 찾아가게 한다.

### 최종 저장 payload
1. **최상위 구조**
- 본 실행 결과는 출력 디렉토리의 `parsed-<mode>.json`에 아래 구조로 저장한다.

| 필드 | 값 |
|---|---|
| `format` | `finiq_disclosure_html_parse_v1` |
| `mode` | 실행한 parser mode |
| `cancelled` | 중지 요청으로 일부만 처리했는지 여부 |
| `filter_settings` | 실행에 사용한 공시 조건과 record 필터 |
| `warning_report_counts` | warning 전체와 수준별 건수 |
| `summary` | 찾은 파일, 저장 record, 실패 파일 수 |
| `families` | 중복을 제거한 정정공시 family 객체 |
| `records` | parser의 업무 필드·상태·경고를 포함한 최종 record 목록 |
| `errors` | 파일별 parsing 실패 목록 |
| `warnings` | record warning에 파일 정보·수준·code를 더해 정리한 별도 목록 |

  - 의도 : record의 원본 warning은 보존하면서, 집계·추적에 쓰는 family, warning, error도 payload 최상위에 역할별로 나누어 저장한다.
2. **summary 계산**

| 필드 | 계산 기준 |
|---|---|
| `found_files` | 정렬과 `limit` 적용 후 처리 대상으로 선택한 HTML 파일 수 |
| `parsed_files` | parser가 성공하고 filter까지 통과해 `records[]`에 들어간 수 |
| `failed_files` | `skip_errors=True` 실행에서 `errors[]`에 기록된 수 |

- filter에서 제외된 성공 record는 `parsed_files`에 포함되지 않는다.
  - 의도 : summary가 최종 payload에 실제로 들어 있는 record와 error의 수를 그대로 보여 주게 한다.

### 진단과 미리보기 구조
1. **source_file 사용 범위**
- `source_file`은 preview, warning, error처럼 원문 위치를 알아야 하는 응답에서 사용할 수 있다.
- 최종 저장 payload의 `records[]`에는 넣지 않는다.
  - 의도 : 원문을 찾기 위한 컴퓨터 경로와 업무 데이터를 분리한다.
2. **원문 table 미리보기**
- 원문 미리보기는 `source_file`을 다시 읽어 base record를 만든다.
- `source_preview.tables[]`의 각 table은 `index`, `chapter_title`, 보여 줄 `rows`, 그 table에서 숨긴 row 수인 `omitted_rows`를 가진다. 여기의 `rows`는 base record의 `logical_rows`에서 가져온다.
- 한 record에서 최대 12개 table과 전체 120개 row까지만 보여 준다.
- `source_preview.omitted_rows`는 12개 table 또는 120개 row 제한 때문에 원문 전체에서 보여 주지 못한 row의 총수이다.
- 미리보기용 `source_preview`는 최종 저장 `records[]`의 필드가 아니다.
  - 의도 : 큰 HTML 전체를 응답에 복사하지 않고도 추출에 사용된 원문 row를 확인할 수 있게 한다.
