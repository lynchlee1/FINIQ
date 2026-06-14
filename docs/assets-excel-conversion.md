# Quantiwise 변환

## 구현 내용

- `/Users/wonwoolee/Documents/GitHub/FINIQ/resources/Quantiwise` 아래 Excel 목록 조회 및 Sheet 읽기 기능 추가.
- Market Desk Web UI의 `/utility/assets-excel`은 `Quantiwise - 미리보기`, `/utility/assets-excel/save`는 `Quantiwise - 저장하기`로 분리한다.
- `Quantiwise - 미리보기`는 원본 데이터 경로 아래 Excel 파일 하나와 Sheet 하나를 선택해 Sheet preview를 보여준다.
- `Quantiwise - 저장하기`는 원본 데이터 경로 아래 모든 Excel 파일을 사전 점검 및 Wide Parquet 저장 대상으로 사용한다.
- 변환 결과는 Excel 파일명이 아니라 계정명 기준으로 저장한다. 예: `stock_price.parquet`, `volume.parquet`.
- Code-Name 매핑은 계정 Parquet와 별도인 `code_name_mapping.parquet`에 저장한다.
- 변환 메타데이터는 `manifest.json`에 저장한다. 원천 파일/Sheet, 실제 날짜 목록, 명시적 날짜 구간, 충돌, skipped Sheet, 출력 파일 정보를 포함한다.
- 기본 저장 방식은 기존 Parquet/manifest를 읽어 새 Excel 데이터와 병합하는 `update`다. 선택 파일 기준 재생성은 `replace`로 명시한다.
- 사전 점검 API는 저장 없이 Sheet/계정 매핑, 기존 출력 감지, 충돌 샘플, skipped Sheet를 반환한다.
- Sheet 미리보기는 Quantiwise 형식을 자동 해석해 실제 Wide Parquet 변환 기준의 날짜/코드/계정명을 보여준다.
- Quantiwise 형식 Sheet의 미리보기는 상단 설정 영역에서 `Period(From)`, `Period(To)`만 메타데이터로 가져오고, 실제 표는 `D A T E` 아래 데이터 영역을 기준으로 날짜를 세로축, 종목코드를 가로축으로 보여준다.
- Sheet 미리보기는 먼저 Sheet 목록만 읽고, 사용자가 Sheet를 선택한 뒤에 본문 rows를 읽는다.
- 사전 점검 UI는 정상 매핑, 미매핑, 형식 오류, 충돌을 분리해서 보여준다.
- 변환 결과 UI는 계정별 행/코드/구간뿐 아니라 결측률과 최근 샘플 행을 함께 보여준다.
- 같은 파일/Sheet 미리보기 요청은 프론트엔드에서 캐시해 반복 조회 체감 속도를 낮춘다.
- 스캔 중 Sheet 요약은 이미 읽은 변환 frame을 재사용해 같은 Sheet를 다시 읽지 않는다.
- 관련 테스트를 추가했다. Excel 조회/읽기, 경로 검증, 파일 선택, 기존 출력 업데이트, 계정명 저장, 충돌 처리, 인접 구간 병합, 복수 구간, 단일 Sheet 구간 보존을 검증한다.

## 반드시 따를 규칙

- 데이터 형식은 Wide Format + Parquet.
- 계정 데이터 저장 형식은 Parquet로 고정한다.
- Code-Name 매핑을 별도로 보관해 종목코드 wide table을 기업명 기준으로 해석할 수 있어야 한다.
- 실제 대용량 변환은 사용자가 명시적으로 지시하기 전까지 실행하지 않는다.
- 기존 관리 DB가 있으면 기본적으로 덮어쓰기보다 업데이트 병합으로 처리한다.
- 변환 대상 파일은 원본 데이터 경로 아래 전체 Excel 파일로 고정한다. 개별 파일 체크박스나 필터 선택 UI를 두지 않는다.
- 실행 전 Sheet/계정 매핑과 skipped Sheet를 확인할 수 있어야 한다.
- 실행 전 기존 출력 폴더의 Parquet/manifest 존재 여부를 감지하고 업데이트/재생성 의미를 보여줘야 한다.
- 파일을 바꿀 때 이전 파일의 Sheet 선택과 본문 결과가 새 파일에 재사용되면 안 된다.
- 하나의 Sheet는 하나의 연속 날짜 구간이다. 주말/휴일/중간 공백 때문에 Sheet 내부를 여러 구간으로 쪼개지 않는다.
- 휴일 여부를 추정하지 않는다. 실제 관측 날짜는 `date_index`, 명시적 구간은 `date_segments`에 저장한다.
- 원천 Sheet의 `date_segments`는 항상 1개이며 `start`, `end`, `count`를 기록한다.
- 계정 단위 `date_segments`는 여러 개 가능하다.
- 원천 Sheet 구간이 겹치거나 하루 차이로 인접하면 계정 단위에서 하나로 병합한다.
- 날짜 차이가 3일이어도 사이가 주말뿐이면 연속으로 보고 병합한다. 예: 금요일 `end` 다음 월요일 `start`.
- 그 외 2일 이상 떨어진 구간은 계정 단위에서 별도 구간으로 유지한다. 이것만으로 변환을 중단하지 않는다.
- 같은 계정/날짜/종목코드 값이 겹치고 값이 다르면 항상 중단(`error`)한다.

## 저장 계약

- Parquet: `<output_directory>/<account_name>.parquet`
- Parquet 구조: `date` 컬럼 + 종목코드별 wide 컬럼
- Code-Name mapping Parquet: `<output_directory>/code_name_mapping.parquet`
- Code-Name mapping 구조: `code`, `name`, `source_files`, `source_sheets`
- Manifest format: `finiq_asset_wide_parquet_v1`
- Write mode: `update` 또는 `replace`
- Account metadata: `path`, `rows`, `columns`, `date_start`, `date_end`, `date_index`, `date_segments`, `sources`
- Source metadata: `file_name`, `sheet_name`, `date_start`, `date_end`, `date_index`, `date_segments`, `rows`, `columns`

## 검증

```bash
python3 -m pytest tests/test_assets_excel.py tests/market_desk/test_server.py
npm run build -w @finiq/app-market-desk --
```
