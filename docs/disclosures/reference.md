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
- `04-external-html-download`는 KIND 외부 HTML과 원본 연결 manifest를 저장한다.
- `04-external-html-compress`는 압축한 문서 선택 정보를 저장한다.
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
│       └── kind_disclosure_html_manifest.json
├── 04-external-html-compress/
│   └── <mode>/
│       └── compressed-external-html.json
├── 05-internal-html-download/
│   └── <mode>/
│       ├── <YYYY>/
│       │   └── <acpt_no>.html
│       └── kind_disclosure_html_manifest.json
├── 06-sections/
│   └── <mode>/
│       └── <YYYY>/
│           └── <acpt_no>.html
├── 07-converted/
│   └── <mode>/
│       └── parsed-<mode>.json
└── 09-disclosure-graph/
    └── disclosure-graph.json
```

### 단계별 작업공간 연결

- `01-list`부터 `07-converted`까지의 저장 폴더는 바로 아래의 `finiq-stage-link.json`으로 다른 작업공간의 같은 이름 폴더를 사용할 수 있다. 04단계는 원본 저장과 압축 결과를 독립적으로 연결할 수 있도록 `04-external-html-download`, `04-external-html-compress` 두 폴더를 사용한다.
- 연결 파일이 없는 단계는 `<data_root>` 아래의 로컬 단계 폴더를 사용한다.
- 연결된 단계의 읽기와 쓰기는 모두 대상 작업공간에서 수행한다. 연결 오류가 나도 로컬 단계 폴더로 우회하지 않는다.
- 연결된 단계에서는 저장 설정에 남아 있는 기존 명시 경로보다 연결 대상 경로를 우선한다. 연결되지 않은 단계의 명시 경로 동작은 유지한다.
- `finiq-stage-link.json`은 로컬 단계의 기존 파일·폴더와 함께 둘 수 있으며, 연결된 동안에는 대상 단계가 로컬 단계를 대신한다.
- 연결을 추가할 때 대상 작업공간 아래에 같은 이름의 단계 폴더가 없으면 생성한다. 대상 단계가 다시 연결 파일을 포함하는 연쇄 연결은 허용하지 않는다.
- `target_workspace`가 상대 경로이면 선택한 `<data_root>`를 기준으로 해석한다.

```json
{
  "format": "finiq_stage_link_v1",
  "schema_version": 1,
  "target_workspace": "/Volumes/HDD/database-B"
}
```

예를 들어 `<data_root>/01-list/finiq-stage-link.json`이 위 작업공간을 가리키면 01단계의 실제 입출력 경로는 `/Volumes/HDD/database-B/01-list`가 된다. 다른 단계는 각각 연결 파일이 있을 때만 같은 방식으로 전환한다.

각 작업은 실제로 읽거나 쓰는 단계의 연결만 해석한다. 따라서 사용하지 않는 단계의 연결이 끊겨 있어도 현재 작업은 계속할 수 있으며, 끊어진 연결은 해당 단계를 사용하는 작업에서만 오류가 된다. 예를 들어 공시원문 목차 검사는 05단계만 확인하고, 목차 저장은 05·06단계만 확인한다.

각 01-07 세부 페이지의 우측 `설정` 패널에 있는 `단계별 저장 위치`에서 현재 단계의 연결을 추가, 변경하거나 해제할 수 있다. 외부 HTML 페이지는 저장·압축 폴더를 각각 표시하고, `공시 자동화`의 `실행 설정`에서는 여덟 저장 폴더의 연결 상태를 함께 관리한다. 대상 경로로는 단계 폴더가 아니라 대상 작업공간 루트를 선택한다. 연결 파일은 로컬 단계의 기존 데이터와 함께 둘 수 있으며, 연결된 동안에는 대상 단계가 로컬 단계를 대신한다. 연결 해제는 `finiq-stage-link.json`만 제거하므로 로컬 데이터가 다시 보이고 대상 작업공간의 데이터는 이동하거나 삭제하지 않는다.

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
