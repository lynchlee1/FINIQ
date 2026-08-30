# Chart View 검증과 중단

아래 경로는 `src/finiq/` 기준이다.

## 가격 조회

- **market\_desk/analytics/company.py**
- **일반 종목 코드와 `KRX-DELISTING:<ticker>` 중 하나 이상에서 예외가 발생했고 두 후보 모두 유효한 가격 행을 반환하지 못함**
  - 마지막으로 발생한 예외를 원인으로 연결한 가격 조회 오류를 발생시킨다.

## 분석 입력

- **market\_desk/analytics/ontology\_graph.py**
- **JSON에 NaN·Infinity가 들어가려 함**
  - 오류로 처리한다.
- **빈도가 `자동`·`일봉`·`3일봉`·`5일봉`·`7일봉`·`20일봉`·`월봉` 중 하나가 아님**
  - 오류로 처리한다.

- **market\_desk/web/features/market\_data/service\_common.py**
- **빈도가 `자동`·`일봉`·`주봉`·`월봉` 중 하나가 아님**
  - 오류로 처리한다.

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

## 차트 값

- **lib/charts.ts**
- **차트 숫자가 유한하지 않음**
  - 오류로 처리한다.
