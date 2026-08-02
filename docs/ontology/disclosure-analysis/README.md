# 공시 분석

> **문서 목적:** Triple Barrier 실행과 저장 결과 화면의 Feature, Fallback과 Shutdown을 설명한다.
>
> **다루지 않는 내용:** 일반 가격 조회와 차트 구성은 [Chart View](../chart-view/README.md)에서 설명한다.

## Feature

아래 경로는 `src/finiq/` 기준이다.

### `charts-and-backtests`

**Triple Barrier 계산 기능**

- triple-barrier 기간 안에 barrier에 닿지 않으면 마지막 가격 봉을 종료값으로 사용하고 `기간 만료`로 기록한다.
- 같은 장중 행에서 위·아래 barrier에 모두 닿으면 빈 계산값과 `status=failed`를 저장하고 다음 이벤트를 계속 계산한다.

**Triple Barrier 입력·저장 기능**

**경로:** `market_desk/analytics/triple_barrier.py`

- **같은 manifest·공시·종목 코드·설정 hash를 가진 행이 이미 있음**
  - `INSERT OR IGNORE`로 기존 결과를 남기고 새 값으로 덮어쓰지 않는다. 먼저 저장된 결과가 이후 실행에서도 유지된다.
- **`전체`가 아닌 공시 그룹을 선택해 분석함**
  - SQLite `classification`에서 선택 그룹을 통과한 공시에 KIND 분류 폴더에서 읽은 같은 그룹의 공시를 추가한다. 같은 공시 ID가 두 원본에 있으면 뒤에 추가한 KIND 분류 폴더의 record를 남긴다.

## Fallback

아래 경로는 `src/finiq/` 기준이다.

- **market_desk/analytics/triple_barrier.py**
- **공시일 이후의 진입 가격이나 지정 거래일 뒤의 종료 가격이 없음**
  - 계산값이 빈 `status=failed` 행을 저장하고 다음 공시를 계속 계산한다. 성공 행과 실패 행은 같은 결과 DB에 저장된다.
- **요청한 가격 항목 이름과 정확히 같은 Parquet 접두어가 없음**
  - 항목별 조정 가격 접두어와 일반 가격 접두어를 순서대로 확인하고 파일명순 첫 Parquet을 사용한다.
- **DB에서 읽은 `vertical_datetime`·`touched_datetime`·`error_message`가 `null`임**
  - 빈 문자열로 반환한다.

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

- **lib/disclosureBacktests.ts**
- **백테스트 event의 접수번호·공시 시각·그룹·제목이 없음**
  - row key는 marker 시각과 제목을 합쳐 만들고, 공시 시각은 marker 시각, 그룹은 `기타`, 제목은 `-`를 사용한다.
- **진입 가격 봉이 없거나 진입 종가가 유효한 양수가 아님**
  - 결과를 `가격 없음`, 수익률을 `null`로 두고 다음 event를 계산한다.

## Shutdown

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

- **lib/disclosureBacktests.ts**
- **계산법을 알 수 없음**
  - 오류로 처리한다.
