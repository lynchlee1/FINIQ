# KIND Search Result Download Reference

## Paths

- KIND 조건검색 응답을 입력으로 받아 `<data_root>/01-list/<START_DATE>_<END_DATE>`에 `*_post_page_*.body`, `kind_workflow.input.json`, `kind_workflow.checkpoint.json`을 저장한다.
- `START_DATE`와 `END_DATE`는 한 요청을 연도 경계로 나눈 기간의 실제 시작일과 종료일이며 `YYYYMMDD` 형식으로 기록한다. 기간 폴더 하나가 반드시 달력 연도 전체를 뜻하지는 않는다.
- 같은 연도에 여러 번 이어받으면 각 요청의 기간별 폴더를 나란히 보존한다. 앞선 폴더를 확장하거나 합치지 않는다.

### `<data_root>/01-list/<START_DATE>_<END_DATE>/*_post_page_*.body`

#### I/O Structure

- KIND 조건검색 응답 본문을 페이지별로 보존한 출력 파일이다.

### `<data_root>/01-list/<START_DATE>_<END_DATE>/kind_workflow.input.json`

#### I/O Structure

- 다운로드에 사용한 검색 조건과 요청 metadata를 기록한 출력 파일이다.
- `format`은 `finiq_kind_workflow_input_v1`이다.
- 현재 `format`과 필수 필드를 기록한다.
- `search_filters`의 공시유형은 `disclosure_type_groups`만 입력한다.
- `disclosureTypeArrXX`, `disclosureTypeXX`, `pDisclosureTypeXX`는 `disclosure_type_groups`에서 만들며 직접 입력하지 않는다.
- 시장, 증권 종류와 공시 유형은 허용된 값만 사용한다.
- 저장된 검색 조건은 현재 형식으로 정확히 바꿀 수 있어야 한다.
- 실행 요청의 `output_directory`는 저장 위치를 정할 때만 사용하며 이 JSON에는 기록하지 않는다.

#### Defaults and Exceptions

- 회사명과 제출인은 `""`, 시장과 증권 종류는 `전체`다.
- 처리 방법을 고르지 않으면 연도 단위로 나눈다.

### `<data_root>/01-list/<START_DATE>_<END_DATE>/kind_workflow.checkpoint.json`

#### I/O Structure

- 페이지별 다운로드 진행 내역과 검증 상태를 기록한 출력 파일이다.
- `saved_files`와 `last_saved_file`은 이 JSON이 있는 폴더를 기준으로 한 상대 파일명이다.
- 내장된 `input`에도 `output_directory`를 기록하지 않는다.

## Existing Data Inspection

### Detection and Verification

#### I/O Structure

- 검증 대상은 `*_post_page_*.body`가 있는 단일 결과 디렉터리나 연도별 하위 폴더다. 본문 파일이 없는 폴더는 이름이 날짜 형식과 비슷해도 기존 범위로 반환하지 않는다.
- 연도 분할 폴더의 `YYYYMMDD_YYYYMMDD` 기간과 `kind_workflow.input.json`의 `start_date`, `end_date`가 다르면 해당 범위의 `status`는 `stale`이다.
- 각 범위는 현재 검색 조건과 저장 조건의 비교 결과를 `filters_match`와 `metadata_status`로 반환한다. 어느 범위라도 다르면 전체 재사용과 다운로드 연결을 막는다.
- `disclosure_type_groups`는 빈 그룹을 제외하고 그룹별 코드 집합을 비교한다. 같은 코드를 선택한 순서는 비교 결과에 영향을 주지 않는다.
- KIND 재검증을 실행하면 각 범위의 로컬 건수와 현재 KIND 건수를 `local_count`, `kind_count`로 반환한다. 페이지 구조나 원격 건수 검증에 실패한 범위는 `status=stale`과 `error_detail`을 반환한다.
- 로컬 건수는 유효한 공시 링크를 가진 모든 행을 포함한다. `a#companysum`이 없는 행도 회사 관계가 없는 공시로 계산한다.
- `a#companysum`이 둘 이상이거나 공시 행을 해석할 수 없으면 `error_detail`에 원본 파일과 행 위치를 포함해 실패 처리한다.
- 백그라운드 검사 진행 내역에는 로컬 검사 worker 수, KIND 조회 대기·시작과 범위별 완료가 포함된다. 여러 기간의 로컬 검사는 병렬 실행하지만 KIND 현재 건수 조회는 한 번에 하나씩 실행한다.

### Cleanup

#### I/O Structure

- 정리 응답의 `format`은 `kind_download_folder_cleanup_v1`이다.
- `dry_run=true`는 `deletion_candidate_count`와 `deletion_candidates`만 확인하며 파일을 지우지 않는다.
- 실제 삭제는 같은 검사 입력, `delete_confirmed=true`, `delete_confirmation_text="확인했습니다."`가 모두 필요하다.
- 실제 삭제 응답의 `deleted_files`와 `deleted_count`는 처리 내역이다. 응답에 함께 있는 `deletion_candidates`는 삭제 전 감사 목록이므로 삭제 후 현재 실패 목록으로 사용하지 않는다.
- 페이지 번호 중복·누락, 페이지 크기 불일치, 기간 불일치나 읽을 수 없는 페이지네이션이 발견되면 해당 기간의 본문과 workflow 보조 파일을 같은 삭제 후보 목록에 넣는다.
- 취소 요청은 삭제 묶음을 시작하기 전에 확인한다. 삭제가 시작된 뒤에는 확인된 후보 묶음을 끝까지 처리해 본문과 workflow 보조 파일 사이에 취소로 인한 부분 상태를 만들지 않는다.

### Inspection-to-download transition

#### I/O Structure

- 검사 완료 후 다운로드를 시작할 때는 완료된 검사 작업 ID를 `inspection_job_id`로 함께 보낸다.
- 같은 `inspection_job_id`로 다운로드 시작을 다시 요청하면 기존 다운로드 작업을 반환하며 새 작업을 중복 생성하지 않는다.
