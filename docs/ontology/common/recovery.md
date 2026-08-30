# 복구

아래 경로는 `src/` 기준이다.

## 공시 분류 결과

- **finiq/data_scraper/data/facade.py, finiq/market_desk/data/facade.py**
- **완료된 `classification` 결과가 없음**
  - `summary`와 `companies`가 빈 결과를 반환한다. index 조회이면 `shards`도 빈 목록으로 반환한다.

- **finiq/data_scraper/storage/classification_store.py**
- **폴더별 `classification` 부분 cache가 없거나 JSON 문법·형식·원본 signature·검증 상태가 현재 입력과 맞지 않음**
  - cache를 사용하지 않고 원본 결과 페이지를 다시 읽어 회사별 결과를 만든다.

- **finiq/data_scraper/workflow/workflow.py**
- **공시 행에 회사 ID가 없음**
  - 공시를 임의 회사에 귀속하지 않는다. 회사별 결과에서는 제외하고 `unlinked_disclosures`에 포함하며, `parsed_disclosures = classified_disclosures + unlinked_disclosures`를 검증한다.

## 병렬 실행

- **병렬 처리를 지원하지 않음**
  - worker 1개로 실행한다.

- **finiq/data_scraper/workflow/workflow.py**
- **회사 분류·보조 JSON 내보내기·페이지 검증에 쓸 process pool을 만들거나 사용하다 `BrokenProcessPool`, 운영체제·권한·runtime 오류가 발생함**
  - 같은 대상 전체를 직렬 처리로 다시 실행한다. 이 목록에 포함되지 않는 오류는 대체 처리하지 않는다.

아래 경로는 `src/finiq/market_desk/web/` 기준이다.

## 작업공간 경로 선택

- **routers/market_data.py**
- **회사·분석·내보내기 요청에서 `classification` 경로가 빠졌거나 실제 경로가 없음**
  - 회사 목록은 존재하는 요청 경로, 존재하는 공통 설정 경로, 작업공간에서 찾은 기본 경로 순서로 사용한다.
  - 분석과 내보내기는 요청 경로가 없으면 공통 설정 경로를 사용한다. 공통 설정 경로도 비어 있을 때만 작업공간 기본 경로를 사용한다.
  - 회사 목록은 사용할 파일이 없거나 읽기에 실패하면 빈 목록을 반환하고 분석은 빈 차트와 안내 문구를 반환한다. 내보내기는 사용할 파일이 없으면 실패 처리한다.

아래 경로는 `src/finiq/market_desk/web/features/` 기준이다.

## 원본 탐색

- **market_data/discovery.py**
- **현재 선택한 기본 원본을 사용할 수 없음**
  - 회사 분류는 `kind.company_classification.sqlite`를 먼저 찾고 없으면 탐색 결과에서 첫 파일을 사용한다.
  - 가격 원본은 현재 선택 경로가 탐색 결과에 있으면 유지하고 없으면 첫 가격 폴더를 사용한다. 탐색 결과가 없으면 `null`을 반환한다.

## 회사 응답 보정

- **market_data/service_common.py, market_data/service_payloads.py, market_data/service_insight.py**
- **회사 응답에서 식별값·건수·기간·요약 metadata 일부가 빠짐**
  - 회사 key는 `company_key`, `company_id`, `company_name`, 빈 문자열 순서로 사용하고 `disclosure_count`가 없으면 `disclosures` 목록 길이를 사용한다.
  - 유효한 공시일이 하나도 없으면 조회 기본 기간을 이달 1일부터 오늘까지로 정한다. 형식이 맞지 않는 공시일은 기본 기간을 계산할 때 제외한다.
  - 회사별 상세값과 index metadata를 함께 읽을 때 회사 ID는 값이 있는 원천을 사용하고 badge는 상세값, index metadata 순서로 사용한다.
  - 회사 index에 `summary.companies`가 없으면 실제 회사 목록 길이를 사용한다. 명시된 0은 그대로 유지한다.

## 연도 폴더 정리

- **storage/partition.py**
- **나눌 파일명에서 첫 네 글자가 연도가 아니거나 이동 뒤에도 연도 폴더가 비지 않음**
  - 연도를 확인하지 못한 파일은 옮기지 않고 `skipped_invalid_year_files`에 포함한다.
  - 병합 대상 파일을 모두 처리한 뒤에도 파일이 남은 연도 폴더는 삭제하지 않는다.

아래 경로는 `src/finiq/` 기준이다.

## SQLite shard 경로

- **market_desk/analytics/ontology_graph.py, market_desk/analytics/triple_barrier.py**
- **manifest shard에 적힌 절대 `path`를 사용할 수 없음**
  - manifest 폴더를 기준으로 `relative_path`를 사용한다. 이 값도 비어 있으면 shard 연도에 맞는 `<year>.sqlite`를 사용한다.

아래 경로는 저장소 최상위 폴더 기준이다.

## 프로젝트 루트

- **src/finiq/config.py**
- **현재 실행 폴더에서 `src/finiq`를 찾지 못함**
  - 설치된 `config.py` 상위 폴더에서 `src/finiq`를 다시 찾고 그 위치도 맞지 않으면 현재 실행 폴더를 프로젝트 루트로 사용한다.
