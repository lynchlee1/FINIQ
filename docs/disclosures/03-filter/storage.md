# 03 파일과 저장 형식

- 기본 필터는 `<data_root>/02-table/sqlite_manifest.json`과 그 파일이 가리키는 `<data_root>/02-table/<YYYY>.sqlite`를 입력으로 받아 `<data_root>/03-filter/<mode>/filter.json`에 조건과 실행 상태를, 같은 mode 폴더의 `filtered.json`에 전달 결과를 저장한다.
- 파생 필터는 `<data_root>/03-filter/<parent_mode>/filtered.json`을 입력으로 받아 `<data_root>/03-filter/<parent_mode>/subfilters/<mode>/filter.json`과 `filtered.json`을 저장한다.

## `<data_root>/02-table/sqlite_manifest.json`

- 검색할 SQLite 조각과 원본·중복·저장 행 수를 기록한 입력 파일이다.

## `<data_root>/02-table/<YYYY>.sqlite`

- 연도별 공시 레코드를 검색하는 입력 SQLite 조각이다.

## `<data_root>/03-filter/<mode>/filter.json`

- mode를 정의하는 검색 조건, 실행 상태, 실행 metadata와 결과 요약을 관리하는 원본 출력 파일이다.
- 실행 상태는 `ready`, `running`, `interrupted`, `completed`, `failed`다.
- 완료 결과는 기존 표준 전달 파일인 `filtered.json`, 중단된 증분 결과는 `filter.pending.json`에 두고 `filter.json`의 `result_file` 또는 `pending_file`로 참조한다.
- `result_fingerprint`와 `pending_fingerprint`는 각 결과 파일의 canonical JSON SHA-256이며 파일명이 아니라 metadata에만 기록한다. 명시적 검사나 실행 시 파일 내용과 대조하고, 목록 조회는 결과 파일을 열지 않는다.
- 결과에는 적용한 조건, 02단계 입력 내용의 `source_fingerprint`, 검색 범위와 선택한 공시의 `acpt_no`를 기록한다.
- 데이터베이스 입력은 실행 요청의 `data_root`로 정하고 manifest 절대 경로는 저장하지 않는다.

## `<data_root>/03-filter/<mode>/filtered.json`

- 같은 mode의 `filter.json` 선택 결과를 다음 작업에 전달하는 파생 출력 파일이다.
- `format`은 `kind_disclosure_filter_v1`이고 객체 맨 위의 `disclosures` 목록에 선택한 공시를 둔다.
- 각 공시는 비어 있지 않은 `acpt_no`와 ISO 날짜로 시작하는 `disclosed_at`을 가진다.
- 회사 링크가 없던 공시는 `company_key`, `company_name`, `company_id`가 `null`이고, 원본 회사 칸 표시는 `company_cell_text`에 유지된다.
- `source_sqlite_manifest_path`는 저장하지 않는다.

### 제약과 분기

- `<data_root>/03-filter` 바로 아래에는 `filtered.json`을 만들지 않는다.

## `<data_root>/03-filter/<parent_mode>/subfilters/<mode>/filter.json`

- 완료된 기본 필터에 추가 조건을 적용하는 한 단계 파생 필터의 원본 출력 파일이다.
- `mode`에는 자식 이름, `parent_mode`에는 상위 기본 필터 이름을 기록한다.
- `parent_result_fingerprint`는 실행에 사용한 상위 `filtered.json` 결과를 식별한다.
- 상위 결과의 현재 fingerprint와 다르면 파생 결과는 stale이며 후속 단계의 입력으로 사용할 수 없다.

## `<data_root>/03-filter/<parent_mode>/subfilters/<mode>/filtered.json`

- 파생 필터가 선택한 공시만 담는 전달 파일이며 모든 `acpt_no`는 상위 `<parent_mode>/filtered.json`에도 존재한다.
- 상위 필터가 변경되면 이 파일을 자동 보완하거나 다른 입력으로 대신하지 않는다.

### 제약과 분기

- 파생 필터 아래에 다시 `subfilters`를 만들지 않는다.
