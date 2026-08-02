# Ontology 페이지 문서

> **문서 목적:** 공시 00~09 화면 밖의 문서를 연결하고 여러 Ontology 화면이 함께 쓰는 규칙을 설명한다.
>
> **다루지 않는 내용:** 공시 00~09단계의 동작은 [공시분석 단계 문서](../disclosures/README.md)에서 설명한다.

## 문서 안내

각 하위 문서는 해당 화면에만 적용되는 규칙만 설명한다.

| 문서 | 화면과 범위 |
|---|---|
| [Quantiwise](./quantiwise/README.md) | Excel 미리보기, Parquet 변환하기·미리보기·병합하기 |
| [Graph View](./graph-view/README.md) | 회사별 공시 시간선과 공시 관계 그래프 화면 |
| [Chart View](./chart-view/README.md) | 회사 가격 조회와 주가-공시 차트 |
| [공시 분석](./disclosure-analysis/README.md) | Triple Barrier 실행과 저장 결과 |

## Feature

### 공통 작업공간

- 표준 작업공간은 [공시 작업 폴더](../workspace-layout.md)의 `01-list`부터 `07-converted`까지 정해진 경로를 사용한다. 화면은 개별 단계 경로를 보내지 않는다.
- 주가 데이터는 `database/00-stock`을 루트로 사용하고 항목별 Parquet은 `database/00-stock/by_item`에 둔다.

### 회사 자료 병합

- 같은 회사 ID의 자료를 여러 폴더에서 합칠 때 먼저 읽은 회사명·회사 ID·시장을 유지한다. 먼저 읽은 값이 비어 있으면 뒤 자료의 값으로 채우고 badge는 중복 없이 합친다.
- `acpt_no`가 같은 공시는 먼저 읽은 한 건만 남기고 제거한 건수를 집계한다.

### `storage-utility`

- 덮어쓰기가 꺼져 있고 목적지에 같은 이름의 파일이 이미 있으면 기존 목적지 파일을 유지하고 새 원본 파일은 옮기지 않는다.

## Fallback

아래 경로는 `src/` 기준이다.

- **finiq/data_scraper/data/facade.py, finiq/market_desk/data/facade.py**
- **완료된 `classification` 결과가 없음**
  - `summary`와 `companies`가 빈 결과를 반환한다. index 조회이면 `shards`도 빈 목록으로 반환한다.

- **finiq/data_scraper/storage/classification_store.py**
- **폴더별 `classification` 부분 cache가 없거나 JSON 문법·형식·원본 signature·검증 상태가 현재 입력과 맞지 않음**
  - cache를 사용하지 않고 원본 결과 페이지를 다시 읽어 회사별 결과를 만든다.

- **finiq/data_scraper/workflow/workflow.py**
- **회사 분류·보조 JSON 내보내기·페이지 검증의 process pool을 만들거나 사용하는 중 `BrokenProcessPool`, 운영체제·권한·runtime 오류가 발생함**
  - 같은 대상 전체를 직렬 처리로 다시 실행한다. 이 목록에 포함되지 않는 오류는 대체 처리하지 않는다.

아래 경로는 `src/finiq/market_desk/web/` 기준이다.

- **routers/market_data.py**
- **회사·분석·내보내기 요청의 `classification` 경로가 없거나 존재하지 않음**
  - 회사 목록은 존재하는 요청 경로, 존재하는 공통 설정 경로, 작업공간에서 찾은 기본 경로 순서로 사용한다.
  - 분석과 내보내기는 요청 경로가 없으면 공통 설정 경로를 사용하고, 공통 설정 경로도 비어 있을 때만 작업공간의 기본 경로를 사용한다.
  - 회사 목록은 사용할 파일이 없거나 읽기에 실패하면 빈 목록을 반환하고, 분석은 빈 차트와 안내 문구를 반환한다. 내보내기는 사용할 파일이 없으면 실패 처리한다.

아래 경로는 `src/finiq/market_desk/web/features/` 기준이다.

- **market_data/discovery.py**
- **현재 선택한 기본 원본을 사용할 수 없음**
  - 회사 분류는 `kind.company_classification.sqlite`를 먼저 찾고, 없으면 탐색 결과의 첫 파일을 사용한다.
  - 가격 원본은 현재 선택 경로가 탐색 결과에 있으면 유지하고, 없으면 첫 가격 폴더를 사용한다. 탐색 결과가 없으면 `null`을 반환한다.

- **market_data/service_common.py, market_data/service_payloads.py, market_data/service_insight.py**
- **회사 응답의 식별값·건수·기간·요약 metadata 일부가 없음**
  - 회사 key는 `company_key`, `company_id`, `company_name`, 빈 문자열 순서로 사용하고, `disclosure_count`가 없으면 `disclosures` 목록 길이를 사용한다.
  - 유효한 공시일이 하나도 없으면 조회 기본 기간을 현재 달의 1일부터 오늘까지로 정한다. 형식이 맞지 않는 공시일은 기본 기간 계산에서 제외한다.
  - 회사별 상세값과 index metadata를 함께 읽을 때 회사 ID는 값이 있는 원천을 사용하고 badge는 상세값, index metadata 순서로 사용한다.
  - 회사 index의 `summary.companies`가 없으면 실제 회사 목록 길이를 사용한다. 명시된 0은 그대로 유지한다.

