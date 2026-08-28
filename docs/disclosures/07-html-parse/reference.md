# Disclosure HTML Parse Reference

## Overview

07단계는 06단계가 잘라 둔 공시 HTML을 선택한 `parser_method`로 읽고 JSON으로 저장한다. 필요하면 앞 단계의 metadata를 연결하고, parsing이 끝난 값으로 저장 대상을 한 번 더 거른다.

```text
06단계 HTML ──┐
03단계 metadata ├─→ parser_method별 parsing ─→ 결과 필터 ─→ parsed-<mode>.json
04단계 metadata ┘
```

- 필수 입력: `<data_root>/06-sections/<mode>/<YYYY>/<acpt_no>.html`
- 파생 필터 HTML 입력: `<data_root>/06-sections/<parent_mode>/<YYYY>/<acpt_no>.html`
- 선택 입력: `<data_root>/03-filter/<mode>/filtered.json`
- 파생 필터 입력: `<data_root>/03-filter/<parent_mode>/subfilters/<mode>/filtered.json`
- 선택 입력: `<data_root>/04-external-html-compress/<mode>/compressed-external-html.json`
- 출력: `<data_root>/07-converted/<mode>/parsed-<mode>.json`

## Parse Request

`parse_disclosure_html_payload()`에 실행 조건을 객체로 전달한다.

`input_directory`와 `output_directory`는 실행 위치를 정하는 요청값이다. 작업공간 밖의 경로도 지정할 수 있지만 저장 결과에는 두 경로를 복사하지 않는다.

### Required Fields

| 항목 | 형식 | 설명 |
| --- | --- | --- |
| `mode` | 문자열 | 작업공간 `조건검색 필터` 이름 |
| `parser_method` | 문자열 | `PARSER_REGISTRY`에 등록된 파싱 방법 |
| `input_directory` | 디렉터리 경로 | `<data_root>/06-sections/<mode>`처럼 `<YYYY>/<acpt_no>.html`을 찾을 모드 디렉터리 |
| `output_directory` | 디렉터리 경로 | `parsed-<mode>.json`을 저장할 디렉터리 |
| `skip_errors` | 불리언 | `true`이면 파일 하나가 실패해도 오류를 기록하고 다음 파일을 처리 |

### Optional Fields

| 항목 | 형식 | 기본값과 설명 |
| --- | --- | --- |
| `filtered_metadata_path` | 파일 경로 | 회사명, 시장, 공시시각을 연결할 `filtered.json` |
| `compressed_metadata_path` | 파일 경로 | 제목, 본문 문서번호, 정정공시 묶음을 연결할 압축 metadata |
| `parent_mode` | 문자열 | 파생 필터일 때 상위 기본 필터 mode |
| `limit` | 1 이상의 정수 | 정렬된 입력 중 앞에서 몇 건을 처리할지 제한; 기본값은 제한 없음 |
| `progress_interval` | 1 이상의 정수 | `1000`; `skip_errors=true`일 때 이 건수마다 중간 결과를 저장 |
| `parallel_workers` | 1 이상의 정수 | 기본값은 가용 CPU 수이며 입력 파일 수를 넘지 않음 |
| `cancel_token` | 문자열 | 실행 중인 작업과 취소 요청을 연결하는 값 |
| `filter_blocks` | 배열 | 공시 metadata 조건; 기본값은 빈 배열 |
| `record_filters` | 배열 | parsing 결과의 업무 field 조건; 기본값은 빈 배열 |

```json
{
  "mode": "<mode>",
  "parser_method": "<parser_method>",
  "parent_mode": "<parent_mode>",
  "input_directory": "/data/06-sections/<mode>",
  "output_directory": "/data/07-converted/<mode>",
  "skip_errors": true,
  "filtered_metadata_path": "/data/03-filter/<mode>/filtered.json",
  "compressed_metadata_path": "/data/04-external-html-compress/<mode>/compressed-external-html.json",
  "progress_interval": 1000
}
```

### Result Filters

`record_filters`는 HTML을 parsing한 뒤 나온 업무값에 적용한다. 각 조건은 `field`, `operator`, `value`로 구성한다.

| `operator` | 판단 방법 | `value` |
| --- | --- | --- |
| `contains` | 값에 지정한 문자열이 포함되는지 확인 | 문자열; 기본 operator |
| `equals` | 값이 지정한 문자열과 같은지 확인 | 문자열 |
| `exists` | 값이 비어 있지 않은지 확인 | 사용하지 않음 |
| `in` | 값이 지정한 후보 중 하나인지 확인 | 비어 있지 않은 배열 |

