# Quantiwise 정상 동작

기본 자료 흐름과 정상 실행 계약을 설명한다.

## 정상 동작

아래 경로는 `src/` 기준이다.

- **finiq/data/assets\_excel.py**
- **같은 계정명·날짜 범위·종목 코드에도 서로 다른 파일명을 만듦**
  - 모든 파일명에 종목 코드 목록 SHA256을 포함하고 완성된 이름이 겹치면 뒤 파일에 `__2`, `__3`을 붙인다.
- **병합 입력들이 같은 날짜·종목·계정 칸을 가지며 한 입력에만 실제 값이 있음**
  - 빈 칸을 실제 값으로 채운다.
- **계정 mapping 입력을 따로 보내지 않음**
  - 코드에 등록된 기본 시트·계정 ID·계정명 mapping 전체를 사용한다.
- **Excel preview에서 시트를 지정하지 않음**
  - 통합문서 첫 시트를 읽는다. 기본 preview는 앞 100행을 반환하고 변환 parser preview는 앞 20행과 날짜 열을 포함해 13개 열까지 반환한다.
- **finiq/data/assets\_parquet\_cleanup.py**
- **같은 계정 Parquet에서 한 파일이 다른 파일을 완전히 포함함**
  - 더 작은 파일을 삭제 후보로 두고 모든 값을 포함한 파일을 남긴다.
- **같은 계정 Parquet 파일 두 개에서 날짜·종목 열·값이 모두 같음**
  - 값이 있는 칸 수 → 행 수 → 열 수 → 숫자 suffix → 전체 경로 이름 순서로 하나를 남긴다.

- **finiq/market\_desk/analytics/quanti\_integrated.py**
- **통합 과정에서 같은 DataFrame index를 가진 행이 두 번 이상 생김**
  - 입력을 합친 순서에서 마지막 행만 남기고 앞에 있는 같은 index 행은 제거한다.

- **finiq/market\_desk/analytics/quanti\_market\_history.py**
- **날짜가 중복됨**
  - 마지막 값을 사용한다. 겹친 날짜에는 마지막 입력이 우선한다.
아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

### `asset-excel`

- 화면은 backend `outputs`에서 받은 `output_file`, `account_name`, `date_start`, `date_end`, `companies_hash`를 그대로 사용한다.
