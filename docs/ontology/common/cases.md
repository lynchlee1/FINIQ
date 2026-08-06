# Ontology 공통 사양 Cases

## 복구 동작

아래 경로는 `src/` 기준이다.

- **병렬 처리를 지원하지 않음**
  - worker 1개로 실행한다.

- **finiq/data_scraper/data/facade.py, finiq/market_desk/data/facade.py**
- **완료된 `classification` 결과가 없음**
  - `summary`와 `companies`가 빈 결과를 반환한다. index 조회이면 `shards`도 빈 목록으로 반환한다.

- **finiq/data_scraper/storage/classification_store.py**
- **폴더별 `classification` 부분 cache가 없거나 JSON 문법·형식·원본 signature·검증 상태가 현재 입력과 맞지 않음**
  - cache를 사용하지 않고 원본 결과 페이지를 다시 읽어 회사별 결과를 만든다.

- **finiq/data_scraper/workflow/workflow.py**
- **회사 분류·보조 JSON 내보내기·페이지 검증에 쓸 process pool을 만들거나 사용하다 `BrokenProcessPool`, 운영체제·권한·runtime 오류가 발생함**
  - 같은 대상 전체를 직렬 처리로 다시 실행한다. 이 목록에 포함되지 않는 오류는 대체 처리하지 않는다.

아래 경로는 `src/finiq/market_desk/web/` 기준이다.

- **routers/market_data.py**
- **회사·분석·내보내기 요청에서 `classification` 경로가 빠졌거나 실제 경로가 없음**
  - 회사 목록은 존재하는 요청 경로, 존재하는 공통 설정 경로, 작업공간에서 찾은 기본 경로 순서로 사용한다.
  - 분석과 내보내기는 요청 경로가 없으면 공통 설정 경로를 사용한다. 공통 설정 경로도 비어 있을 때만 작업공간 기본 경로를 사용한다.
  - 회사 목록은 사용할 파일이 없거나 읽기에 실패하면 빈 목록을 반환하고 분석은 빈 차트와 안내 문구를 반환한다. 내보내기는 사용할 파일이 없으면 실패 처리한다.

아래 경로는 `src/finiq/market_desk/web/features/` 기준이다.

- **market_data/discovery.py**
- **현재 선택한 기본 원본을 사용할 수 없음**
  - 회사 분류는 `kind.company_classification.sqlite`를 먼저 찾고 없으면 탐색 결과에서 첫 파일을 사용한다.
  - 가격 원본은 현재 선택 경로가 탐색 결과에 있으면 유지하고 없으면 첫 가격 폴더를 사용한다. 탐색 결과가 없으면 `null`을 반환한다.

- **market_data/service_common.py, market_data/service_payloads.py, market_data/service_insight.py**
- **회사 응답에서 식별값·건수·기간·요약 metadata 일부가 빠짐**
  - 회사 key는 `company_key`, `company_id`, `company_name`, 빈 문자열 순서로 사용하고 `disclosure_count`가 없으면 `disclosures` 목록 길이를 사용한다.
  - 유효한 공시일이 하나도 없으면 조회 기본 기간을 이달 1일부터 오늘까지로 정한다. 형식이 맞지 않는 공시일은 기본 기간을 계산할 때 제외한다.
  - 회사별 상세값과 index metadata를 함께 읽을 때 회사 ID는 값이 있는 원천을 사용하고 badge는 상세값, index metadata 순서로 사용한다.
  - 회사 index에 `summary.companies`가 없으면 실제 회사 목록 길이를 사용한다. 명시된 0은 그대로 유지한다.

- **storage/partition.py**
- **나눌 파일명에서 첫 네 글자가 연도가 아니거나 이동 뒤에도 연도 폴더가 비지 않음**
  - 연도를 확인하지 못한 파일은 옮기지 않고 `skipped_invalid_year_files`에 포함한다.
  - 병합 대상 파일을 모두 처리한 뒤에도 파일이 남은 연도 폴더는 삭제하지 않는다.

아래 경로는 `src/finiq/` 기준이다.