`record_filters`의 모든 조건을 만족하고 `filter_blocks`도 통과한 record만 `records`에 저장한다. 필터에서 빠진 record는 parsing 실패로 세지 않는다.

## How HTML Becomes Rows

mode 문서에 나오는 `N=1`, `logical_rows` 같은 표현은 아래 과정을 전제로 한다.

1. `rowspan`과 `colspan`으로 합쳐진 셀을 실제 칸마다 펼친다.
2. `positional_rows`에는 빈 칸까지 포함해 원래 열 위치를 남긴다.
3. `logical_rows`에서는 빈 칸과 바로 앞 칸과 같은 값을 제거한다.
4. mode parser는 주로 `logical_rows`에서 라벨을 찾는다.

예를 들어 한 행의 `logical_rows`가 아래와 같다면 셀 번호는 왼쪽부터 1로 시작한다.

```text
N=1             N=2      N=3
사채의 종류     회차     제3회
```

따라서 “`N=2`가 `회차`인 행의 `N=3` 값을 읽는다”는 설명은 위 행에서 `제3회`를 읽는다는 뜻이다.

문자와 숫자는 다음 규칙으로 정리한다.

- 줄바꿈을 포함해 연속한 공백은 한 칸으로 바꾼다.
- 라벨에서는 공백과 맨 앞의 숫자·로마자 번호를 제거한다. 두 단계 번호와 뒤의 점까지 제거할 수 있다.
- mode 문서의 `정확히 일치`, `시작`, `포함`은 라벨을 정리한 뒤 적용한다.
- 숫자는 문자열에서 처음 찾은 부호 있는 정수를 읽고 천 단위 쉼표를 제거한다.
- `-`는 각 field 규칙이 명시적으로 허용할 때만 0으로 바꾼다.

## Input Files

### Section HTML

`<data_root>/06-sections/<mode>/<YYYY>/<acpt_no>.html`이 실제 parsing 대상이다.

- 입력 루트는 모드 디렉터리 `<data_root>/06-sections/<mode>`이다. 파생 필터는 `<data_root>/06-sections/<parent_mode>`를 사용한다.
- `06-sections` 단계 루트나 `06-sections/<YYYY>/`는 입력으로 쓰지 않는다.
- 입력 루트 바로 아래의 4자리 숫자 연도 폴더만 찾는다.
- 연도 폴더 바로 아래의 `.html` 파일만 읽고 더 깊은 파일은 읽지 않는다.
- 확장자를 뺀 파일명 전체를 `acpt_no`로 사용한다.
- 서로 다른 연도 폴더에 같은 `acpt_no`가 있으면 실행을 시작하지 않는다.
- byte 입력은 UTF-8로만 decode한다.
- 깨진 HTML 문법은 복구하며 읽지만 `rowspan`이나 `colspan`이 유효한 양의 정수가 아니면 실패한다.

### Filtered Metadata

`<data_root>/03-filter/<mode>/filtered.json`을 지정하면 HTML의 `acpt_no`와 같은 항목에서 회사명, 시장, 공시시각을 가져온다.

- 최상위 `format`은 `kind_disclosure_filter_v1`이어야 한다.
- `disclosures`는 객체 배열이어야 한다.
- 각 `acpt_no`는 비어 있지 않고 서로 달라야 한다.
- 선택한 모든 HTML에 `YYYY-MM-DD HH:MM` 형식의 `disclosed_at`이 있어야 한다.
- `market`이 `유가증권`이면 결과에는 `코스피`로 저장한다.
- 파생 필터는 자식 `mode`와 `parent_mode`를 함께 지정한다. HTML 입력은 상위 `06-sections/<parent_mode>`이고, 작업공간 기본 메타데이터 경로는 자식의 중첩 `filtered.json`으로 정하며, parser는 `parser_method`로만 선택한다.

### Compressed External HTML Metadata

`<data_root>/04-external-html-compress/<mode>/compressed-external-html.json`을 지정하면 제목, 본문 문서번호와 정정공시 관계를 연결한다.

