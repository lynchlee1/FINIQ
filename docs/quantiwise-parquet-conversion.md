# Quantiwise Parquet 변환 규칙

## Scope

Market Desk의 Quantiwise Excel 워크플로는 Excel 원본을 Wide Format Parquet로
변환하고, 생성된 Parquet를 미리보기/병합한다.

대상 UI:

- `Excel 미리보기`: Excel 파일과 Sheet preview
- `Parquet 변환하기`: 선택한 Excel 파일을 Sheet 단위 Parquet로 변환
- `Parquet 미리보기`: 생성된 Parquet preview
- `Parquet 병합하기`: 같은 계정 Parquet 2개씩 선택해 병합

## Data Contract

- 데이터 형식: Wide Format + Parquet
- Sheet 저장 단위: Sheet 하나당 Parquet 하나
- Parquet 파일명: `<accountName>_<YYYYMMDD>_<YYYYMMDD>_<companiesHash>.parquet`
- Parquet 구조: `date` 컬럼 + 종목코드별 wide 컬럼
- `companiesHash`: Wide Parquet 컬럼 순서의 종목코드 목록을 이어 붙인 문자열의 SHA256 hex
- Code-Name mapping: `<output_directory>/code_name_mapping.parquet`
- Code-Name mapping 구조: `code`, `name`
- Account mapping Parquet: 생성하지 않음
- Manifest: 생성하지 않음
- Write mode: `replace`

계정 Parquet footer metadata는 필수다.

- `account_id`
- `account_name`
- `date_start`
- `date_end`
- `rows`
- `columns`
- `non_null_cells`
- `total_cells`
- `missing_ratio`

`Parquet 모아보기`, `Parquet 미리보기`, `Parquet 병합하기`는 footer metadata를
fallback 계산 없이 필수로 읽는다.

## Conversion Rules

- 원본 데이터 경로와 결과 데이터 경로는 호출자가 명시한다. 빈 경로를 기본값으로 대체하지 않는다.
- 계정명은 언더바 없는 lower camel case를 사용한다.
- 계정 ID는 `S00001` 형식으로 고정한다.
- `account_id`와 `account_name`에는 `_`를 사용할 수 없다.
- 계정명/ID 매핑 원본은 앱 설정의 `asset_excel_account_mappings`다.
- `Parquet 변환하기`는 실행 전 `계정-ID 매핑`을 편집, 추가, 삭제할 수 있다.
- 변환/미리보기 스캔은 요청 payload의 매핑 목록을 기본 매핑 대신 사용한다.
- `account_mapping.parquet`는 생성하지 않으며, 기존 출력 폴더에 남아 있어도 계정 Parquet 스캔 대상에서 제외한다.
- Excel 읽기 엔진은 `calamine`으로 고정한다. `openpyxl` fallback은 사용하지 않는다.
- Excel 스캔은 파일 단위 병렬 처리하되 워커 수는 최대 4개다.
- 실제 대용량 변환은 사용자가 명시적으로 지시하기 전까지 실행하지 않는다.

## Preview Rules

- Sheet 미리보기는 먼저 Sheet 목록만 읽고, 사용자가 Sheet를 선택한 뒤 본문 rows를 읽는다.
- 같은 파일/Sheet 미리보기 요청은 프론트엔드에서 캐시한다.
- 파일을 바꾸면 이전 파일의 Sheet 선택과 본문 결과를 재사용하지 않는다.
- Quantiwise 형식 Sheet는 `Period(From)`, `Period(To)`만 메타데이터로 가져온다.
- 실제 표는 `D A T E` 아래 데이터 영역을 기준으로 날짜를 세로축, 종목코드를 가로축으로 보여준다.
- `Parquet 미리보기`는 생성된 Sheet Parquet를 `Excel 미리보기`와 같은 선택/표 양식으로 보여준다.

## Conversion Execution

