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
| `cells` | 2차원 목록 | span을 펼친 cell의 text와 위치 정보이다. |
| `positional_rows` | 2차원 문자열 목록 | 실제 column 위치와 반복값을 보존한 row이다. |
| `logical_rows` | 2차원 문자열 목록 | label 검색이 쉽도록 빈값과 연속 중복값을 줄인 row이다. |

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

### 공통 base record
1. **record 생성**
- `build_base_record()`는 HTML을 한 번 parsing해 아래 필드를 만든 뒤 개별 parser에 전달한다.

| 필드 | 공통 생성 값 | 역할 |
|---|---|---|
| `acpt_no` | `Path(file_path).stem` | KIND 공시를 구분하는 번호 |
| `mode` | 호출한 parser의 mode | 어떤 parser로 만든 record인지 표시 |
| `title` | 빈 문자열 | 외부에서 주입할 제목의 자리 |
| `상장구분` | `null` | 외부 metadata에서 연결할 시장 구분의 자리 |
| `raw_tables` | 모든 HTML table의 공통 구조 | table별 검색과 원문 확인에 사용 |

- `acpt_no`는 확장자만 제거한 파일명 전체를 그대로 사용하며, 숫자 여부를 검사하지 않는다.
  - 공시 HTML 파일명에는 `_`가 사용되지 않는다. 파일명에 `_`가 포함됨을 가정하는 모든 로직은 치명적인 보안 문제로 간주한다.
- base record는 `source_file`, `raw_rows`, 빈 `correction_families`, `rcept_no`를 생성하지 않는다.
- base record의 `title`은 항상 빈 문자열이다.
  - 의도 : 공통 단계에서는 작성하지 않고 외부 metadata를 통해 다음 단계에서 연결한다.
2. **개별 parser의 직접 반환값**
- `parse_*()`는 HTML 파일에서 필요한 정보를 찾아 record로 만드는 함수이다. 
- `직접 반환값`은 이 함수를 호출한 직후 받는 결과를 뜻한다. 아직 저장용 형태로 바뀌기 전의 결과물이다.
- 각 `parse_*()`는 먼저 공통 정보가 들어 있는 base record를 받아 모드별로 필요한 필드를 추가해서 반환한다.
- parser는 HTML의 표에서 필요한 행과 값을 찾는 동안 각 항목이 잘 처리되었는지 기록한다. 기록할 내용이 하나라도 발생하면 `field_parse_status`에 저장하고, 하나도 발생하지 않으면 빈 `field_parse_status`를 만들지 않는다.
- 문제가 발견되면 `parse_warnings`에 warning을 심각도에 따라 기록한다. warning이 없는 빈 목록은 record에 추가하지 않는다.

| 필드 | 들어가는 warning |
|---|---|
| `weak_warning` | 약한 수준의 warning |
| `medium_warning` | 중간 수준의 warning |
| `strong_warning` | 강한 수준의 warning |

- 직접 반환값에는 parser가 어떤 원문을 읽었는지 확인할 수 있도록 `raw_tables`가 포함된다.
- 반면 `source_file`, `raw_rows`, `correction_families`, `rcept_no`는 포함되지 않는다.
  즉, 직접 반환값은 다음과 같이 이해할 수 있다.

| 구분 | 필드 |
|---|---|
| 항상 포함되는 공통 정보 | `acpt_no`, `mode`, `title`, `상장구분`, `raw_tables` |
| 공시 유형에 따라 추가되는 정보 | 각 parser schema가 정의한 업무 필드 |
| 처리 결과가 있을 때만 포함되는 정보 | `field_parse_status` |
| warning이 있을 때만 포함되는 정보 | `parse_warnings`와 warning이 존재하는 심각도별 목록 |
| 포함되지 않는 정보 | `source_file`, `raw_rows`, `correction_families`, `rcept_no` |

  - 의도 : parser가 직접 반환하는 필드의 범위를 일정하게 유지하고,
  빈 상태나 빈 warning 목록처럼 의미 없는 값은 만들지 않는다.

### parser 반환값에서 저장 record까지
1. **원문 분석용 필드 제거**
- 웹 parsing workflow는 parser 반환값을 받은 직후 저장 대상이 아닌 `raw_tables`를 제거한다.
  - 의도 : parsing에 필요한 원문 table은 직접 분석 결과에만 두고 저장 record에는 넣지 않는다.