- **storage/partition.py**
- **분할할 파일명의 첫 네 글자가 연도가 아니거나 이동 뒤 연도 폴더가 비지 않음**
  - 연도를 확인하지 못한 파일은 옮기지 않고 `skipped_invalid_year_files`에 포함한다.
  - 병합 대상 파일을 모두 처리한 뒤에도 파일이 남은 연도 폴더는 삭제하지 않는다.

아래 경로는 `src/finiq/` 기준이다.

- **market_desk/analytics/ontology_graph.py, market_desk/analytics/triple_barrier.py**
- **manifest shard의 절대 `path`를 사용할 수 없음**
  - manifest 폴더 기준 `relative_path`를 사용한다. 이 값도 비어 있으면 shard 연도의 `<year>.sqlite`를 사용한다.

아래 경로는 저장소 최상위 폴더 기준이다.

- **src/finiq/config.py**
- **현재 실행 폴더에서 `src/finiq`를 찾지 못함**
  - 설치된 `config.py`의 상위 폴더에서 `src/finiq`를 다시 찾고, 그 위치도 맞지 않으면 현재 실행 폴더를 프로젝트 루트로 사용한다.

## Shutdown

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
- **manifest의 shard 항목이 현재 SQLite 파일을 가리키지 않거나 shard 건수 검사를 통과하지 못함**
  - 오류로 처리한다.
- **조회 대상 SQLite 표에 필수 열이 없음**
  - 오류로 처리한다.

- **market_data/service_insight.py**
- **요청의 `stock_code_override`가 비어 있거나 숫자 6자리가 아님**
  - 오류로 처리한다.

아래 경로는 `src/finiq/market_desk/web/routers/` 기준이다.

- **market_data.py**
- **내보내기에 사용할 `classification` 경로가 끝까지 없거나 파일 생성이 실패함**
  - 오류로 처리한다.
- **분석 원본을 찾은 뒤 결과 생성이 실패함**
  - 오류로 처리한다.

## Serving

**Feature**

**병렬 처리 기능**

- worker 값을 입력하지 않으면 실행 환경의 CPU 수를 사용한다.
- 입력한 worker 수는 CPU 수와 실제 작업 수를 넘지 않게 줄인다.
- 병렬 처리를 지원하지 않거나 작업이 하나이면 worker 1개를 사용한다.

**회사 검색 응답 기능**

- 회사 검색은 SQLite 회사에 Quantiwise 가격 mapping에만 있는 회사를 추가한다. 추가 회사는 시장·공시일을 빈 값, 공시 건수를 0으로 두고 가격 자료가 있는 것으로 표시한다.
- 시장을 알 수 없는 추가 회사는 전체 시장 검색에만 포함한다.
- 검색 결과는 요청한 `limit`만큼 반환한다. 값을 입력하지 않으면 30건을 사용하며 `total`에는 전체 건수를 기록한다.

**작업 상태 보관 기능**

- 진행 내역은 최근 100줄만 메모리에 보관한다.
- 끝난 작업은 마지막 갱신 뒤 설정한 시간이 지나면 메모리에서 지운다. 기본 보존 시간은 60분이다.

**화면 표시 범위**

- 회사 badge는 3개까지만 보여 준다. 전체 회사 자료는 바꾸지 않는다.
- 그래프 이름이 너무 길면 끝을 `…`로 줄이고 방문 기록은 최근 10개만 보여 준다. 원본 그래프는 바꾸지 않는다.
- Quantiwise 화면은 진행 내역 30줄, 계정 문제 5개, 미리보기 12열, 중복·불일치 항목 20개까지만 보여 준다. 전체 결과와 개수는 바꾸지 않는다.

**Fallback**

**빈 값 표시 기능**

- 차트, 그래프와 Quantiwise의 빈 값은 `-` 또는 `N/A`로 표시한다.
- 숫자 `0`은 빈 값으로 바꾸지 않는다.

**설정 저장 실패 후 화면 유지 기능**

- 설정을 저장하지 못해도 현재 입력값은 화면에 남긴다.
- 화면 값이 남아 있어도 서버 설정은 바뀌지 않을 수 있다.

**Shutdown**

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

- **hooks/useJobPolling.ts**
- **작업 상태를 확인하지 못함**
  - 오류로 처리한다. 서버가 `404`를 반환하면 저장한 작업 ID도 지운다.

- **hooks/useJobStreaming.ts**
- **서버가 결과 본문을 보내지 않거나, 실패 이유를 읽을 수 없거나, 오류 알림을 보내거나, 결과 없이 전송을 끝냄**
  - 오류로 처리한다.

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
- **`html_parse_mode`에 영문·숫자·점·밑줄·하이픈 이외의 문자가 있거나 첫 글자가 영문·숫자가 아님**
  - 오류로 처리한다.
