# Quantiwise 변환

## 구현 내용

- `/Users/wonwoolee/Documents/GitHub/FINIQ/resources/Quantiwise` 아래 Excel 목록 조회 및 Sheet 읽기 기능 추가.
- Market Desk Web UI의 `/utility/assets-excel`은 `Quantiwise - Excel 미리보기`, `/utility/assets-excel/convert`는 `Parquet 변환하기`, `/utility/assets-excel/parquet`은 `Quantiwise - Parquet 미리보기`, `/utility/assets-excel/merge`는 `Quantiwise - 병합하기`로 분리한다.
- `Quantiwise - Excel 미리보기`는 원본 데이터 경로 아래 Excel 파일 하나와 Sheet 하나를 선택해 Sheet preview를 보여준다.
- `Parquet 변환하기`는 원본 데이터 경로 아래 모든 Excel 파일을 변환 전 확인 및 Wide Parquet 변환 대상으로 사용한다.
- `Quantiwise - 병합하기`는 사용자가 고른 `병합 대상 경로` 안에서 같은 계정 Parquet 파일을 2개씩 하나 이상 선택해 `병합 결과 경로`에 결과를 저장한다.
- 원본 데이터 경로와 데이터 경로는 UI/API 호출자가 명시적으로 지정한다. Quantiwise UI/API는 기본 경로나 출력 경로를 자동 생성하지 않는다.
- 변환 결과는 Sheet 하나당 Parquet 하나로 저장한다. 파일명은 `<accountName>_<YYYYMMDD>_<YYYYMMDD>_<companiesHash>.parquet` 형식이다. 예: `nxtHigh_20001231_20251223_<sha256>.parquet`.
- `companiesHash`는 Wide Parquet 컬럼 순서의 종목코드 목록을 순서대로 이어붙인 문자열의 SHA256 hex 값이다.
- Code-Name 매핑은 Sheet Parquet와 별도인 `code_name_mapping.parquet`에 저장한다.
- 계정명과 계정 ID 매핑의 원본은 앱 설정의 `asset_excel_account_mappings`다. `account_mapping.parquet`는 생성하지 않는다. 계정명은 언더바 없는 lower camel case를 사용하고, ID는 `S00001` 형식으로 고정한다. `account_id`와 `account_name`에는 `_`를 사용할 수 없다.
- `Parquet 변환하기`는 실행 전 `계정-ID 매핑`을 편집, 추가, 삭제할 수 있고, 변환/미리보기 스캔은 요청 payload의 매핑 목록을 기본 매핑 대신 사용한다.
- 계정 Parquet 메타데이터는 각 Parquet footer에 저장한다. `manifest.json`은 생성하지 않는다.
- 변환하기의 저장 방식은 기존 manifest 병합 없이 Excel을 Parquet로 생성하는 `replace`다.
- 병합하기는 `병합 대상 경로` 하나를 입력으로 사용하고, 그 안에서 선택한 같은 계정 Parquet 파일 2개 묶음들의 날짜/종목코드 값을 `병합 결과 경로`에 병합한다.
- `Quantiwise - 병합하기`의 `병합대상 모아보기`는 같은 계정 Parquet 파일이 2개 이상 있는 항목만 표시한다.
- `동일 폴더에서 작업하기`가 활성화되면 `병합 결과 경로` 값과 관계없이 `병합 대상 경로`에 병합 결과를 저장한다. 기본값은 비활성화다.
- `병합된 요소 정리하기`가 활성화되면 병합 성공 후에만 선택된 원본 Parquet 파일을 `병합 대상 경로/merged`로 옮긴다. 기본값은 활성화다.
- `병합 대상 경로/merged`에 같은 이름의 보관 파일이 이미 있으면 기존 파일을 덮어쓰지 않고 `__2`, `__3` suffix로 비어 있는 보관 파일명을 사용한다.
- `중복 검사하기`는 `병합 대상 경로`와 바로 아래 `merged` 폴더에서 같은 계정 Parquet끼리 date, 종목코드, 내부 값을 비교한다. 한 파일의 모든 `(date, 종목코드, 값)`이 더 완전한 같은 계정 파일에 손실 없이 포함되면 더 작은 파일을 삭제 후보로 표시한다. 삭제는 사용자가 `확인했습니다.`를 입력하고 삭제 허가를 체크한 뒤에만 실행한다.
- 병합하기는 계정별 결과가 완전한 날짜/종목코드 직사각형이 되는 경우만 허용한다. 실제 값 결측은 허용하지만, 어느 입력에도 존재하지 않는 날짜/종목코드 조합이 생기는 partial table은 병합하지 않는다.
- 변환 전 확인 API는 저장 없이 Sheet/계정 매핑, 기존 출력 감지, skipped Sheet를 반환한다.
- `Quantiwise 변환`은 변환 job 내부에서 저장 전 확인을 자동 수행한다. 별도 확인 버튼이나 실행 전 중복 전체 스캔을 두지 않는다.
- Sheet 미리보기는 Quantiwise 형식을 자동 해석해 실제 Wide Parquet 변환 기준의 날짜/코드/계정명을 보여준다.
- Quantiwise 형식 Sheet의 미리보기는 상단 설정 영역에서 `Period(From)`, `Period(To)`만 메타데이터로 가져오고, 실제 표는 `D A T E` 아래 데이터 영역을 기준으로 날짜를 세로축, 종목코드를 가로축으로 보여준다.
- Sheet 미리보기는 먼저 Sheet 목록만 읽고, 사용자가 Sheet를 선택한 뒤에 본문 rows를 읽는다.
- 변환 전 확인 UI는 정상 매핑, 미매핑, 형식 오류를 분리해서 보여준다.
- 변환 결과 UI는 Sheet Parquet별 ID, 계정, 파일, 행/코드/구간, 결측률을 함께 보여준다. 원본 Sheet/source 컬럼은 표시하지 않는다.
- `Quantiwise - Parquet 미리보기`는 데이터 경로 아래 생성된 Sheet Parquet를 읽어 `Quantiwise - Excel 미리보기`의 `Sheet 읽기/미리보기`와 같은 선택/표 양식으로 보여준다.
- 같은 파일/Sheet 미리보기 요청은 프론트엔드에서 캐시해 반복 조회 체감 속도를 낮춘다.
- 실제 변환 실행은 실행 전 preview API로 전체 Excel을 다시 읽지 않는다.
- Excel 읽기 엔진은 `calamine`으로 고정한다. `openpyxl` fallback은 사용하지 않는다.
- Excel 스캔은 파일 단위로 병렬 처리하되, 워커 수는 최대 4개로 제한한다.
- 변환 실행은 Sheet를 읽는 즉시 데이터 경로 아래 임시 폴더에 Sheet Parquet를 저장하고, 해당 Sheet frame을 오래 보관하지 않는다.
- 임시 저장이 모두 성공하면 기존 파일명 충돌 규칙을 적용해 최종 Parquet로 승격한다. 저장 중 작업이 중단되면 최종 Parquet를 남기지 않는다.
- `실패분 이어서 실행`은 예상 output filename이 데이터 경로에 이미 있으면 해당 Sheet를 건너뛰고, 누락된 Sheet만 다시 생성한다.
- 관련 테스트를 추가했다. Excel 조회/읽기, 경로 검증, 파일 선택, Sheet 단위 저장, 기존 출력과 별도 생성, 취소 시 임시 저장 정리, 단일 Sheet 구간 보존을 검증한다.

