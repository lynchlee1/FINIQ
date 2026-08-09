# Annual SQLite Conversion Reference

## Paths

- `<data_root>/01-list/<YYYYMMDD>_<YYYYMMDD>`의 `*_post_page_*.body`와 `kind_workflow.input.json`을 입력으로 받아 `<data_root>/02-table`에 `<YYYY>.sqlite`와 `sqlite_manifest.json`을 저장한다.

### `<data_root>/01-list/<YYYYMMDD>_<YYYYMMDD>/*_post_page_*.body`

#### I/O Structure

- KIND 조건검색 결과 한 페이지의 응답 본문을 담은 입력 파일이다.
- 공시 결과 파일명은 `_post_page_<숫자>.body`로 끝난다.
- 결과표는 `summary`에 `회사명`과 `공시제목`이 모두 있는 유일한 표다.
- 결과표 바로 아래에는 `tbody`가 하나만 있다.
- 공시 행은 해당 `tbody > tr`이며 바로 아래에 `td`가 5개 이상 있다.
- 회사 칸에는 회사 ID와 회사명 `title`을 가진 유일한 `a#companysum`이 있다.
- 제목 칸에는 표시 제목과 필수 식별값 `acpt_no`를 가진 유일한 공시 링크가 있다.
- 공시일은 네 자리 연도로 시작한다.

#### Defaults and Exceptions

- 회사 칸에는 이미지가 없을 수 있으며, 이미지가 있으면 모든 이미지에 비어 있지 않은 `alt`가 있다.

### `<data_root>/01-list/<YYYYMMDD>_<YYYYMMDD>/kind_workflow.input.json`

#### I/O Structure

- 다운로드에 사용한 검색 조건과 workflow metadata를 기록한 입력 파일이다.
- workflow metadata에는 page size, 요청 간 대기 시간과 timeout이 있다.

### `<data_root>/02-table/<YYYY>.sqlite`

#### I/O Structure

- 공시 레코드를 공시일 연도별로 나눈 출력 파일이다.
- 연도별 조각은 SQLite FTS5 표를 사용한다.

### `<data_root>/02-table/sqlite_manifest.json`

#### I/O Structure

- 원본과 연도별 SQLite 조각, 행 수 검증 결과를 연결한 출력 파일이다.
- `sqlite_manifest.json`에는 입력 종류, 테이블 이름, 전체 원본·중복·저장 행 수가 있다.
- 연도별 SQLite는 manifest가 있는 폴더 기준의 `relative_path`와 저장 행 수를 기록한다.
- 페이지별 원본 파일은 실행 입력 루트 기준의 상대 경로로 기록하고 페이지 번호와 원본·중복·저장 행 수를 함께 둔다.
- 입력 루트, manifest 자체 경로, shard 루트와 절대 SQLite 경로는 기록하지 않는다.
