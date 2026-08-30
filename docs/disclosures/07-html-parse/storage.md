# 07 파일과 저장 형식

## 목차 HTML

`<data_root>/06-sections/<mode>/<YYYY>/<acpt_no>.html`이 실제 parsing 대상이다.

- 입력 루트는 모드 디렉터리 `<data_root>/06-sections/<mode>`이다. 파생 필터는 `<data_root>/06-sections/<parent_mode>`를 사용한다.
- `06-sections` 단계 루트나 `06-sections/<YYYY>/`는 입력으로 쓰지 않는다.
- 입력 루트 바로 아래의 4자리 숫자 연도 폴더만 찾는다.
- 연도 폴더 바로 아래의 `.html` 파일만 읽고 더 깊은 파일은 읽지 않는다.
- 확장자를 뺀 파일명 전체를 `acpt_no`로 사용한다.
- 서로 다른 연도 폴더에 같은 `acpt_no`가 있으면 실행을 시작하지 않는다.
- byte 입력은 UTF-8로만 decode한다.
- 깨진 HTML 문법은 복구하며 읽지만 `rowspan`이나 `colspan`이 유효한 양의 정수가 아니면 실패한다.

## 필터 metadata

`<data_root>/03-filter/<mode>/filtered.json`을 지정하면 HTML의 `acpt_no`와 같은 항목에서 회사명, 시장, 공시시각을 가져온다.

- 최상위 `format`은 `kind_disclosure_filter_v1`이어야 한다.
- `disclosures`는 객체 배열이어야 한다.
- 각 `acpt_no`는 비어 있지 않고 서로 달라야 한다.
- 선택한 모든 HTML에 `YYYY-MM-DD HH:MM` 형식의 `disclosed_at`이 있어야 한다.
- `market`이 `유가증권`이면 결과에는 `코스피`로 저장한다.
- 파생 필터는 자식 `mode`와 `parent_mode`를 함께 지정한다. HTML 입력은 상위 `06-sections/<parent_mode>`이고, 작업공간 기본 메타데이터 경로는 자식의 중첩 `filtered.json`으로 정하며, parser는 `parser_method`로만 선택한다.

## 외부 HTML 압축 metadata

`<data_root>/04-external-html-compress/<mode>/compressed-external-html.json`을 지정하면 제목, 본문 문서번호와 정정공시 관계를 연결한다.

- 최상위 `format`은 `finiq_disclosure_external_html_docs_v1`이어야 한다.
- `records`는 객체 배열이어야 한다.
- 각 record에는 비어 있지 않은 `acpt_no`, `selected_main_doc_no`와 `metadata` 객체가 있어야 한다.
- `title`은 결과 record의 `title`, `selected_main_doc_no`는 `doc_no`가 된다.
- `mainDoc`가 둘 이상이고 모든 문서를 연결할 수 있을 때만 correction family를 만든다.
- 파생 필터는 상위 기본 필터의 압축 metadata를 읽되 자식 `filtered.json`의 `acpt_no` 부분집합만 변환한다.

## 저장 결과

결과 파일의 최상위 `format`은 `finiq_disclosure_html_parse_v1`이다.

### 최상위 필드

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

### 집계값

세 집계값:

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

### 공통 record 필드

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