## 반드시 따를 규칙

- 데이터 형식은 Wide Format + Parquet.
- Sheet 데이터 저장 형식은 Parquet로 고정한다.
- Code-Name 매핑을 별도로 보관해 종목코드 wide table을 기업명 기준으로 해석할 수 있어야 한다.
- 실제 대용량 변환은 사용자가 명시적으로 지시하기 전까지 실행하지 않는다.
- Quantiwise 경로 입력은 모두 명시 지정한다. 빈 원본 데이터 경로, 데이터 경로, 병합 대상, 병합 결과 경로를 기본값으로 대체하지 않는다.
- 병합하기는 `병합 대상 경로` 안의 account Parquet 파일을 같은 계정별로 정확히 2개 선택한 경우만 실행한다. 경로 안의 모든 파일을 한 번에 병합하지 않는다.
- 기존 관리 DB와 합치는 작업은 변환하기가 아니라 병합하기에서 처리한다.
- 변환 대상 파일은 원본 데이터 경로 아래 전체 Excel 파일로 고정한다. 개별 파일 체크박스나 필터 선택 UI를 두지 않는다.
- 변환 실행 시 Sheet/계정 매핑과 skipped Sheet를 job 로그와 결과 payload에서 자동 확인할 수 있어야 한다.
- 실패분 이어서 실행은 새 병합 기능이 아니며, 이미 완료된 Sheet Parquet를 재생성하지 않는 재시도 옵션으로만 사용한다.
- 기존 출력 폴더의 Parquet 존재 여부는 내부 선택지 구성에만 사용하고, `Parquet 변환하기` 실행 화면에서 기존 결과 감지 경고를 표시하지 않는다.
- 파일을 바꿀 때 이전 파일의 Sheet 선택과 본문 결과가 새 파일에 재사용되면 안 된다.
- 하나의 Sheet는 하나의 연속 날짜 구간이다. 주말/휴일/중간 공백 때문에 Sheet 내부를 여러 구간으로 쪼개지 않는다.
- 휴일 여부를 추정하지 않는다. 저장 메타데이터의 날짜 구간은 `date_start`, `date_end`만 기록한다.
- 같은 계정/날짜/종목코드가 여러 Sheet에 있더라도 변환하기에서는 병합하거나 충돌 판단하지 않는다. 각 Sheet를 별도 Parquet로 저장한다.
- 계정명은 파일명과 metadata에서 언더바 없는 lower camel case를 사용한다. 기존 snake_case 계정명은 저장하지 않는다.
- 병합하기에서 날짜축으로 두 구간을 이어 붙일 때는 구간이 겹치거나 한 구간의 종료일과 다음 구간의 시작일이 하루 차이인 경우만 허용한다. 그보다 큰 외부 날짜 공백은 같은 종목코드 집합이어도 병합하지 않는다.