2. **외부 metadata 연결**
- `raw_tables`를 제외한 record에 외부 metadata의 저장 필드를 연결한다.
- 정정공시 family가 확인되면 record에 `family_id`, `current_sequence`, `family_member_count`를 직접 추가하고, 전체 family는 payload 최상위 `families`에 별도로 모은다.
- 외부 필드의 출처는 [외부 메타데이터 병합 규칙](../external-metadata.md)을 따른다.
3. **최종 records 변환**
- metadata와 family 참조를 연결한 record를 payload의 최종 `records[]`에 넣는다.
- parser가 만든 `field_parse_status`, `field_parse_status_detail`, `parse_warnings`, `weak_warning`, `medium_warning`, `strong_warning`과 공시별 업무 필드는 `records[]`에 그대로 남는다.
- payload 최상위의 `warnings[]`는 record의 warning을 없애고 옮긴 목록이 아니라, 파일 식별자·경고 수준·`warning_code`를 더해 별도로 정리한 목록이다.
  - 의도 : 업무 record에는 필요한 값만 남기고 반복되는 family 전체 정보는 최상위에 한 번만 저장한다.

### 정정공시 family 구조
정정공시 family는 하나의 원공시와 그 뒤에 이어진 정정공시들을 한 묶음으로 나타낸 구조이다.

1. **생성 결과**
- metadata 연결 단계에서 family 전체는 payload 최상위 `families`에 아래 구조로 모은다.

```text
{
  family_id: {
    members: [구성원, ...]
  }
}
```

- `family_id`는 순서상 마지막 구성원의 `acpt_no`이다.
- 각 구성원의 `sequence`는 첫 번째가 0인 정수이다.
- family에 속한 record에는 `family_id`, `current_sequence`, `family_member_count`를 직접 추가한다.
- record에 `correction_families`를 임시로 만들지 않는다.
  - 의도 : record 참조와 최상위 family를 처음부터 최종 저장 위치에 맞게 만든다. 레거시 구조를 거쳤다가 다시 돌아오는 로직을 사용해선 안된다. 
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
| `input_directory` | 입력 HTML을 찾는 최상위 원문 디렉토리의 절대 경로 |
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
1. **원문 위치 확인**
- `input_directory`는 원문 위치를 확인하는 유일한 저장 경로이다.
- 원문을 한 폴더에 모아 저장한 경우 `input_directory` 바로 아래에서 `<acpt_no>.html`을 찾는다.
- 연도별로 나누어 저장한 경우 `input_directory` 바로 아래의 연도 폴더들에서 `<acpt_no>.html`을 찾는다.
- warning과 error 항목은 `acpt_no`를 가진다. preview의 바깥 record도 `acpt_no`를 가지며, 어느 항목도 개별 파일 경로나 파일명을 저장하지 않는다.
  - 의도 : 같은 최상위 경로를 record마다 반복하지 않고 식별자로 원문을 찾는다.
2. **원문 table 미리보기**
- 원문 미리보기는 payload 최상위 `input_directory`와 record의 `acpt_no`로 원문을 찾아 base record를 만든다.
- `source_preview`는 바깥 preview record의 `acpt_no`를 사용하며 식별자를 중복하지 않는다. 원문을 찾으면 `available`, `title`, `tables`, `omitted_rows`를 가진다.
- `source_preview.tables[]`의 각 table은 `index`, 보여 줄 `rows`, 그 table에서 숨긴 row 수인 `omitted_rows`를 가진다. 여기의 `rows`는 base record의 `logical_rows`에서 가져온다.
- 한 record에서 최대 12개 table과 전체 120개 row까지만 보여 준다.
- `source_preview.omitted_rows`는 12개 table 또는 120개 row 제한 때문에 원문 전체에서 보여 주지 못한 row의 총수이다.
- 미리보기용 `source_preview`는 최종 저장 `records[]`의 필드가 아니다.
  - 의도 : 큰 HTML 전체를 응답에 복사하지 않고도 추출에 사용된 원문 row를 확인할 수 있게 한다.
