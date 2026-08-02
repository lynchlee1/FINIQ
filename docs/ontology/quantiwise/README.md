# Quantiwise

> **문서 목적:** Excel 미리보기와 Parquet 변환·미리보기·병합 화면의 Feature, Fallback과 Shutdown을 설명한다.
>
> **다루지 않는 내용:** 가격 조회와 차트 구성은 [Chart View](../chart-view/README.md)에서 설명한다.

## Feature

아래 경로는 `src/` 기준이다.

- **finiq/data/assets\_excel.py**
- **같은 계정명·날짜 범위·종목 코드여도 구분되는 파일명을 만듦**
  - 모든 파일명에 종목 코드 목록 SHA256을 포함하고, 완성된 이름이 겹치면 뒤 파일에 `__2`, `__3`을 붙인다.
- **병합 입력들이 같은 날짜·종목·계정 칸에 서로 다른 실제 값을 가짐**
  - 두 입력의 실제 값이 같으면 그 값을 유지하며 충돌로 처리하지 않는다. 두 입력의 실제 값이 다르면 병합 전체를 오류로 처리하며 병합 결과를 남기지 않고 하나의 값을 선택하지 않는다.
- **병합 입력들이 같은 날짜·종목·계정 칸을 가지며 한 입력에만 실제 값이 있음**
  - 빈 칸을 실제 값으로 채운다.
- **계정 mapping 입력을 따로 보내지 않음**
  - 코드에 등록된 기본 시트·계정 ID·계정명 mapping 전체를 사용한다.
- **Excel preview에서 시트를 지정하지 않음**
  - 통합문서의 첫 시트를 읽는다. 기본 preview는 앞의 100행을 반환하고, 변환 parser preview는 앞의 20행과 날짜 열을 포함한 13개 열까지 반환한다.
- 잘못된 날짜와 중복 종목 코드·날짜의 backend 검증 오류 문장은 앞의 5개, 병합 표의 누락 종목 코드 오류 문장은 앞의 3개만 포함한다. 검증과 실패 판단은 전체 값을 사용한다.

- **finiq/data/assets\_parquet\_cleanup.py**
- **동일한 계정 Parquet에서 하나의 Parquet이 다른 Parquet을 완전히 포함함**
  - 더 작은 파일을 삭제 후보로 두고 모든 값을 포함한 파일을 남긴다.
- **동일한 계정 Parquet에서 두 개의 Parquet이 날짜·종목 열·값이 완전히 같음**
  - 값이 있는 칸 수 → 행 수 → 열 수 → 숫자 suffix → 전체 경로 이름 순서로 하나를 남긴다.

- **finiq/market\_desk/analytics/quanti\_integrated.py**
- **통합 과정에서 같은 DataFrame index를 가진 행이 두 번 이상 생김**
  - 입력을 합친 순서에서 마지막 행만 남기고 앞의 같은 index 행은 제거한다.

- **finiq/market\_desk/analytics/quanti\_market\_history.py**
- **날짜가 중복됨**
  - 마지막 값을 사용한다. 겹친 날짜에는 마지막 입력이 우선한다.
- 시장 대응표에 없는 값의 오류 문장은 앞의 10개 열에서 열마다 앞의 5개 값만 포함한다. 검증과 실패 판단은 전체 값을 사용한다.

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

### `asset-excel`

- 화면은 backend `outputs`의 `output_file`, `account_name`, `date_start`, `date_end`, `companies_hash`를 그대로 사용한다.

- **features/assets-excel/AssetExcelUtilityView.tsx**
- **Excel 원본 목록을 갱신한 뒤 이전 선택 경로와 새 목록의 경로가 하나도 일치하지 않음**
  - 새 목록에 있는 모든 Excel 파일을 선택한다. 따라서 원본 폴더가 바뀌었거나 이전 선택이 비어 있으면 전체 선택 상태로 시작한다.

## Fallback

아래 경로는 `src/` 기준이다.

- **finiq/data/assets_excel.py**
- **여러 Excel 파일을 변환할 때 시트명에 대응하는 계정명 mapping이 없음**
  - 해당 시트의 이유와 상태를 `skipped`에 기록하고 다음 시트와 파일을 계속 변환한다.
- **시트의 필수 표시·종목 코드·날짜·계정 ID를 읽는 과정에서 `ValueError`가 발생함**
  - 해당 시트만 Parquet 결과에서 제외하고 실패 이유를 `skipped`에 기록한다.
- **Excel preview에 `Name` 행이나 일부 종목명이 없음**
  - 해당 종목의 이름을 빈 문자열로 반환하고 코드와 값 preview는 계속 만든다.
- **기존 `code_name_mapping.parquet`이 없거나 `code` 열이 없음**
  - 기존 code-name mapping을 빈 목록으로 보고 병합을 계속한다.
- **finiq/market_desk/analytics/quanti_market_history.py**
- **시장 항목 registry에 원본값과 표준 시장명을 연결하는 `values`가 없음**
  - 빈 대응표를 반환한다. 시장 이력을 만들 때는 `DEFAULT_MARKET_VALUE_MAP`을 적용하고 호출자가 준 대응표가 있으면 같은 key의 기본값을 덮어쓴다.
- **시장 항목 Parquet에 표준 `A######` 종목 열이 없음**
  - 6자리 숫자로만 된 열과 이름이 `_######`로 끝나는 열도 종목 열로 사용한다.

## Shutdown

아래 경로는 `src/` 기준이다.

- **finiq/data/assets\_excel.py**
- **통합문서를 `calamine`으로 읽을 수 없음**
  - 읽기 요청을 오류로 처리한다.
- **병합 입력 Parquet 하나에 `date` 열이 없음**
  - 병합 전체를 오류로 처리하며 병합 결과를 남기지 않는다.
- **통합 Parquet 병합 요청의 `input_directories`가 비어 있거나 배열이 아님**
  - 이전 `input_directory` 이름으로 대체하지 않고 요청을 오류로 처리한다.
- **단일 Excel preview에서 필수 필드 값을 찾지 못함**
  - preview 요청을 오류로 처리한다.
- **단일 Excel preview에 값이 있는 잘못된 날짜가 있음**
  - 행을 제외해 정상처럼 보이는 일부 preview를 만들지 않고 요청을 오류로 처리한다.
- **Parquet 결과 교체나 병합 입력 이동 중 오류가 발생함**
  - 이번 실행에서 새로 올린 결과를 제거하고 기존 결과와 이미 옮긴 입력을 원래 위치로 복원한 뒤 오류로 처리한다.

- **finiq/data/assets\_parquet\_cleanup.py**
- **중복 정리 요청 전체를 오류로 처리하는 경우**
  - Parquet footer, 계정 metadata, 표 본문 중 하나가 누락되어 정상적인 작동이 불가능한 경우
  - 날짜를 읽거나 변환할 수 없는 경우
- **footer의 `account_name`이 비어 있음**
  - 중복 정리 요청 전체를 오류로 처리한다.
- **삭제 후보 파일이 정리 실행 전에 없어짐**
  - 중복 정리 요청 전체를 오류로 처리한다.

- **finiq/market\_desk/analytics/quanti\_integrated.py**
- **통합문서나 시트를 읽을 수 없거나 비어 있음**
  - 오류로 처리한다.
- **입력 폴더·`date` 열이 없거나 병합할 항목 자료가 비어 있음**
  - 오류로 처리한다.

- **finiq/market\_desk/analytics/quanti\_market\_history.py**
- **대응표에서 찾을 수 없는 시장값이 하나라도 있음**
  - 오류로 처리한다.