- 변환 대상은 `대상 파일`에서 선택한 Excel 파일이다.
- 화면 최초 로딩 시 전체 Excel을 선택하되, 사용자가 일부 파일만 남겨 실행할 수 있다.
- 변환 전 확인 API는 저장 없이 Sheet/계정 매핑, 기존 출력 감지, skipped Sheet를 반환한다.
- 실제 변환 job은 저장 전 확인을 자동 수행한다. 별도 확인 버튼이나 실행 전 중복 전체 스캔은 두지 않는다.
- 변환 실행은 Sheet를 읽는 즉시 결과 데이터 경로 아래 임시 폴더에 Sheet Parquet를 저장한다.
- 모든 임시 저장이 성공하면 파일명 충돌 규칙을 적용해 최종 Parquet로 승격한다.
- 취소/실패하면 최종 Parquet를 남기지 않고 임시 폴더를 정리한다.
- `실패분 이어서 실행`은 예상 output filename이 이미 있으면 해당 Sheet를 건너뛰고 누락된 Sheet만 생성한다.
- 같은 계정/날짜/종목코드가 여러 Sheet에 있어도 변환하기에서는 병합하거나 충돌 판단하지 않는다.
- 하나의 Sheet는 하나의 연속 날짜 구간이다. 주말/휴일/중간 공백 때문에 Sheet 내부를 여러 구간으로 쪼개지 않는다.
- 휴일 여부를 추정하지 않는다. 저장 메타데이터 날짜 구간은 `date_start`, `date_end`만 기록한다.

## Merge Rules

- 병합하기는 `병합 대상 데이터 경로` 안의 같은 계정 Parquet 파일을 정확히 2개 선택한 경우만 실행한다.
- 경로 안의 모든 파일을 한 번에 병합하지 않는다.
- 기존 관리 DB와 합치는 작업은 변환하기가 아니라 병합하기에서 처리한다.
- `병합대상 모아보기`는 같은 계정 Parquet 파일이 2개 이상 있는 항목만 표시한다.
- `동일 폴더에서 작업하기`가 켜지면 `병합 결과 데이터 경로`와 관계없이 `병합 대상 데이터 경로`에 결과를 저장한다. 기본값은 off다.
- `병합된 요소 정리하기`가 켜지면 병합 성공 후 선택 원본을 `병합 대상 데이터 경로/merged`로 옮긴다. 기본값은 on이다.
- `merged`에 같은 이름이 있으면 덮어쓰지 않고 `__2`, `__3` suffix를 사용한다.
- 병합 결과와 Code-Name mapping은 임시 폴더에 먼저 저장하고, 모든 병합이 성공한 뒤 최종 파일로 승격한다.
- 병합 중 취소/실패하면 최종 Parquet를 남기지 않는다.
- 병합 결과는 계정별 날짜/종목코드 직사각형이 완전한 경우만 허용한다.
- 실제 값 결측은 허용하지만, 어느 입력에도 없는 날짜/종목코드 조합이 생기는 partial table은 병합하지 않는다.
- 날짜축 병합은 구간이 겹치거나 한 구간의 종료일과 다음 구간의 시작일이 하루 차이인 경우만 허용한다.

## Duplicate Cleanup

- `중복 검사하기`는 기본적으로 `병합 대상 데이터 경로` 바로 안의 Parquet만 검사한다.
- `내부까지 검사`를 켠 경우에만 하위 폴더를 포함한다.
- 같은 계정 Parquet끼리 date, 종목코드, 내부 값을 비교한다.
- 한 파일의 모든 `(date, 종목코드, 값)`이 더 완전한 같은 계정 파일에 손실 없이 포함되면 더 작은 파일을 삭제 후보로 표시한다.
- 삭제는 사용자가 `확인했습니다.`를 입력하고 삭제 허가를 체크한 뒤에만 실행한다.

## Verification

```bash
python3 -m pytest tests/test_assets_excel.py tests/market_desk/test_server.py
npm run build -w @finiq/app-market-desk --
```