## 저장 계약

- Parquet: `<output_directory>/<accountName>_<date_start_yyyymmdd>_<date_end_yyyymmdd>_<companiesHash>.parquet`
- Parquet 구조: `date` 컬럼 + 종목코드별 wide 컬럼
- Code-Name mapping Parquet: `<output_directory>/code_name_mapping.parquet`
- Code-Name mapping 구조: `code`, `name`
- Account mapping Parquet: 생성하지 않음. 이전 버전의 `account_mapping.parquet`가 출력 폴더에 남아 있으면 계정 Parquet 스캔 대상에서 제외한다.
- Manifest: 생성하지 않음
- Write mode: `replace`
- 계정 Parquet footer metadata: `account_id`, `account_name`, `date_start`, `date_end`, `rows`, `columns`, `non_null_cells`, `total_cells`, `missing_ratio`
- `Parquet 모아보기`, `Quantiwise - Parquet 미리보기`, `Quantiwise - 병합하기`는 계정 Parquet footer metadata를 우선이 아니라 필수로 읽는다. 필수 key가 없으면 fallback 계산 없이 에러로 처리한다.

## 검증

```bash
python3 -m pytest tests/test_assets_excel.py tests/market_desk/test_server.py
npm run build -w @finiq/app-market-desk --
```
