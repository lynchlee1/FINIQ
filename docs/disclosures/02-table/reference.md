# 연도별 SQLite 변환 Reference

## 경로

**입력 경로** — `<data_root>/01-list`

**출력 경로** — `<data_root>/02-table`

**입력 파일** — `*_post_page_*.body`

**manifest** — `sqlite_manifest.json`

요청에서는 KIND 원본 폴더를 `root_directory`, 출력 위치를 `output_path`로 지정한다.

## 입력 형식

- 공시 결과 파일명은 `_post_page_<숫자>.body`로 끝난다.
- `kind_workflow.input.json`이 있는 연도별 폴더에는 페이지 번호가 겹치지 않는 공시 결과 파일이 있다.
- workflow metadata에는 page size, 요청 간 대기 시간과 timeout이 있다.
- 결과표는 `summary`에 `회사명`과 `공시제목`이 모두 있는 유일한 표다.
- 결과표 바로 아래에는 `tbody`가 하나만 있다.
- 공시 행은 해당 `tbody > tr`이며 바로 아래에 `td`가 5개 이상 있다.
- 회사 칸에는 회사 ID와 회사명 `title`을 가진 유일한 `a#companysum`이 있다.
- 회사 칸의 모든 이미지에는 비어 있지 않은 `alt`가 있다.
- 제목 칸에는 표시 제목과 필수 식별값 `acpt_no`를 가진 유일한 공시 링크가 있다.
- 공시일은 네 자리 연도로 시작한다.

## 출력 형식

- 연도별 조각은 SQLite FTS5 표를 사용한다.
- `sqlite_manifest.json`에는 원본 경로, 테이블 이름, 전체 원본·중복·저장 행 수가 있다.
- 연도별 SQLite 경로와 저장 행 수를 기록한다.
- 페이지별 원본 파일, 페이지 번호와 원본·중복·저장 행 수를 기록한다.

## 검증식

- 페이지별 `원본 행 수 = 저장 행 수 + 중복 행 수`
- 전체 `원본 행 수 = 실제 SQLite 행 수 + 중복 행 수`
- 연도별 실제 SQLite 행 수 = manifest의 연도별 저장 행 수
- 연도별 저장 행 수 합계 = manifest의 전체 저장 행 수
