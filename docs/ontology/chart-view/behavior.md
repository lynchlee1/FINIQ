# Chart View 정상 동작

기본 자료 흐름과 정상 실행 계약을 설명한다.

## 정상 동작

아래 경로는 `src/finiq/` 기준이다.

- **market\_desk/analytics/chart.py**
- **공시 시각이 15:30 이후이거나 공시 기준일과 같은 날짜에 가격 봉이 없음**
  - 공시 연결 기준일을 다음 달력 날짜로 옮긴 뒤 그날 이후 첫 가격 봉에 marker를 연결한다. 가격 봉이 하나도 없으면 해당 공시 marker를 차트에서 제외한다.

- **market\_desk/analytics/ontology\_graph.py**
- **표시 빈도가 `자동`임**
  - 집계 전 가격 봉이 180개 이하면 `day`, 181~520개면 `week`, 521개 이상이면 `month`로 집계한다.

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

- **components/PriceChart.tsx**
- **현재 hover한 가격 봉이 없음**
  - 배열에서 마지막 가격 봉을 차트 제목에 현재값으로 표시한다.
