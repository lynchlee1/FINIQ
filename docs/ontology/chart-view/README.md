# Chart View

> **문서 목적:** 회사 가격 조회와 주가-공시 차트의 Feature, Fallback과 Shutdown을 설명한다.
>
> **다루지 않는 내용:** Triple Barrier 계산은 [공시 분석](../disclosure-analysis/README.md)에서 설명한다.

## Feature

아래 경로는 `src/finiq/` 기준이다.

- **market\_desk/analytics/chart.py**
- **공시 시각이 15:30 이후이거나 공시 기준일과 같은 날짜의 가격 봉이 없음**
  - 공시 연결 기준일을 다음 달력 날짜로 옮긴 뒤 그 날짜 이후의 첫 가격 봉에 marker를 연결한다. 그 뒤 가격 봉이 하나도 없으면 그 공시의 marker를 차트에서 제외한다.

- **market\_desk/analytics/ontology\_graph.py**
- **표시 빈도가 `자동`임**
  - 집계 전 가격 봉이 180개 이하면 `day`, 181~520개면 `week`, 521개 이상이면 `month`로 집계한다.

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

- **components/PriceChart.tsx**
- **현재 hover한 가격 봉이 없음**
  - 배열의 마지막 가격 봉을 차트 제목의 현재값으로 표시한다.

## Fallback

아래 경로는 `src/finiq/` 기준이다.

- **market_desk/analytics/company.py**
- **가격 조회에 쓸 KIND 회사 ID가 숫자이지만 6자리가 아님**
  - 5자리면 뒤에 `0`을 붙이고 더 짧으면 왼쪽을 `0`으로 채운다. 6자리보다 길거나 숫자가 아니면 종목 코드 후보를 만들지 않는다.
- **Excel 내보내기용 회사 ID가 `A######` 형식이 아니지만 5~6자의 영문·숫자 조합임**
  - 앞에 `A`를 붙여 내보낼 종목 코드로 사용한다.
- **일반 종목 코드 가격 조회가 실패하거나 빈 결과를 반환함**
  - `KRX-DELISTING:<ticker>`를 다시 조회해 상장폐지 종목 가격을 사용한다.
- **가격 행의 날짜 또는 OHLCV 값을 변환하지 못함**
  - 변환하지 못한 행만 제외하고 유효한 행을 날짜순으로 반환한다. 두 가격 원본에서 예외가 발생하지 않았지만 유효한 행이 없으면 빈 목록을 반환한다.

- **market_desk/analytics/chart.py**
- **공시 시각이나 가격 행의 날짜·OHLCV 값을 변환하지 못함**
  - 변환하지 못한 공시와 가격 행을 각각 제외한다. VWAP 열이나 값이 없으면 해당 값은 NaN으로 유지한다.

- **market_desk/analytics/disclosure_groups.py**
- **공시 제목 조건식을 논리식으로 해석하지 못함**
  - 조건식 전체가 제목에 포함되는지 검사한다. 어떤 조건에도 맞지 않으면 `기타`로 분류한다.

- **market_desk/analytics/ontology_graph.py**
- **6자리로 맞춘 회사 ID로 공시를 찾지 못함**
  - ID 끝의 `0`을 제거한 값이 5자리 이상이면 그 값으로 한 번 더 조회한다.
- **category `filtered.json` 행에 `company_id` 또는 `disclosed_date`가 없음**
  - 회사 ID는 `company_key`, 날짜는 `disclosed_at`의 앞 10글자를 사용한다.
- **SQLite shard에서 선택 회사·기간의 공시를 찾지 못함**
  - 선택한 공시 그룹에 해당하는 KIND category `filtered.json`을 조회한다. SQLite에서 한 건이라도 찾으면 category 파일은 읽지 않는다.
- **가격 Parquet, 선택 회사의 종목 열 또는 선택 기간의 가격 행이 없음**
  - 원인을 설명하는 문구와 함께 가격 봉·marker·시간선이 빈 응답을 반환한다.

아래 경로는 `src/finiq/market_desk/web/features/` 기준이다.

- **market_data/service_insight.py**
- **선택 종목의 가격 조회가 예외로 끝남**
  - 원인을 안내 문구로 남기고 가격 봉이 없는 공시 시간선 응답을 반환한다.
아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

- **lib/charts.ts**
- **가격 범위를 계산할 때 고가·저가가 없음**
  - 같은 자료의 `value`를 사용한다. 최솟값과 최댓값이 같으면 표시 범위를 위아래로 넓힌다.

- **components/PriceChart.tsx**
- **가격 봉의 OHLC 값 중 일부가 없음**
  - 빠진 값을 같은 봉의 `value`로 채운다.

## Shutdown

아래 경로는 `src/finiq/` 기준이다.

- **market\_desk/analytics/company.py**
- **일반 종목 코드와 `KRX-DELISTING:<ticker>` 중 하나 이상에서 예외가 발생했고 두 후보 모두 유효한 가격 행을 반환하지 못함**
  - 마지막으로 발생한 예외를 원인으로 연결한 가격 조회 오류를 발생시킨다.

- **market\_desk/analytics/ontology\_graph.py**
- **JSON에 NaN·Infinity가 들어가려 함**
  - 오류로 처리한다.
- **빈도가 `자동`·`일봉`·`3일봉`·`5일봉`·`7일봉`·`20일봉`·`월봉` 중 하나가 아님**
  - 오류로 처리한다.

- **market\_desk/web/features/market\_data/service\_common.py**
- **빈도가 `자동`·`일봉`·`주봉`·`월봉` 중 하나가 아님**
  - 오류로 처리한다.

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

- **lib/charts.ts**
- **차트 숫자가 유한하지 않음**
  - 오류로 처리한다.
