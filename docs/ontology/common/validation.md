# 검증과 중단

아래 조건에서는 일부 결과나 보정값을 반환하지 않고 오류로 처리한다.

## 분석 입력

아래 경로는 `src/finiq/` 기준이다.

### SQLite shard

- **market_desk/analytics/ontology_graph.py, market_desk/analytics/triple_barrier.py**
- **SQLite manifest가 가리키는 shard 파일이 없음**
  - 일부 shard만 읽은 결과를 반환하거나 저장하지 않고 오류로 처리한다.

### HTML 해석

- **data_scraper/parse/_markup.py**
- **문자를 해석할 수 없거나 HTML 문서를 만들 수 없음**
  - 오류로 처리한다.

아래 경로는 `src/finiq/market_desk/web/features/` 기준이다.

### SQLite 입력

- **market_data/service_sources.py**
- **요청한 SQLite manifest 파일이 없거나 형식 검사를 통과하지 못하거나, 지정한 폴더에 manifest가 하나만 있지 않음**
  - 오류로 처리한다.
- **manifest에 적힌 shard 항목이 현재 SQLite 파일을 가리키지 않거나 shard 건수 검사를 통과하지 못함**
  - 오류로 처리한다.
- **조회 대상 SQLite 표에 필수 열이 없음**
  - 오류로 처리한다.

### 종목 코드

- **market_data/service_insight.py**
- **요청에서 `stock_code_override`가 비어 있거나 숫자 6자리가 아님**
  - 오류로 처리한다.

아래 경로는 `src/finiq/market_desk/web/routers/` 기준이다.

### 분석과 내보내기

- **market_data.py**
- **내보내기에 사용할 `classification` 경로가 끝까지 없거나 파일 생성이 실패함**
  - 오류로 처리한다.
- **분석 원본을 찾은 뒤 결과 생성이 실패함**
  - 오류로 처리한다.

## 화면과 서비스

별도 복구 동작은 없다.

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

### API 응답

- **api/client.ts**
- **서버가 성공이 아닌 상태로 응답하거나 응답 내용을 읽을 수 없음**
  - 오류로 처리한다.

아래 경로는 저장소 최상위 폴더 기준이다.

### 실행 설정

- **src/finiq/concurrency.py**
- **worker 값이 정수가 아니거나 1보다 작음**
  - 오류로 처리한다.

- **src/finiq/config.py**
- **설정 파일을 읽지 못하거나 JSON 객체가 아님**
  - 오류로 처리한다.
- **`html_parse_mode`에 영문·숫자·점·밑줄·하이픈 밖의 문자가 있거나 첫 글자가 영문·숫자가 아님**
  - 오류로 처리한다.