- **market_desk/analytics/ontology_graph.py, market_desk/analytics/triple_barrier.py**
- **manifest shard에 적힌 절대 `path`를 사용할 수 없음**
  - manifest 폴더를 기준으로 `relative_path`를 사용한다. 이 값도 비어 있으면 shard 연도에 맞는 `<year>.sqlite`를 사용한다.

아래 경로는 저장소 최상위 폴더 기준이다.

- **src/finiq/config.py**
- **현재 실행 폴더에서 `src/finiq`를 찾지 못함**
  - 설치된 `config.py` 상위 폴더에서 `src/finiq`를 다시 찾고 그 위치도 맞지 않으면 현재 실행 폴더를 프로젝트 루트로 사용한다.

## 중단 조건

아래 경로는 `src/finiq/` 기준이다.

- **market_desk/analytics/ontology_graph.py, market_desk/analytics/triple_barrier.py**
- **SQLite manifest가 가리키는 shard 파일이 없음**
  - 일부 shard만 읽은 결과를 반환하거나 저장하지 않고 오류로 처리한다.

- **data_scraper/parse/_markup.py**
- **문자를 해석할 수 없거나 HTML 문서를 만들 수 없음**
  - 오류로 처리한다.

아래 경로는 `src/finiq/market_desk/web/features/` 기준이다.

- **market_data/service_sources.py**
- **요청한 SQLite manifest 파일이 없거나 형식 검사를 통과하지 못하거나, 지정한 폴더에 manifest가 하나만 있지 않음**
  - 오류로 처리한다.
- **manifest에 적힌 shard 항목이 현재 SQLite 파일을 가리키지 않거나 shard 건수 검사를 통과하지 못함**
  - 오류로 처리한다.
- **조회 대상 SQLite 표에 필수 열이 없음**
  - 오류로 처리한다.

- **market_data/service_insight.py**
- **요청에서 `stock_code_override`가 비어 있거나 숫자 6자리가 아님**
  - 오류로 처리한다.

아래 경로는 `src/finiq/market_desk/web/routers/` 기준이다.

- **market_data.py**
- **내보내기에 사용할 `classification` 경로가 끝까지 없거나 파일 생성이 실패함**
  - 오류로 처리한다.
- **분석 원본을 찾은 뒤 결과 생성이 실패함**
  - 오류로 처리한다.

## 화면과 서비스 계약

### 복구 동작

- 없음.

### 중단 조건

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

- **api/client.ts**
- **서버가 성공이 아닌 상태로 응답하거나 응답 내용을 읽을 수 없음**
  - 오류로 처리한다.

아래 경로는 저장소 최상위 폴더 기준이다.

- **src/finiq/concurrency.py**
- **worker 값이 정수가 아니거나 1보다 작음**
  - 오류로 처리한다.

- **src/finiq/config.py**
- **설정 파일을 읽지 못하거나 JSON 객체가 아님**
  - 오류로 처리한다.
- **`html_parse_mode`에 영문·숫자·점·밑줄·하이픈 밖의 문자가 있거나 첫 글자가 영문·숫자가 아님**
  - 오류로 처리한다.

## 조건부 동작

### 회사 자료 병합

- 여러 폴더에서 회사 ID가 같은 자료를 합칠 때는 먼저 읽은 회사명·회사 ID·시장을 유지한다. 먼저 읽은 값이 비어 있으면 뒤에 읽은 값으로 채우고 badge는 중복 없이 합친다.

- `acpt_no`가 같은 공시는 먼저 읽은 한 건만 남기고 제거한 건수를 집계한다.

### `storage-utility`

- 덮어쓰기가 꺼진 상태에서 목적지에 같은 이름을 가진 파일이 있으면 기존 파일을 유지하고 새 원본 파일은 옮기지 않는다.

### 병렬 처리

- worker 값을 입력하지 않으면 실행 환경에서 확인한 CPU 수를 사용한다.

- 작업이 하나이면 worker 1개를 사용한다.

- 입력한 worker 수가 CPU 수나 실제 작업 수보다 크면 둘 중 작은 값으로 줄인다.

### 회사 검색 응답

- 검색 결과는 요청한 `limit`만큼 반환한다. 값을 입력하지 않으면 30건을 사용하며 `total`에는 전체 건수를 기록한다.

- 시장을 알 수 없는 추가 회사는 전체 시장 검색에만 포함한다.
