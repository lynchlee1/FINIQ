# 제목 조회와 공시 선택 Reference

## 경로

- `<data_root>/02-table/sqlite_manifest.json`과 그 파일이 가리키는 `<data_root>/02-table/<YYYY>.sqlite`를 입력으로 받아 `<data_root>/03-filter`에 `<workflow-name>.json`과 `<mode>/filtered.json`을 저장한다.

## 입력 형식

### `sqlite_manifest.json`

- 검색할 SQLite 조각과 원본·중복·저장 행 수를 기록한 파일이다.

### `<YYYY>.sqlite`

- 연도별 공시 레코드를 검색하는 SQLite 조각이다.

## 출력 형식

### `<workflow-name>.json`

- 검색 조건, 실행 상태, 완료 또는 중단 결과를 함께 관리하는 원본 파일이다.

### `<mode>/filtered.json`

- `<workflow-name>.json`의 선택 결과를 다음 작업에 전달하는 mode별 파생 파일이다.
- `03-filter` 바로 아래에는 `filtered.json`을 만들지 않는다.

## 상태와 값

- 실행 상태는 대기 `ready`, 실행 중 `running`, 중단 `interrupted`, 완료 `completed`, 실패 `failed`다.
