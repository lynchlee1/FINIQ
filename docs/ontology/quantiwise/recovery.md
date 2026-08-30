# Quantiwise 복구

아래 경로는 `src/` 기준이다.

## Excel 변환과 preview

- **finiq/data/assets_excel.py**
- **여러 Excel 파일을 변환할 때 시트명에 대응하는 계정명 mapping이 없음**
  - 해당 시트에서 건너뛴 이유와 상태를 `skipped`에 기록하고 다음 시트와 파일을 계속 변환한다.
- **시트에서 필수 표시·종목 코드·날짜·계정 ID를 읽다가 `ValueError`가 발생함**
  - 해당 시트만 Parquet 결과에서 제외하고 실패 이유를 `skipped`에 기록한다.
- **Excel preview에 `Name` 행이나 일부 종목명이 없음**
  - 해당 종목 이름은 빈 문자열로 반환하고 코드와 값 preview는 계속 만든다.
- **기존 `code_name_mapping.parquet`이 없거나 `code` 열이 없음**
  - 기존 code-name mapping을 빈 목록으로 보고 병합을 계속한다.

## 시장 항목 변환

- **finiq/market_desk/analytics/quanti_market_history.py**
- **시장 항목 registry에 원본값과 표준 시장명을 연결하는 `values`가 없음**
  - 빈 대응표를 반환한다. 시장 이력을 만들 때는 `DEFAULT_MARKET_VALUE_MAP`을 적용하고 호출자가 준 대응표가 있으면 같은 key에 있는 기본값을 덮어쓴다.
- **시장 항목 Parquet에 표준 `A######` 종목 열이 없음**
  - 6자리 숫자로만 된 열과 이름이 `_######`로 끝나는 열도 종목 열로 사용한다.

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

## 원본 선택

- **features/assets-excel/AssetExcelUtilityView.tsx**
- **Excel 원본 목록을 갱신한 뒤 이전 선택 경로가 새 목록에 하나도 없음**
  - 새 목록에 있는 모든 Excel 파일을 선택한다. 원본 폴더가 바뀌었거나 이전 선택이 비어 있으면 전체 선택 상태로 시작한다.