- 최상위 `format`은 `finiq_disclosure_external_html_docs_v1`이어야 한다.
- `records`는 객체 배열이어야 한다.
- 각 record에는 비어 있지 않은 `acpt_no`, `selected_main_doc_no`와 `metadata` 객체가 있어야 한다.
- `title`은 결과 record의 `title`, `selected_main_doc_no`는 `doc_no`가 된다.
- `mainDoc`가 둘 이상이고 모든 문서를 연결할 수 있을 때만 correction family를 만든다.
- 파생 필터는 상위 기본 필터의 압축 metadata를 읽되 자식 `filtered.json`의 `acpt_no` 부분집합만 변환한다.

## Saved Result

결과 파일의 최상위 `format`은 `finiq_disclosure_html_parse_v1`이다.

### Top-Level Fields

| 항목 | 형식 | 바로 확인할 수 있는 내용 |
| --- | --- | --- |
| `format` | 문자열 | 어떤 schema로 저장했는지 |
| `mode` | 문자열 | 어떤 작업공간 필터로 저장했는지 |
| `parser_method` | 문자열 | 어떤 parser를 실행했는지 |
| `cancelled` | 불리언 | 취소 요청 때문에 입력 전체를 처리하지 못했는지 |
| `filter_settings` | 객체 | 어떤 `filter_blocks`와 `record_filters`를 적용했는지 |
| `summary` | 객체 | 찾은 파일, 저장한 record, 실패한 파일 수 |
| `records` | 배열 | parsing에 성공하고 필터도 통과한 결과 |
| `errors` | 배열 | `skip_errors=true`로 건너뛴 파일별 오류 |
| `warnings` | 배열 | parsing은 성공했지만 확인이 필요한 내용 |
| `warning_report_counts` | 객체 | warning을 수준과 공시별로 모은 집계 |
| `families` | 객체 | 저장한 record가 속한 정정공시 묶음 |

### Summary Counts

세 집계값은 다음처럼 읽는다.

- `found_files`: `limit`까지 적용한 뒤 처리 대상으로 선택한 HTML 수
- `parsed_files`: parsing 성공 수가 아니라 필터까지 통과해 `records`에 저장한 수
- `failed_files`: `skip_errors=true`로 건너뛰어 `errors`에 남긴 수

필터에서 제외된 성공 record는 세 값 중 `parsed_files`나 `failed_files`에 들어가지 않는다. 따라서 세 값을 더해도 항상 `found_files`가 되지는 않는다.

필터에서 제외됐더라도 parsing 중 warning이 생겼다면 그 warning은 최상위 `warnings`와 집계에 남는다.

```json
{
  "format": "finiq_disclosure_html_parse_v1",
  "mode": "<mode>",
  "cancelled": false,
  "filter_settings": {"filter_blocks": [], "record_filters": []},
  "warning_report_counts": {
    "count": 0,
    "report_count": 0,
    "weak_warning": {"count": 0, "report_count": 0, "reports": {}},
    "medium_warning": {"count": 0, "report_count": 0, "reports": {}},
    "strong_warning": {"count": 0, "report_count": 0, "reports": {}}
  },
  "summary": {"found_files": 1, "parsed_files": 1, "failed_files": 0},
  "families": {},
  "records": [
    {
      "acpt_no": "202608090001",
      "mode": "<mode>",
      "title": "",
      "상장구분": null
    }
  ],
  "errors": [],
  "warnings": []
}
```

위 예시는 공통 구조만 보여 준다. 실제 record에는 선택한 mode의 업무 field가 추가된다.

### Fields Shared by Every Record

| 항목 | 형식 | 언제 들어가는지 |
| --- | --- | --- |
| `acpt_no` | 문자열 | 항상 포함; HTML 파일명에서 가져온 식별값 |
| `mode` | 문자열 | 항상 포함 |
| `title` | 문자열 | 항상 포함; metadata가 없거나 parser가 title을 받지 않으면 빈 문자열 |
| `상장구분` | 문자열 또는 `null` | 항상 포함; filtered metadata가 있으면 시장값을 연결 |
| `doc_no`, `disclosed_at` | 문자열 | 해당 metadata가 있을 때만 포함 |
| `family_id` | 문자열 | 완성된 correction family에 속할 때만 포함 |
| `current_sequence` | 정수 | family 안의 문서 순서; 0부터 시작 |
| `family_member_count` | 정수 | family에 속한 전체 문서 수 |
| `parse_warnings`, `weak_warning`, `medium_warning`, `strong_warning` | 문자열 배열 | 해당 warning이 있을 때만 포함 |

`raw_tables`는 HTML에서 값을 뽑거나 preview를 만들 때만 쓰는 중간 자료다. 최종 `records`에는 저장하지 않는다. `raw_rows`, `rcept_no`, `source_file`과 빈 `correction_families`도 만들지 않는다.

