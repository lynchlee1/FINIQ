# Quantiwise 변환

## 구현 내용

- `/Users/wonwoolee/Documents/GitHub/FINIQ/resources/Quantiwise` 아래 Excel 목록 조회 및 Sheet 읽기 기능 추가.
- Market Desk Web UI의 `/utility/assets-excel`은 `Quantiwise - 미리보기`, `/utility/assets-excel/convert`는 `Quantiwise - 변환하기`, `/utility/assets-excel/merge`는 `Quantiwise - 병합하기`로 분리한다.
- `Quantiwise - 미리보기`는 원본 데이터 경로 아래 Excel 파일 하나와 Sheet 하나를 선택해 Sheet preview를 보여준다.
- `Quantiwise - 변환하기`는 원본 데이터 경로 아래 모든 Excel 파일을 변환 전 확인 및 Wide Parquet 변환 대상으로 사용한다.
- `Quantiwise - 병합하기`는 생성된 Quantiwise Parquet 경로 2개를 읽어 별도 데이터 경로에 병합 결과를 저장한다.
- 변환 결과는 Sheet 하나당 Parquet 하나로 저장한다. 파일명은 `<accountName>_<YYYYMMDD>_<YYYYMMDD>.parquet` 형식이다. 예: `nxtHigh_20001231_20251223.parquet`.
- Code-Name 매핑은 Sheet Parquet와 별도인 `code_name_mapping.parquet`에 저장한다.
- 계정명과 계정 ID 매핑은 `account_mapping.parquet`에 저장한다. 계정명은 언더바 없는 lower camel case를 사용하고, ID는 `S00001` 형식으로 고정한다.
- 변환 메타데이터는 `manifest.json`에 저장한다. 원천 파일/Sheet, 실제 날짜 목록, 명시적 날짜 구간, 충돌, skipped Sheet, 출력 파일 정보를 포함한다.
- 변환하기의 저장 방식은 기존 Parquet/manifest 병합 없이 Excel을 Parquet로 생성하는 `replace`다.
- 병합하기는 생성된 Parquet 경로를 별도로 받아 같은 Parquet 이름의 날짜/종목코드 값을 병합한다.
- 변환 전 확인 API는 저장 없이 Sheet/계정 매핑, 기존 출력 감지, skipped Sheet를 반환한다.
- `Quantiwise 변환`은 변환 job 내부에서 저장 전 확인을 자동 수행한다. 별도 확인 버튼이나 실행 전 중복 전체 스캔을 두지 않는다.
- Sheet 미리보기는 Quantiwise 형식을 자동 해석해 실제 Wide Parquet 변환 기준의 날짜/코드/계정명을 보여준다.
- Quantiwise 형식 Sheet의 미리보기는 상단 설정 영역에서 `Period(From)`, `Period(To)`만 메타데이터로 가져오고, 실제 표는 `D A T E` 아래 데이터 영역을 기준으로 날짜를 세로축, 종목코드를 가로축으로 보여준다.
- Sheet 미리보기는 먼저 Sheet 목록만 읽고, 사용자가 Sheet를 선택한 뒤에 본문 rows를 읽는다.
- 변환 전 확인 UI는 정상 매핑, 미매핑, 형식 오류를 분리해서 보여준다.
- 변환 결과 UI는 Sheet Parquet별 원본 Sheet, 계정, 행/코드/구간, 결측률과 최근 샘플 행을 함께 보여준다.
- 같은 파일/Sheet 미리보기 요청은 프론트엔드에서 캐시해 반복 조회 체감 속도를 낮춘다.
- 스캔 중 Sheet 요약은 이미 읽은 변환 frame을 재사용해 같은 Sheet를 다시 읽지 않는다.
- 실제 변환 실행은 실행 전 preview API로 전체 Excel을 다시 읽지 않고, background job의 파일 단위 병렬 스캔 결과를 바로 Sheet Parquet로 저장한다.
- Excel 스캔은 파일 단위로 병렬 처리하되, 워커 수는 최대 4개로 제한한다.
- Sheet Parquet 저장은 독립 파일 단위로 병렬 처리하되, 워커 수는 최대 4개로 제한한다.
- 병렬 저장은 임시 폴더에 먼저 쓴 뒤 전체 저장 성공 후 최종 Parquet로 승격한다. 저장 중 작업이 중단되면 최종 Parquet와 manifest를 남기지 않는다.
- 관련 테스트를 추가했다. Excel 조회/읽기, 경로 검증, 파일 선택, Sheet 단위 저장, 기존 출력과 별도 생성, 병렬 취소, 단일 Sheet 구간 보존을 검증한다.

