# Ontology 공통 사양

> **문서 목적:** 여러 Ontology 화면이 분석 자료를 찾고 합치며 작업 상태를 다루는 공통 규칙을 설명한다.
>
> **다루지 않는 내용:** 공시 00~09단계 동작은 [공시분석 공통 사양](../../disclosures/common/reference.md)에서 설명한다.

처음 작업하는 흐름은 [FINIQ 공통 흐름 익히기](../../common/getting-started/tutorials.md)에서 익힌다.

## 문서 안내

아래 절은 해당 화면만 따르는 규칙을 설명한다.

**[Quantiwise](../quantiwise/reference.md)** — Excel 미리보기, Parquet 변환하기·미리보기·병합하기

**[Graph View](../graph-view/reference.md)** — 회사별 공시 시간선과 공시 관계 그래프 화면

**[Chart View](../chart-view/reference.md)** — 회사 가격 조회와 주가-공시 차트

**[공시 분석](../disclosure-analysis/reference.md)** — Triple Barrier 실행과 저장 결과

## 함께 쓰는 사양

### 작업공간

- 공시 자료는 [공시분석 공통 사양](../../disclosures/common/reference.md)에 정한 `01-list`부터 `07-converted`까지 표준 경로를 사용한다. Ontology 화면은 개별 단계 경로를 보내지 않는다.
- `작업공간 디렉토리` 아래 `database/00-stock`에 주가 자료를 둔다.
- 항목별 Parquet은 `database/00-stock/by_item`에 둔다.

### 비동기 작업

- 진행 내역 최근 100줄을 메모리에 보관한다.
- 끝난 작업은 마지막 갱신 뒤 기본 60분이 지나면 메모리에서 지운다.

### 화면 표시

- 공통 표시와 비동기 작업 복구 규칙은 [공통 화면 사양](../../common/common-ui/reference.md)를 따른다.
- 빈 값은 문맥에 따라 `-` 또는 `N/A`로 표시하고 숫자 `0`은 그대로 표시한다.

### 진행 내역

**Ontology 작업** — 최근 100줄

**Quantiwise** — 최근 30줄

### 결과 예시

**회사 badge** — 3개

**그래프 방문 기록** — 10개

**Quantiwise 계정 문제** — 5개

**Quantiwise 미리보기** — 12열

**Quantiwise 중복·불일치 항목** — 20개

## 정상 동작

### 회사 자료 병합

- 여러 폴더에서 회사 ID가 같은 자료를 합칠 때는 먼저 읽은 회사명·회사 ID·시장을 유지한다. 먼저 읽은 값이 비어 있으면 뒤에 읽은 값으로 채우고 badge는 중복 없이 합친다.
- `acpt_no`가 같은 공시는 먼저 읽은 한 건만 남기고 제거한 건수를 집계한다.

### `storage-utility`

- 덮어쓰기가 꺼진 상태에서 목적지에 같은 이름을 가진 파일이 있으면 기존 파일을 유지하고 새 원본 파일은 옮기지 않는다.

## 복구 동작

아래 경로는 `src/` 기준이다.

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
  - 회사 목록은 사용할 파일이 없거나 읽기에 실패하면 빈 목록을 반환하고, 분석은 빈 차트와 안내 문구를 반환한다. 내보내기는 사용할 파일이 없으면 실패 처리한다.

아래 경로는 `src/finiq/market_desk/web/features/` 기준이다.

- **market_data/discovery.py**
- **현재 선택한 기본 원본을 사용할 수 없음**
  - 회사 분류는 `kind.company_classification.sqlite`를 먼저 찾고, 없으면 탐색 결과에서 첫 파일을 사용한다.
  - 가격 원본은 현재 선택 경로가 탐색 결과에 있으면 유지하고, 없으면 첫 가격 폴더를 사용한다. 탐색 결과가 없으면 `null`을 반환한다.

- **market_data/service_common.py, market_data/service_payloads.py, market_data/service_insight.py**
- **회사 응답에서 식별값·건수·기간·요약 metadata 일부가 빠짐**
  - 회사 key는 `company_key`, `company_id`, `company_name`, 빈 문자열 순서로 사용하고, `disclosure_count`가 없으면 `disclosures` 목록 길이를 사용한다.
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
  - 설치된 `config.py` 상위 폴더에서 `src/finiq`를 다시 찾고, 그 위치도 맞지 않으면 현재 실행 폴더를 프로젝트 루트로 사용한다.

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

### 정상 동작

#### 병렬 처리

- worker 값을 입력하지 않으면 실행 환경에서 확인한 CPU 수를 사용한다.
- 입력한 worker 수는 CPU 수와 실제 작업 수를 넘지 않게 줄인다.
- 병렬 처리를 지원하지 않거나 작업이 하나이면 worker 1개를 사용한다.

#### 회사 검색 응답

- 회사 검색은 SQLite 회사에 Quantiwise 가격 mapping에만 있는 회사를 추가한다. 추가 회사는 시장·공시일을 빈 값, 공시 건수를 0으로 두고 가격 자료가 있는 것으로 표시한다.
- 시장을 알 수 없는 추가 회사는 전체 시장 검색에만 포함한다.
- 검색 결과는 요청한 `limit`만큼 반환한다. 값을 입력하지 않으면 30건을 사용하며 `total`에는 전체 건수를 기록한다.

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
