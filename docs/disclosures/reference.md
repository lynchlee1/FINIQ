# Disclosure Workflow Reference

## Paths

- `<data_root>`를 공시 작업공간 루트로 사용하면 각 단계의 기본 입력과 출력을 아래 폴더에 저장한다.
- 화면이 별도 경로를 받는 작업은 작업공간 밖의 입력·출력 경로도 실행 요청으로 지정할 수 있다.
- 어느 루트를 선택하더라도 단계별 하위 폴더, 파일명과 상대 배치는 아래 구조를 바꾸지 않는다.
- 실행 요청과 API 응답은 실제 경로를 전달할 수 있지만 저장 결과 JSON에는 절대 입력·출력 디렉터리를 기록하지 않는다. 파일 연결에는 결과 JSON 위치 기준의 상대 경로나 내용 fingerprint를 사용한다.

### `<data_root>`

#### I/O Structure

- `disclosure-workspace.json`은 공시 작업공간 설정을 저장한다.
- `01-list`는 KIND 조건검색 응답과 다운로드 metadata를 저장한다.
- `02-table`은 연도별 공시 SQLite와 변환 manifest를 저장한다.
- `03-filter`는 mode별 조건검색 filter와 선택 결과를 저장한다.
- `04-external-html-download`는 KIND 외부 HTML, 원본 연결 manifest와 압축한 문서 선택 정보를 저장한다.
- `05-internal-html-download`는 KIND 본문 HTML과 원본 연결 manifest를 저장한다.
- `06-sections`는 공시별로 선택한 목차의 HTML을 저장한다.
- `07-converted`는 mode별 파싱 결과를 저장한다.
- `09-disclosure-graph`는 공시 graph를 저장한다.

```text
<data_root>/
├── disclosure-workspace.json
├── 01-list/
│   └── <YYYYMMDD>_<YYYYMMDD>/
│       ├── *_post_page_*.body
│       ├── kind_workflow.input.json
│       └── kind_workflow.checkpoint.json
├── 02-table/
│   ├── <YYYY>.sqlite
│   └── sqlite_manifest.json
├── 03-filter/
│   └── <mode>/
│       ├── filter.json
│       └── filtered.json
├── 04-external-html-download/
│   └── <mode>/
│       ├── <YYYY>/
│       │   └── <acpt_no>.html
│       ├── kind_disclosure_html_manifest.json
│       └── compressed-external-html.json
├── 05-internal-html-download/
│   └── <mode>/
│       ├── <YYYY>/
│       │   └── <acpt_no>.html
│       └── kind_disclosure_html_manifest.json
├── 06-sections/
│   └── <YYYY>/
│       └── <acpt_no>.html
├── 07-converted/
│   └── <mode>/
│       └── parsed-<mode>.json
└── 09-disclosure-graph/
    └── disclosure-graph.json
```

## Identifiers

KIND와 DART의 모든 식별자는 로마자를 포함할 수 있는 텍스트다. 숫자로 변환하거나 숫자 형식으로 제한하지 않는다.

### KIND

#### I/O Structure

- `company_id`는 회사 링크가 있는 공시에서 기업을 구분한다. 회사 링크가 없는 공시에는 `company_id`가 없을 수 있다.
- `acpt_no`와 `doc_no`는 문서를 구분한다.
- `company_cell_text`는 KIND 회사 칸의 원문 표시값이며 식별자가 아니다.

### DART

#### I/O Structure

- `corp_code`와 `stock_code`는 기업을 구분한다.
- `rcept_no`는 문서를 구분한다.