## 반드시 따를 규칙

- 데이터 형식은 Wide Format + Parquet.
- Sheet 데이터 저장 형식은 Parquet로 고정한다.
- Code-Name 매핑을 별도로 보관해 종목코드 wide table을 기업명 기준으로 해석할 수 있어야 한다.
- 실제 대용량 변환은 사용자가 명시적으로 지시하기 전까지 실행하지 않는다.
- 기존 관리 DB와 합치는 작업은 변환하기가 아니라 병합하기에서 처리한다.
- 변환 대상 파일은 원본 데이터 경로 아래 전체 Excel 파일로 고정한다. 개별 파일 체크박스나 필터 선택 UI를 두지 않는다.
- 변환 실행 시 Sheet/계정 매핑과 skipped Sheet를 job 로그와 결과 payload에서 자동 확인할 수 있어야 한다.
- 변환 실행 전 기존 출력 폴더의 Parquet/manifest 존재 여부를 감지하고 변환하기가 기존 Parquet를 병합하지 않는다는 의미를 보여줘야 한다.
- 파일을 바꿀 때 이전 파일의 Sheet 선택과 본문 결과가 새 파일에 재사용되면 안 된다.
- 하나의 Sheet는 하나의 연속 날짜 구간이다. 주말/휴일/중간 공백 때문에 Sheet 내부를 여러 구간으로 쪼개지 않는다.
- 휴일 여부를 추정하지 않는다. 실제 관측 날짜는 `date_index`, 명시적 구간은 `date_segments`에 저장한다.
- 원천 Sheet의 `date_segments`는 항상 1개이며 `start`, `end`, `count`를 기록한다.
- 같은 계정/날짜/종목코드가 여러 Sheet에 있더라도 변환하기에서는 병합하거나 충돌 판단하지 않는다. 각 Sheet를 별도 Parquet로 저장한다.
- 계정명은 파일명과 metadata에서 언더바 없는 lower camel case를 사용한다. 기존 snake_case 계정명은 `legacy_account_name`으로만 보관한다.

## 저장 계약

- Parquet: `<output_directory>/<accountName>_<date_start_yyyymmdd>_<date_end_yyyymmdd>.parquet`
- Parquet 구조: `date` 컬럼 + 종목코드별 wide 컬럼
- Code-Name mapping Parquet: `<output_directory>/code_name_mapping.parquet`
- Code-Name mapping 구조: `code`, `name`, `source_files`, `source_sheets`
- Account mapping Parquet: `<output_directory>/account_mapping.parquet`
- Account mapping 구조: `account_id`, `account_name`, `legacy_account_name`, `sheet_name`
- Manifest format: `finiq_asset_wide_parquet_v1`
- Write mode: `update` 또는 `replace`
- Output metadata: `path`, `output_file`, `account_id`, `account_name`, `legacy_account_name`, `file_name`, `relative_path`, `sheet_name`, `rows`, `columns`, `date_start`, `date_end`, `date_index`, `date_segments`, `sources`
- Source metadata: `file_name`, `relative_path`, `sheet_name`, `account_id`, `account_name`, `legacy_account_name`, `output_file`, `date_start`, `date_end`, `date_index`, `date_segments`, `rows`, `columns`

## 검증

```bash
python3 -m pytest tests/test_assets_excel.py tests/market_desk/test_server.py
npm run build -w @finiq/app-market-desk --
```
