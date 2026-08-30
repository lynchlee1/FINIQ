# 01 파일과 저장 형식

- KIND 조건검색 응답을 입력으로 받아 `<data_root>/01-list/<START_DATE>_<END_DATE>`에 `*_post_page_*.body`, `kind_workflow.input.json`, `kind_workflow.checkpoint.json`을 저장한다.
- `START_DATE`와 `END_DATE`는 실제 요청 기간을 `YYYYMMDD` 형식으로 기록한 값이다.

## `<data_root>/01-list/<START_DATE>_<END_DATE>/*_post_page_*.body`

- KIND 조건검색 응답 본문을 페이지별로 보존한 출력 파일이다.

## `<data_root>/01-list/<START_DATE>_<END_DATE>/kind_workflow.input.json`

- 다운로드에 사용한 검색 조건과 요청 metadata를 기록한 출력 파일이다.
- `format`은 `finiq_kind_workflow_input_v1`이다.
- 현재 `format`과 필수 필드를 기록한다.
- `search_filters`의 공시유형은 `disclosure_type_groups`만 입력한다.
- `disclosureTypeArrXX`, `disclosureTypeXX`, `pDisclosureTypeXX`는 `disclosure_type_groups`에서 만들며 직접 입력하지 않는다.
- 시장, 증권 종류와 공시 유형은 허용된 값만 사용한다.
- 저장된 검색 조건은 현재 형식으로 정확히 바꿀 수 있어야 한다.
- 실행 요청의 `output_directory`는 저장 위치를 정할 때만 사용하며 이 JSON에는 기록하지 않는다.

### 기본값

- 회사명과 제출인은 `""`, 시장과 증권 종류는 `전체`다.
- 처리 방법을 고르지 않으면 연도 단위로 나눈다.

## `<data_root>/01-list/<START_DATE>_<END_DATE>/kind_workflow.checkpoint.json`

- 페이지별 다운로드 진행 내역과 검증 상태를 기록한 출력 파일이다.
- `saved_files`와 `last_saved_file`은 이 JSON이 있는 폴더를 기준으로 한 상대 파일명이다.
- 내장된 `input`에도 `output_directory`를 기록하지 않는다.
