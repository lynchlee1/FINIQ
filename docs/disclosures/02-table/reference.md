# 연도별 SQLite 변환 Reference

## 경로

- `<data_root>/01-list/<YYYYMMDD>_<YYYYMMDD>`의 `*_post_page_*.body`와 `kind_workflow.input.json`을 입력으로 받아 `<data_root>/02-table`에 `<YYYY>.sqlite`와 `sqlite_manifest.json`을 저장한다.

요청에서는 `<data_root>/01-list`를 `root_directory`, `<data_root>/02-table`을 `output_path`로 지정한다.

## 입력 형식

### `*_post_page_*.body`

- KIND 조건검색 결과 한 페이지의 응답 본문이다.
- 공시 결과 파일명은 `_post_page_<숫자>.body`로 끝난다.
- 결과표는 `summary`에 `회사명`과 `공시제목`이 모두 있는 유일한 표다.
- 결과표 바로 아래에는 `tbody`가 하나만 있다.
- 공시 행은 해당 `tbody > tr`이며 바로 아래에 `td`가 5개 이상 있다.
- 회사 칸에는 회사 ID와 회사명 `title`을 가진 유일한 `a#companysum`이 있다.
- 회사 칸의 모든 이미지에는 비어 있지 않은 `alt`가 있다.
- 제목 칸에는 표시 제목과 필수 식별값 `acpt_no`를 가진 유일한 공시 링크가 있다.
- 공시일은 네 자리 연도로 시작한다.

### `kind_workflow.input.json`

- 다운로드에 사용한 검색 조건과 workflow metadata를 기록한 파일이다.
- `kind_workflow.input.json`이 있는 연도별 폴더에는 페이지 번호가 겹치지 않는 공시 결과 파일이 있다.
- workflow metadata에는 page size, 요청 간 대기 시간과 timeout이 있다.

## 출력 형식

### `<YYYY>.sqlite`

- 공시 레코드를 공시일 연도별로 나눈 SQLite 조각이다.
- 연도별 조각은 SQLite FTS5 표를 사용한다.

### `sqlite_manifest.json`

- 원본과 연도별 SQLite 조각, 행 수 검증 결과를 연결한 파일이다.
- `sqlite_manifest.json`에는 원본 경로, 테이블 이름, 전체 원본·중복·저장 행 수가 있다.
- 연도별 SQLite 경로와 저장 행 수를 기록한다.
- 페이지별 원본 파일, 페이지 번호와 원본·중복·저장 행 수를 기록한다.

## 검증식

- 페이지별 `원본 행 수 = 저장 행 수 + 중복 행 수`
- 전체 `원본 행 수 = 실제 SQLite 행 수 + 중복 행 수`
- 연도별 실제 SQLite 행 수 = manifest의 연도별 저장 행 수
- 연도별 저장 행 수 합계 = manifest의 전체 저장 행 수
