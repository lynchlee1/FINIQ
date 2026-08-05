# 공시 분석 정상 동작

기본 자료 흐름과 정상 실행 계약을 설명한다.

## 정상 동작

아래 경로는 `src/finiq/` 기준이다.

### `charts-and-backtests`

**Triple Barrier 계산 기능**

- triple-barrier 기간 안에 barrier에 닿지 않으면 마지막 가격 봉을 종료값으로 사용하고 `기간 만료`로 기록한다.

**Triple Barrier 입력·저장 기능**

**경로:** `market_desk/analytics/triple_barrier.py`

- **같은 manifest·공시·종목 코드·설정 hash를 가진 행이 이미 있음**
  - `INSERT OR IGNORE`로 기존 결과를 남기고 새 값으로 덮어쓰지 않는다. 먼저 저장된 결과가 이후 실행에서도 유지된다.
- **`전체`가 아닌 공시 그룹을 선택해 분석함**
  - SQLite `classification`에서 선택 그룹을 통과한 공시에 KIND 분류 폴더에서 읽은 같은 그룹 공시를 추가한다. 두 원본에 같은 공시 ID가 있으면 뒤에 추가한 KIND 분류 폴더 record를 남긴다.