## Field Status

일부 mode는 각 업무값을 얼마나 확실하게 읽었는지 `field_parse_status`에 기록한다.

| 상태 | 뜻 |
| --- | --- |
| `parsed` | 정해진 위치에서 유효한 값을 읽음 |
| `explicit_zero` | 원문에 0 또는 이 field에서 0으로 인정하는 `-`가 적혀 있음 |
| `source_not_found` | 정해진 위치에서 값을 찾지 못함 |
| `not_applicable` | 해당 공시 유형에는 적용하지 않는 field라서 찾지 않음 |

`source_not_found`는 “일부 값을 찾지 못했다”는 상태이지 파일 전체의 parsing 실패를 뜻하지 않는다. mode가 반드시 필요로 하는 표가 없거나 입력 형식 자체가 잘못된 경우에만 파일 오류가 된다.

## Warnings and Errors

warning은 record를 저장할 수 있지만 확인이 필요한 경우이고, error는 해당 파일의 record를 만들지 못한 경우다.

### Warning Item

| 항목 | 의미 |
| --- | --- |
| `index`, `total` | 전체 입력에서 현재 파일의 순서와 입력 수 |
| `mode`, `acpt_no` | parser mode와 원본 공시 식별값 |
| `warning` | 사람이 확인할 warning 문장 |
| `level` | `weak_warning`, `medium_warning`, `strong_warning` 중 하나 |
| `warning_code` | 전용 code, `source_not_found:<field>` 또는 일반 `parse_warning` |

한 record의 `parse_warnings`는 수준별 warning 목록과 같은 문장 집합이어야 한다. 빈 문장, 중복 문장, 수준이 없는 문장, 두 수준에 동시에 들어간 문장이 있으면 저장 전에 실패한다.

### Error Item

`errors[]`의 각 항목은 `index`, `total`, `mode`, `acpt_no`, `error_type`, `error`를 가진다.

- `skip_errors=true`: 오류를 `errors`에 넣고 다음 파일을 처리한다.
- `skip_errors=false`: 첫 파일 오류에서 전체 실행을 중단하고 최종 결과를 저장하지 않는다.

## Correction Families

correction family는 최초 공시와 이후 정정공시를 한 묶음으로 표현한다.

```text
records[]
└── family_id, current_sequence, family_member_count

families[family_id]
└── members[]
    └── sequence, acpt_no, doc_no, title, disclosed_at, is_correction_report
```

각 record에는 어느 family의 몇 번째 문서인지만 기록한다. 구성원 전체 정보는 최상위 `families[family_id].members`에 한 번만 둔다. 필요한 구성원을 모두 연결하지 못하면 불완전한 family를 만들지 않는다.

## Preview and Inspection

| 기능 | 입력과 결과 |
| --- | --- |
| Preview | `mode`, `input_directory`, 선택 metadata 경로, `filter_blocks`, `limit`을 받아 record를 보여 줌; `limit` 기본값은 3 |
| Source preview | 한 preview record 안에서 원문 표를 최대 12개, 전체 120행까지 보여 주고 나머지 행 수를 기록 |
| Filter candidates | `mode`, `input_directory`, `field`와 선택 metadata 경로·`parallel_workers`를 받아 값별 전체 건수와 최대 20개의 `acpt_no` 예시를 반환 |
| Cancel | 비어 있지 않은 `cancel_token`으로 새 작업 제출을 멈추고 이미 처리한 record를 저장; 제출을 마친 병렬 작업은 끝날 수 있음 |
| Excel export | 모든 record key를 열로 만들고 목록·객체는 JSON 문자열로 기록 |

preview record 하나가 공시 한 건을 나타낸다. 공시 식별값인 `acpt_no`는 그 record의 바깥쪽에 있고, 내부 `source_preview`에는 표와 생략 행 정보만 둔다.

사채 요약처럼 저장 결과와 원문 HTML을 함께 읽는 조회 요청은 결과 폴더와 `input_directory`를 각각 받는다. 조회 함수는 저장 JSON 안에서 원문 경로를 찾거나 결과 위치로 입력 위치를 추론하지 않는다.

`latest_only=true`로 Excel을 만들면 correction family마다 마지막 문서만 남기고 family가 없는 record는 그대로 유지한다. 08단계의 정정 내역 비교는 이 단계가 저장한 `families`와 record 순서를 사용한다.
