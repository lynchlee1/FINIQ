# Disclosure Filtering Reference

## Paths

- `<data_root>/02-table/sqlite_manifest.json`과 그 파일이 가리키는 `<data_root>/02-table/<YYYY>.sqlite`를 입력으로 받아 `<data_root>/03-filter/<mode>/filter.json`에 조건과 실행 상태를, 같은 mode 폴더의 `filtered.json`에 전달 결과를 저장한다.

### `<data_root>/02-table/sqlite_manifest.json`

#### I/O Structure

- 검색할 SQLite 조각과 원본·중복·저장 행 수를 기록한 입력 파일이다.

### `<data_root>/02-table/<YYYY>.sqlite`

#### I/O Structure

- 연도별 공시 레코드를 검색하는 입력 SQLite 조각이다.

### `<data_root>/03-filter/<mode>/filter.json`

#### I/O Structure

- mode를 정의하는 검색 조건, 실행 상태, 실행 metadata와 완료 또는 중단 결과를 함께 관리하는 원본 출력 파일이다.
- 실행 상태는 `ready`, `running`, `interrupted`, `completed`, `failed`다.
- 완료 결과는 `result`, 중단된 증분 결과는 `pending.result`에 둔다.
- 결과에는 적용한 조건, 원본 공시 건수, 검색 시작 위치, 검색 대상 건수, 검사 완료 건수, 검색 결과 건수와 선택한 공시의 `acpt_no`를 기록한다.
- 데이터베이스 입력은 실행 요청의 `data_root`로 정하고 manifest 절대 경로는 저장하지 않는다.

### `<data_root>/03-filter/<mode>/filtered.json`

#### I/O Structure

- 같은 mode의 `filter.json` 선택 결과를 다음 작업에 전달하는 파생 출력 파일이다.
- `format`은 `kind_disclosure_filter_v1`이고 객체 맨 위의 `disclosures` 목록에 선택한 공시를 둔다.
- 각 공시는 비어 있지 않은 `acpt_no`와 ISO 날짜로 시작하는 `disclosed_at`을 가진다.
- 회사 링크가 없던 공시는 `company_key`, `company_name`, `company_id`가 `null`이고, 원본 회사 칸 표시는 `company_cell_text`에 유지된다.
- `source_sqlite_manifest_path`는 저장하지 않는다.

#### Defaults and Exceptions

- `<data_root>/03-filter` 바로 아래에는 `filtered.json`을 만들지 않는다.
