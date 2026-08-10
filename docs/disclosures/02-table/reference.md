# Annual SQLite Conversion Reference

## Paths

- `<data_root>/01-list` 아래 기간별 `<START_DATE>_<END_DATE>` 폴더의 `*_post_page_*.body`와 `kind_workflow.input.json`을 입력으로 받아 `<data_root>/02-table`에 `<YEAR>.sqlite`와 `sqlite_manifest.json`을 저장한다.
- 기본 입력은 개별 기간 폴더가 아니라 여러 기간 폴더를 포함하는 `01-list`다. 변환기는 입력 경로 아래의 원본 페이지를 재귀적으로 수집한다.

```text
<data_root>/
├── 01-list/
│   ├── <START_DATE>_<END_DATE>/
│   └── <NEXT_START_DATE>_<NEXT_END_DATE>/
└── 02-table/
    ├── <YEAR>.sqlite
    └── sqlite_manifest.json
```

- 같은 `YEAR`에 속하는 기간 폴더의 공시는 하나의 `<YEAR>.sqlite`에 함께 저장한다.
- `START_DATE`, `END_DATE`, `NEXT_START_DATE`, `NEXT_END_DATE`는 각 다운로드 요청의 실제 기간이며 `YYYYMMDD` 형식이다.

### `<data_root>/01-list/<START_DATE>_<END_DATE>/*_post_page_*.body`

#### I/O Structure

- KIND 조건검색 결과 한 페이지의 응답 본문을 담은 입력 파일이다.
- 공시 결과 파일명은 `_post_page_<숫자>.body`로 끝난다.
- 결과표는 `summary`에 `회사명`과 `공시제목`이 모두 있는 유일한 표다.
- 결과표 바로 아래에는 `tbody`가 하나만 있다.
- 공시 행은 해당 `tbody > tr`이며 바로 아래에 `td`가 5개 이상 있다.
- 회사 칸의 `a#companysum`은 0개 또는 1개다. 링크가 있으면 회사 ID와 회사명 `title`이 모두 있어야 한다.
- 회사 링크가 없으면 공시는 회사 관계 없이 저장하며 회사 칸의 표시 문자열만 별도 보존한다.
- 회사 링크가 둘 이상이면 관계가 모호한 입력으로 처리한다.
- 제목 칸에는 표시 제목과 필수 식별값 `acpt_no`를 가진 유일한 공시 링크가 있다.
- 공시일은 네 자리 연도로 시작한다.

#### Defaults and Exceptions

- 회사 칸에는 이미지가 없을 수 있으며, 이미지가 있으면 모든 이미지에 비어 있지 않은 `alt`가 있다.

### `<data_root>/01-list/<START_DATE>_<END_DATE>/kind_workflow.input.json`

#### I/O Structure

- 다운로드에 사용한 검색 조건과 workflow metadata를 기록한 입력 파일이다.
- workflow metadata에는 page size, 요청 간 대기 시간과 timeout이 있다.

### `<data_root>/02-table/<YEAR>.sqlite`

#### I/O Structure

- 공시 레코드를 공시일 연도별로 나눈 출력 파일이다.
- SQLite `schema_version`은 `3`이다.
- `company_key`, `company_name`, `company_id`는 회사 링크가 없는 공시에서 `NULL`이다.
- `company_cell_text`는 KIND 회사 칸의 정규화한 표시 문자열이며 회사 식별자나 회사명으로 사용하지 않는다.
- 같은 연도의 여러 기간 폴더에서 읽은 레코드는 폴더 경계와 관계없이 해당 연도의 `<YEAR>.sqlite` 하나에 합친다.
- 연도 SQLite는 기존 파일에 증분 추가하지 않는다. 현재 입력 경로의 전체 원본으로 임시 파일을 만든 뒤 완성된 파일로 교체한다.
- 따라서 입력을 특정 기간 폴더 하나로 제한하면 다른 기간의 기존 행은 자동으로 유지되지 않는다. 여러 기간을 합치려면 해당 폴더를 모두 포함하는 공통 상위 경로를 입력해야 한다.
- 연도별 조각은 SQLite FTS5 표를 사용한다.

### `<data_root>/02-table/sqlite_manifest.json`

#### I/O Structure

- 원본과 연도별 SQLite 조각, 행 수 검증 결과를 연결한 출력 파일이다.
- `sqlite_manifest.json`에는 입력 종류, 스키마 버전, 테이블 이름, 전체 원본·중복·저장 행 수와 회사 미연결 공시 수 `unlinked_disclosures`가 있다.
- 연도별 SQLite는 manifest가 있는 폴더 기준의 `relative_path`, 저장 행 수와 `unlinked_disclosures`를 기록한다.
- 페이지별 원본 파일은 실행 입력 루트 기준의 상대 경로로 기록하고 페이지 번호와 원본·중복·저장 행 수를 함께 둔다.
- 입력 루트, manifest 자체 경로, shard 루트와 절대 SQLite 경로는 기록하지 않는다.
