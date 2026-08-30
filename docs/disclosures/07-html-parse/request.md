# 07 요청과 행 변환

06단계가 잘라 둔 공시 HTML을 선택한 `parser_method`로 읽고 JSON으로 저장한다. 필요하면 앞 단계의 metadata를 연결하고, parsing이 끝난 값으로 저장 대상을 한 번 더 거른다.

```text
06단계 HTML ──┐
03단계 metadata ├─→ parser_method별 parsing ─→ 결과 필터 ─→ parsed-<mode>.json
04단계 metadata ┘
```

## 변환 요청

`parse_disclosure_html_payload()`에 실행 조건을 객체로 전달한다.

`input_directory`와 `output_directory`는 실행 위치를 정하는 요청값이다. 작업공간 밖의 경로도 지정할 수 있지만 저장 결과에는 두 경로를 복사하지 않는다.

### 필수 필드

| 항목 | 형식 | 설명 |
| --- | --- | --- |
| `mode` | 문자열 | 작업공간 `조건검색 필터` 이름 |
| `parser_method` | 문자열 | `PARSER_REGISTRY`에 등록된 파싱 방법 |
| `input_directory` | 디렉터리 경로 | `<data_root>/06-sections/<mode>`처럼 `<YYYY>/<acpt_no>.html`을 찾을 모드 디렉터리 |
| `output_directory` | 디렉터리 경로 | `parsed-<mode>.json`을 저장할 디렉터리 |
| `skip_errors` | 불리언 | `true`이면 파일 하나가 실패해도 오류를 기록하고 다음 파일을 처리 |

### 선택 필드

| 항목 | 형식 | 기본값과 설명 |
| --- | --- | --- |
| `filtered_metadata_path` | 파일 경로 | 회사명, 시장, 공시시각을 연결할 `filtered.json` |
| `compressed_metadata_path` | 파일 경로 | 제목, 본문 문서번호, 정정공시 묶음을 연결할 압축 metadata |
| `parent_mode` | 문자열 | 파생 필터일 때 상위 기본 필터 mode |
| `limit` | 1 이상의 정수 | 정렬된 입력 중 앞에서 몇 건을 처리할지 제한; 기본값은 제한 없음 |
| `progress_interval` | 1 이상의 정수 | `1000`; 이 건수마다 진행 로그를 남기고 `skip_errors=true`일 때 중간 결과도 저장 |
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

### 결과 필터

`record_filters`는 HTML을 parsing한 뒤 나온 업무값에 적용한다. 각 조건은 `field`, `operator`, `value`로 구성한다.

| `operator` | 판단 방법 | `value` |
| --- | --- | --- |
| `contains` | 값에 지정한 문자열이 포함되는지 확인 | 문자열; 기본 operator |
| `equals` | 값이 지정한 문자열과 같은지 확인 | 문자열 |
| `exists` | 값이 비어 있지 않은지 확인 | 사용하지 않음 |
| `in` | 값이 지정한 후보 중 하나인지 확인 | 비어 있지 않은 배열 |

`record_filters`의 모든 조건을 만족하고 `filter_blocks`도 통과한 record만 `records`에 저장한다. 필터에서 빠진 record는 parsing 실패로 세지 않는다.

## HTML을 행으로 바꾸는 과정

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
