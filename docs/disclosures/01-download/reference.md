# KIND 조건검색 결과 저장 Reference

## 경로

- KIND 조건검색 응답을 입력으로 받아 `<data_root>/01-list/<YYYYMMDD>_<YYYYMMDD>`에 `*_post_page_*.body`, `kind_workflow.input.json`, `kind_workflow.checkpoint.json`을 저장한다.

## 입력 형식

### KIND 조건검색 조건

- KIND에서 조건검색을 진행할 조건이다.

## 입력 제약과 기본값

### 검색 조건

- `search_filters`의 공시유형은 `disclosure_type_groups`만 입력한다.
- `disclosureTypeArrXX`, `disclosureTypeXX`, `pDisclosureTypeXX`는 `disclosure_type_groups`에서 만들며 직접 입력하지 않는다.
- 시장, 증권 종류와 공시 유형은 허용된 값만 사용한다.
- 저장된 검색 조건은 현재 형식으로 정확히 바꿀 수 있어야 한다.

### 기본값

- 회사명과 제출인은 `""`, 시장과 증권 종류는 `전체`다.
- 처리 방법을 고르지 않으면 연도 단위로 나눈다.

## 출력 형식

### `*_post_page_*.body`

- KIND 조건검색 응답 본문을 페이지별로 보존한 파일이다.

### `kind_workflow.input.json`

- 다운로드에 사용한 검색 조건과 요청 metadata를 기록한 파일이다.
- 정상 다운로드가 끝났을 때만 만든다.
- `format`은 `finiq_kind_workflow_input_v1`이다.
- 본문 파일이 있는 폴더에는 읽을 수 있고 필수 필드와 현재 `format`을 갖춘 `kind_workflow.input.json`이 있어야 한다.

### `kind_workflow.checkpoint.json`

- 페이지별 다운로드 진행 내역과 검증 상태를 기록한 파일이다.
- 저장된 마지막 페이지와 pagination 정보를 재개 기준으로 사용한다.

### `<YYYYMMDD>_<YYYYMMDD>`

- 하위 폴더 이름에는 연도별 시작일과 종료일을 YYYYMMDD 형식으로 기록한다.

## 출력 무결성

### 다운로드 목록 일관성

- 한 기간의 모든 페이지를 받은 직후 같은 검색 조건으로 첫 페이지를 다시 요청한다.
- 다시 받은 페이지 정보와 공시 행이 첫 다운로드와 같을 때만 새 임시 결과를 게시한다.
- 두 목록이 다르면 새 임시 결과를 게시하지 않고 이전 기간 결과를 유지한다.

### 기존 결과 무결성

- `kind_workflow.input.json`의 조건으로 연도별 재검색한 전체 공시 수는 저장값과 같아야 한다.
- 페이지 번호는 중복 없이 1부터 연속해야 한다.
- 본문 간 전체 페이지 수와 건수는 일치해야 한다.

## 재사용과 복구

- 기존 결과 폴더를 읽을 수 없으면 빈 결과로 취급하지 않는다.
- 저장된 pagination을 읽을 수 없으면 앞선 페이지 값이나 `null` 요약으로 대신하지 않는다.
- 무결성 검증이 실패한 기간의 본문과 workflow 보조 파일은 현재 실행 입력에서 제외한다.
- 재다운로드를 확인하면 빈 시작 상태에서 전체 검색기간의 페이지를 다시 만든다.
